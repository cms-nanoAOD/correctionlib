#include <mutex>
#include <cmath>
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

  const std::map<std::string, FormulaImpl::OpCode, std::less<void>> tformula_ufmap = {
    {"log",   FormulaImpl::OpCode::Log},
    {"log10", FormulaImpl::OpCode::Log10},
    {"exp",   FormulaImpl::OpCode::Exp},
    {"erf",   FormulaImpl::OpCode::Erf},
    {"sqrt",  FormulaImpl::OpCode::Sqrt},
    {"abs",   FormulaImpl::OpCode::Abs},
    {"cos",   FormulaImpl::OpCode::Cos},
    {"sin",   FormulaImpl::OpCode::Sin},
    {"tan",   FormulaImpl::OpCode::Tan},
    {"acos",  FormulaImpl::OpCode::Acos},
    {"asin",  FormulaImpl::OpCode::Asin},
    {"atan",  FormulaImpl::OpCode::Atan},
    {"cosh",  FormulaImpl::OpCode::Cosh},
    {"sinh",  FormulaImpl::OpCode::Sinh},
    {"tanh",  FormulaImpl::OpCode::Tanh},
    {"acosh", FormulaImpl::OpCode::Acosh},
    {"asinh", FormulaImpl::OpCode::Asinh},
    {"atanh", FormulaImpl::OpCode::Atanh},
  };

  const std::map<std::string, FormulaImpl::OpCode, std::less<void>> tformula_bfmap = {
    {"atan2", FormulaImpl::OpCode::Atan2},
    {"pow",   FormulaImpl::OpCode::Pow},
    {"max",   FormulaImpl::OpCode::Max},
    {"min",   FormulaImpl::OpCode::Min},
  };

  const std::map<std::string, FormulaImpl::OpCode, std::less<void>> tformula_exprmap = {
    {"==", FormulaImpl::OpCode::Equal},
    {"!=", FormulaImpl::OpCode::NotEqual},
    {">",  FormulaImpl::OpCode::Greater},
    {"<",  FormulaImpl::OpCode::Less},
    {">=", FormulaImpl::OpCode::GreaterEq},
    {"<=", FormulaImpl::OpCode::LessEq},
    {"-",  FormulaImpl::OpCode::Minus},
    {"+",  FormulaImpl::OpCode::Plus},
    {"/",  FormulaImpl::OpCode::Div},
    {"*",  FormulaImpl::OpCode::Times},
    {"^",  FormulaImpl::OpCode::Pow},
  };

  struct CompileContext {
      const std::vector<double>& params;
      const std::vector<size_t>& variableIdx;
      bool bind_parameters;
  };

  FormulaImpl::Ptr compile_tformula_ast(
      const PEGParser::AstPtr ast,
      CompileContext& context
      ) {
    if (ast->is_token) {
      if (ast->name == "LITERAL") {
        return std::make_unique<FormulaImpl>(FormulaImpl::OpCode::LoadLiteral, ast->token_to_number<double>(), 0, nullptr, nullptr);
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
        return std::make_unique<FormulaImpl>(FormulaImpl::OpCode::LoadVariable, 0.0, context.variableIdx[idx], nullptr, nullptr);
      }
      else if (ast->name == "PARAMETER") {
        auto pidx = ast->token_to_number<size_t>();
        if ( context.bind_parameters ) {
          if ( pidx >= context.params.size() ) {
            throw std::runtime_error("Insufficient parameters for formula");
          }
          return std::make_unique<FormulaImpl>(FormulaImpl::OpCode::LoadLiteral, context.params[pidx], 0, nullptr, nullptr);
        }
        else {
          return std::make_unique<FormulaImpl>(FormulaImpl::OpCode::LoadParameter, 0.0, pidx, nullptr, nullptr);
        }
      }
    }
    else if (ast->name == "UATOM" ) {
      if ( ast->nodes.size() != 2 ) { throw std::runtime_error("UATOM without 2 nodes?"); }
      const auto name = ast->nodes[0]->token;
      FormulaImpl::OpCode op;
      if      ( name == "-" ) { op = FormulaImpl::OpCode::Negative; }
      else { throw std::runtime_error("Unrecognized unary operation: " + std::string(name)); }
      return std::make_unique<FormulaImpl>(op, 0.0, 0, compile_tformula_ast(ast->nodes[1], context), nullptr);
    }
    else if (ast->name == "CALLU" ) {
      if ( ast->nodes.size() != 2 ) { throw std::runtime_error("CALLU without 2 nodes?"); }
      const auto name = ast->nodes[0]->token;
      const auto iter = tformula_ufmap.find(name);
      if ( iter == tformula_ufmap.end() ) {
        throw std::runtime_error("unrecognized unary function: " + std::string(name));
      }
      return std::make_unique<FormulaImpl>(iter->second, 0.0, 0, compile_tformula_ast(ast->nodes[1], context), nullptr);
    }
    else if (ast->name == "CALLB" ) {
      if ( ast->nodes.size() != 3 ) { throw std::runtime_error("CALLB without 3 nodes?"); }
      const auto name = ast->nodes[0]->token;
      const auto iter = tformula_bfmap.find(name);
      if ( iter == tformula_bfmap.end() ) {
        throw std::runtime_error("unrecognized binary function: " + std::string(name));
      }
      return std::make_unique<FormulaImpl>(iter->second, 0.0, 0, compile_tformula_ast(ast->nodes[1], context), compile_tformula_ast(ast->nodes[2], context));
    }
    else if (ast->name == "EXPRESSION" ) {
      if ( ast->nodes.size() != 3 ) { throw std::runtime_error("EXPRESSION without 3 nodes?"); }
      const auto name = ast->nodes[1]->token;
      const auto iter = tformula_exprmap.find(name);
      if ( iter == tformula_exprmap.end() ) {
        throw std::runtime_error("unrecognized binary operation: " + std::string(name));
      }
      return std::make_unique<FormulaImpl>(iter->second, 0.0, 0, compile_tformula_ast(ast->nodes[0], context), compile_tformula_ast(ast->nodes[2], context));
    }
    throw std::runtime_error("Unrecognized AST node");
  }

}

FormulaImpl::Ptr FormulaImpl::parse(
    FormulaImpl::ParserType type,
    const std::string_view expression,
    const std::vector<double>& params,
    const std::vector<size_t>& variableIdx,
    bool bind_parameters
    ) {
  if ( type == ParserType::TFormula ) {
    const std::lock_guard<std::mutex> lock(tformula_parser.m);
    CompileContext ctx{params, variableIdx, bind_parameters};
    return compile_tformula_ast(tformula_parser.parse(expression), ctx);
  }
  throw std::runtime_error("Unrecognized formula parser type");
}

double FormulaImpl::evaluate(const std::vector<Variable::Type>& values, const std::vector<double>& params) const {
  double left{999}, right{1000};
  if ( left_ ) left = left_->evaluate(values, params);
  if ( right_ ) right = right_->evaluate(values, params);
  switch (op_) {
    case OpCode::LoadLiteral:
      return lit_;
    case OpCode::LoadVariable:
      return std::get<double>(values[idx_]);
    case OpCode::LoadParameter:
      return params[idx_];

    // unary operators
    case OpCode::Negative: return -left;
    // unary functions
    case OpCode::Log: return std::log(left);
    case OpCode::Log10: return std::log10(left);
    case OpCode::Exp: return std::exp(left);
    case OpCode::Erf: return std::erf(left);
    case OpCode::Sqrt: return std::sqrt(left);
    case OpCode::Abs: return std::abs(left);
    case OpCode::Cos: return std::cos(left);
    case OpCode::Sin: return std::sin(left);
    case OpCode::Tan: return std::tan(left);
    case OpCode::Acos: return std::acos(left);
    case OpCode::Asin: return std::asin(left);
    case OpCode::Atan: return std::atan(left);
    case OpCode::Cosh: return std::cosh(left);
    case OpCode::Sinh: return std::sinh(left);
    case OpCode::Tanh: return std::tanh(left);
    case OpCode::Acosh: return std::acosh(left);
    case OpCode::Asinh: return std::asinh(left);
    case OpCode::Atanh: return std::atanh(left);

    // binary functions
    case OpCode::Atan2: return std::atan2(left, right);
    case OpCode::Pow: return std::pow(left, right);
    case OpCode::Max: return std::max(left, right);
    case OpCode::Min: return std::min(left, right);
    // binary operators
    case OpCode::Equal: return (left == right) ? 1. : 0.;
    case OpCode::NotEqual: return (left != right) ? 1. : 0.;
    case OpCode::Greater: return (left > right) ? 1. : 0.;
    case OpCode::Less: return (left < right) ? 1. : 0.;
    case OpCode::GreaterEq: return (left >= right) ? 1. : 0.;
    case OpCode::LessEq: return (left <= right) ? 1. : 0.;
    case OpCode::Minus: return left - right;
    case OpCode::Plus: return left + right;
    case OpCode::Div: return left / right;
    case OpCode::Times: return left * right;
    case OpCode::Undefined:
      throw std::runtime_error("Unrecognized AST node");
  }
}
