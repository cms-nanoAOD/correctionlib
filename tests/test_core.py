import json
import math

import pytest

import correctionlib._core as core
from correctionlib import schemav2 as schema


def wrap(*corrs):
    cset = schema.CorrectionSet(
        schema_version=2,
        corrections=list(corrs),
    )
    return core.CorrectionSet.from_string(cset.json())


def test_evaluator_v1():
    with pytest.raises(RuntimeError):
        cset = core.CorrectionSet.from_string("{")

    with pytest.raises(RuntimeError):
        cset = core.CorrectionSet.from_string("{}")

    with pytest.raises(RuntimeError):
        cset = core.CorrectionSet.from_string('{"schema_version": "blah"}')

    cset = wrap(
        schema.Correction(
            name="test corr",
            version=2,
            inputs=[],
            output=schema.Variable(name="a scale", type="real"),
            data=1.234,
        )
    )
    assert set(cset) == {"test corr"}
    sf = cset["test corr"]
    assert sf.version == 2
    assert sf.description == ""

    with pytest.raises(RuntimeError):
        sf.evaluate(0, 1.2, 35.0, 0.01)

    assert sf.evaluate() == 1.234

    cset = wrap(
        schema.Correction(
            name="test corr",
            version=2,
            inputs=[
                schema.Variable(name="pt", type="real"),
                schema.Variable(name="syst", type="string"),
            ],
            output=schema.Variable(name="a scale", type="real"),
            data=schema.Binning.parse_obj(
                {
                    "nodetype": "binning",
                    "input": "pt",
                    "edges": [0, 20, 40],
                    "flow": "error",
                    "content": [
                        schema.Category.parse_obj(
                            {
                                "nodetype": "category",
                                "input": "syst",
                                "content": [
                                    {"key": "blah", "value": 1.1},
                                    {"key": "blah2", "value": 2.2},
                                ],
                            }
                        ),
                        schema.Category.parse_obj(
                            {
                                "nodetype": "category",
                                "input": "syst",
                                "content": [
                                    {"key": "blah2", "value": 1.3},
                                    {
                                        "key": "blah3",
                                        "value": {
                                            "nodetype": "formula",
                                            "expression": "0.25*x + exp([0])",
                                            "parser": "TFormula",
                                            "variables": ["pt"],
                                            "parameters": [3.1],
                                        },
                                    },
                                ],
                            }
                        ),
                    ],
                }
            ),
        )
    )
    assert set(cset) == {"test corr"}
    sf = cset["test corr"]
    assert sf.version == 2
    assert sf.description == ""

    with pytest.raises(RuntimeError):
        # too many inputs
        sf.evaluate(0, 1.2, 35.0, 0.01)

    with pytest.raises(RuntimeError):
        # not enough inputs
        sf.evaluate(1.2)

    with pytest.raises(RuntimeError):
        # wrong type
        sf.evaluate(5)

    with pytest.raises(RuntimeError):
        # wrong type
        sf.evaluate("asdf")

    assert sf.evaluate(12.0, "blah") == 1.1
    # Do we need pytest.approx? Maybe not
    assert sf.evaluate(31.0, "blah3") == 0.25 * 31.0 + math.exp(3.1)


def test_tformula():
    formulas = [
        ("23.*x", lambda x: 23.0 * x),
        ("23.*log(max(x, 0.1))", lambda x: 23.0 * math.log(max(x, 0.1))),
        ("2.2e3 + x", lambda x: 2.2e3 + x),
        ("-2e-3 * x", lambda x: -2e-3 * x),
    ]
    cset = {
        "schema_version": 2,
        "corrections": [
            {
                "name": "test",
                "version": 1,
                "inputs": [
                    {"name": "index", "type": "int"},
                    {"name": "x", "type": "real"},
                ],
                "output": {"name": "f", "type": "real"},
                "data": {
                    "nodetype": "category",
                    "input": "index",
                    "content": [
                        {
                            "key": i,
                            "value": {
                                "nodetype": "formula",
                                "expression": expr,
                                "parser": "TFormula",
                                "variables": ["x"],
                            },
                        }
                        for i, (expr, _) in enumerate(formulas)
                    ],
                },
            }
        ],
    }
    schema.CorrectionSet.parse_obj(cset)
    corr = core.CorrectionSet.from_string(json.dumps(cset))["test"]
    test_values = [1.0, 32.0, -3.0, 1550.0]
    for i, (_, expected) in enumerate(formulas):
        for x in test_values:
            assert corr.evaluate(i, x) == expected(x)


def test_binning():
    def binning(flow):
        cset = wrap(
            schema.Correction(
                name="test",
                version=2,
                inputs=[schema.Variable(name="x", type="real")],
                output=schema.Variable(name="a scale", type="real"),
                data=schema.Binning(
                    nodetype="binning",
                    input="x",
                    edges=[0.0, 1.0, 3.0],
                    content=[1.0, 2.0],
                    flow=flow,
                ),
            )
        )
        return cset["test"]

    corr = binning(flow="error")
    with pytest.raises(RuntimeError):
        corr.evaluate(-1.0)
    assert corr.evaluate(0.0) == 1.0
    assert corr.evaluate(0.2) == 1.0
    assert corr.evaluate(1.0) == 2.0
    with pytest.raises(RuntimeError):
        corr.evaluate(3.0)

    corr = binning(flow="clamp")
    assert corr.evaluate(-1.0) == 1.0
    assert corr.evaluate(1.0) == 2.0
    assert corr.evaluate(3.0) == 2.0
    assert corr.evaluate(3000.0) == 2.0

    corr = binning(flow=42.0)
    assert corr.evaluate(-1.0) == 42.0
    assert corr.evaluate(0.0) == 1.0
    assert corr.evaluate(1.0) == 2.0
    assert corr.evaluate(2.9) == 2.0
    assert corr.evaluate(3.0) == 42.0

    def multibinning(flow):
        cset = wrap(
            schema.Correction(
                name="test",
                version=2,
                inputs=[
                    schema.Variable(name="x", type="real"),
                    schema.Variable(name="y", type="real"),
                ],
                output=schema.Variable(name="a scale", type="real"),
                data=schema.MultiBinning(
                    nodetype="multibinning",
                    inputs=["x", "y"],
                    edges=[
                        [0.0, 1.0, 3.0],
                        [10.0, 20.0, 30.0, 40.0],
                    ],
                    content=[float(i) for i in range(2 * 3)],
                    flow=flow,
                ),
            )
        )
        return cset["test"]

    corr = multibinning(flow="error")
    with pytest.raises(RuntimeError):
        corr.evaluate(0.0, 5.0)
    with pytest.raises(RuntimeError):
        corr.evaluate(-1.0, 5.0)
    assert corr.evaluate(0.0, 10.0) == 0.0
    assert corr.evaluate(0.0, 20.0) == 1.0
    assert corr.evaluate(0.0, 30.0) == 2.0
    with pytest.raises(RuntimeError):
        corr.evaluate(0.0, 40.0)
    assert corr.evaluate(1.0, 10.0) == 3.0
    assert corr.evaluate(1.0, 20.0) == 4.0
    assert corr.evaluate(1.0, 30.0) == 5.0
    with pytest.raises(RuntimeError):
        corr.evaluate(2.0, 5.0)

    corr = multibinning(flow="clamp")
    assert corr.evaluate(-1.0, 5.0) == 0.0
    assert corr.evaluate(-1.0, 25.0) == 1.0
    assert corr.evaluate(-1.0, 35.0) == 2.0
    assert corr.evaluate(-1.0, 45.0) == 2.0
    assert corr.evaluate(0.0, 45.0) == 2.0
    assert corr.evaluate(2.0, 45.0) == 5.0
    assert corr.evaluate(3.0, 45.0) == 5.0
    assert corr.evaluate(3.0, 35.0) == 5.0
    assert corr.evaluate(3.0, 25.0) == 4.0
    assert corr.evaluate(3.0, 15.0) == 3.0
    assert corr.evaluate(3.0, 5.0) == 3.0
    assert corr.evaluate(0.0, 5.0) == 0.0

    corr = multibinning(flow=42.0)
    assert corr.evaluate(-1.0, 5.0) == 42.0
    assert corr.evaluate(2.0, 45.0) == 42.0
    assert corr.evaluate(3.0, 5.0) == 42.0

    corr = multibinning(
        flow=schema.Formula(
            nodetype="formula",
            expression="2.*x + 5.*y",
            parser="TFormula",
            variables=["x", "y"],
        )
    )
    assert corr.evaluate(-1.0, 5.0) == 2.0 * -1 + 5.0 * 5.0
    assert corr.evaluate(0.0, 10.0) == 0.0
