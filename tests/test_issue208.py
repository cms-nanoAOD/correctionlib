import pytest

from correctionlib import schemav2 as schema


def _make_binning(edges, content):
    corr = schema.Correction(
        name="test corr",
        version=2,
        inputs=[
            schema.Variable(name="x", type="real"),
        ],
        output=schema.Variable(name="a scale", type="real"),
        data=schema.Binning.model_validate(
            {
                "nodetype": "binning",
                "input": "x",
                "edges": edges,
                "flow": "error",
                "content": content,
            }
        ),
    )
    return corr.to_evaluator()


def test_string_infinity():
    corr = _make_binning([0, 20, 40, "inf"], [1.0, 1.1, 1.2])
    assert corr.evaluate(10.0) == 1.0
    assert corr.evaluate(100.0) == 1.2
    corr = _make_binning([0, 20, 40, "+inf"], [1.0, 1.1, 1.2])
    assert corr.evaluate(100.0) == 1.2
    corr = _make_binning(["-inf", 20, 40, "+inf"], [1.0, 1.1, 1.2])
    assert corr.evaluate(-100.0) == 1.0

    with pytest.raises(ValueError):
        _make_binning([0, 20, 40, "infinity"], [1.0, 1.1, 1.2])
    with pytest.raises(ValueError):
        _make_binning([0, 20, 40, float("inf")], [1.0, 1.1, 1.2])
    with pytest.raises(ValueError):
        _make_binning([0, "inf", 20, 40], [1.0, 1.1, 1.2])
