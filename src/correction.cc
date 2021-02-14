#include <rapidjson/filereadstream.h>
#include <rapidjson/error/en.h>
#include <algorithm>
#include <cmath>
#include "correction.h"

using namespace correction;

Variable::Variable(const rapidjson::Value& json) :
  name_(json["name"].GetString()),
  description_(json.HasMember("description") && json["description"].IsString() ? json["description"].GetString() : "")
{
  if (json["type"] == "string") { type_ = VarType::string; }
  else if (json["type"] == "int") { type_ = VarType::integer; }
  else if (json["type"] == "real") { type_ = VarType::real; }
  else { throw std::runtime_error("Unrecognized variable type"); }
}

std::string Variable::type() const {
  if ( type_ == VarType::string ) { return "string"; }
  else if ( type_ == VarType::integer ) { return "int"; }
  else if ( type_ == VarType::real ) { return "real"; }
  return "";
}

void Variable::validate(const Type& t) const {
  if ( std::holds_alternative<std::string>(t) ) {
    if ( type_ != VarType::string ) {
      throw std::runtime_error("Input " + name() + " has wrong type: got string expected " + type());
    }
  }
  else if ( std::holds_alternative<int>(t) ) {
    if ( type_ != VarType::integer ) {
      throw std::runtime_error("Input " + name() + " has wrong type: got int expected " + type());
    }
  }
  else if ( std::holds_alternative<double>(t) ) {
    if ( type_ != VarType::real ) {
      throw std::runtime_error("Input " + name() + " has wrong type: got real-valued expected " + type());
    }
  }
}

bool Formula::eager_compilation { true };
std::map<Formula::ParserType, peg::parser> Formula::parsers_;
std::mutex Formula::parsers_mutex_;

constexpr auto TFormula_grammar_v1 = R"(
EXPRESSION  <- ATOM (BINARYOP ATOM)* {
                 precedence
                   L - +
                   L / *
                   R ^
               }
UNARYOP     <- < '-' >
BINARYOP    <- < [-+/*^] >
UNARYF      <- <
  'log' |
  'log10' |
  'exp' |
  'erf' |
  'sqrt' |
  'abs' |
  'cos' |
  'sin' |
  'tan' |
  'acos' |
  'asin' |
  'atan' |
  'cosh' |
  'sinh' |
  'tanh' |
  'acosh' |
  'asinh' |
  'atanh'
  >
BINARYF     <- <
  'atan2' |
  'pow' |
  'max' |
  'min'
  >
PARAMETER   <- < '[' [0-9]+ ']' >
VARIABLE    <- < [xyzt] >
LITERAL     <- < '-'? [0-9]+ ('.' [0-9]*)? >
CALLU       <- UNARYF '(' EXPRESSION ')'
CALLB       <- BINARYF '(' EXPRESSION ',' EXPRESSION ')'
ATOM        <- LITERAL / UATOM
UATOM       <- UNARYOP? ( NAME / CALLU / CALLB / '(' EXPRESSION ')' )
NAME        <- PARAMETER / VARIABLE
%whitespace <- [ \t]*
)";

Formula::Formula(const rapidjson::Value& json) :
  expression_(json["expression"].GetString())
{
  if (json["parser"] == "TFormula") { type_ = ParserType::TFormula; }
  else if (json["parser"] == "numexpr") {
    type_ = ParserType::numexpr;
    throw std::runtime_error("numexpr formula parser is not yet supported");
  }
  else { throw std::runtime_error("Unrecognized formula parser type"); }

  for (const auto& item : json["parameters"].GetArray()) {
    variableIdx_.push_back(item.GetInt());
  }

  if ( eager_compilation ) build_ast();
}

void Formula::build_ast() const {
  std::shared_ptr<peg::Ast> peg_ast;
  {
    const std::lock_guard<std::mutex> lock(parsers_mutex_);
    auto& parser = parsers_[type_];
    if ( ! parser ) {
      if ( type_ == ParserType::TFormula ) parser.load_grammar(TFormula_grammar_v1);
      parser.enable_ast();
      parser.enable_packrat_parsing();
    }
    int pos;
    std::string msg;
    parser.log = [&](size_t ln, size_t col, const std::string &themsg) {
      pos = col;
      msg = themsg;
    };
    if ( ! parser.parse(expression_, peg_ast) ) {
      throw std::runtime_error(
        "Failed to parse Formula expression at position " + std::to_string(pos) + ":\n"
        + expression_ + "\n"
        + std::string(pos, ' ') + "^\n"
        + msg
      );
    }
    peg_ast = parser.optimize_ast(peg_ast);
  }
  ast_ = std::make_unique<Ast>(translate_ast(*peg_ast));
}

const Formula::Ast Formula::translate_ast(const peg::Ast& ast) const {
  if (ast.is_token) {
    if (ast.name == "LITERAL") {
      return {Ast::NodeType::Literal, ast.token_to_number<double>(), {}};
    }
    else if (ast.name == "VARIABLE") {
      if ( ast.token == "x" ) {
        if ( variableIdx_.size() < (size_t) 1 ) {
          throw std::runtime_error("Insufficient variables for formula");
        }
        return {Ast::NodeType::Variable, (size_t) 0, {}};
      }
      else if ( ast.token == "y" ) {
        if ( variableIdx_.size() < (size_t) 2 ) {
          throw std::runtime_error("Insufficient variables for formula");
        }
        return {Ast::NodeType::Variable, (size_t) 1, {}};
      }
      else if ( ast.token == "z" ) {
        if ( variableIdx_.size() < (size_t) 3 ) {
          throw std::runtime_error("Insufficient variables for formula");
        }
        return {Ast::NodeType::Variable, (size_t) 2, {}};
      }
      else if ( ast.token == "t" ) {
        if ( variableIdx_.size() < (size_t) 4 ) {
          throw std::runtime_error("Insufficient variables for formula");
        }
        return {Ast::NodeType::Variable, (size_t) 3, {}};
      }
    }
    else if (ast.name == "PARAMETER") {
      throw std::runtime_error("parameter not implemented");
    }
  }
  else if (ast.name == "UATOM" ) {
    if ( ast.nodes.size() != 2 ) { throw std::runtime_error("UATOM without 2 nodes?"); }
    return {
      Ast::NodeType::UAtom,
      ast.nodes[0]->token[0],
      {translate_ast(*ast.nodes[1])}
    };
  }
  else if (ast.name == "CALLU" ) {
    if ( ast.nodes.size() != 2 ) { throw std::runtime_error("CALLU without 2 nodes?"); }
    Ast::UnaryFcn fun;
    auto name = ast.nodes[0]->token;
    if      ( name == "log" )   { fun = [](double x) { return std::log(x); }; }
    else if ( name == "log10" ) { fun = [](double x) { return std::log10(x); }; }
    else if ( name == "exp" )   { fun = [](double x) { return std::exp(x); }; }
    else if ( name == "erf" )   { fun = [](double x) { return std::erf(x); }; }
    else if ( name == "sqrt" )  { fun = [](double x) { return std::sqrt(x); }; }
    else if ( name == "abs" )   { fun = [](double x) { return std::abs(x); }; }
    else if ( name == "cos" )   { fun = [](double x) { return std::cos(x); }; }
    else if ( name == "sin" )   { fun = [](double x) { return std::sin(x); }; }
    else if ( name == "tan" )   { fun = [](double x) { return std::tan(x); }; }
    else if ( name == "acos" )  { fun = [](double x) { return std::acos(x); }; }
    else if ( name == "asin" )  { fun = [](double x) { return std::asin(x); }; }
    else if ( name == "atan" )  { fun = [](double x) { return std::atan(x); }; }
    else if ( name == "cosh" )  { fun = [](double x) { return std::cosh(x); }; }
    else if ( name == "sinh" )  { fun = [](double x) { return std::sinh(x); }; }
    else if ( name == "tanh" )  { fun = [](double x) { return std::tanh(x); }; }
    else if ( name == "acosh" ) { fun = [](double x) { return std::acosh(x); }; }
    else if ( name == "asinh" ) { fun = [](double x) { return std::asinh(x); }; }
    else if ( name == "atanh" ) { fun = [](double x) { return std::atanh(x); }; }
    else {
      throw std::runtime_error("unrecognized unary function: " + std::string(name));
    }
    return {
      Ast::NodeType::UnaryCall,
      fun,
      {translate_ast(*ast.nodes[1])}
    };
  }
  else if (ast.name == "CALLB" ) {
    if ( ast.nodes.size() != 3 ) { throw std::runtime_error("CALLB without 3 nodes?"); }
    Ast::BinaryFcn fun;
    auto name = ast.nodes[0]->token;
    if      ( name == "atan2" ) { fun = [](double x, double y) { return std::atan2(x, y); }; }
    else if ( name == "pow" )   { fun = [](double x, double y) { return std::pow(x, y); }; }
    else if ( name == "max" )   { fun = [](double x, double y) { return std::max(x, y); }; }
    else if ( name == "min" )   { fun = [](double x, double y) { return std::min(x, y); }; }
    else {
      throw std::runtime_error("unrecognized binary function: " + std::string(name));
    }
    return {
      Ast::NodeType::BinaryCall,
      fun,
      {translate_ast(*ast.nodes[1]), translate_ast(*ast.nodes[2])}
    };
  }
  else if (ast.name == "EXPRESSION" ) {
    if ( ast.nodes.size() != 3 ) { throw std::runtime_error("EXPRESSION without 3 nodes?"); }
    return {
      Ast::NodeType::Expression,
      ast.nodes[1]->token[0],
      {translate_ast(*ast.nodes[0]), translate_ast(*ast.nodes[2])}
    };
  }
  throw std::runtime_error("Unrecognized AST node");
}

double Formula::evaluate(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values) const {
  std::vector<double> variables;
  variables.reserve(variableIdx_.size());
  for ( auto idx : variableIdx_ ) { variables.push_back(std::get<double>(values[idx])); }
  if ( ! ast_ ) build_ast();
  return eval_ast(*ast_, variables);
}

double Formula::eval_ast(const Formula::Ast& ast, const std::vector<double>& variables) const {
  switch (ast.nodetype) {
    case Ast::NodeType::Literal:
      return std::get<double>(ast.data);
    case Ast::NodeType::Variable:
      return variables[std::get<size_t>(ast.data)];
    case Ast::NodeType::Parameter:
      throw std::runtime_error("parameter not implemented");
    case Ast::NodeType::UAtom:
      switch (std::get<char>(ast.data)) {
        case '-': return -eval_ast(ast.children[0], variables);
      }
    case Ast::NodeType::UnaryCall:
      return std::get<Ast::UnaryFcn>(ast.data)(
          eval_ast(ast.children[0], variables)
          );
    case Ast::NodeType::BinaryCall:
      return std::get<Ast::BinaryFcn>(ast.data)(
          eval_ast(ast.children[0], variables), eval_ast(ast.children[1], variables)
          );
    case Ast::NodeType::Expression:
      auto left = eval_ast(ast.children[0], variables);
      auto right = eval_ast(ast.children[1], variables);
      switch (std::get<char>(ast.data)) {
        case '+': return left + right;
        case '-': return left - right;
        case '*': return left * right;
        case '/': return left / right;
        case '^': return std::pow(left, right);
      }
  }
  throw std::runtime_error("Unrecognized AST node");
}

Content resolve_content(const rapidjson::Value& json) {
  if ( json.IsDouble() ) { return json.GetDouble(); }
  else if ( json.HasMember("parser") ) { return Formula(json); }
  else if ( json.HasMember("nodetype") ) {
    if ( json["nodetype"] == "binning" ) { return Binning(json); }
    else if ( json["nodetype"] == "multibinning" ) { return MultiBinning(json); }
    else if ( json["nodetype"] == "category" ) { return Category(json); }
  }
  throw std::runtime_error("Unrecognized Content node type");
}

Binning::Binning(const rapidjson::Value& json)
{
  if (json["nodetype"] != "binning") { throw std::runtime_error("Attempted to construct Binning node but data is not that type"); }
  for (const auto& item : json["edges"].GetArray()) {
    edges_.push_back(item.GetDouble());
  }
  for (const auto& item : json["content"].GetArray()) {
    content_.push_back(resolve_content(item));
  }
  if ( edges_.size() != content_.size() + 1 ) {
    throw std::runtime_error("Inconsistency in Binning: number of content nodes does not match binning");
  }
}

const Content& Binning::child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const {
  double value = std::get<double>(values[depth]);
  auto it = std::lower_bound(std::begin(edges_), std::end(edges_), value) - 1;
  size_t idx = std::distance(std::begin(edges_), it);
  if ( idx < 0 ) {
    throw std::runtime_error("Index below bounds in Binning var: " + inputs[depth].name() + " val: " + std::to_string(value));
  }
  else if ( idx >= edges_.size() - 1 ) {
    throw std::runtime_error("Index above bounds in Binning var:" + inputs[depth].name() + " val: " + std::to_string(value));
  }
  return content_.at(idx);
}

MultiBinning::MultiBinning(const rapidjson::Value& json)
{
  if (json["nodetype"] != "multibinning") { throw std::runtime_error("Attempted to construct MultiBinning node but data is not that type"); }
  std::vector<size_t> dim_sizes;
  for (const auto& dimension : json["edges"].GetArray()) {
    std::vector<double> dim_edges;
    for (const auto& item : dimension.GetArray()) {
      dim_edges.push_back(item.GetDouble());
    }
    edges_.push_back(dim_edges);
    dim_sizes.push_back(dim_edges.size() - 1);
  }
  size_t n = dim_sizes.size();
  dim_strides_.resize(n);
  dim_strides_[n - 1] = 1;
  for (size_t i=2; i <= n; ++i) {
    dim_strides_[n - i] = dim_strides_[n - i + 1] * dim_sizes[n - i + 1];
  }
  size_t total = dim_strides_[0] * dim_sizes[0];
  for (const auto& item : json["content"].GetArray()) {
    content_.push_back(resolve_content(item));
  }
  if ( content_.size() != total ) {
    throw std::runtime_error("Inconsistency in MultiBinning: number of content nodes does not match binning");
  }
}

const Content& MultiBinning::child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const {
  size_t idx {0};
  for (size_t i=0; i < edges_.size(); ++i) {
    double value = std::get<double>(values[depth + i]);
    auto it = std::lower_bound(std::begin(edges_[i]), std::end(edges_[i]), value) - 1;
    size_t localidx = std::distance(std::begin(edges_[i]), it);
    if ( localidx < 0 ) {
      throw std::runtime_error("Index below bounds in MultiBinning var:" + inputs[depth + i].name() + " val: " + std::to_string(value));
    }
    else if ( localidx >= edges_[i].size() - 1) {
      throw std::runtime_error("Index above bounds in MultiBinning var:" + inputs[depth + i].name() + " val: " + std::to_string(value));
    }
    idx += localidx * dim_strides_[i];
  }
  return content_.at(idx);
}

Category::Category(const rapidjson::Value& json)
{
  if (json["nodetype"] != "category") { throw std::runtime_error("Attempted to construct Category node but data is not that type"); }
  const auto keys = json["keys"].GetArray();
  const auto vals = json["content"].GetArray();
  auto key=std::begin(keys);
  auto val=std::begin(vals);
  for (; key != std::end(keys) && val != std::end(vals); ++key, ++val)
  {
    if ( key == std::end(keys) || val == std::end(vals) ) {
      throw std::runtime_error("Inconsistency in Category: number of keys does not match number of values");
    }
    if ( key->IsString() ) { str_map_.try_emplace(key->GetString(), resolve_content(*val)); }
    else if ( key->IsInt() ) { int_map_.try_emplace(key->GetInt(), resolve_content(*val)); }
    else {
      throw std::runtime_error("Invalid key type in Category");
    }
  }
}

const Content& Category::child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const {
  if ( auto pval = std::get_if<std::string>(&values[depth]) ) {
    try {
      return str_map_.at(*pval);
    } catch (std::out_of_range ex) {
      throw std::runtime_error("Index not available in Category var:" + inputs[depth].name() + " val: " + *pval);
    }
  }
  else if ( auto pval = std::get_if<int>(&values[depth]) ) {
    try {
      return int_map_.at(*pval);
    } catch (std::out_of_range ex) {
      throw std::runtime_error("Index not available in Category var:" + inputs[depth].name() + " val: " + std::to_string(*pval));
    }
  }
  throw std::runtime_error("Invalid variable type");
}

struct node_evaluate {
  double operator() (double node);
  double operator() (const Binning& node);
  double operator() (const MultiBinning& node);
  double operator() (const Category& node);
  double operator() (const Formula& node);

  const std::vector<Variable>& inputs;
  const std::vector<Variable::Type>& values;
  const int depth;
};

double node_evaluate::operator() (double node) { return node; }

double node_evaluate::operator() (const Binning& node) {
  return std::visit(
      node_evaluate{inputs, values, depth + 1},
      node.child(inputs, values, depth)
      );
}

double node_evaluate::operator() (const MultiBinning& node) {
  return std::visit(
      node_evaluate{inputs, values, depth + 1},
      node.child(inputs, values, depth)
      );
}

double node_evaluate::operator() (const Category& node) {
  return std::visit(
      node_evaluate{inputs, values, depth + 1},
      node.child(inputs, values, depth)
      );
}

double node_evaluate::operator() (const Formula& node) {
  return node.evaluate(inputs, values);
}

Correction::Correction(const rapidjson::Value& json) :
  name_(json["name"].GetString()),
  description_(json.HasMember("description") && json["description"].IsString() ? json["description"].GetString() : ""),
  version_(json["version"].GetInt()),
  output_(json["output"]),
  data_(resolve_content(json["data"]))
{
  for (const auto& item : json["inputs"].GetArray()) {
    inputs_.emplace_back(item);
  }
}

double Correction::evaluate(const std::vector<Variable::Type>& values) const {
  if ( values.size() > inputs_.size() ) {
    throw std::runtime_error("Too many inputs");
  }
  else if ( values.size() < inputs_.size() ) {
    throw std::runtime_error("Insufficient inputs");
  }
  for (size_t i=0; i < inputs_.size(); ++i) {
    inputs_[i].validate(values[i]);
  }
  return std::visit(node_evaluate{inputs_, values, 0}, data_);
}

std::unique_ptr<CorrectionSet> CorrectionSet::from_file(const std::string& fn) {
  rapidjson::Document json;
  FILE* fp = fopen(fn.c_str(), "rb");
  char readBuffer[65536];
  rapidjson::FileReadStream is(fp, readBuffer, sizeof(readBuffer));
  rapidjson::ParseResult ok = json.ParseStream(is);
  if (!ok) {
    throw std::runtime_error(
        std::string("JSON parse error: ") + rapidjson::GetParseError_En(ok.Code())
        + " at offset " + std::to_string(ok.Offset())
        );
  }
  fclose(fp);
  return std::make_unique<CorrectionSet>(json);
}

std::unique_ptr<CorrectionSet> CorrectionSet::from_string(const char * data) {
  rapidjson::Document json;
  rapidjson::ParseResult ok = json.Parse(data);
  if (!ok) {
    throw std::runtime_error(
        std::string("JSON parse error: ") + rapidjson::GetParseError_En(ok.Code())
        + " at offset " + std::to_string(ok.Offset())
        );
  }
  return std::make_unique<CorrectionSet>(json);
}


// deprecated
CorrectionSet::CorrectionSet(const std::string& fn) {
  rapidjson::Document json;
  FILE* fp = fopen(fn.c_str(), "rb");
  char readBuffer[65536];
  rapidjson::FileReadStream is(fp, readBuffer, sizeof(readBuffer));
  json.ParseStream(is);
  fclose(fp);
  schema_version_ = json["schema_version"].GetInt();
  for (const auto& item : json["corrections"].GetArray()) {
    auto corr = std::make_shared<Correction>(item);
    corrections_[corr->name()] = corr;
  }
}

CorrectionSet::CorrectionSet(const rapidjson::Value& json) {
  if ( json.HasMember("schema_version") && json["schema_version"].IsInt() ) {
    schema_version_ = json["schema_version"].GetInt();
  }
  else { throw std::runtime_error("Missing schema_version in CorrectionSet document"); }
  if ( json.HasMember("corrections") && json["corrections"].IsArray() ) {
    for (const auto& item : json["corrections"].GetArray()) {
      auto corr = std::make_shared<Correction>(item);
      corrections_[corr->name()] = corr;
    }
  }
  else { throw std::runtime_error("Missing corrections array in CorrectionSet document"); }
}

bool CorrectionSet::validate() {
  // TODO: validate with https://rapidjson.org/md_doc_schema.html
  return true;
}
