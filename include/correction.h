#ifndef CORRECTION_H
#define CORRECTION_H

#include <string>
#include <vector>
#include <variant>
#include <map>
#include <mutex>
#include <rapidjson/document.h>
#include "peglib.h"

namespace correction {

class Variable {
  public:
    typedef std::variant<int, double, std::string> Type;

    Variable(const rapidjson::Value& json);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    std::string type() const;
    void validate(const Type& t) const;

  private:
    enum class VarType {string, integer, real};
    std::string name_;
    std::string description_;
    VarType type_;
};


class Formula;
class Binning;
class MultiBinning;
class Category;
typedef std::variant<double, Binning, MultiBinning, Category, Formula> Content;

class Formula {
  public:
    enum class ParserType {TFormula, numexpr};
    static bool eager_compilation; // true by default

    Formula(const rapidjson::Value& json);
    std::string expression() const { return expression_; };
    double evaluate(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values) const;

  private:
    std::string expression_;
    ParserType type_;
    std::vector<int> variableIdx_;

    static std::map<ParserType, peg::parser> parsers_;
    static std::mutex parsers_mutex_; // could be one per parser, but this is good enough
    struct Ast {
      enum class NodeType {
        Literal,
        Variable,
        Parameter,
        UnaryCall,
        BinaryCall,
        UAtom,
        Expression,
      };

      typedef double (*UnaryFcn)(double);
      typedef double (*BinaryFcn)(double, double);
      typedef std::variant<
        std::monostate,
        double, // literal
        size_t, // variable/parameter index
        char, // unary / binary op
        UnaryFcn,
        BinaryFcn
      > NodeData;

      NodeType nodetype;
      NodeData data;
      std::vector<Ast> children;
    };
    mutable std::unique_ptr<Ast> ast_;
    void build_ast() const;
    const Ast translate_ast(const peg::Ast& ast) const;
    double eval_ast(const Ast& ast, const std::vector<double>& variables) const;
};

class Binning {
  public:
    Binning(const rapidjson::Value& json);
    const Content& child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const;

  private:
    std::vector<double> edges_;
    std::vector<Content> content_;
};

class MultiBinning {
  public:
    MultiBinning(const rapidjson::Value& json);
    int ndimensions() const { return edges_.size(); };
    const Content& child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const;

  private:
    std::vector<std::vector<double>> edges_;
    std::vector<size_t> dim_strides_;
    std::vector<Content> content_;
};

class Category {
  public:
    Category(const rapidjson::Value& json);
    const Content& child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const;

  private:
    std::map<int, Content> int_map_;
    std::map<std::string, Content> str_map_;
};

class Correction {
  public:
    Correction(const rapidjson::Value& json);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    int version() const { return version_; };
    // TODO: expose inputs and output
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    std::string name_;
    std::string description_;
    int version_;
    std::vector<Variable> inputs_;
    Variable output_;
    Content data_;
};

typedef std::shared_ptr<const Correction> CorrectionPtr;

class CorrectionSet {
  public:
    static std::unique_ptr<CorrectionSet> from_file(const std::string& fn);
    static std::unique_ptr<CorrectionSet> from_string(const char * data);

    CorrectionSet(const std::string& fn);  // deprecated
    CorrectionSet(const rapidjson::Value& json);
    bool validate();
    int schema_version() const { return schema_version_; };
    auto size() const { return corrections_.size(); };
    auto begin() const { return corrections_.cbegin(); };
    auto end() const { return corrections_.cend(); };
    CorrectionPtr at(const std::string& key) const { return corrections_.at(key); };
    CorrectionPtr operator[](const std::string& key) const { return at(key); };

  private:
    int schema_version_;
    std::map<std::string, CorrectionPtr> corrections_;
};

} // namespace correction

#endif // CORRECTION_H
