"""Malformed or hand-written JSON must raise a Python exception, never crash or misbehave."""

import json

import pytest

import correctionlib._core as core


def _make(data, inputs, **extra):
    corr = {
        "name": "test",
        "version": 1,
        "inputs": inputs,
        "output": {"name": "out", "type": "real"},
        "data": data,
    }
    corr.update(extra)
    cset = {"schema_version": 2, "corrections": [corr]}
    return core.CorrectionSet.from_string(json.dumps(cset))["test"]


REAL_X = [{"name": "x", "type": "real"}]
REAL_XY = [{"name": "x", "type": "real"}, {"name": "y", "type": "real"}]


def test_integer_valued_edges():
    # JSON does not distinguish 0 from 0.0; hand-written files often use integers
    corr = _make(
        {
            "nodetype": "binning",
            "input": "x",
            "edges": [0, 20, 40],
            "content": [1.0, 2.0],
            "flow": "clamp",
        },
        REAL_X,
    )
    assert corr.evaluate(10.0) == 1.0
    assert corr.evaluate(25.0) == 2.0

    corr = _make(
        {
            "nodetype": "binning",
            "input": "x",
            "edges": {"n": 2, "low": 0, "high": 40},
            "content": [1.0, 2.0],
            "flow": "clamp",
        },
        REAL_X,
    )
    assert corr.evaluate(10.0) == 1.0
    assert corr.evaluate(25.0) == 2.0

    with pytest.raises(RuntimeError, match="Invalid edge type"):
        _make(
            {
                "nodetype": "binning",
                "input": "x",
                "edges": [0.0, None],
                "content": [1.0],
                "flow": "clamp",
            },
            REAL_X,
        )


def test_int64_category_keys():
    corr = _make(
        {
            "nodetype": "category",
            "input": "x",
            "content": [
                {"key": 2**40, "value": 1.0},
                {"key": -(2**40), "value": 2.0},
                {"key": 2**63 - 1, "value": 3.0},
            ],
        },
        [{"name": "x", "type": "int"}],
    )
    assert corr.evaluate(2**40) == 1.0
    assert corr.evaluate(-(2**40)) == 2.0
    assert corr.evaluate(2**63 - 1) == 3.0


def test_multibinning_inputs_edges_mismatch():
    with pytest.raises(RuntimeError, match="does not match number of inputs"):
        _make(
            {
                "nodetype": "multibinning",
                "inputs": ["x"],
                "edges": [[0.0, 1.0], [0.0, 1.0]],
                "content": [1.0],
                "flow": "clamp",
            },
            REAL_XY,
        )


@pytest.mark.parametrize(
    "edges",
    [[0.0, 1.0], {"n": 1, "low": 0.0, "high": 1.0}],
    ids=["nonuniform", "uniform"],
)
def test_multibinning_non_string_input(edges):
    with pytest.raises(RuntimeError, match="Expected string"):
        _make(
            {
                "nodetype": "multibinning",
                "inputs": [1],
                "edges": [edges],
                "content": [1.0],
                "flow": "clamp",
            },
            REAL_X,
        )


def test_formula_non_string_variable():
    with pytest.raises(RuntimeError, match="Expected string"):
        _make(
            {
                "nodetype": "formula",
                "expression": "x",
                "parser": "TFormula",
                "variables": [1],
            },
            REAL_X,
        )


def test_formula_non_numeric_parameter():
    with pytest.raises(RuntimeError, match="Expected number"):
        _make(
            {
                "nodetype": "formula",
                "expression": "[0]",
                "parser": "TFormula",
                "variables": [],
                "parameters": ["a"],
            },
            [],
        )


def test_formularef_bad_index():
    generic = [
        {
            "nodetype": "formula",
            "expression": "[0]",
            "parser": "TFormula",
            "variables": [],
        }
    ]
    corr = _make(
        {"nodetype": "formularef", "index": 0, "parameters": [3.0]},
        [],
        generic_formulas=generic,
    )
    assert corr.evaluate() == 3.0

    with pytest.raises(RuntimeError, match="out of range"):
        _make(
            {"nodetype": "formularef", "index": 1, "parameters": [3.0]},
            [],
            generic_formulas=generic,
        )
    with pytest.raises(RuntimeError, match="invalid type"):
        _make(
            {"nodetype": "formularef", "index": -1, "parameters": [3.0]},
            [],
            generic_formulas=generic,
        )
    with pytest.raises(RuntimeError, match="Expected number"):
        _make(
            {"nodetype": "formularef", "index": 0, "parameters": ["a"]},
            [],
            generic_formulas=generic,
        )
