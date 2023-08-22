#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
#ifndef __clang__
#pragma GCC diagnostic ignored "-Wclass-memaccess"
#endif
#include <rapidjson/document.h>
#pragma GCC diagnostic pop
#include <rapidjson/filereadstream.h>
#include <rapidjson/error/en.h>
#include <optional>
#include <algorithm>
#include <stdexcept>
#include <cmath>
#include <cstdlib> // std::abort
#include <random>
#include "correction.h"
#define XXH_INLINE_ALL 1
#include "xxhash.h"
#include "pcg_random.hpp"
#if __has_include(<zlib.h>)
#include <zlib.h>
#include "gzfilereadstream.h"
#define WITH_ZLIB 1
#endif

using namespace correction;

class correction::JSONObject {
  public:
    JSONObject(rapidjson::Value::ConstObject&& json) : json_(json) { }
    // necessary to force use of const Value::GetObject() method
    // must check if json is an object in calling code!
    JSONObject(const rapidjson::Document& json) : json_(json.GetObject()) { }

    template<typename T>
    T getRequired(const char * key) const {
      const auto it = json_.FindMember(key);
      if ( it != json_.MemberEnd() ) {
        if ( it->value.template Is<T>() ) {
          return it->value.template Get<T>();
        } else {
          throw std::runtime_error(
              "Encountered invalid type for required attribute '"
              + std::string(key) + "'");
        }
      }
      throw std::runtime_error(
          "Object missing required attribute '"
          + std::string(key) + "'");
    }

    const rapidjson::Value& getRequiredValue(const char * key) const {
      const auto it = json_.FindMember(key);
      if ( it != json_.MemberEnd() ) {
        return it->value;
      }
      throw std::runtime_error(
          "Object missing required attribute '"
          + std::string(key) + "'");
    }

    template<typename T>
    std::optional<T> getOptional(const char * key) const {
      const auto it = json_.FindMember(key);
      if ( it != json_.MemberEnd() ) {
        if ( it->value.template Is<T>() ) {
          return it->value.template Get<T>();
        } else if ( it->value.IsNull() ) {
          return std::nullopt;
        } else {
          throw std::runtime_error(
              "Encountered invalid type for optional attribute '"
              + std::string(key) + "'");
        }
      }
      return std::nullopt;
    }

    // escape hatch
    inline auto FindMember(const char * key) const { return json_.FindMember(key); }
    inline auto MemberEnd() const { return json_.MemberEnd(); }

  private:
    rapidjson::Value::ConstObject json_;
};

template<>
std::string_view JSONObject::getRequired<std::string_view>(const char * key) const {
  const auto it = json_.FindMember(key);
  if ( it != json_.MemberEnd() ) {
    if ( it->value.IsString() ) {
      return std::string_view(it->value.GetString(), it->value.GetStringLength());
    } else {
      throw std::runtime_error(
          "Encountered invalid type for required attribute '"
          + std::string(key) + "'");
    }
  }
  throw std::runtime_error(
      "Object missing required attribute '"
      + std::string(key) + "'");
}

namespace {
  Content resolve_content(const rapidjson::Value& json, const Correction& context) {
    if ( json.IsDouble() ) { return json.GetDouble(); }
    else if ( json.IsObject() && json.HasMember("nodetype") ) {
      auto obj = JSONObject(json.GetObject());
      auto type = obj.getRequired<std::string_view>("nodetype");
      if ( type == "binning" ) { return Binning(obj, context); }
      else if ( type == "multibinning" ) { return MultiBinning(obj, context); }
      else if ( type == "category" ) { return Category(obj, context); }
      else if ( type == "formula" ) { return Formula(obj, context); }
      else if ( type == "formularef" ) { return FormulaRef(obj, context); }
      else if ( type == "transform" ) { return Transform(obj, context); }
      else if ( type == "hashprng" ) { return HashPRNG(obj, context); }
      else { throw std::runtime_error("Unrecognized Content object nodetype"); }
    }
    throw std::runtime_error("Invalid Content node type");
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
    double operator() (const HashPRNG& node) {
      return node.evaluate(values);
    };

    const std::vector<Variable::Type>& values;
  };
}

Variable::Variable(const JSONObject& json) :
  name_(json.getRequired<const char *>("name")),
  description_(json.getOptional<const char*>("description").value_or(""))
{
  auto type = json.getRequired<std::string_view>("type");
  if (type == "string") { type_ = VarType::string; }
  else if (type == "int") { type_ = VarType::integer; }
  else if (type == "real") { type_ = VarType::real; }
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

Formula::Formula(const JSONObject& json, const Correction& context, bool generic) :
  expression_(json.getRequired<const char *>("expression")),
  generic_(generic)
{
  auto parser_type = json.getRequired<std::string_view>("parser");
  if (parser_type == "TFormula") { type_ = FormulaAst::ParserType::TFormula; }
  else if (parser_type == "numexpr") {
    type_ = FormulaAst::ParserType::numexpr;
    throw std::runtime_error("numexpr formula parser is not yet supported");
  }
  else { throw std::runtime_error("Unrecognized formula parser type"); }

  std::vector<size_t> variableIdx;
  for (const auto& item : json.getRequired<rapidjson::Value::ConstArray>("variables")) {
    auto idx = context.input_index(item.GetString());
    if ( context.inputs()[idx].type() != Variable::VarType::real ) {
      throw std::runtime_error("Formulas only accept real-valued inputs, got type "
          + context.inputs()[idx].typeStr() + " for variable " + context.inputs()[idx].name());
    }
    variableIdx.push_back(idx);
  }

  std::vector<double> params;
  if ( auto items = json.getOptional<rapidjson::Value::ConstArray>("parameters") ) {
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

FormulaRef::FormulaRef(const JSONObject& json, const Correction& context) {
  formula_ = context.formula_ref(json.getRequired<int>("index"));
  for (const auto& item : json.getRequired<rapidjson::Value::ConstArray>("parameters")) {
    parameters_.push_back(item.GetDouble());
  }
}

double FormulaRef::evaluate(const std::vector<Variable::Type>& values) const {
  return formula_->evaluate(values, parameters_);
}

Transform::Transform(const JSONObject& json, const Correction& context) {
  variableIdx_ = context.input_index(json.getRequired<std::string_view>("input"));
  const auto& variable = context.inputs()[variableIdx_];
  if ( variable.type() == Variable::VarType::string ) {
    throw std::runtime_error("Transform cannot rewrite string inputs");
  }
  rule_ = std::make_unique<Content>(resolve_content(json.getRequiredValue("rule"), context));
  content_ = std::make_unique<Content>(resolve_content(json.getRequiredValue("content"), context));
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

HashPRNG::HashPRNG(const JSONObject& json, const Correction& context)
{
  const auto& inputs = json.getRequired<rapidjson::Value::ConstArray>("inputs");
  variablesIdx_.reserve(inputs.Size());
  for (const auto& input : inputs) {
    if ( ! input.IsString() ) { throw std::runtime_error("invalid hashprng input type"); }
    size_t idx = context.input_index(input.GetString());
    if ( context.inputs().at(idx).type() == Variable::VarType::string ) {
      throw std::runtime_error("HashPRNG cannot use string inputs as entropy sources");
    }
    variablesIdx_.push_back(idx);
  }
  auto dist = json.getRequired<std::string_view>("distribution");
  if (dist == "stdflat") { dist_ = Distribution::stdflat; }
  else if (dist == "stdnormal") { dist_ = Distribution::stdnormal; }
  else if (dist == "normal") { dist_ = Distribution::normal; }
  else { throw std::runtime_error("invalid distribution type for hashprng"); }

}

double HashPRNG::evaluate(const std::vector<Variable::Type>& values) const {
  pcg32_oneseq gen;
  size_t nbytes = sizeof(uint64_t)*variablesIdx_.size();
  uint64_t* seedData = (uint64_t*) alloca(nbytes);
  for(size_t i=0; i<variablesIdx_.size(); ++i) {
    if ( auto v = std::get_if<int>(&values[variablesIdx_[i]]) ) {
      seedData[i] = static_cast<uint64_t>(*v);
    }
    else if ( auto v = std::get_if<double>(&values[variablesIdx_[i]]) ) {
      seedData[i] = *reinterpret_cast<const uint64_t*>(v);
    }
    else { throw std::logic_error("I should not have ever seen a string"); }
  }
  gen.seed(XXH64((const void*) seedData, nbytes, 0ul));
  switch (dist_) {
    case Distribution::stdflat:
      return std::uniform_real_distribution<>()(gen);
    case Distribution::stdnormal:
      // if not a temporary, it may reuse the spare value
      return std::normal_distribution<>()(gen);
    case Distribution::normal:
      double u, v, s;
      do {
        // cheap but wrong-ish https://www.pcg-random.org/using-pcg-c.html#generating-doubles
        u = std::ldexp(gen(), -31) - 1;
        v = std::ldexp(gen(), -31) - 1;
        s = u*u + v*v;
      } while ( s>= 1.0 || s == 0.0 );
      return u * std::sqrt(-2.0 * std::log(s) / s);
    default:
      std::abort(); // never reached if the switch is exhaustive
  };
}

Binning::Binning(const JSONObject& json, const Correction& context)
{
  const auto& content = json.getRequired<rapidjson::Value::ConstArray>("content");

  // set bins_
  const auto &edgesObj = json.getRequiredValue("edges");
  if ( edgesObj.IsArray() ) { // non-uniform binning
    std::vector<double> edges;
    rapidjson::Value::ConstArray edgesArr = edgesObj.GetArray();
    for (const auto& edge : edgesArr) {
      if ( ! edge.IsDouble() ) { throw std::runtime_error("Invalid edges array type"); }
      double val = edge.GetDouble();
      if ( edges.size() > 0 && edges.back() >= val ) { throw std::runtime_error("binning edges are not monotone increasing"); }
      edges.push_back(val);
    }
    if ( edges.size() != content.Size() + 1 ) {
      throw std::runtime_error("Inconsistency in Binning: number of content nodes does not match binning");
    }
    _NonUniformBins bins{std::move(edges)};
    bins_ = std::move(bins);
  } else if ( edgesObj.IsObject() ) { // UniformBinning
    const JSONObject uniformBins{edgesObj.GetObject()};
    const auto n = uniformBins.getRequired<uint32_t>("n");
    if ( n == 0 ) {
      throw std::runtime_error("Error when processing Binning with UniformBinning: number of bins is zero");
    }
    if ( n != content.Size() ) {
      throw std::runtime_error("Inconsistency in Binning: number of content nodes does not match binning");
    }
    const auto low = uniformBins.getRequired<double>("low");
    const auto high = uniformBins.getRequired<double>("high");
    bins_ = _UniformBins{n, low, high};
  } else {
    throw std::runtime_error ("Error when processing Binning: edges are neither an array nor a UniformBinning object");
  }

  variableIdx_ = context.input_index(json.getRequired<std::string_view>("input"));
  Content default_value{0.};
  const auto& flowbehavior = json.getRequiredValue("flow");
  if ( flowbehavior == "clamp" ) {
    flow_ = _FlowBehavior::clamp;
  }
  else if ( flowbehavior == "error" ) {
    flow_ = _FlowBehavior::error;
  }
  else {
    flow_ = _FlowBehavior::value;
    default_value = resolve_content(flowbehavior, context);
  }

  // set bin contents
  contents_.push_back(std::move(default_value));
  for (size_t i=0; i < content.Size(); ++i)
    contents_.push_back(resolve_content(content[i], context));
}

const Content& Binning::child(const std::vector<Variable::Type>& values) const {
  double value = std::get<double>(values[variableIdx_]);

  if ( auto *bins = std::get_if<_UniformBins>(&bins_) ) { // uniform binning
    std::size_t binIdx = bins->n * ((value - bins->low) / (bins->high - bins->low));
    if (value < bins->low || value >= bins->high) {
      switch (flow_) {
        case _FlowBehavior::value:
            return contents_[0u]; // the default value
        case _FlowBehavior::clamp:
          binIdx = value < bins->low ? 0 : bins->n - 1; // assuming we always have at least 1 bin
          break;
        case _FlowBehavior::error:
          const std::string belowOrAbove = value < bins->low ? "below" : "above";
          const auto msg = "Index " + belowOrAbove + " bounds in Binning for input argument " + std::to_string(variableIdx_) + " value: " + std::to_string(value);
          throw std::runtime_error(std::move(msg));
      }
    }

    return contents_[binIdx + 1u]; // skipping the default value at index 0
  }

  // otherwise we have non-uniform binning
  const auto bins = std::get<_NonUniformBins>(bins_);

  auto it = std::upper_bound(std::begin(bins), std::end(bins), value);
  if ( it == std::begin(bins) ) {
    if ( flow_ == _FlowBehavior::value ) {
      // default value already at std::begin
    }
    else if ( flow_ == _FlowBehavior::error ) {
      throw std::runtime_error("Index below bounds in Binning for input argument " + std::to_string(variableIdx_) + " value: " + std::to_string(value));
    }
    else { // clamp
      it++;
    }
  }
  else if ( it == std::end(bins) ) {
    if ( flow_ == _FlowBehavior::value ) {
      it = std::begin(bins);
    }
    else if ( flow_ == _FlowBehavior::error ) {
      throw std::runtime_error("Index above bounds in Binning for input argument " + std::to_string(variableIdx_) + " value: " + std::to_string(value));
    }
    else { // clamp
      it--;
    }
  }

  return contents_[std::distance(std::begin(bins), it)];
}

MultiBinning::MultiBinning(const JSONObject& json, const Correction& context)
{
  const auto& inputs = json.getRequired<rapidjson::Value::ConstArray>("inputs");

  const auto& edges = json.getRequired<rapidjson::Value::ConstArray>("edges");
  axes_.reserve(edges.Size());
  size_t idx {0};
  for (const auto& dimension : edges) {
    const auto& input = inputs[idx];
    if ( dimension.IsArray() ) { // non-uniform binning
      std::vector<double> dim_edges;
      dim_edges.reserve(dimension.GetArray().Size());
      for (const auto& item : dimension.GetArray()) {
        double val = item.GetDouble();
        if ( dim_edges.size() > 0 && dim_edges.back() >= val ) { throw std::runtime_error("binning edges are not monotone increasing"); }
        dim_edges.push_back(val);
      }
      if ( ! input.IsString() ) { throw std::runtime_error("invalid multibinning input type"); }
      axes_.push_back({context.input_index(input.GetString()), 0, _NonUniformBins(std::move(dim_edges))});
    } else if ( dimension.IsObject() ) { // UniformBinning
      const JSONObject uniformBins{dimension.GetObject()};
      const auto n = uniformBins.getRequired<uint32_t>("n");
      if ( n == 0 ) {
        auto msg = "Error when processing MultiBinning: number of bins for dimension " + std::to_string(idx) + " is zero";
        throw std::runtime_error(std::move(msg));
      }
      const auto low = uniformBins.getRequired<double>("low");
      const auto high = uniformBins.getRequired<double>("high");
      axes_.push_back({context.input_index(input.GetString()), 0, _UniformBins{n, low, high}});
    } else {
      auto msg = "Error when processing MultiBinning: edges for dimension " + std::to_string(idx) + " are neither an array nor a UniformBinning object";
      throw std::runtime_error (std::move(msg));
    }
    ++idx;
  }

  const auto& content = json.getRequired<rapidjson::Value::ConstArray>("content");
  size_t stride {1};
  --idx; // now corresponds to the last dimension
  for (auto it=axes_.rbegin(); it != axes_.rend(); ++it) {
    it->stride = stride;
    stride *= nbins(idx);
    --idx;
  }
  content_.reserve(content.Size() + 1); // + 1 for default value
  for (const auto& item : content) {
    content_.push_back(resolve_content(item, context));
  }
  if ( content_.size() != stride ) {
    throw std::runtime_error("Inconsistency in MultiBinning: number of content nodes does not match binning");
  }

  const auto& flowbehavior = json.getRequiredValue("flow");
  if ( flowbehavior == "clamp" ) {
    flow_ = _FlowBehavior::clamp;
  }
  else if ( flowbehavior == "error" ) {
    flow_ = _FlowBehavior::error;
  }
  else {
    flow_ = _FlowBehavior::value;
    // store default value at end of content array
    content_.push_back(resolve_content(flowbehavior, context));
  }
}

// TODO factor out logic in common with Binning::child.
// One notable difference is that MultiBinning stores the default value at the end of content_ instead of the beginning.
const Content& MultiBinning::child(const std::vector<Variable::Type>& values) const {
  size_t idx {0};
  size_t localidx {0};

  for (const auto& [variableIdx, stride, edgesVariant] : axes_) {
    double value = std::get<double>(values[variableIdx]);

    if ( auto *bins = std::get_if<_UniformBins>(&edgesVariant) ) { // uniform bins
      std::size_t binIdx = bins->n * ((value - bins->low) / (bins->high - bins->low));
      if (value < bins->low || value >= bins->high) {
        switch (flow_) {
          case _FlowBehavior::value:
              return content_.back(); // the default value
          case _FlowBehavior::clamp:
            binIdx = value < bins->low ? 0 : bins->n - 1; // assuming we always have at least 1 bin
            break;
          case _FlowBehavior::error:
            const std::string belowOrAbove = value < bins->low ? "below" : "above";
            const auto msg = "Index " + belowOrAbove + " bounds in MultiBinning for input argument " + std::to_string(variableIdx) + " value: " + std::to_string(value);
            throw std::runtime_error(std::move(msg));
        }
      }
      localidx = binIdx;
    } else { // non-uniform bins
      const auto edges = std::get<_NonUniformBins>(edgesVariant);
      auto it = std::upper_bound(std::begin(edges), std::end(edges), value);
      if ( it == std::begin(edges) ) {
        if ( flow_ == _FlowBehavior::value ) {
          return *content_.rbegin();
        }
        else if ( flow_ == _FlowBehavior::error ) {
          throw std::runtime_error("Index below bounds in MultiBinning for input argument " + std::to_string(variableIdx) + " val: " + std::to_string(value));
        }
        else { // clamp
          it++;
        }
      }
      else if ( it == std::end(edges) ) {
        if ( flow_ == _FlowBehavior::value ) {
          return content_.back();
        }
        else if ( flow_ == _FlowBehavior::error ) {
          throw std::runtime_error("Index above bounds in MultiBinning input argument" + std::to_string(variableIdx) + " val: " + std::to_string(value));
        }
        else { // clamp
          it--;
        }
      }
      localidx = std::distance(std::begin(edges), it) - 1;
    }

    idx += localidx * stride;
  }

  return content_.at(idx);
}

size_t MultiBinning::nbins(size_t dimension) const
{
  if ( const auto *bins = std::get_if<_UniformBins>(&axes_[dimension].bins) )
    return bins->n; // using uniform bins

  // otherwise we must have non-uniform bins
  const auto &bins = std::get<_NonUniformBins>(axes_[dimension].bins);
  return bins.size() - 1;
}

Category::Category(const JSONObject& json, const Correction& context)
{
  variableIdx_ = context.input_index(json.getRequired<std::string_view>("input"));
  const auto& variable = context.inputs()[variableIdx_];
  if ( variable.type() == Variable::VarType::string ) {
    map_ = StrMap();
  } // (default-constructed as IntMap)
  for (const auto& kv_pair : json.getRequired<rapidjson::Value::ConstArray>("content"))
  {
    if ( ! (kv_pair.IsObject() && kv_pair.HasMember("key") && kv_pair.HasMember("value")) ) {
      throw std::runtime_error("Expected CategoryItem object");
    }
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

  const auto def = json.FindMember("default");
  if ( def != json.MemberEnd() && ! def->value.IsNull() ) {
    default_ = std::make_unique<Content>(resolve_content(def->value, context));
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
        throw std::out_of_range("Index not available in Category for input argument " + std::to_string(variableIdx_) + " val: " + *pval);
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
        throw std::out_of_range("Index not available in Category for input argument " + std::to_string(variableIdx_) + " val: " + std::to_string(*pval));
      }
    }
  }
  throw std::runtime_error("Invalid variable type");
}

Correction::Correction(const JSONObject& json) :
  name_(json.getRequired<const char *>("name")),
  description_(json.getOptional<const char*>("description").value_or("")),
  version_(json.getRequired<int>("version")),
  output_(json.getRequired<rapidjson::Value::ConstObject>("output"))
{
  if ( output_.type() != Variable::VarType::real ) { throw std::runtime_error("Outputs can only be real-valued"); }
  for (const auto& item : json.getRequired<rapidjson::Value::ConstArray>("inputs")) {
    if ( ! item.IsObject() ) { throw std::runtime_error("invalid input item type"); }
    inputs_.emplace_back(item.GetObject());
  }
  if ( const auto& items = json.getOptional<rapidjson::Value::ConstArray>("generic_formulas") ) {
    for (const auto& item : *items) {
      if ( ! item.IsObject() ) { throw std::runtime_error("invalid generic_formulas item type"); }
      formula_refs_.push_back(std::make_shared<Formula>(item.GetObject(), *this, true));
    }
  }

  data_ = resolve_content(json.getRequiredValue("data"), *this);
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

CompoundCorrection::CompoundCorrection(const JSONObject& json, const CorrectionSet& context) :
  name_(json.getRequired<const char *>("name")),
  description_(json.getOptional<const char*>("description").value_or("")),
  output_(json.getRequired<rapidjson::Value::ConstObject>("output"))
{
  if ( output_.type() != Variable::VarType::real ) { throw std::runtime_error("Outputs can only be real-valued"); }
  for (const auto& item : json.getRequired<rapidjson::Value::ConstArray>("inputs")) {
    if ( ! item.IsObject() ) { throw std::runtime_error("invalid inputs item type"); }
    inputs_.emplace_back(item.GetObject());
  }
  for (const auto& item : json.getRequired<rapidjson::Value::ConstArray>("inputs_update")) {
    if ( ! item.IsString() ) { throw std::runtime_error("invalid inputs_update item type"); }
    size_t idx = input_index(item.GetString());
    if ( inputs_[idx].type() != Variable::VarType::real ) {
      throw std::runtime_error("CompoundCorrection updatable inputs must be real-valued");
    }
    inputs_update_.emplace_back(idx);
  }

  const auto& op = json.getRequired<std::string_view>("input_op");
  if ( op == "+" ) { input_op_ = UpdateOp::Add; }
  else if ( op == "*" ) { input_op_ = UpdateOp::Multiply; }
  else if ( op == "/" ) { input_op_ = UpdateOp::Divide; }
  else { throw std::runtime_error("Invalid CompoundCorrection input update op"); }

  const auto& out_op = json.getRequired<std::string_view>("output_op");
  if ( out_op == "+" ) { output_op_ = UpdateOp::Add; }
  else if ( out_op == "*" ) { output_op_ = UpdateOp::Multiply; }
  else if ( out_op == "/" ) { output_op_ = UpdateOp::Divide; }
  else if ( out_op == "last" ) { output_op_ = UpdateOp::Last; }
  else { throw std::runtime_error("Invalid CompoundCorrection output update op"); }

  for (const auto& item : json.getRequired<rapidjson::Value::ConstArray>("stack")) {
    if ( ! item.IsString() ) { throw std::runtime_error("Invalid type"); }
    Correction::Ref corr;
    try {
      corr = context.at(item.GetString());
    } catch (std::out_of_range& ex) {
      throw std::runtime_error("CompoundCorrection constituent "
          + std::string(item.GetString()) + " not found in the CorrectionSet");
    }
    std::vector<size_t> inmap;
    for (const auto& input : corr->inputs()) {
      inmap.push_back(input_index(input.name()));
    }
    stack_.emplace_back(std::move(inmap), corr);
  }
}

size_t CompoundCorrection::input_index(const std::string_view name) const {
  size_t idx = 0;
  for (const auto& var : inputs_) {
    if ( name == var.name() ) return idx;
    idx++;
  }
  throw std::runtime_error("Error: could not find variable " + std::string(name) + " in inputs");
}

double CompoundCorrection::evaluate(const std::vector<Variable::Type>& values) const {
  if ( values.size() > inputs_.size() ) {
    throw std::runtime_error("Too many inputs");
  }
  else if ( values.size() < inputs_.size() ) {
    throw std::runtime_error("Insufficient inputs");
  }
  for (size_t i=0; i < inputs_.size(); ++i) {
    inputs_[i].validate(values[i]);
  }
  std::vector<Variable::Type> ivalues(values);
  std::vector<Variable::Type> cvalues;
  cvalues.reserve(values.size());
  double out = 0.;
  double sf = 0.;
  bool start{true};
  for(const auto& [inmap, corr] : stack_) {
    cvalues.clear();
    for(size_t pos : inmap) cvalues.push_back(ivalues[pos]);
    sf = corr->evaluate(cvalues);
    for(size_t pos : inputs_update_) {
      switch ( input_op_ ) {
        case UpdateOp::Add: std::get<double>(ivalues[pos]) += sf; break;
        case UpdateOp::Multiply: std::get<double>(ivalues[pos]) *= sf; break;
        case UpdateOp::Divide: std::get<double>(ivalues[pos]) /= sf; break;
        case UpdateOp::Last: throw std::logic_error("Illegal update op");
      }
    }
    if ( start ) { out = sf; start = false; }
    else {
      switch ( output_op_ ) {
        case UpdateOp::Add: out += sf; break;
        case UpdateOp::Multiply: out *= sf; break;
        case UpdateOp::Divide: out /= sf; break;
        case UpdateOp::Last: out = sf;
      }
    }
  }
  return out;
}

std::unique_ptr<CorrectionSet> CorrectionSet::from_file(const std::string& fn) {
  rapidjson::Document json;
  FILE* fp = fopen(fn.c_str(), "rb");
  if ( fp == nullptr ) {
    throw std::runtime_error("Failed to open file: " + fn);
  }
  constexpr unsigned char magicref[4] = {0x1f, 0x8b};
  unsigned char magic[2];
  fread(magic, sizeof *magic, 2, fp);
  rewind(fp);
  char readBuffer[65536];
  rapidjson::ParseResult ok;
  if (memcmp(magic, magicref, sizeof(magic)) == 0) {
    fclose(fp);
#ifdef WITH_ZLIB
    gzFile_s* fpz = gzopen(fn.c_str(), "r");
    rapidjson::GzFileReadStream is(fpz, readBuffer, sizeof(readBuffer));
    ok = json.ParseStream<rapidjson::kParseNanAndInfFlag>(is);
    gzclose(fpz);
#else
    throw std::runtime_error("Gzip-compressed JSON files are only supported if ZLIB is found when the package is built");
#endif
  } else {
    rapidjson::FileReadStream is(fp, readBuffer, sizeof(readBuffer));
    ok = json.ParseStream<rapidjson::kParseNanAndInfFlag>(is);
    fclose(fp);
  }
  if (!ok) {
    throw std::runtime_error(
        std::string("JSON parse error: ") + rapidjson::GetParseError_En(ok.Code())
        + " at offset " + std::to_string(ok.Offset())
        );
  }
  if ( ! json.IsObject() ) { throw std::runtime_error("Expected CorrectionSet object"); }
  return std::make_unique<CorrectionSet>(json);
}

std::unique_ptr<CorrectionSet> CorrectionSet::from_string(const char * data) {
  rapidjson::Document json;
  rapidjson::ParseResult ok = json.Parse<rapidjson::kParseNanAndInfFlag>(data);
  if (!ok) {
    throw std::runtime_error(
        std::string("JSON parse error: ") + rapidjson::GetParseError_En(ok.Code())
        + " at offset " + std::to_string(ok.Offset())
        );
  }
  if ( ! json.IsObject() ) { throw std::runtime_error("Expected CorrectionSet object"); }
  return std::make_unique<CorrectionSet>(json);
}

CorrectionSet::CorrectionSet(const JSONObject& json) {
  schema_version_ = json.getRequired<int>("schema_version");
  if ( schema_version_ > evaluator_version ) {
    throw std::runtime_error("Evaluator is designed for schema v" + std::to_string(evaluator_version) + " and is not forward-compatible");
  }
  else if ( schema_version_ < evaluator_version ) {
    throw std::runtime_error("Evaluator is designed for schema v" + std::to_string(evaluator_version) + " and is not backward-compatible");
  }
  description_ = json.getOptional<const char*>("description").value_or("");
  for (const auto& item : json.getRequired<rapidjson::Value::ConstArray>("corrections")) {
    if ( ! item.IsObject() ) { throw std::runtime_error("Expected Correction object"); }
    auto corr = std::make_shared<Correction>(item.GetObject());
    corrections_[corr->name()] = corr;
  }
  if (auto items = json.getOptional<rapidjson::Value::ConstArray>("compound_corrections")) {
    for (const auto& item : *items) {
      if ( ! item.IsObject() ) { throw std::runtime_error("Expected CompoundCorrection object"); }
      auto corr = std::make_shared<CompoundCorrection>(item.GetObject(), *this);
      compoundcorrections_[corr->name()] = corr;
    }
  }
}

bool CorrectionSet::validate() {
  // TODO: validate with https://rapidjson.org/md_doc_schema.html
  return true;
}
