#ifndef CORRECTION_H
#define CORRECTION_H

#include <string>
#include <vector>
#include <variant>
#include <map>
#include <memory>
#include "correctionlib_version.h"

namespace correction {

constexpr int evaluator_version { 2 };

class JSONObject; // internal wrapper around rapidjson

class Variable {
  public:
    enum class VarType {string, integer, real};
    typedef std::variant<int, double, std::string> Type;

    Variable(const JSONObject& json);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    VarType type() const { return type_; };
    std::string typeStr() const;
    void validate(const Type& t) const;

    static Variable from_string(const char * data);

  private:
    std::string name_;
    std::string description_;
    VarType type_;
};

class Formula;
class FormulaRef;
class Transform;
class HashPRNG;
class Binning;
class MultiBinning;
class Category;
typedef std::variant<double, Formula, FormulaRef, Transform, HashPRNG, Binning, MultiBinning, Category> Content;
class Correction;

class FormulaAst {
  public:
    enum class ParserType {TFormula, numexpr};
    enum class NodeType {
      Literal,
      Variable,
      Parameter,
      Unary,
      Binary,
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
      Atan2,
      Max,
      Min
    };
    enum class UnaryOp {
      Negative,
      Log,
      Log10,
      Exp,
      Erf,
      Sqrt,
      Abs,
      Cos,
      Sin,
      Tan,
      Acos,
      Asin,
      Atan,
      Cosh,
      Sinh,
      Tanh,
      Acosh,
      Asinh,
      Atanh
    };
    using NodeData = std::variant<
      std::monostate,
      double, // literal/parameter
      size_t, // parameter/variable index
      UnaryOp,
      BinaryOp
    >;
    // TODO: try std::unique_ptr<const Ast> child1, child2 or std::array
    using Children = std::vector<FormulaAst>;

    static FormulaAst parse(
        ParserType type,
        const std::string_view expression,
        const std::vector<double>& params,
        const std::vector<size_t>& variableIdx,
        bool bind_parameters
        );

    FormulaAst(NodeType nodetype, NodeData data, Children children) :
      nodetype_(nodetype), data_(data), children_(children) {};
    const NodeType &nodetype() const { return nodetype_; }
    const NodeData &data() const { return data_; }
    const Children& children() const { return children_; }
    double evaluate(const std::vector<Variable::Type>& variables, const std::vector<double>& parameters) const;

  private:
    NodeType nodetype_;
    NodeData data_;
    Children children_;
};

class Formula {
  public:
    typedef std::shared_ptr<const Formula> Ref;

    Formula(const JSONObject& json, const Correction& context, bool generic = false);
    Formula(const JSONObject& json, const std::vector<Variable>& inputs, bool generic = false);
    std::string expression() const { return expression_; };
    const FormulaAst &ast() const { return *ast_; };
    double evaluate(const std::vector<Variable::Type>& values) const;
    double evaluate(const std::vector<Variable::Type>& values, const std::vector<double>& parameters) const;

    static Ref from_string(const char * data, std::vector<Variable>& inputs);

  private:
    std::string expression_;
    FormulaAst::ParserType type_;
    std::unique_ptr<FormulaAst> ast_;
    bool generic_;
};

class FormulaRef {
  public:
    FormulaRef(const JSONObject& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    Formula::Ref formula_;
    std::vector<double> parameters_;
};

class Transform {
  public:
    Transform(const JSONObject& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    size_t variableIdx_;
    std::unique_ptr<const Content> rule_;
    std::unique_ptr<const Content> content_;
};

class HashPRNG {
  public:
    HashPRNG(const JSONObject& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    enum class Distribution { stdflat, stdnormal, normal };
    std::vector<size_t> variablesIdx_;
    Distribution dist_;
};

// common internal for Binning and MultiBinning
enum class _FlowBehavior {value, clamp, error};

using _NonUniformBins = std::vector<double>;

struct _UniformBins {
   std::size_t n; // number of bins
   double low; // lower edge of first bin
   double high; // upper edge of last bin
};

class Binning {
  public:
    Binning(const JSONObject& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    std::variant<_UniformBins, _NonUniformBins> bins_; // bin edges
    // bin contents: contents_[i] is the value corresponding to bins_[i+1].
    // the default value is at contents_[0]
    std::vector<Content> contents_;
    size_t variableIdx_;
    _FlowBehavior flow_;
};

struct _MultiBinningAxis {
  size_t variableIdx;
  size_t stride;
  std::variant<_UniformBins, _NonUniformBins> bins;
};

class MultiBinning {
  public:
    MultiBinning(const JSONObject& json, const Correction& context);
    size_t ndimensions() const { return axes_.size(); };
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    size_t nbins(size_t dimension) const;

    std::vector<_MultiBinningAxis> axes_;
    std::vector<Content> content_;
    _FlowBehavior flow_;
};

class Category {
  public:
    Category(const JSONObject& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    typedef std::map<int, Content> IntMap;
    typedef std::map<std::string, Content> StrMap;
    std::variant<IntMap, StrMap> map_;
    std::unique_ptr<const Content> default_;
    size_t variableIdx_;
};

class Correction {
  public:
    typedef std::shared_ptr<const Correction> Ref;

    Correction(const JSONObject& json);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    int version() const { return version_; };
    const std::vector<Variable>& inputs() const { return inputs_; };
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

typedef Correction::Ref CorrectionPtr; // deprecated
class CorrectionSet;

class CompoundCorrection {
  public:
    typedef std::shared_ptr<const CompoundCorrection> Ref;

    CompoundCorrection(const JSONObject& json, const CorrectionSet& context);
    std::string name() const { return name_; };
    std::string description() const { return description_; };
    const std::vector<Variable>& inputs() const { return inputs_; };
    size_t input_index(const std::string_view name) const;
    const Variable& output() const { return output_; };
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    enum class UpdateOp {Add, Multiply, Divide, Last};

    std::string name_;
    std::string description_;
    std::vector<Variable> inputs_;
    Variable output_;
    std::vector<size_t> inputs_update_;
    UpdateOp input_op_;
    UpdateOp output_op_;
    std::vector<std::tuple<std::vector<size_t>, Correction::Ref>> stack_;
};

class CorrectionSet {
  public:
    static std::unique_ptr<CorrectionSet> from_file(const std::string& fn);
    static std::unique_ptr<CorrectionSet> from_string(const char * data);

    CorrectionSet(const JSONObject& json);
    bool validate();
    int schema_version() const { return schema_version_; };
    std::string description() const { return description_; };
    auto size() const { return corrections_.size(); };
    auto begin() const { return corrections_.cbegin(); };
    auto end() const { return corrections_.cend(); };
    Correction::Ref at(const std::string& key) const { return corrections_.at(key); };
    Correction::Ref operator[](const std::string& key) const { return at(key); };
    const auto& compound() const { return compoundcorrections_; };

  private:
    int schema_version_;
    std::map<std::string, Correction::Ref> corrections_;
    std::map<std::string, CompoundCorrection::Ref> compoundcorrections_;
    std::string description_;
};

} // namespace correction

#endif // CORRECTION_H
