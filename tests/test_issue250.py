import correctionlib.schemav2 as cs
from correctionlib.highlevel import Correction


def test_issue250():
    formula = cs.Formula(
        nodetype="formula",
        expression="((min(max(x,20.),140.)>20.0&&min(max(x,20.),140.)<=30.0))*0.8434999999999999",
        parser="TFormula",
        variables=["x"],
    )
    corr = cs.Correction(
        name="test",
        version=2,
        inputs=[cs.Variable(name="x", type="real")],
        output=cs.Variable(name="a scale", type="real"),
        data=formula,
    ).to_evaluator()

    assert corr.evaluate(15.0) == 0.0
    assert corr.evaluate(20.0) == 0.0
    assert corr.evaluate(25.0) == 0.8434999999999999
    assert corr.evaluate(35.0) == 0.0

    binning = cs.Binning(
        nodetype="binning",
        input="x",
        edges=[20.0, 30.0, 140.0],
        content=[0.8434999999999999, 0.0],
        flow=0.0,
    )
    corr = cs.Correction(
        name="test",
        version=2,
        inputs=[cs.Variable(name="x", type="real")],
        output=cs.Variable(name="a scale", type="real"),
        data=binning,
    ).to_evaluator()

    assert corr.evaluate(15.0) == 0.0
    # bin edges are inclusive on the low side
    assert corr.evaluate(20.0) == 0.8434999999999999
    assert corr.evaluate(25.0) == 0.8434999999999999
    assert corr.evaluate(35.0) == 0.0


def _make(formula: str) -> Correction:
    formula_obj = cs.Formula(
        nodetype="formula",
        expression=formula,
        parser="TFormula",
        variables=["x"],
    )
    return cs.Correction(
        name="test",
        version=2,
        inputs=[cs.Variable(name="x", type="real")],
        output=cs.Variable(name="a scale", type="real"),
        data=formula_obj,
    ).to_evaluator()


def test_formula_logic():
    assert _make("x > 5").evaluate(6.0) == 1.0
    assert _make("x > 5").evaluate(5.0) == 0.0

    assert _make("x < 5").evaluate(4.0) == 1.0
    assert _make("x < 5").evaluate(5.0) == 0.0

    assert _make("x > 5 || x < 3").evaluate(6.0) == 1.0
    assert _make("x > 5 || x < 3").evaluate(4.0) == 0.0
    assert _make("x > 5 || x < 3").evaluate(2.0) == 1.0

    assert _make("x > 5 && x < 10").evaluate(11.0) == 0.0
    assert _make("x > 5 && x < 10").evaluate(6.0) == 1.0
    assert _make("x > 5 && x < 10").evaluate(4.0) == 0.0

    assert _make("(x > 5 && x < 10) || (x > 20 && x < 30)").evaluate(6.0) == 1.0
    assert _make("(x > 5 && x < 10) || (x > 20 && x < 30)").evaluate(25.0) == 1.0
    assert _make("(x > 5 && x < 10) || (x > 20 && x < 30)").evaluate(15.0) == 0.0
