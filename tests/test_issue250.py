import correctionlib.schemav2 as cs


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
