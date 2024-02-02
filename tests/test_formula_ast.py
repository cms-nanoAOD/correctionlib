import correctionlib._core as core
from correctionlib import schemav2 as schema


def test_access_formula_ast():
    """Test that we can access a Formula's AST from Python"""

    c = schema.Correction(
        name="test",
        version=2,
        inputs=[schema.Variable(name="x", type="real")],
        output=schema.Variable(name="a scale", type="real"),
        data=schema.Formula(
            nodetype="formula",
            expression="23.*log(x)",
            parser="TFormula",
            variables=["x"],
        ),
    )

    formula = core.Formula.from_string(
        c.data.model_dump_json(),
        [core.Variable.from_string(v.model_dump_json()) for v in c.inputs],
    )
    ast = formula.ast

    assert ast.nodetype == core.FormulaAst.NodeType.BINARY
    assert ast.data == core.FormulaAst.BinaryOp.TIMES
    assert ast.children[0].nodetype == core.FormulaAst.NodeType.LITERAL
    assert ast.children[0].data == 23.0
    assert ast.children[1].nodetype == core.FormulaAst.NodeType.UNARY
    assert ast.children[1].data == core.FormulaAst.UnaryOp.LOG
    assert ast.children[1].children[0].nodetype == core.FormulaAst.NodeType.VARIABLE
    # the index of variable x in the inputs
    assert ast.children[1].children[0].data == 0
