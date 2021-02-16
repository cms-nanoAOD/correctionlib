#include <rapidjson/filereadstream.h>
#include <rapidjson/error/en.h>
#include <optional>
#include <algorithm>
#include <cmath>
#include "correction.h"

using namespace correction;

// A helper for getting optional object attributes
template<typename T>
std::optional<T> getOptional(const rapidjson::Value& json, const char * key) {
  const auto it = json.FindMember(key);
  if ( it != json.MemberEnd() ) {
    if ( it->value.template Is<T>() ) {
      return it->value.template Get<T>();
    }
  }
  return std::nullopt;
}

Variable::Variable(const rapidjson::Value& json) :
  name_(json["name"].GetString()),
  description_(getOptional<const char*>(json, "description").value_or(""))
{
  if (json["type"] == "string") { type_ = VarType::string; }
  else if (json["type"] == "int") { type_ = VarType::integer; }
  else if (json["type"] == "real") { type_ = VarType::real; }
  else { throw std::runtime_error("Unrecognized variable type"); }
}

std::string Variable::typeStr() const {
  if ( type_ == VarType::string ) { return "string"; }
  else if ( type_ == VarType::integer ) { return "int"; }
  else if ( type_ == VarType::real ) { return "real"; }
  return "";
}

void Variable::validate(const Type& t) const {
  if ( std::holds_alternative<std::string>(t) ) {
    if ( type_ != VarType::string ) {
      throw std::runtime_error("Input " + name() + " has wrong type: got string expected " + typeStr());
    }
  }
  else if ( std::holds_alternative<int>(t) ) {
    if ( type_ != VarType::integer ) {
      throw std::runtime_error("Input " + name() + " has wrong type: got int expected " + typeStr());
    }
  }
  else if ( std::holds_alternative<double>(t) ) {
    if ( type_ != VarType::real ) {
      throw std::runtime_error("Input " + name() + " has wrong type: got real-valued expected " + typeStr());
    }
  }
}

size_t find_variable_index(const rapidjson::Value& item, const std::vector<Variable>& inputs) {
  size_t idx = 0;
  for (const auto& var : inputs) {
    if ( item.GetString() == var.name() ) break;
    idx++;
  }
  if ( idx == inputs.size() ) {
    throw std::runtime_error("Error: could not find variable " + std::string(item.GetString()) + " in inputs");
  }
  return idx;
}

std::map<Formula::ParserType, peg::parser> Formula::parsers_;
std::mutex Formula::parsers_mutex_;

constexpr auto TFormula_grammar = R"(
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
PARAMETER   <- '[' < [0-9]+ > ']'
VARIABLE    <- < [xyzt] >
LITERAL     <- < '-'? [0-9]+ ('.' [0-9]*)? ('e' '-'? [0-9]+)? >
CALLU       <- UNARYF '(' EXPRESSION ')'
CALLB       <- BINARYF '(' EXPRESSION ',' EXPRESSION ')'
ATOM        <- LITERAL / UATOM
UATOM       <- UNARYOP? ( NAME / CALLU / CALLB / '(' EXPRESSION ')' )
NAME        <- PARAMETER / VARIABLE
%whitespace <- [ \t]*
)";

Formula::Formula(const rapidjson::Value& json, const std::vector<Variable>& inputs) :
  expression_(json["expression"].GetString())
{
  if (json["parser"] == "TFormula") { type_ = ParserType::TFormula; }
  else if (json["parser"] == "numexpr") {
    type_ = ParserType::numexpr;
    throw std::runtime_error("numexpr formula parser is not yet supported");
  }
  else { throw std::runtime_error("Unrecognized formula parser type"); }

  for (const auto& item : json["variables"].GetArray()) {
    variableIdx_.push_back(find_variable_index(item, inputs));
  }

  std::vector<double> params;
  if ( auto items = getOptional<rapidjson::Value::ConstArray>(json, "parameters") ) {
    for (const auto& item : *items) {
      params.push_back(item.GetDouble());
    }
  }

  build_ast(params);
}

void Formula::build_ast(const std::vector<double>& params) {
  std::shared_ptr<peg::Ast> peg_ast;
  {
    const std::lock_guard<std::mutex> lock(parsers_mutex_);
    auto& parser = parsers_[type_];
    if ( ! parser ) {
      if ( type_ == ParserType::TFormula ) parser.load_grammar(TFormula_grammar);
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
    ast_ = std::make_unique<Ast>(translate_ast(*peg_ast, params));
  }
}

const Formula::Ast Formula::translate_ast(const peg::Ast& ast, const std::vector<double>& params) const {
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
      auto pidx = ast.token_to_number<size_t>();
      if ( pidx >= params.size() ) {
        throw std::runtime_error("Insufficient parameters for formula");
      }
      return {Ast::NodeType::Literal, params[pidx], {}};
    }
  }
  else if (ast.name == "UATOM" ) {
    if ( ast.nodes.size() != 2 ) { throw std::runtime_error("UATOM without 2 nodes?"); }
    return {
      Ast::NodeType::UAtom,
      ast.nodes[0]->token[0],
      {translate_ast(*ast.nodes[1], params)}
    };
  }
  else if (ast.name == "CALLU" ) {
    if ( ast.nodes.size() != 2 ) { throw std::runtime_error("CALLU without 2 nodes?"); }
    Ast::UnaryFcn fun;
    auto name = ast.nodes[0]->token;
    // TODO: lookup in static map
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
      {translate_ast(*ast.nodes[1], params)}
    };
  }
  else if (ast.name == "CALLB" ) {
    if ( ast.nodes.size() != 3 ) { throw std::runtime_error("CALLB without 3 nodes?"); }
    Ast::BinaryFcn fun;
    auto name = ast.nodes[0]->token;
    // TODO: lookup in static map
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
      {translate_ast(*ast.nodes[1], params), translate_ast(*ast.nodes[2], params)}
    };
  }
  else if (ast.name == "EXPRESSION" ) {
    if ( ast.nodes.size() != 3 ) { throw std::runtime_error("EXPRESSION without 3 nodes?"); }
    return {
      Ast::NodeType::Expression,
      ast.nodes[1]->token[0],
      {translate_ast(*ast.nodes[0], params), translate_ast(*ast.nodes[2], params)}
    };
  }
  throw std::runtime_error("Unrecognized AST node");
}

double Formula::evaluate(const std::vector<Variable::Type>& values) const {
  std::vector<double> variables;
  variables.reserve(variableIdx_.size());
  for ( auto idx : variableIdx_ ) { variables.push_back(std::get<double>(values[idx])); }
  return eval_ast(*ast_, variables);
}

double Formula::eval_ast(const Formula::Ast& ast, const std::vector<double>& variables) const {
  switch (ast.nodetype) {
    case Ast::NodeType::Literal:
      return std::get<double>(ast.data);
    case Ast::NodeType::Variable:
      return variables[std::get<size_t>(ast.data)];
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

Content resolve_content(const rapidjson::Value& json, const std::vector<Variable>& inputs) {
  if ( json.IsDouble() ) { return json.GetDouble(); }
  else if ( json.HasMember("nodetype") ) {
    if ( json["nodetype"] == "binning" ) { return Binning(json, inputs); }
    else if ( json["nodetype"] == "multibinning" ) { return MultiBinning(json, inputs); }
    else if ( json["nodetype"] == "category" ) { return Category(json, inputs); }
    else if ( json["nodetype"] == "formula" ) { return Formula(json, inputs); }
  }
  throw std::runtime_error("Unrecognized Content node type");
}

Binning::Binning(const rapidjson::Value& json, const std::vector<Variable>& inputs)
{
  if (json["nodetype"] != "binning") { throw std::runtime_error("Attempted to construct Binning node but data is not that type"); }
  std::vector<double> edges;
  for (const auto& item : json["edges"].GetArray()) {
    edges.push_back(item.GetDouble());
  }
  const auto& content = json["content"].GetArray();
  if ( edges.size() != content.Size() + 1 ) {
    throw std::runtime_error("Inconsistency in Binning: number of content nodes does not match binning");
  }
  bins_.reserve(edges.size());
  // first bin is a dummy content node (represents upper_bound returning underflow)
  bins_.push_back({*edges.begin(), 0.});
  for (size_t i=0; i < content.Size(); ++i) {
    bins_.push_back({edges[i + 1], resolve_content(content[i], inputs)});
  }
  variableIdx_ = find_variable_index(json["input"], inputs);
  if ( json["flow"] == "clamp" ) {
    flow_ = _FlowBehavior::clamp;
  }
  else if ( json["flow"] == "error" ) {
    flow_ = _FlowBehavior::error;
  }
  else { // Content node
    flow_ = _FlowBehavior::value;
    default_value_ = std::make_unique<const Content>(resolve_content(json["flow"], inputs));
  }
}

const Content& Binning::child(const std::vector<Variable::Type>& values) const {
  double value = std::get<double>(values[variableIdx_]);
  auto it = std::upper_bound(std::begin(bins_), std::end(bins_), value, [](const double& a, const auto& b) { return a < std::get<0>(b); });
  if ( it == std::begin(bins_) ) {
    if ( flow_ == _FlowBehavior::value ) {
      return *default_value_;
    }
    else if ( flow_ == _FlowBehavior::error ) {
      throw std::runtime_error("Index below bounds in Binning for input " + std::to_string(variableIdx_) + " value: " + std::to_string(value));
    }
    else { // clamp
      it++;
    }
  }
  else if ( it == std::end(bins_) ) {
    if ( flow_ == _FlowBehavior::value ) {
      return *default_value_;
    }
    else if ( flow_ == _FlowBehavior::error ) {
      throw std::runtime_error("Index above bounds in Binning for input " + std::to_string(variableIdx_) + " value: " + std::to_string(value));
    }
    else { // clamp
      it--;
    }
  }
  return std::get<1>(*it);
}

MultiBinning::MultiBinning(const rapidjson::Value& json, const std::vector<Variable>& inputs)
{
  if (json["nodetype"] != "multibinning") { throw std::runtime_error("Attempted to construct MultiBinning node but data is not that type"); }
  axes_.reserve(json["edges"].GetArray().Size());
  size_t idx {0};
  for (const auto& dimension : json["edges"].GetArray()) {
    std::vector<double> dim_edges;
    dim_edges.reserve(dimension.GetArray().Size());
    for (const auto& item : dimension.GetArray()) {
      dim_edges.push_back(item.GetDouble());
    }
    const auto& input = json["inputs"].GetArray()[idx];
    axes_.push_back({find_variable_index(input, inputs), 0, std::move(dim_edges)});
    idx++;
  }

  size_t stride {1};
  for (auto it=axes_.rbegin(); it != axes_.rend(); ++it) {
    std::get<1>(*it) = stride;
    stride *= std::get<2>(*it).size() - 1;
  }
  for (const auto& item : json["content"].GetArray()) {
    content_.push_back(resolve_content(item, inputs));
  }
  if ( content_.size() != stride ) {
    throw std::runtime_error("Inconsistency in MultiBinning: number of content nodes does not match binning");
  }
  if ( json["flow"] == "clamp" ) {
    flow_ = _FlowBehavior::clamp;
  }
  else if ( json["flow"] == "error" ) {
    flow_ = _FlowBehavior::error;
  }
  else { // Content node
    flow_ = _FlowBehavior::value;
    default_value_ = std::make_unique<const Content>(resolve_content(json["flow"], inputs));
  }
}

const Content& MultiBinning::child(const std::vector<Variable::Type>& values) const {
  size_t idx {0};
  for (const auto& [variableIdx, stride, edges] : axes_) {
    double value = std::get<double>(values[variableIdx]);
    auto it = std::upper_bound(std::begin(edges), std::end(edges), value);
    if ( it == std::begin(edges) ) {
      if ( flow_ == _FlowBehavior::value ) {
        return *default_value_;
      }
      else if ( flow_ == _FlowBehavior::error ) {
        throw std::runtime_error("Index below bounds in MultiBinning for input " + std::to_string(variableIdx) + " val: " + std::to_string(value));
      }
      else { // clamp
        it++;
      }
    }
    else if ( it == std::end(edges) ) {
      if ( flow_ == _FlowBehavior::value ) {
        return *default_value_;
      }
      else if ( flow_ == _FlowBehavior::error ) {
        throw std::runtime_error("Index above bounds in MultiBinning input " + std::to_string(variableIdx) + " val: " + std::to_string(value));
      }
      else { // clamp
        it--;
      }
    }
    size_t localidx = std::distance(std::begin(edges), it) - 1;
    idx += localidx * stride;
  }
  return content_.at(idx);
}

Category::Category(const rapidjson::Value& json, const std::vector<Variable>& inputs)
{
  if (json["nodetype"] != "category") { throw std::runtime_error("Attempted to construct Category node but data is not that type"); }
  variableIdx_ = find_variable_index(json["input"], inputs);
  const auto& variable = inputs[variableIdx_];
  if ( variable.type() == Variable::VarType::string ) {
    map_ = StrMap();
  } // (default-constructed as IntMap)
  for (const auto& kv_pair : json["content"].GetArray())
  {
    if ( kv_pair["key"].IsString() ) {
      if ( variable.type() != Variable::VarType::string ) {
        throw std::runtime_error("Category got a key not of type string, but its input is string type");
      }
      std::get<StrMap>(map_).try_emplace(kv_pair["key"].GetString(), resolve_content(kv_pair["value"], inputs));
    }
    else if ( kv_pair["key"].IsInt() ) {
      if ( variable.type() != Variable::VarType::integer ) {
        throw std::runtime_error("Category got a key not of type int, but its input is int type");
      }
      std::get<IntMap>(map_).try_emplace(kv_pair["key"].GetInt(), resolve_content(kv_pair["value"], inputs));
    }
    else {
      throw std::runtime_error("Invalid key type in Category");
    }
  }
  if ( auto default_key = getOptional<const char*>(json, "default") ) {
    if ( variable.type() != Variable::VarType::string ) {
      throw std::runtime_error("Category got a default key not of type string, but its input is string type");
    }
    default_ = &std::get<StrMap>(map_).at(*default_key);
  }
  else if ( auto default_key = getOptional<int>(json, "default") ) {
    if ( variable.type() != Variable::VarType::integer ) {
      throw std::runtime_error("Category got a default key not of type int, but its input is int type");
    }
    default_ = &std::get<IntMap>(map_).at(*default_key);
  }
}

const Content& Category::child(const std::vector<Variable::Type>& values) const {
  if ( auto pval = std::get_if<std::string>(&values[variableIdx_]) ) {
    try {
      return std::get<StrMap>(map_).at(*pval);
    } catch (std::out_of_range ex) {
      if ( default_ == nullptr ) {
        throw std::runtime_error("Index not available in Category for index " + std::to_string(variableIdx_) + " val: " + *pval);
      }
      else {
        return *default_;
      }
    }
  }
  else if ( auto pval = std::get_if<int>(&values[variableIdx_]) ) {
    try {
      return std::get<IntMap>(map_).at(*pval);
    } catch (std::out_of_range ex) {
      if ( default_ == nullptr ) {
        throw std::runtime_error("Index not available in Category for index " + std::to_string(variableIdx_) + " val: " + std::to_string(*pval));
      }
      else {
        return *default_;
      }
    }
  }
  throw std::runtime_error("Invalid variable type");
}

struct node_evaluate {
  double operator() (double node) { return node; };
  double operator() (const Binning& node) {
    return std::visit(
        node_evaluate{values},
        node.child(values)
        );
  };
  double operator() (const MultiBinning& node) {
    return std::visit(
        node_evaluate{values},
        node.child(values)
        );
  };
  double operator() (const Category& node) {
    return std::visit(
        node_evaluate{values},
        node.child(values)
        );
  };
  double operator() (const Formula& node) {
    return node.evaluate(values);
  };

  const std::vector<Variable::Type>& values;
};

Correction::Correction(const rapidjson::Value& json) :
  name_(json["name"].GetString()),
  description_(getOptional<const char*>(json, "description").value_or("")),
  version_(json["version"].GetInt()),
  output_(json["output"])
{
  for (const auto& item : json["inputs"].GetArray()) {
    inputs_.emplace_back(item);
  }
  data_ = resolve_content(json["data"], inputs_);
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
  return std::visit(node_evaluate{values}, data_);
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

CorrectionSet::CorrectionSet(const rapidjson::Value& json) {
  if ( auto schema_version_ = getOptional<int>(json, "schema_version") ) {
    if ( schema_version_ > evaluator_version ) {
      throw std::runtime_error("Evaluator is designed for schema v" + std::to_string(evaluator_version) + " and is not forward-compatible");
    }
    else if ( schema_version_ < evaluator_version ) {
      throw std::runtime_error("Evaluator is designed for schema v" + std::to_string(evaluator_version) + " and is not backward-compatible");
    }
  }
  else {
    throw std::runtime_error("Missing schema_version in CorrectionSet document");
  }
  if ( auto items = getOptional<rapidjson::Value::ConstArray>(json, "corrections") ) {
    for (const auto& item : *items) {
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
