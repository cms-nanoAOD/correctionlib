import pytest

import correctionlib.schemav2 as cs
from correctionlib.highlevel import Correction


def _make_formula(formula: str, ninputs: int) -> Correction:
    inputs = [cs.Variable(name=f"input{i}", type="real") for i in range(ninputs)]
    formula_obj = cs.Formula(
        nodetype="formula",
        expression=formula,
        parser="TFormula",
        variables=[input.name for input in inputs],
    )
    return cs.Correction(
        name="test",
        version=2,
        inputs=inputs,
        output=cs.Variable(name="a scale", type="real"),
        data=formula_obj,
    ).to_evaluator()


def test_formula_manyvars():
    corr = _make_formula("x[0] + 2*x[1] + 3*x[2] + 4*x[3] + 5*x[4]", ninputs=5)

    assert corr.evaluate(1.0, 1.0, 1.0, 1.0, 1.0) == 15.0
    assert corr.evaluate(0.0, 0.0, 0.0, 0.0, 0.0) == 0.0
    assert corr.evaluate(1.0, 2.0, 3.0, 4.0, 5.0) == 1 + 4 + 9 + 16 + 25

    with pytest.raises(RuntimeError):
        corr = _make_formula("x[0] + x[5]", ninputs=2)

    with pytest.raises(RuntimeError):
        corr = _make_formula("x[-1] + x[0]", ninputs=2)

    with pytest.raises(RuntimeError):
        corr = _make_formula("x[abc] + x[0]", ninputs=2)
