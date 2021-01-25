#include "rapidjson/document.h"
#include "rapidjson/filereadstream.h"
#include <cstdio>
#include <string>
#include <vector>
#include <variant>
#include <map>


class Variable {
  public:
    enum class VarType {string, integer, real};

    Variable(const rapidjson::Value& json) :
      name_(json["name"].GetString()),
      description_(json.HasMember("description") ? json["description"].GetString() : "")
    {
      if (json["type"] == "string") { type_ = VarType::string; }
      else if (json["type"] == "int") { type_ = VarType::integer; }
      else if (json["type"] == "real") { type_ = VarType::real; }
      else { throw std::runtime_error("Unrecognized variable type"); } 
    };
    std::string name() { return name_; };
    std::string description() { return description_; };

  private:
    std::string name_;
    std::string description_;
    VarType type_;
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

  private:
    std::vector<double> edges_;
    std::vector<Content> content_;
};

class MultiBinning {
  public:
    MultiBinning(const rapidjson::Value& json);

  private:
    std::vector<std::vector<double>> edges_;
    std::vector<int> dimensions_;
    std::vector<Content> content_;
};

class Category {
  public:
    Category(const rapidjson::Value& json);

  private:
    std::map<int, Content> int_map_;
    std::map<std::string, Content> str_map_;
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

MultiBinning::MultiBinning(const rapidjson::Value& json)
{
  if (json["nodetype"] != "multibinning") { throw std::runtime_error("Attempted to construct MultiBinning node but data is not that type"); } 
  for (const auto& dimension : json["edges"].GetArray()) {
    std::vector<double> dim_edges;
    for (const auto& item : dimension.GetArray()) {
      dim_edges.push_back(item.GetDouble());
    }
    edges_.push_back(dim_edges);
    dimensions_.push_back(dim_edges.size() - 1);
  }
  for (const auto& item : json["content"].GetArray()) {
    content_.push_back(resolve_content(item));
  }
  int total {1};
  for (const auto dim : dimensions_ ) total *= dim;
  if ( content_.size() != total ) {
    throw std::runtime_error("Inconsistency in MultiBinning: number of content nodes does not match binning");
  }
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
  } else {
    printf("Usage: %s filename.json\n", argv[0]);
  }
}
