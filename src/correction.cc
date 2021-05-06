#include <rapidjson/document.h>
#include <rapidjson/filereadstream.h>
#include <rapidjson/error/en.h>
#include <optional>
#include <algorithm>
#include <stdexcept>
#include <cmath>
#include "correction.h"

using namespace correction;

namespace {
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

  Content resolve_content(const rapidjson::Value& json, const Correction& context) {
    if ( json.IsDouble() ) { return json.GetDouble(); }
    else if ( json.HasMember("nodetype") ) {
      if ( json["nodetype"] == "binning" ) { return Binning(json, context); }
      else if ( json["nodetype"] == "multibinning" ) { return MultiBinning(json, context); }
      else if ( json["nodetype"] == "category" ) { return Category(json, context); }
      else if ( json["nodetype"] == "formula" ) { return Formula(json, context); }
      else if ( json["nodetype"] == "formularef" ) { return FormulaRef(json, context); }
      else if ( json["nodetype"] == "transform" ) { return Transform(json, context); }
    }
    throw std::runtime_error("Unrecognized Content node type");
  }

  struct node_evaluate {
    double operator() (double node) { return node; };
    double operator() (const Binning& node) {
      return std::visit(*this, node.child(values));
    };
    double operator() (const MultiBinning& node) {
      return std::visit(*this, node.child(values));
    };
    double operator() (const Category& node) {
      return std::visit(*this, node.child(values));
    };
    double operator() (const Formula& node) {
      return node.evaluate(values);
    };
    double operator() (const FormulaRef& node) {
      return node.evaluate(values);
    };
    double operator() (const Transform& node) {
      return node.evaluate(values);
    };

    const std::vector<Variable::Type>& values;
  };

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

Formula::Formula(const rapidjson::Value& json, const Correction& context, bool generic) :
  expression_(json["expression"].GetString()),
  generic_(generic)
{
  if (json["parser"] == "TFormula") { type_ = FormulaAst::ParserType::TFormula; }
  else if (json["parser"] == "numexpr") {
    type_ = FormulaAst::ParserType::numexpr;
    throw std::runtime_error("numexpr formula parser is not yet supported");
  }
  else { throw std::runtime_error("Unrecognized formula parser type"); }

  std::vector<size_t> variableIdx;
  for (const auto& item : json["variables"].GetArray()) {
    auto idx = context.input_index(item.GetString());
    if ( context.inputs()[idx].type() != Variable::VarType::real ) {
      throw std::runtime_error("Formulas only accept real-valued inputs, got type "
          + context.inputs()[idx].typeStr() + " for variable " + context.inputs()[idx].name());
    }
    variableIdx.push_back(idx);
  }

  std::vector<double> params;
  if ( auto items = getOptional<rapidjson::Value::ConstArray>(json, "parameters") ) {
    for (const auto& item : *items) {
      params.push_back(item.GetDouble());
    }
  }

  ast_ = std::make_unique<FormulaAst>(FormulaAst::parse(type_, expression_, params, variableIdx, !generic));
}

double Formula::evaluate(const std::vector<Variable::Type>& values) const {
  if ( generic_ ) {
    throw std::runtime_error("Generic formulas must be evaluated with parameters");
  }
  return ast_->evaluate(values, {});
}

double Formula::evaluate(const std::vector<Variable::Type>& values, const std::vector<double>& params) const {
  return ast_->evaluate(values, params);
}

FormulaRef::FormulaRef(const rapidjson::Value& json, const Correction& context) {
  formula_ = context.formula_ref(json["index"].GetInt());
  for (const auto& item : json["parameters"].GetArray()) {
    parameters_.push_back(item.GetDouble());
  }
}

double FormulaRef::evaluate(const std::vector<Variable::Type>& values) const {
  return formula_->evaluate(values, parameters_);
}

Transform::Transform(const rapidjson::Value& json, const Correction& context) {
  variableIdx_ = context.input_index(json["input"].GetString());
  const auto& variable = context.inputs()[variableIdx_];
  if ( variable.type() == Variable::VarType::string ) {
    throw std::runtime_error("Transform cannot rewrite string inputs");
  }
  rule_ = std::make_unique<Content>(resolve_content(json["rule"], context));
  content_ = std::make_unique<Content>(resolve_content(json["content"], context));
}

double Transform::evaluate(const std::vector<Variable::Type>& values) const {
  std::vector<Variable::Type> new_values(values);
  double vnew = std::visit(node_evaluate{values}, *rule_);
  auto& v = new_values[variableIdx_];
  if ( std::holds_alternative<double>(v) ) {
    v = vnew;
  }
  else if ( std::holds_alternative<int>(v) ) {
    v = (int) std::round(vnew);
  }
  else {
    throw std::logic_error("I should not have ever seen a string");
  }
  return std::visit(node_evaluate{new_values}, *content_);
}

Binning::Binning(const rapidjson::Value& json, const Correction& context)
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
  variableIdx_ = context.input_index(json["input"].GetString());
  Content default_value{0.};
  if ( json["flow"] == "clamp" ) {
    flow_ = _FlowBehavior::clamp;
  }
  else if ( json["flow"] == "error" ) {
    flow_ = _FlowBehavior::error;
  }
  else { // Content node
    flow_ = _FlowBehavior::value;
    default_value = resolve_content(json["flow"], context);
  }
  bins_.reserve(edges.size());
  // first bin is never accessed for content in range (corresponds to std::upper_bound underflow)
  // use it to store default value
  bins_.push_back({*edges.begin(), std::move(default_value)});
  for (size_t i=0; i < content.Size(); ++i) {
    bins_.push_back({edges[i + 1], resolve_content(content[i], context)});
  }
}

const Content& Binning::child(const std::vector<Variable::Type>& values) const {
  double value = std::get<double>(values[variableIdx_]);
  auto it = std::upper_bound(std::begin(bins_), std::end(bins_), value, [](const double& a, const auto& b) { return a < std::get<0>(b); });
  if ( it == std::begin(bins_) ) {
    if ( flow_ == _FlowBehavior::value ) {
      // default value already at std::begin
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
      it = std::begin(bins_);
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

MultiBinning::MultiBinning(const rapidjson::Value& json, const Correction& context)
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
    axes_.push_back({context.input_index(input.GetString()), 0, std::move(dim_edges)});
    idx++;
  }

  size_t stride {1};
  for (auto it=axes_.rbegin(); it != axes_.rend(); ++it) {
    std::get<1>(*it) = stride;
    stride *= std::get<2>(*it).size() - 1;
  }
  content_.reserve(json["content"].GetArray().Size() + 1); // + 1 for default value
  for (const auto& item : json["content"].GetArray()) {
    content_.push_back(resolve_content(item, context));
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
    // store default value at end of content array
    content_.push_back(resolve_content(json["flow"], context));
  }
}

const Content& MultiBinning::child(const std::vector<Variable::Type>& values) const {
  size_t idx {0};
  for (const auto& [variableIdx, stride, edges] : axes_) {
    double value = std::get<double>(values[variableIdx]);
    auto it = std::upper_bound(std::begin(edges), std::end(edges), value);
    if ( it == std::begin(edges) ) {
      if ( flow_ == _FlowBehavior::value ) {
        return *content_.rbegin();
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
        return *content_.rbegin();
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

Category::Category(const rapidjson::Value& json, const Correction& context)
{
  if (json["nodetype"] != "category") { throw std::runtime_error("Attempted to construct Category node but data is not that type"); }
  variableIdx_ = context.input_index(json["input"].GetString());
  const auto& variable = context.inputs()[variableIdx_];
  if ( variable.type() == Variable::VarType::string ) {
    map_ = StrMap();
  } // (default-constructed as IntMap)
  for (const auto& kv_pair : json["content"].GetArray())
  {
    if ( kv_pair["key"].IsString() ) {
      if ( variable.type() != Variable::VarType::string ) {
        throw std::runtime_error("Category got a key not of type string, but its input is string type");
      }
      std::get<StrMap>(map_).try_emplace(kv_pair["key"].GetString(), resolve_content(kv_pair["value"], context));
    }
    else if ( kv_pair["key"].IsInt() ) {
      if ( variable.type() != Variable::VarType::integer ) {
        throw std::runtime_error("Category got a key not of type int, but its input is int type");
      }
      std::get<IntMap>(map_).try_emplace(kv_pair["key"].GetInt(), resolve_content(kv_pair["value"], context));
    }
    else {
      throw std::runtime_error("Invalid key type in Category");
    }
  }
  const auto it = json.FindMember("default");
  if ( it != json.MemberEnd() && !it->value.IsNull() ) {
    default_ = std::make_unique<Content>(resolve_content(it->value, context));
  }
}

const Content& Category::child(const std::vector<Variable::Type>& values) const {
  if ( auto pval = std::get_if<std::string>(&values[variableIdx_]) ) {
    try {
      return std::get<StrMap>(map_).at(*pval);
    } catch (std::out_of_range& ex) {
      if ( default_ ) {
        return *default_;
      }
      else {
        throw std::out_of_range("Index not available in Category for index " + std::to_string(variableIdx_) + " val: " + *pval);
      }
    }
  }
  else if ( auto pval = std::get_if<int>(&values[variableIdx_]) ) {
    try {
      return std::get<IntMap>(map_).at(*pval);
    } catch (std::out_of_range& ex) {
      if ( default_ ) {
        return *default_;
      }
      else {
        throw std::out_of_range("Index not available in Category for index " + std::to_string(variableIdx_) + " val: " + std::to_string(*pval));
      }
    }
  }
  throw std::runtime_error("Invalid variable type");
}

Correction::Correction(const rapidjson::Value& json) :
  name_(json["name"].GetString()),
  description_(getOptional<const char*>(json, "description").value_or("")),
  version_(json["version"].GetInt()),
  output_(json["output"])
{
  for (const auto& item : json["inputs"].GetArray()) {
    inputs_.emplace_back(item);
  }
  if ( const auto& items = getOptional<rapidjson::Value::ConstArray>(json, "generic_formulas") ) {
    for (const auto& item : *items) {
      formula_refs_.push_back(std::make_shared<Formula>(item, *this, true));
    }
  }

  data_ = resolve_content(json["data"], *this);
  initialized_ = true;
}

size_t Correction::input_index(const std::string_view name) const {
  size_t idx = 0;
  for (const auto& var : inputs_) {
    if ( name == var.name() ) return idx;
    idx++;
  }
  throw std::runtime_error("Error: could not find variable " + std::string(name) + " in inputs");
}

double Correction::evaluate(const std::vector<Variable::Type>& values) const {
  if ( ! initialized_ ) {
    throw std::logic_error("Not initialized");
  }
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
  if ( const auto& items = getOptional<rapidjson::Value::ConstArray>(json, "corrections") ) {
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
