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

constexpr int evaluator_version { 2 };

class Variable {
  public:
    enum class VarType {string, integer, real};
    typedef std::variant<int, double, std::string> Type;

    Variable(const rapidjson::Value& json);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    VarType type() const { return type_; };
    std::string typeStr() const;
    void validate(const Type& t) const;

  private:
    std::string name_;
    std::string description_;
    VarType type_;
};


class Formula;
class Binning;
class MultiBinning;
class Category;
typedef std::variant<double, Formula, Binning, MultiBinning, Category> Content;

class Formula {
  public:
    enum class ParserType {TFormula, numexpr};

    Formula(const rapidjson::Value& json, const std::vector<Variable>& inputs);
    std::string expression() const { return expression_; };
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    std::string expression_;
    ParserType type_;
    std::vector<size_t> variableIdx_;

    static std::map<ParserType, peg::parser> parsers_;
    static std::mutex parsers_mutex_; // could be one per parser, but this is good enough
    struct Ast {
      enum class NodeType {
        Literal,
        Variable,
        UnaryCall,
        BinaryCall,
        UAtom,
        Expression,
      };

      typedef double (*UnaryFcn)(double);
      typedef double (*BinaryFcn)(double, double);
      typedef std::variant<
        std::monostate,
        double, // literal/parameter
        size_t, // variable index
        char, // unary / binary op
        UnaryFcn,
        BinaryFcn
      > NodeData;

      NodeType nodetype;
      NodeData data;
      std::vector<Ast> children;
      // TODO: try std::unique_ptr<const Ast> child1, child2 or std::array
    };
    std::unique_ptr<const Ast> ast_;
    void build_ast(const std::vector<double>& params);
    const Ast translate_ast(const peg::Ast& ast, const std::vector<double>& params) const;
    double eval_ast(const Ast& ast, const std::vector<double>& variables) const;
};

class Binning {
  public:
    Binning(const rapidjson::Value& json, const std::vector<Variable>& inputs);
    const Content& child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const;

  private:
    std::vector<std::tuple<double, Content>> bins_;
    size_t variableIdx_;
};

class MultiBinning {
  public:
    MultiBinning(const rapidjson::Value& json, const std::vector<Variable>& inputs);
    int ndimensions() const { return axes_.size(); };
    const Content& child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const;

  private:
    // variableIdx, stride, edges
    std::vector<std::tuple<size_t, size_t, std::vector<double>>> axes_;
    std::vector<Content> content_;
};

class Category {
  public:
    Category(const rapidjson::Value& json, const std::vector<Variable>& inputs);
    const Content& child(const std::vector<Variable>& inputs, const std::vector<Variable::Type>& values, const int depth) const;

  private:
    typedef std::map<int, Content> IntMap;
    typedef std::map<std::string, Content> StrMap;
    std::variant<IntMap, StrMap> map_;
    size_t variableIdx_;
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
