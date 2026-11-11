import json
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest
from pydantic import ValidationError

from correctionlib import convert, schemav1
from correctionlib import schemav2 as schema
from correctionlib._core import CorrectionSet
from correctionlib.highlevel import model_auto


def correction(data, **kwargs):
    return schema.Correction(
        name="test",
        version=kwargs.pop("version", 1),
        inputs=kwargs.pop("inputs", []),
        output={"name": "out", "type": "real"},
        data=data,
        **kwargs,
    )


def numeric_field(field, value):
    if field == "content":
        return correction(value).data
    if field == "formula_parameter":
        return schema.Formula(
            nodetype="formula",
            expression="[0]",
            parser="TFormula",
            variables=[],
            parameters=[value],
        ).parameters[0]
    if field == "formularef_parameter":
        return schema.FormulaRef(
            nodetype="formularef", index=0, parameters=[value]
        ).parameters[0]
    if field == "uniform_low":
        return schema.UniformBinning(n=1, low=value, high=4).low
    if field == "uniform_high":
        return schema.UniformBinning(n=1, low=-1, high=value).high
    if field == "edge":
        return schema.Binning(
            nodetype="binning",
            input="x",
            edges=[0, value, 4],
            content=[1, 2],
            flow="error",
        ).edges[1]
    if field == "multiedge":
        return schema.MultiBinning(
            nodetype="multibinning",
            inputs=["x"],
            edges=[[0, value, 4]],
            content=[1, 2],
            flow="error",
        ).edges[0][1]
    if field == "default":
        return schema.Category(
            nodetype="category", input="x", content=[], default=value
        ).default
    if field == "flow":
        return schema.Binning(
            nodetype="binning",
            input="x",
            edges=[0, 1],
            content=[1],
            flow=value,
        ).flow
    if field == "transform_rule":
        return schema.Transform(
            nodetype="transform", input="x", rule=value, content=1
        ).rule
    raise AssertionError(field)


NUMERIC_FIELDS = [
    "content",
    "formula_parameter",
    "formularef_parameter",
    "uniform_low",
    "uniform_high",
    "edge",
    "multiedge",
    "default",
    "flow",
    "transform_rule",
]


@pytest.mark.parametrize("field", NUMERIC_FIELDS)
@pytest.mark.parametrize(
    "value",
    [
        "2",
        b"2",
        True,
        np.bool_(True),
        2 + 3j,
        np.complex64(2 + 3j),
        np.complex128(2 + 3j),
    ],
)
def test_reject_nonreal_scalars(field, value):
    with pytest.raises(ValidationError):
        numeric_field(field, value)


@pytest.mark.parametrize("value", [2 + 0j, np.complex64(2), np.complex128(2)])
def test_complex_without_imaginary_part_is_not_real(value):
    with pytest.raises(ValidationError):
        correction(value)


@pytest.mark.parametrize("field", NUMERIC_FIELDS)
@pytest.mark.parametrize(
    "value",
    [2, 2.0, np.int64(2), np.float32(2), np.float64(2), Decimal("2.5"), Fraction(3, 2)],
)
def test_real_builder_scalars(field, value):
    result = numeric_field(field, value)
    assert type(result) is float
    assert result == float(value)


def integer_field(field, value):
    if field == "version":
        return correction(1, version=value).version
    if field == "index":
        return schema.FormulaRef(
            nodetype="formularef", index=value, parameters=[]
        ).index
    if field == "bins":
        return schema.UniformBinning(n=value, low=0, high=1).n
    raise AssertionError(field)


@pytest.mark.parametrize("field", ["version", "index", "bins"])
@pytest.mark.parametrize(
    "value",
    ["2", b"2", 2.0, True, np.bool_(True), np.float64(2), Decimal(2), Fraction(2)],
)
def test_reject_noninteger_metadata(field, value):
    with pytest.raises(ValidationError):
        integer_field(field, value)


@pytest.mark.parametrize("field", ["version", "index", "bins"])
@pytest.mark.parametrize("value", [2, np.int32(2), np.int64(2), np.uint64(2)])
def test_integer_builder_scalars(field, value):
    result = integer_field(field, value)
    assert type(result) is int
    assert result == 2


@pytest.mark.parametrize("value", [2.0, "2", np.float64(2), Decimal(2), Fraction(2)])
def test_schema_version_requires_integer(value):
    with pytest.raises(ValidationError):
        schema.CorrectionSet(schema_version=value, corrections=[])


@pytest.mark.parametrize("value", [2, np.int64(2)])
def test_schema_version_integer(value):
    cset = schema.CorrectionSet(schema_version=value, corrections=[])
    assert type(cset.schema_version) is int
    assert cset.schema_version == 2


def wrap_category(node, where):
    if where == "root":
        return node
    if where in {"bin", "bin_flow"}:
        return {
            "nodetype": "binning",
            "input": "b",
            "edges": [0, 1],
            "content": [node if where == "bin" else 1],
            "flow": node if where == "bin_flow" else "error",
        }
    if where in {"multibin", "multibin_flow"}:
        return {
            "nodetype": "multibinning",
            "inputs": ["b"],
            "edges": [[0, 1]],
            "content": [node if where == "multibin" else 1],
            "flow": node if where == "multibin_flow" else "error",
        }
    if where in {"category_value", "category_default"}:
        return {
            "nodetype": "category",
            "input": "outer",
            "content": [{"key": "ok", "value": node}]
            if where == "category_value"
            else [],
            "default": node if where == "category_default" else 0,
        }
    if where in {"transform_rule", "transform_content"}:
        return {
            "nodetype": "transform",
            "input": "b",
            "rule": node if where == "transform_rule" else 1,
            "content": node if where == "transform_content" else 1,
        }
    raise AssertionError(where)


@pytest.mark.parametrize(
    "where",
    [
        "root",
        "bin",
        "bin_flow",
        "multibin",
        "multibin_flow",
        "category_value",
        "category_default",
        "transform_rule",
        "transform_content",
    ],
)
@pytest.mark.parametrize(
    "input_type,key", [("int", "a"), ("string", 1), ("real", 1), ("real", "a")]
)
def test_category_keys_follow_referenced_input(where, input_type, key):
    node = {"nodetype": "category", "input": "x", "content": [{"key": key, "value": 3}]}
    with pytest.raises(ValidationError):
        correction(
            wrap_category(node, where),
            inputs=[
                {"name": "x", "type": input_type},
                {"name": "b", "type": "real"},
                {"name": "outer", "type": "string"},
            ],
        )


@pytest.mark.parametrize("default", [None, 0, 3])
def test_empty_real_category_is_not_evaluable(default):
    with pytest.raises(ValidationError):
        correction(
            {"nodetype": "category", "input": "x", "content": [], "default": default},
            inputs=[{"name": "x", "type": "real"}],
        )


@pytest.mark.parametrize("input_type,argument", [("int", 1), ("string", "a")])
@pytest.mark.parametrize("default", [None, 0, 3])
def test_empty_discrete_category(input_type, argument, default):
    corr = correction(
        {"nodetype": "category", "input": "x", "content": [], "default": default},
        inputs=[{"name": "x", "type": input_type}],
    )
    evaluator = corr.to_evaluator()
    if default is None:
        with pytest.raises(IndexError):
            evaluator.evaluate(argument)
    else:
        assert evaluator.evaluate(argument) == default


def test_preconstructed_category_still_needs_correction_context():
    node = schema.Category(
        nodetype="category", input="x", content=[{"key": "a", "value": 1}]
    )
    with pytest.raises(ValidationError):
        correction(node, inputs=[{"name": "x", "type": "int"}])


def test_reused_category_has_no_stored_input_context():
    node = schema.Category(
        nodetype="category", input="x", content=[{"key": "a", "value": 1}]
    )
    before = node.model_dump()
    assert (
        correction(node, inputs=[{"name": "x", "type": "string"}])
        .to_evaluator()
        .evaluate("a")
        == 1
    )
    with pytest.raises(ValidationError):
        correction(node, inputs=[{"name": "x", "type": "int"}])
    assert node.model_dump() == before
    assert (
        correction(node, inputs=[{"name": "x", "type": "string"}])
        .to_evaluator()
        .evaluate("a")
        == 1
    )


@pytest.mark.parametrize(
    "types,key,arguments",
    [
        (["int", "string"], 1, (1, "a")),
        (["string", "int"], "1", ("1", 1)),
    ],
)
def test_category_resolves_first_matching_input(types, key, arguments):
    corr = correction(
        {"nodetype": "category", "input": "x", "content": [{"key": key, "value": 3}]},
        inputs=[{"name": "x", "type": kind} for kind in types],
    )
    assert corr.to_evaluator().evaluate(*arguments) == 3


def test_category_does_not_use_last_duplicate_input_type():
    with pytest.raises(ValidationError):
        correction(
            {"nodetype": "category", "input": "x", "content": [{"key": 1, "value": 3}]},
            inputs=[{"name": "x", "type": "string"}, {"name": "x", "type": "int"}],
        )


def test_nested_formula_and_builder_containers():
    corr = correction(
        {
            "nodetype": "category",
            "input": "cat",
            "content": [],
            "default": {
                "nodetype": "formularef",
                "index": np.int64(0),
                "parameters": (np.float64(2), np.int64(1)),
            },
        },
        inputs=({"name": "cat", "type": "string"}, {"name": "x", "type": "real"}),
        generic_formulas=(
            {
                "nodetype": "formula",
                "expression": "[0]*x+[1]",
                "parser": "TFormula",
                "variables": ("x",),
            },
        ),
    )
    assert corr.to_evaluator().evaluate("anything", 3.0) == 7
    corr.description = "Models remain mutable for authoring."
    assert corr.description.endswith("authoring.")


@pytest.mark.parametrize("edges", [["-inf", 0, "+inf"], ["-inf", 0, "inf"]])
def test_infinity_sentinels_and_integer_edges(edges):
    corr = correction(
        {
            "nodetype": "binning",
            "input": "x",
            "edges": edges,
            "content": [1, 2],
            "flow": "error",
        },
        inputs=[{"name": "x", "type": "real"}],
    )
    assert corr.to_evaluator().evaluate(-1.0) == 1
    assert corr.to_evaluator().evaluate(1.0) == 2


def test_float_infinity_compatibility_switch(monkeypatch):
    kwargs = dict(
        nodetype="binning",
        input="x",
        edges=[float("-inf"), 0, float("inf")],
        content=[1, 2],
        flow="error",
    )
    with pytest.raises(ValidationError):
        schema.Binning(**kwargs)
    monkeypatch.setattr(schema, "IGNORE_FLOAT_INF", True)
    assert schema.Binning(**kwargs).edges[0] == float("-inf")


def test_uniform_invalid_low_is_validation_error():
    with pytest.raises(ValidationError):
        schema.UniformBinning(n=1, low="0", high=1)


def test_histogram_builder_uses_numpy_values_and_edges():
    class Axis(list):
        name = "x"
        label = "x"

    class Histogram:
        name = "histogram"
        label = "out"
        axes = [Axis([(np.float64(0), np.float64(1)), (np.float64(1), np.float64(2))])]

        def values(self):
            return np.array([3, 4], dtype=np.int64)

    corr = convert.from_histogram(Histogram())
    assert corr.to_evaluator().evaluate(0.5) == 3
    assert corr.to_evaluator().evaluate(1.5) == 4


@pytest.mark.parametrize(
    "data",
    [
        "3.0",
        True,
        {"nodetype": "category", "input": "x", "content": [{"key": "a", "value": 3}]},
    ],
)
def test_json_and_cli_reject_original_mismatches(tmp_path, data):
    payload = {
        "schema_version": 2,
        "corrections": [
            {
                "name": "test",
                "version": 1,
                "inputs": [{"name": "x", "type": "int"}],
                "output": {"name": "out", "type": "real"},
                "data": data,
            }
        ],
    }
    text = json.dumps(payload)
    with pytest.raises(ValidationError):
        schema.CorrectionSet.model_validate_json(text)
    with pytest.raises(ValidationError):
        model_auto(text)
    with pytest.raises(RuntimeError):
        CorrectionSet.from_string(text)
    filename = tmp_path / "bad.json"
    filename.write_text(text)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "correctionlib.cli",
            "validate",
            "--quiet",
            str(filename),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr


@pytest.mark.parametrize("data", [3, 3.0])
def test_json_and_cli_accept_numeric_content(tmp_path, data):
    text = json.dumps(
        {
            "schema_version": 2,
            "corrections": [
                {
                    "name": "test",
                    "version": 1,
                    "inputs": [],
                    "output": {"name": "out", "type": "real"},
                    "data": data,
                }
            ],
        }
    )
    cset = schema.CorrectionSet.model_validate_json(text)
    assert cset.to_evaluator()["test"].evaluate() == 3
    assert CorrectionSet.from_string(text)["test"].evaluate() == 3
    filename = tmp_path / "valid.json"
    filename.write_text(text)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "correctionlib.cli",
            "validate",
            "--quiet",
            str(filename),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_schema1_validation_is_unchanged(tmp_path):
    payload = {
        "schema_version": 1,
        "corrections": [
            {
                "name": "one",
                "version": 1,
                "inputs": [],
                "output": {"name": "out", "type": "real"},
                "data": 1,
            }
        ],
    }
    text = json.dumps(payload)
    assert isinstance(model_auto(text), schemav1.CorrectionSet)
    filename = tmp_path / "schema1.json"
    filename.write_text(text)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "correctionlib.cli",
            "validate",
            "--quiet",
            str(filename),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
