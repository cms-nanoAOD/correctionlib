import correctionlib._core as core
from correctionlib import schemav2 as schema


def wrap(*corrs):
    cset = schema.CorrectionSet(
        schema_version=schema.VERSION,
        corrections=list(corrs),
    )
    return core.CorrectionSet.from_string(cset.model_dump_json())


def test_transform_nested_rule_and_content():
    # Build a nested transform tree with transforms in both the rule and
    # content paths to exercise recursive evaluation and scratch-buffer reuse.
    cset = wrap(
        schema.Correction(
            name="nested_transform",
            version=2,
            inputs=[
                schema.Variable(name="x", type="real"),
                schema.Variable(name="y", type="real"),
            ],
            output=schema.Variable(name="out", type="real"),
            data=schema.Transform(
                nodetype="transform",
                input="x",
                rule=schema.Transform(
                    nodetype="transform",
                    input="y",
                    rule=1.0,
                    content=schema.Formula(
                        nodetype="formula",
                        expression="x + y",
                        parser="TFormula",
                        variables=["x", "y"],
                    ),
                ),
                content=schema.Transform(
                    nodetype="transform",
                    input="y",
                    rule=schema.Transform(
                        nodetype="transform",
                        input="x",
                        rule=2.0,
                        content=schema.Formula(
                            nodetype="formula",
                            expression="x + y",
                            parser="TFormula",
                            variables=["x", "y"],
                        ),
                    ),
                    content=schema.Formula(
                        nodetype="formula",
                        expression="x + y",
                        parser="TFormula",
                        variables=["x", "y"],
                    ),
                ),
            ),
        )
    )

    corr = cset["nested_transform"]
    # x=3, y=4
    # outer rule: transform y->1 then x+y => 3+1 = 4, so x becomes 4
    # outer content: transform y with rule:
    #   inner rule transform x->2 then x+y => 2+4 = 6, so y becomes 6
    # final content: x+y = 4+6 = 10
    assert corr.evaluate(3.0, 4.0) == 10.0
