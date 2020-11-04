#include "rapidjson/document.h"
#include "rapidjson/filereadstream.h"
#include <cstdio>
#include <string>
#include <vector>


class Variable {
  public:
    enum VarType {string, integer, real};

    Variable(const rapidjson::Value& json) :
      name_(json["name"].GetString())
    {
      if (json["type"] == "string") { type_ = VarType::string; }
      else if (json["type"] == "int") { type_ = VarType::integer; }
      else if (json["type"] == "real") { type_ = VarType::real; }
      // TODO: description
    };
    std::string name() { return name_; };

  private:
    std::string name_;
    VarType type_;
};

class Correction {
  public:
    Correction(const rapidjson::Value& json) :
      name_(json["name"].GetString()),
      // TODO: description, version
      output_(json["output"])
    {
      for (const auto& item : json["inputs"].GetArray()) {
        inputs_.emplace_back(item);
      }
    };
    std::string name() { return name_; };

  private:
    std::string name_;
    std::vector<Variable> inputs_;
    Variable output_;
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
