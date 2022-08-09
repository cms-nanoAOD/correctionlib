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
      std::vector<double> literals;
      std::vector<size_t> indices;
      std::vector<FormulaImpl::OpCode> instructions;
      size_t curdepth{0};
      size_t maxdepth{0};
  };

  void compile_tformula_ast(
      const PEGParser::AstPtr ast,
      CompileContext& context
      ) {
    if (ast->is_token) {
      if (ast->name == "LITERAL") {
        context.literals.push_back(ast->token_to_number<double>());
        context.instructions.push_back(FormulaImpl::OpCode::LoadLiteral);
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
        context.indices.push_back(context.variableIdx[idx]);
        context.instructions.push_back(FormulaImpl::OpCode::LoadVariable);
      }
      else if (ast->name == "PARAMETER") {
        auto pidx = ast->token_to_number<size_t>();
        if ( context.bind_parameters ) {
          if ( pidx >= context.params.size() ) {
            throw std::runtime_error("Insufficient parameters for formula");
          }
          context.literals.push_back(context.params[pidx]);
          context.instructions.push_back(FormulaImpl::OpCode::LoadLiteral);
        }
        else {
          context.indices.push_back(pidx);
          context.instructions.push_back(FormulaImpl::OpCode::LoadParameter);
        }
      }
    }
    else if (ast->name == "UATOM" ) {
      if ( ast->nodes.size() != 2 ) { throw std::runtime_error("UATOM without 2 nodes?"); }
      const auto name = ast->nodes[0]->token;
      FormulaImpl::OpCode op;
      if      ( name == "-" ) { op = FormulaImpl::OpCode::Negative; }
      else { throw std::runtime_error("Unrecognized unary operation: " + std::string(name)); }
      compile_tformula_ast(ast->nodes[1], context);
      context.instructions.push_back(op);
    }
    else if (ast->name == "CALLU" ) {
      if ( ast->nodes.size() != 2 ) { throw std::runtime_error("CALLU without 2 nodes?"); }
      const auto name = ast->nodes[0]->token;
      const auto iter = tformula_ufmap.find(name);
      if ( iter == tformula_ufmap.end() ) {
        throw std::runtime_error("unrecognized unary function: " + std::string(name));
      }
      compile_tformula_ast(ast->nodes[1], context);
      context.instructions.push_back(iter->second);
    }
    else if (ast->name == "CALLB" ) {
      if ( ast->nodes.size() != 3 ) { throw std::runtime_error("CALLB without 3 nodes?"); }
      const auto name = ast->nodes[0]->token;
      const auto iter = tformula_bfmap.find(name);
      if ( iter == tformula_bfmap.end() ) {
        throw std::runtime_error("unrecognized binary function: " + std::string(name));
      }
      compile_tformula_ast(ast->nodes[1], context);
      context.instructions.push_back(FormulaImpl::OpCode::PushStack);
      context.curdepth++;
      context.maxdepth = std::max(context.maxdepth, context.curdepth);
      compile_tformula_ast(ast->nodes[2], context);
      context.instructions.push_back(iter->second);
      context.curdepth--;
    }
    else if (ast->name == "EXPRESSION" ) {
      if ( ast->nodes.size() != 3 ) { throw std::runtime_error("EXPRESSION without 3 nodes?"); }
      const auto name = ast->nodes[1]->token;
      const auto iter = tformula_exprmap.find(name);
      if ( iter == tformula_exprmap.end() ) {
        throw std::runtime_error("unrecognized binary operation: " + std::string(name));
      }
      compile_tformula_ast(ast->nodes[0], context);
      context.instructions.push_back(FormulaImpl::OpCode::PushStack);
      context.curdepth++;
      context.maxdepth = std::max(context.maxdepth, context.curdepth);
      compile_tformula_ast(ast->nodes[2], context);
      context.instructions.push_back(iter->second);
      context.curdepth--;
    }
    else {
      throw std::runtime_error("Unrecognized AST node");
    }
  }

  std::map<FormulaImpl::OpCode, const char *> opnames = {
    {FormulaImpl::OpCode::LoadLiteral, "LoadLiteral"},
    {FormulaImpl::OpCode::LoadVariable, "LoadVariable"},
    {FormulaImpl::OpCode::LoadParameter, "LoadParameter"},
    {FormulaImpl::OpCode::PushStack, "PushStack"},
    {FormulaImpl::OpCode::Negative, "Negative"},
    {FormulaImpl::OpCode::Log, "Log"},
    {FormulaImpl::OpCode::Log10, "Log10"},
    {FormulaImpl::OpCode::Exp, "Exp"},
    {FormulaImpl::OpCode::Erf, "Erf"},
    {FormulaImpl::OpCode::Sqrt, "Sqrt"},
    {FormulaImpl::OpCode::Abs, "Abs"},
    {FormulaImpl::OpCode::Cos, "Cos"},
    {FormulaImpl::OpCode::Sin, "Sin"},
    {FormulaImpl::OpCode::Tan, "Tan"},
    {FormulaImpl::OpCode::Acos, "Acos"},
    {FormulaImpl::OpCode::Asin, "Asin"},
    {FormulaImpl::OpCode::Atan, "Atan"},
    {FormulaImpl::OpCode::Cosh, "Cosh"},
    {FormulaImpl::OpCode::Sinh, "Sinh"},
    {FormulaImpl::OpCode::Tanh, "Tanh"},
    {FormulaImpl::OpCode::Acosh, "Acosh"},
    {FormulaImpl::OpCode::Asinh, "Asinh"},
    {FormulaImpl::OpCode::Atanh, "Atanh"},
    {FormulaImpl::OpCode::Atan2, "Atan2"},
    {FormulaImpl::OpCode::Pow, "Pow"},
    {FormulaImpl::OpCode::Max, "Max"},
    {FormulaImpl::OpCode::Min, "Min"},
    {FormulaImpl::OpCode::Equal, "Equal"},
    {FormulaImpl::OpCode::NotEqual, "NotEqual"},
    {FormulaImpl::OpCode::Greater, "Greater"},
    {FormulaImpl::OpCode::Less, "Less"},
    {FormulaImpl::OpCode::GreaterEq, "GreaterEq"},
    {FormulaImpl::OpCode::LessEq, "LessEq"},
    {FormulaImpl::OpCode::Minus, "Minus"},
    {FormulaImpl::OpCode::Plus, "Plus"},
    {FormulaImpl::OpCode::Div, "Div"},
    {FormulaImpl::OpCode::Times, "Times"},
    {FormulaImpl::OpCode::Undefined, "Undefined"},
  };

}

FormulaImpl::Ptr FormulaImpl::parse(
    FormulaImpl::ParserType type,
    const std::string_view expression,
    const std::vector<double>& params,
    const std::vector<size_t>& variableIdx,
    bool bind_parameters
    ) {
  CompileContext context{params, variableIdx, bind_parameters};
  if ( type == ParserType::TFormula ) {
    const std::lock_guard<std::mutex> lock(tformula_parser.m);
    compile_tformula_ast(tformula_parser.parse(expression), context);
  }
  else {
    throw std::runtime_error("Unrecognized formula parser type");
  }
  if ( false ) {
    std::cout << "max depth: " << context.maxdepth << std::endl;
    size_t ilit{0}, iidx{0};
    for(auto op : context.instructions) {
      if ( op == OpCode::LoadLiteral )
        std::cout << opnames[op] << ": " << context.literals[ilit++] << std::endl;
      else if ( op == OpCode::LoadVariable or op == OpCode::LoadParameter )
        std::cout << opnames[op] << ": " << context.indices[iidx++] << std::endl;
      else
        std::cout << opnames[op] << std::endl;
    }
  }
  return std::make_unique<FormulaImpl>(context.instructions, context.literals, context.indices, context.maxdepth);
}

double FormulaImpl::evaluate(const std::vector<Variable::Type>& values, const std::vector<double>& params) const {
  double* stack = (double*) alloca(stacksize_*sizeof(double));
  size_t sptr{0}, litptr{0}, idxptr{0};
  double reg;
  for (const auto& op : ops_) {
    switch (op) {
      // load vars
      case OpCode::LoadLiteral:
        reg = literals_[litptr++];
        break;
      case OpCode::LoadVariable:
        reg = std::get<double>(values[indices_[idxptr++]]);
        break;
      case OpCode::LoadParameter:
        reg = params[indices_[idxptr++]];
        break;
      case OpCode::PushStack:
        assert(sptr < stacksize_);
        stack[sptr++] = reg;
        break;

      // unary operators
      case OpCode::Negative:
        reg *= -1.0;
        break;

      // unary functions
      case OpCode::Log:
        reg = std::log(reg);
        break;
      case OpCode::Log10:
        reg = std::log10(reg);
        break;
      case OpCode::Exp:
        reg = std::exp(reg);
        break;
      case OpCode::Erf:
        reg = std::erf(reg);
        break;
      case OpCode::Sqrt:
        reg = std::sqrt(reg);
        break;
      case OpCode::Abs:
        reg = std::abs(reg);
        break;
      case OpCode::Cos:
        reg = std::cos(reg);
        break;
      case OpCode::Sin:
        reg = std::sin(reg);
        break;
      case OpCode::Tan:
        reg = std::tan(reg);
        break;
      case OpCode::Acos:
        reg = std::acos(reg);
        break;
      case OpCode::Asin:
        reg = std::asin(reg);
        break;
      case OpCode::Atan:
        reg = std::atan(reg);
        break;
      case OpCode::Cosh:
        reg = std::cosh(reg);
        break;
      case OpCode::Sinh:
        reg = std::sinh(reg);
        break;
      case OpCode::Tanh:
        reg = std::tanh(reg);
        break;
      case OpCode::Acosh:
        reg = std::acosh(reg);
        break;
      case OpCode::Asinh:
        reg = std::asinh(reg);
        break;
      case OpCode::Atanh:
        reg = std::atanh(reg);
        break;

      // binary functions
      case OpCode::Atan2:
        reg = std::atan2(stack[--sptr], reg);
        break;
      case OpCode::Pow:
        reg = std::pow(stack[--sptr], reg);
        break;
      case OpCode::Max:
        reg = std::max(stack[--sptr], reg);
        break;
      case OpCode::Min:
        reg = std::min(stack[--sptr], reg);
        break;

      // binary operators
      case OpCode::Equal:
        reg = stack[--sptr] == reg;
        break;
      case OpCode::NotEqual:
        reg = stack[--sptr] != reg;
        break;
      case OpCode::Greater:
        reg = stack[--sptr] > reg;
        break;
      case OpCode::Less:
        reg = stack[--sptr] < reg;
        break;
      case OpCode::GreaterEq:
        reg = stack[--sptr] >= reg;
        break;
      case OpCode::LessEq:
        reg = stack[--sptr] <= reg;
        break;
      case OpCode::Minus:
        reg = stack[--sptr] - reg;
        break;
      case OpCode::Plus:
        reg = stack[--sptr] + reg;
        break;
      case OpCode::Div:
        reg = stack[--sptr] / reg;
        break;
      case OpCode::Times:
        reg = stack[--sptr] * reg;
        break;

      case OpCode::Undefined:
        throw std::runtime_error("Unrecognized AST node");
    }
  }
  assert(sptr == 0);
  return reg;
}
