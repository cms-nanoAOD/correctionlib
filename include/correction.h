#ifndef CORRECTION_H
#define CORRECTION_H

#include <string>
#include <vector>
#include <variant>
#include <map>
#include <rapidjson/document.h>

class Variable {
  public:
    typedef std::variant<std::string, int, double> Type;

    Variable(const rapidjson::Value& json);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    void set(Type t);
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

    Formula(const rapidjson::Value& json);
    std::string expression() const { return expression_; };
    double evaluate(const std::vector<Variable> inputs) const;

  private:
    std::string expression_;
    ParserType type_;
    std::vector<int> parameterIdx_;
    // mutable std::unique_ptr<TFormula>;
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
  double operator() (const Formula& node);

  const std::vector<Variable> inputs;
  const int depth;
};

class Correction {
  public:
    Correction(const rapidjson::Value& json);
    std::string name() const { return name_; };
    double evaluate(const std::vector<Variable::Type> inputs);

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
    CorrectionSet(const std::string& fn);
    bool validate();
    int schema_version() const { return schema_version_; };
    auto size() const { return corrections_.size(); };
    auto begin() const { return corrections_.cbegin(); };
    auto end() const { return corrections_.cend(); };
    const Correction& operator[](const std::string& key) const {
      for (auto& corr : corrections_) {
        if ( corr.name() == key ) return corr;
      }
      throw std::runtime_error("No such correction");
    };

  private:
    int schema_version_;
    std::vector<Correction> corrections_;
};

#endif // CORRECTION_H
