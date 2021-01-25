#include "rapidjson/document.h"
#include "rapidjson/filereadstream.h"
#include <cstdio>
#include <string>
#include <vector>
#include <variant>
#include <map>
#include <algorithm>


class Variable {
  public:
    typedef std::variant<std::string, int, double> Type;

    Variable(const rapidjson::Value& json) :
      name_(json["name"].GetString()),
      description_(json.HasMember("description") ? json["description"].GetString() : "")
    {
      if (json["type"] == "string") { type_ = VarType::string; }
      else if (json["type"] == "int") { type_ = VarType::integer; }
      else if (json["type"] == "real") { type_ = VarType::real; }
      else { throw std::runtime_error("Unrecognized variable type"); } 
    };
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    void set(Type t) {
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
    };
    inline bool isString() const { return type_ == VarType::string; }
    inline bool isInt() const { return type_ == VarType::integer; }
    inline bool isDouble() const { return type_ == VarType::real; }
    std::string getString() const { return std::get<std::string>(value_); }
    int getInt() const { return std::get<int>(value_); }
    double getDouble() const { return std::get<double>(value_); }

  private:
    enum class VarType {string, integer, real};
    std::string name_;
    std::string description_;
    VarType type_;
    Type value_;
};


class Formula {
  public:
    enum class ParserType {TFormula, numexpr};

    Formula(const rapidjson::Value& json) :
      expression_(json["expression"].GetString())
    {
      if (json["parser"] == "TFormula") { type_ = ParserType::TFormula; }
      else if (json["parser"] == "numexpr") { type_ = ParserType::numexpr; }
      else { throw std::runtime_error("Unrecognized formula parser type"); } 

      for (const auto& item : json["parameters"].GetArray()) {
        parameterIdx_.push_back(item.GetInt());
      }
    };
    std::string expression() { return expression_; };
    double evaluate(const std::vector<Variable> inputs) {
      // TODO
      return 0.;
    };

  private:
    std::string expression_;
    ParserType type_;
    std::vector<int> parameterIdx_;
};

class Binning;
class MultiBinning;
class Category;
typedef std::variant<double, Binning, MultiBinning, Category, Formula> Content;

class Binning {
  public:
    Binning(const rapidjson::Value& json);
    Content child(const std::vector<Variable> inputs, const int depth) const;

  private:
    std::vector<double> edges_;
    std::vector<Content> content_;
};

class MultiBinning {
  public:
    MultiBinning(const rapidjson::Value& json);
    int ndimensions() const { return edges_.size(); };
    Content child(const std::vector<Variable> inputs, const int depth) const;

  private:
    std::vector<std::vector<double>> edges_;
    std::vector<size_t> dim_strides_;
    std::vector<Content> content_;
};

class Category {
  public:
    Category(const rapidjson::Value& json);
    Content child(const std::vector<Variable> inputs, const int depth) const;

  private:
    std::map<int, Content> int_map_;
    std::map<std::string, Content> str_map_;
};

struct node_evaluate {
  double operator() (double node);
  double operator() (const Binning& node);
  double operator() (const MultiBinning& node);
  double operator() (const Category& node);
  double operator() (Formula node);

  const std::vector<Variable> inputs;
  const int depth;
};

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

double node_evaluate::operator() (Formula node) {
  return node.evaluate(inputs);
}

class Correction {
  public:
    Correction(const rapidjson::Value& json) :
      name_(json["name"].GetString()),
      description_(json.HasMember("description") ? json["description"].GetString() : ""),
      version_(json["version"].GetInt()),
      output_(json["output"]),
      data_(resolve_content(json["data"]))
    {
      for (const auto& item : json["inputs"].GetArray()) {
        inputs_.emplace_back(item);
      }
    };
    std::string name() { return name_; };
    double evaluate(const std::vector<Variable::Type> inputs) {
      if ( inputs.size() != inputs_.size() ) {
        throw std::runtime_error("Insufficient inputs");
      }
      // FIXME: thread safety
      for (size_t i=0; i < inputs.size(); ++i) {
        inputs_[i].set(inputs[i]);
      }
      return std::visit(node_evaluate{inputs_, 0}, data_);
    };

  private:
    std::string name_;
    std::string description_;
    int version_;
    std::vector<Variable> inputs_;
    Variable output_;
    Content data_;
};

class CorrectionSet {
  public:
    CorrectionSet(std::string fn) {
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
    };

    bool validate() {
      // TODO: validate with https://rapidjson.org/md_doc_schema.html
      return true;
    };

    auto begin() { return corrections_.begin(); };
    auto end() { return corrections_.end(); };
    Correction& operator[](const std::string& key) {
      for (auto& corr : corrections_) {
        if ( corr.name() == key ) return corr;
      }
      throw std::runtime_error("No such correction");
    };

  private:
    int schema_version_;
    std::vector<Correction> corrections_;
};


int main(int argc, char** argv) {
  if ( argc == 2 ) {
    auto cset = CorrectionSet(argv[1]);
    for (auto& corr : cset) {
      printf("Correction: %s\n", corr.name().c_str());
    }
    double out = cset["scalefactors_Tight_Electron"].evaluate({1.3, 25.});
    printf("scalefactors_Tight_Electron(1.3, 25) = %f\n", out);
    out = cset["DeepCSV_2016LegacySF"].evaluate({"central", 0, 1.2, 35., 0.01});
    printf("DeepCSV_2016LegacySF('central', 0, 1.2, 35., 0.5) = %f\n", out);
  } else {
    printf("Usage: %s filename.json\n", argv[0]);
  }
}
