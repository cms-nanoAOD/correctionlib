import pytest

import correctionlib.schemav2 as cs


def test_issue217():
    content = [1.1, 1.08, 1.06, 1.04, 1.02, 1.0]
    corr = cs.Correction(
        name="NJetweight",
        version=1,
        inputs=[cs.Variable(name="nJets", type="int", description="Number of jets")],
        output=cs.Variable(
            name="weight", type="real", description="Multiplicative event weight"
        ),
        data=cs.Binning(
            nodetype="binning",
            input="nJets",
            edges=[0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
            content=content,
            flow="clamp",
        ),
    )
    ceval = corr.to_evaluator()
    assert [ceval.evaluate(i) for i in range(1, 7)] == content


def test_binning_invalidinput():
    corr = cs.Correction(
        name="NJetweight",
        version=1,
        inputs=[cs.Variable(name="bogus", type="string")],
        output=cs.Variable(
            name="weight", type="real", description="Multiplicative event weight"
        ),
        data=cs.Binning(
            nodetype="binning",
            input="bogus",
            edges=[0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
            content=[1.1, 1.08, 1.06, 1.04, 1.02, 1.0],
            flow="clamp",
        ),
    )
    with pytest.raises(RuntimeError):
        corr.to_evaluator()
