#include <rapidjson/filereadstream.h>
#include <algorithm>
#include <charconv>
#include "correction.h"

Variable::Variable(const rapidjson::Value& json) :
  name_(json["name"].GetString()),
  description_(json.HasMember("description") ? json["description"].GetString() : "")
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

peg::parser Formula::parser_(R"(
EXPRESSION  <- ATOM (BINARYOP ATOM)* {
                 precedence
                   L - +
                   L / *
                   R ^
               }
BINARYOP    <- < [-+/*^] >
CALL        <- FUNCTION '(' EXPRESSION (',' EXPRESSION)* ')'
FUNCTION    <- < 'exp' | 'sqrt' | 'log' | 'log10' | 'TMath::Log' | 'max' >
ATOM        <- LITERAL / UATOM
UATOM       <- UNARYOP? ( NAME / CALL / '(' EXPRESSION ')' )
UNARYOP     <- < '-' >
NAME        <- PARAMETER / VARIABLE
PARAMETER   <- < '[' [0-9]+ ']' >
VARIABLE    <- < [xyzt] >
LITERAL     <- < '-'? [0-9]+ ('.' [0-9]*)? >
%whitespace <- [ \t\r\n]*
)");

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

  parser_.enable_ast();
  parser_.enable_packrat_parsing();
  if ( ! parser_.parse(expression_, ast_) ) {
    throw std::runtime_error("Failed to parse expression");
  }
  ast_ = parser_.optimize_ast(ast_);
}

double Formula::evaluate(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values) const {
  std::vector<double> variables;
  for ( auto idx : variableIdx_ ) { variables.push_back(std::get<double>(values[idx])); }
  if ( ast_ ) {
    return eval_ast(*ast_, variables);
  }
  if ( ! evaluator_ ) {
    // TODO: thread-safety: should we acquire a lock when building?
    evaluator_ = std::make_unique<TFormula>("formula", expression_.c_str(), false);
    if ( evaluator_->Compile() != 0 ) {
      throw std::runtime_error("Failed to compile expression " + expression_ + " into TFormula");
    }
  }
  // do we need a lock when evaluating?
  return evaluator_->EvalPar(&variables[0]);
}

double Formula::eval_ast(const peg::Ast& ast, const std::vector<double>& variables) const {
  if (ast.is_token) {
    if (ast.name == "LITERAL") {
      return ast.token_to_number<double>();
    }
    else if (ast.name == "VARIABLE") {
      if ( ast.token == "x" ) { return variables.at(0); }
      else if ( ast.token == "y" ) { return variables.at(1); }
      else if ( ast.token == "z" ) { return variables.at(2); }
      else if ( ast.token == "t" ) { return variables.at(3); }
    }
    else if (ast.name == "PARAMETER") {
      throw std::runtime_error("parameter not impl");
    }
  }
  else if (ast.name == "UATOM" ) {
    auto ope = ast.nodes[0]->token[0];
    auto arg = eval_ast(*ast.nodes[1], variables);
    switch (ope) {
      case '-': return -arg;
    }
  }
  else if (ast.name == "CALL" ) {
    auto fun = ast.nodes[0]->token;
    if ( ast.nodes.size() == 2 ) {
      auto arg = eval_ast(*ast.nodes[1], variables);
      if ( fun == "exp" ) { return std::exp(arg); }
      else if ( fun == "sqrt" ) { return std::sqrt(arg); }
    }
    else {
      throw std::runtime_error("could not match call to number of arguments");
    }
  }
  else if (ast.name == "EXPRESSION" ) {
    auto result = eval_ast(*ast.nodes[0], variables);
    for (auto i = 1u; i < ast.nodes.size(); i += 2) {
      auto num = eval_ast(*ast.nodes[i + 1], variables);
      auto ope = ast.nodes[i]->token[0];
      switch (ope) {
        case '+': result += num; break;
        case '-': result -= num; break;
        case '*': result *= num; break;
        case '/': result /= num; break;
        case '^': result = std::pow(result, num); break;
      }
    }
    return result;
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
    if ( key->IsString() ) { str_map_[key->GetString()] = resolve_content(*val); }
    else if ( key->IsInt() ) { int_map_[key->GetInt()] = resolve_content(*val); }
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
  description_(json.HasMember("description") ? json["description"].GetString() : ""),
  version_(json["version"].GetInt()),
  output_(json["output"]),
  data_(resolve_content(json["data"]))
{
  for (const auto& item : json["inputs"].GetArray()) {
    inputs_.emplace_back(item);
  }
}

double Correction::evaluate(const std::vector<Variable::Type>& values) const {
  if ( values.size() != inputs_.size() ) {
    throw std::runtime_error("Insufficient inputs");
  }
  for (size_t i=0; i < inputs_.size(); ++i) {
    inputs_[i].validate(values[i]);
  }
  return std::visit(node_evaluate{inputs_, values, 0}, data_);
}

CorrectionSet::CorrectionSet(const std::string& fn) {
  rapidjson::Document json;

  FILE* fp = fopen(fn.c_str(), "rb");
  char readBuffer[65536];
  rapidjson::FileReadStream is(fp, readBuffer, sizeof(readBuffer));
  json.ParseStream(is);
  fclose(fp);

  schema_version_ = json["schema_version"].GetInt();
  for (const auto& item : json["corrections"].GetArray()) {
    corrections_.emplace_back(item);
  }
}

bool CorrectionSet::validate() {
  // TODO: validate with https://rapidjson.org/md_doc_schema.html
  return true;
}
