#ifndef CORRECTION_H
#define CORRECTION_H

#include <string>
#include <vector>
#include <variant>
#include <map>
#include <memory>
#include "correctionlib_version.h"

namespace rapidjson {
  // actual definition for class Value;
  template<typename CharType> struct UTF8;
  class CrtAllocator;
  template <typename BaseAllocator> class MemoryPoolAllocator;
  template <typename Encoding, typename Allocator> class GenericValue;
  typedef GenericValue<UTF8<char>, MemoryPoolAllocator<CrtAllocator>> Value;
};


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
class FormulaRef;
class Transform;
class Binning;
class MultiBinning;
class Category;
typedef std::variant<double, Formula, FormulaRef, Transform, Binning, MultiBinning, Category> Content;
class Correction;

class FormulaAst {
  public:
    enum class ParserType {TFormula, numexpr};
    enum class NodeType {
      Literal,
      Variable,
      Parameter,
      UnaryCall,
      BinaryCall,
      UAtom,
      Expression,
      Undefined,
    };
    enum class BinaryOp {
      Equal,
      NotEqual,
      Greater,
      Less,
      GreaterEq,
      LessEq,
      Minus,
      Plus,
      Div,
      Times,
      Pow,
    };
    enum class UnaryOp { Negative };
    typedef double (*UnaryFcn)(double);
    typedef double (*BinaryFcn)(double, double);
    typedef std::variant<
      std::monostate,
      double, // literal/parameter
      size_t, // parameter/variable index
      UnaryOp,
      BinaryOp,
      UnaryFcn,
      BinaryFcn
    > NodeData;
    // TODO: try std::unique_ptr<const Ast> child1, child2 or std::array
    typedef std::vector<FormulaAst> Children;

    static FormulaAst parse(
        ParserType type,
        const std::string_view expression,
        const std::vector<double>& params,
        const std::vector<size_t>& variableIdx,
        bool bind_parameters
        );

    FormulaAst() : nodetype_(NodeType::Undefined) {};
    FormulaAst(NodeType nodetype, NodeData data, Children children) :
      nodetype_(nodetype), data_(data), children_(children) {};
    double evaluate(const std::vector<Variable::Type>& variables, const std::vector<double>& parameters) const;

  private:
    NodeType nodetype_;
    NodeData data_;
    Children children_;
};

class Formula {
  public:
    typedef std::shared_ptr<const Formula> Ref;

    Formula(const rapidjson::Value& json, const Correction& context, bool generic = false);
    std::string expression() const { return expression_; };
    double evaluate(const std::vector<Variable::Type>& values) const;
    double evaluate(const std::vector<Variable::Type>& values, const std::vector<double>& parameters) const;

  private:
    std::string expression_;
    FormulaAst::ParserType type_;
    std::unique_ptr<FormulaAst> ast_;
    bool generic_;
};

class FormulaRef {
  public:
    FormulaRef(const rapidjson::Value& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    Formula::Ref formula_;
    std::vector<double> parameters_;
};

class Transform {
  public:
    Transform(const rapidjson::Value& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    size_t variableIdx_;
    std::unique_ptr<const Content> rule_;
    std::unique_ptr<const Content> content_;
};

// common internal for Binning and MultiBinning
enum class _FlowBehavior {value, clamp, error};

class Binning {
  public:
    Binning(const rapidjson::Value& json, const Correction& context);
    const Content& child(const std::vector<Variable::Type>& values) const;

  private:
    std::vector<std::tuple<double, Content>> bins_;
    size_t variableIdx_;
    _FlowBehavior flow_;
};

class MultiBinning {
  public:
    MultiBinning(const rapidjson::Value& json, const Correction& context);
    size_t ndimensions() const { return axes_.size(); };
    const Content& child(const std::vector<Variable::Type>& values) const;

  private:
    // variableIdx, stride, edges
    std::vector<std::tuple<size_t, size_t, std::vector<double>>> axes_;
    std::vector<Content> content_;
    _FlowBehavior flow_;
};

class Category {
  public:
    Category(const rapidjson::Value& json, const Correction& context);
    const Content& child(const std::vector<Variable::Type>& values) const;

  private:
    typedef std::map<int, Content> IntMap;
    typedef std::map<std::string, Content> StrMap;
    std::variant<IntMap, StrMap> map_;
    std::unique_ptr<const Content> default_;
    size_t variableIdx_;
};

class Correction {
  public:
    Correction(const rapidjson::Value& json);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    int version() const { return version_; };
    const std::vector<Variable>& inputs() const { return inputs_; };
    size_t input_index(const std::string_view name) const;
    Formula::Ref formula_ref(size_t idx) const { return formula_refs_.at(idx); };
    const Variable& output() const { return output_; };
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    std::string name_;
    std::string description_;
    int version_;
    std::vector<Variable> inputs_;
    Variable output_;
    std::vector<Formula::Ref> formula_refs_;
    bool initialized_; // is data_ filled?
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
