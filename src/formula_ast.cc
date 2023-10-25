#include <mutex>
#include <cmath>
#include <cstdlib> // std::abort
#include "peglib.h"
#include "correction.h"

using namespace correction;

namespace {
  class PEGParser {
    public:
      // We are not sure if peglib is threadsafe, so the policy is to lock this
      // parser mutex until we are done with the peg::Ast object
      std::mutex m;
      typedef std::shared_ptr<peg::Ast> AstPtr;

      PEGParser(const char * grammar) {
        parser_.load_grammar(grammar);
        parser_.enable_ast();
        parser_.enable_packrat_parsing();
      };
      AstPtr parse(const std::string_view expression) {
        AstPtr peg_ast;
        int pos;
        std::string msg;
        parser_.log = [&](size_t ln, size_t col, const std::string &themsg) {
          pos = col;
          msg = themsg;
        };
        if ( ! parser_.parse(expression, peg_ast) ) {
          throw std::runtime_error(
            "Failed to parse Formula expression at position " + std::to_string(pos) + ":\n"
            + std::string(expression) + "\n"
            + std::string(pos, ' ') + "^\n"
            + msg
          );
        }
        peg_ast = parser_.optimize_ast(peg_ast);
        return peg_ast;
      };

    private:
      peg::parser parser_;
  };

  PEGParser tformula_parser(R"(
  EXPRESSION  <- ATOM (BINARYOP ATOM)* {
                  precedence
                    L == !=
                    L > < >= <=
                    L - +
                    L / *
                    R ^
                }
  UNARYOP     <- < '-' >
  BINARYOP    <- < '==' | '!=' | '>' | '<' | '>=' | '<=' | '-' | '+' | '/' | '*' | '^' >
  UNARYF      <- < 'log' | 'log10' | 'exp' | 'erf' | 'sqrt' | 'abs' | 'cos' | 'sin' | 'tan' | 'acos' | 'asin' | 'atan' | 'cosh' | 'sinh' | 'tanh' | 'acosh' | 'asinh' | 'atanh' >
  BINARYF     <- < 'atan2' | 'pow' | 'max' | 'min' >
  PARAMETER   <- '[' < [0-9]+ > ']'
  VARIABLE    <- < [xyzt] >
  LITERAL     <- < '-'? [0-9]+ ('.' [0-9]*)? ('e' '-'? [0-9]+)? >
  CALLU       <- UNARYF '(' EXPRESSION ')'
  CALLB       <- BINARYF '(' EXPRESSION ',' EXPRESSION ')'
  ATOM        <- LITERAL / UATOM
  UATOM       <- UNARYOP? ( CALLU / CALLB / NAME / '(' EXPRESSION ')' )
  NAME        <- PARAMETER / VARIABLE
  %whitespace <- [ \t]*
  )");

  struct TranslationContext {
      const std::vector<double>& params;
      const std::vector<size_t>& variableIdx;
      bool bind_parameters;
  };

  FormulaAst translate_tformula_ast(
      const PEGParser::AstPtr ast,
      const TranslationContext& context
      ) {
    if (ast->is_token) {
      if (ast->name == "LITERAL") {
        return {FormulaAst::NodeType::Literal, ast->token_to_number<double>(), {}};
      }
      else if (ast->name == "VARIABLE") {
        size_t idx;
        if ( ast->token == "x" ) idx = 0;
        else if ( ast->token == "y" ) idx = 1;
        else if ( ast->token == "z" ) idx = 2;
        else if ( ast->token == "t" ) idx = 3;
        else {
          throw std::runtime_error("Unrecognized variable name in formula");
        }
        if ( context.variableIdx.size() <= idx ) {
          throw std::runtime_error("Insufficient variables for formula");
        }
        return {FormulaAst::NodeType::Variable, context.variableIdx[idx], {}};
      }
      else if (ast->name == "PARAMETER") {
        auto pidx = ast->token_to_number<size_t>();
        if ( context.bind_parameters ) {
          if ( pidx >= context.params.size() ) {
            throw std::runtime_error("Insufficient parameters for formula");
          }
          return {FormulaAst::NodeType::Literal, context.params[pidx], {}};
        }
        else {
          return {FormulaAst::NodeType::Parameter, pidx, {}};
        }
      }
    }
    else if (ast->name == "UATOM" ) {
      if ( ast->nodes.size() != 2 ) { throw std::runtime_error("UATOM without 2 nodes?"); }
      auto opname = ast->nodes[0]->token;
      FormulaAst::UnaryOp op;
      if      ( opname == "-" ) { op = FormulaAst::UnaryOp::Negative; }
      else { throw std::runtime_error("Unrecognized unary operation: " + std::string(opname)); }
      return {
        FormulaAst::NodeType::Unary,
        op,
        {translate_tformula_ast(ast->nodes[1], context)}
      };
    }
    else if (ast->name == "CALLU" ) {
      if ( ast->nodes.size() != 2 ) { throw std::runtime_error("CALLU without 2 nodes?"); }
      FormulaAst::UnaryOp op;
      auto name = ast->nodes[0]->token;
      // TODO: lookup in static map
      if      ( name == "log" )   { op = FormulaAst::UnaryOp::Log; }
      else if ( name == "log10" ) { op = FormulaAst::UnaryOp::Log10; }
      else if ( name == "exp" )   { op = FormulaAst::UnaryOp::Exp; }
      else if ( name == "erf" )   { op = FormulaAst::UnaryOp::Erf; }
      else if ( name == "sqrt" )  { op = FormulaAst::UnaryOp::Sqrt; }
      else if ( name == "abs" )   { op = FormulaAst::UnaryOp::Abs; }
      else if ( name == "cos" )   { op = FormulaAst::UnaryOp::Cos; }
      else if ( name == "sin" )   { op = FormulaAst::UnaryOp::Sin; }
      else if ( name == "tan" )   { op = FormulaAst::UnaryOp::Tan; }
      else if ( name == "acos" )  { op = FormulaAst::UnaryOp::Acos; }
      else if ( name == "asin" )  { op = FormulaAst::UnaryOp::Asin; }
      else if ( name == "atan" )  { op = FormulaAst::UnaryOp::Atan; }
      else if ( name == "cosh" )  { op = FormulaAst::UnaryOp::Cosh; }
      else if ( name == "sinh" )  { op = FormulaAst::UnaryOp::Sinh; }
      else if ( name == "tanh" )  { op = FormulaAst::UnaryOp::Tanh; }
      else if ( name == "acosh" ) { op = FormulaAst::UnaryOp::Acosh; }
      else if ( name == "asinh" ) { op = FormulaAst::UnaryOp::Asinh; }
      else if ( name == "atanh" ) { op = FormulaAst::UnaryOp::Atanh; }
      else {
        throw std::runtime_error("unrecognized unary function: " + std::string(name));
      }
      return {
        FormulaAst::NodeType::Unary,
        op,
        {translate_tformula_ast(ast->nodes[1], context)}
      };
    }
    else if (ast->name == "CALLB" ) {
      if ( ast->nodes.size() != 3 ) { throw std::runtime_error("CALLB without 3 nodes?"); }
      FormulaAst::BinaryOp op;
      auto name = ast->nodes[0]->token;
      // TODO: lookup in static map
      if      ( name == "atan2" ) { op = FormulaAst::BinaryOp::Atan2; }
      else if ( name == "pow" )   { op = FormulaAst::BinaryOp::Pow; }
      else if ( name == "max" )   { op = FormulaAst::BinaryOp::Max; }
      else if ( name == "min" )   { op = FormulaAst::BinaryOp::Min; }
      else {
        throw std::runtime_error("unrecognized binary function: " + std::string(name));
      }
      return {
        FormulaAst::NodeType::Binary,
        op,
        {translate_tformula_ast(ast->nodes[1], context), translate_tformula_ast(ast->nodes[2], context)}
      };
    }
    else if (ast->name == "EXPRESSION" ) {
      if ( ast->nodes.size() != 3 ) { throw std::runtime_error("EXPRESSION without 3 nodes?"); }
      auto opname = ast->nodes[1]->token;
      FormulaAst::BinaryOp op;
      if      ( opname == "==" ) { op = FormulaAst::BinaryOp::Equal; }
      else if ( opname == "!=" ) { op = FormulaAst::BinaryOp::NotEqual; }
      else if ( opname == ">"  ) { op = FormulaAst::BinaryOp::Greater; }
      else if ( opname == "<"  ) { op = FormulaAst::BinaryOp::Less; }
      else if ( opname == ">=" ) { op = FormulaAst::BinaryOp::GreaterEq; }
      else if ( opname == "<=" ) { op = FormulaAst::BinaryOp::LessEq; }
      else if ( opname == "-"  ) { op = FormulaAst::BinaryOp::Minus; }
      else if ( opname == "+"  ) { op = FormulaAst::BinaryOp::Plus; }
      else if ( opname == "/"  ) { op = FormulaAst::BinaryOp::Div; }
      else if ( opname == "*"  ) { op = FormulaAst::BinaryOp::Times; }
      else if ( opname == "^"  ) { op = FormulaAst::BinaryOp::Pow; }
      else { throw std::runtime_error("Unrecognized binary operation: " + std::string(opname)); }
      return {
        FormulaAst::NodeType::Binary,
        op,
        {translate_tformula_ast(ast->nodes[0], context), translate_tformula_ast(ast->nodes[2], context)}
      };
    }
    throw std::runtime_error("Unrecognized AST node");
  }

}

FormulaAst FormulaAst::parse(
    FormulaAst::ParserType type,
    const std::string_view expression,
    const std::vector<double>& params,
    const std::vector<size_t>& variableIdx,
    bool bind_parameters
    ) {
  if ( type == ParserType::TFormula ) {
    const std::lock_guard<std::mutex> lock(tformula_parser.m);
    return translate_tformula_ast(tformula_parser.parse(expression), TranslationContext{params, variableIdx, bind_parameters});
  }
  throw std::runtime_error("Unrecognized formula parser type");
}

double FormulaAst::evaluate(const std::vector<Variable::Type>& values, const std::vector<double>& params) const {
  switch (nodetype_) {
    case NodeType::Literal:
      return std::get<double>(data_);
    case NodeType::Variable:
      return std::get<double>(values[std::get<size_t>(data_)]);
    case NodeType::Parameter:
      return params[std::get<size_t>(data_)];
    case NodeType::Unary: {
      const auto arg = children_[0].evaluate(values, params);
      switch (std::get<UnaryOp>(data_)) {
        case UnaryOp::Negative: return -arg;
        case UnaryOp::Log: return std::log(arg);
        case UnaryOp::Log10: return std::log10(arg);
        case UnaryOp::Exp: return std::exp(arg);
        case UnaryOp::Erf: return std::erf(arg);
        case UnaryOp::Sqrt: return std::sqrt(arg);
        case UnaryOp::Abs: return std::abs(arg);
        case UnaryOp::Cos: return std::cos(arg);
        case UnaryOp::Sin: return std::sin(arg);
        case UnaryOp::Tan: return std::tan(arg);
        case UnaryOp::Acos: return std::acos(arg);
        case UnaryOp::Asin: return std::asin(arg);
        case UnaryOp::Atan: return std::atan(arg);
        case UnaryOp::Cosh: return std::cosh(arg);
        case UnaryOp::Sinh: return std::sinh(arg);
        case UnaryOp::Tanh: return std::tanh(arg);
        case UnaryOp::Acosh: return std::acosh(arg);
        case UnaryOp::Asinh: return std::asinh(arg);
        case UnaryOp::Atanh: return std::atanh(arg);
      }
    }
    case NodeType::Binary: {
      auto left = children_[0].evaluate(values, params);
      auto right = children_[1].evaluate(values, params);
      switch (std::get<BinaryOp>(data_)) {
        case BinaryOp::Equal: return (left == right) ? 1. : 0.;
        case BinaryOp::NotEqual: return (left != right) ? 1. : 0.;
        case BinaryOp::Greater: return (left > right) ? 1. : 0.;
        case BinaryOp::Less: return (left < right) ? 1. : 0.;
        case BinaryOp::GreaterEq: return (left >= right) ? 1. : 0.;
        case BinaryOp::LessEq: return (left <= right) ? 1. : 0.;
        case BinaryOp::Minus: return left - right;
        case BinaryOp::Plus: return left + right;
        case BinaryOp::Div: return left / right;
        case BinaryOp::Times: return left * right;
        case BinaryOp::Pow: return std::pow(left, right);
        case BinaryOp::Atan2: return std::atan2(left, right);
        case BinaryOp::Max: return std::max(left, right);
        case BinaryOp::Min: return std::min(left, right);
      };
    }
    default:
      std::abort(); // never reached if the switch/case is exhaustive
  }
}
