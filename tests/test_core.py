import json
import math

import pytest

import correctionlib._core as core
from correctionlib import schemav2 as schema


def wrap(*corrs):
    cset = schema.CorrectionSet(
        schema_version=schema.VERSION,
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
                    "edges": [0, 20, 40],
                    "content": [
                        schema.Category.parse_obj(
                            {
                                "nodetype": "category",
                                "content": [
                                    {"key": "blah", "value": 1.1},
                                    {"key": "blah2", "value": 2.2},
                                ],
                            }
                        ),
                        schema.Category.parse_obj(
                            {
                                "nodetype": "category",
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


def test_default_category():
    cset = wrap(
        schema.Correction(
            name="test",
            version=2,
            inputs=[schema.Variable(name="cat", type="string")],
            output=schema.Variable(name="a scale", type="real"),
            data=schema.Category(
                nodetype="category",
                content=[
                    {"key": "blah", "value": 1.2},
                    {"key": "def", "value": 0.0},
                ],
                default="def",
            ),
        )
    )
    assert cset["test"].evaluate("blah") == 1.2
    assert cset["test"].evaluate("asdf") == 0.0
    assert cset["test"].evaluate("def") == 0.0
