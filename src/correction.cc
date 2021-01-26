#include <rapidjson/filereadstream.h>
#include <algorithm>
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

void Variable::set(Type t) {
  if ( std::holds_alternative<std::string>(t) ) {
    if ( type_ == VarType::string ) { value_ = t; }
    else {
      throw std::runtime_error("Input has wrong type: expected string");
    }
  }
  else if ( std::holds_alternative<int>(t) ) {
    if ( type_ == VarType::integer ) { value_ = t; }
    else {
      throw std::runtime_error("Input has wrong type: expected int");
    }
  }
  else if ( std::holds_alternative<double>(t) ) {
    if ( type_ == VarType::real ) { value_ = t; }
    else {
      throw std::runtime_error("Input has wrong type: expected real-valued");
    }
  }
}

Formula::Formula(const rapidjson::Value& json) :
  expression_(json["expression"].GetString())
{
  if (json["parser"] == "TFormula") { type_ = ParserType::TFormula; }
  else if (json["parser"] == "numexpr") { type_ = ParserType::numexpr; }
  else { throw std::runtime_error("Unrecognized formula parser type"); } 

  for (const auto& item : json["parameters"].GetArray()) {
    parameterIdx_.push_back(item.GetInt());
  }
}

double Formula::evaluate(const std::vector<Variable> inputs) const {
  // TODO
  return 0.;
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

Content Binning::child(const std::vector<Variable> inputs, int depth) const {
  double value = inputs[depth].getDouble();
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

Content MultiBinning::child(const std::vector<Variable> inputs, int depth) const {
  size_t idx {0};
  for (size_t i=0; i < edges_.size(); ++i) {
    double value = inputs[depth + i].getDouble();
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

Content Category::child(const std::vector<Variable> inputs, int depth) const {
  auto& value = inputs[depth];
  if ( value.isString() ) {
    try {
      return str_map_.at(value.getString());
    } catch (std::out_of_range ex) {
      throw std::runtime_error("Index not available in Category var:" + value.name() + " val: " + value.getString());
    }
  }
  else if ( value.isInt() ) {
    try {
      return int_map_.at(value.getInt());
    } catch (std::out_of_range ex) {
      throw std::runtime_error("Index not available in Category var:" + value.name() + " val: " + std::to_string(value.getInt()));
    }
  }
  throw std::runtime_error("Invalid variable type");
}

double node_evaluate::operator() (double node) { return node; }

double node_evaluate::operator() (const Binning& node) {
  return std::visit(
      node_evaluate{inputs, depth + 1},
      node.child(inputs, depth)
      );
}

double node_evaluate::operator() (const MultiBinning& node) {
  return std::visit(
      node_evaluate{inputs, depth + 1},
      node.child(inputs, depth)
      );
}

double node_evaluate::operator() (const Category& node) {
  return std::visit(
      node_evaluate{inputs, depth + 1},
      node.child(inputs, depth)
      );
}

double node_evaluate::operator() (const Formula& node) {
  return node.evaluate(inputs);
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

double Correction::evaluate(const std::vector<Variable::Type> inputs) {
  if ( inputs.size() != inputs_.size() ) {
    throw std::runtime_error("Insufficient inputs");
  }
  // FIXME: thread safety
  for (size_t i=0; i < inputs.size(); ++i) {
    inputs_[i].set(inputs[i]);
  }
  return std::visit(node_evaluate{inputs_, 0}, data_);
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
