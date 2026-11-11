import gzip
import json
import subprocess
import sys

import pytest

import correctionlib
from correctionlib import schemav1, schemav2


@pytest.fixture
def correction_set():
    inputs = [{"name": "x", "type": "real"}]
    output = {"name": "weight", "type": "real"}
    return {
        "schema_version": 2,
        "$schema": "https://example.org/custom-corrections.schema.json",
        "description": "A correction set with dependent recipes",
        "corrections": [
            {
                "name": "unused",
                "version": 1,
                "inputs": [],
                "output": output,
                "data": 99.0,
            },
            {
                "name": "offset",
                "description": "Add one",
                "version": 3,
                "inputs": inputs,
                "output": output,
                "data": {
                    "nodetype": "formula",
                    "expression": "x+1",
                    "parser": "TFormula",
                    "variables": ["x"],
                },
            },
            {
                "name": "scale",
                "version": 2,
                "inputs": inputs,
                "output": output,
                "generic_formulas": [
                    {
                        "nodetype": "formula",
                        "expression": "x+999",
                        "parser": "TFormula",
                        "variables": ["x"],
                    },
                    {
                        "nodetype": "formula",
                        "expression": "[0]*x",
                        "parser": "TFormula",
                        "variables": ["x"],
                    },
                ],
                "data": {"nodetype": "formularef", "index": 1, "parameters": [2.0]},
            },
        ],
        "compound_corrections": [
            {
                "name": "unused_recipe",
                "inputs": [],
                "output": output,
                "inputs_update": [],
                "input_op": "*",
                "output_op": "last",
                "stack": ["unused"],
            },
            {
                "name": "sum",
                "inputs": inputs,
                "output": output,
                "inputs_update": [],
                "input_op": "*",
                "output_op": "+",
                "stack": ["scale", "offset"],
            },
            {
                "name": "pipeline",
                "description": "Update x between repeated components",
                "inputs": inputs,
                "output": output,
                "inputs_update": ["x"],
                "input_op": "*",
                "output_op": "last",
                "stack": ["offset", "scale", "offset"],
            },
        ],
    }


def run_filter(tmp_path, payload, *args, compressed=False):
    filename = tmp_path / ("corrections.json.gz" if compressed else "corrections.json")
    opener = gzip.open if compressed else open
    with opener(filename, "wt") as fout:
        json.dump(payload, fout)
    original = filename.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "correctionlib.cli", "filter", str(filename), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert filename.read_bytes() == original
    return result


@pytest.mark.parametrize("compressed", [False, True], ids=["json", "gzip"])
@pytest.mark.parametrize("output_format", ["compact", "indented", "pretty"])
def test_filter_preserves_whole_corrections(
    tmp_path, correction_set, compressed, output_format
):
    """Keep complete objects and metadata in file order without changing their evaluations."""
    original = correctionlib.CorrectionSet.from_string(json.dumps(correction_set))
    assert original["scale"].evaluate(2.0) == 4.0
    assert original["offset"].evaluate(2.0) == 3.0
    assert original.compound["sum"].evaluate(2.0) == 7.0
    assert original.compound["pipeline"].evaluate(2.0) == 73.0

    result = run_filter(
        tmp_path,
        correction_set,
        "--keep",
        "pipeline",
        "--keep",
        "scale",
        "--keep",
        "sum",
        "--keep",
        "offset",
        "--keep",
        "scale",
        "-f",
        output_format,
        compressed=compressed,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    raw = json.loads(result.stdout)
    assert raw["$schema"] == correction_set["$schema"]
    assert "schema_url" not in raw
    assert raw["description"] == correction_set["description"]
    selected = schemav2.CorrectionSet.model_validate_json(result.stdout)
    source = schemav2.CorrectionSet.model_validate(correction_set)
    assert selected.corrections == source.corrections[1:]
    assert selected.compound_corrections == source.compound_corrections[1:]
    if output_format == "compact":
        assert "\n" not in result.stdout
    else:
        assert result.stdout.endswith("\n")
        indent = "    " if output_format == "indented" else "  "
        assert f'\n{indent}"schema_version": 2,' in result.stdout

    evaluator = correctionlib.CorrectionSet.from_string(result.stdout)
    assert list(evaluator) == ["offset", "scale"]
    assert [evaluator["scale"].evaluate(x) for x in (0.0, 2.0, 3.0)] == [0.0, 4.0, 6.0]
    assert [evaluator["offset"].evaluate(x) for x in (0.0, 2.0, 3.0)] == [1.0, 3.0, 4.0]
    assert [evaluator.compound["sum"].evaluate(x) for x in (0.0, 2.0, 3.0)] == [
        1.0,
        7.0,
        10.0,
    ]
    assert [evaluator.compound["pipeline"].evaluate(x) for x in (0.0, 2.0, 3.0)] == [
        1.0,
        73.0,
        289.0,
    ]


@pytest.mark.parametrize("unknown", ["missing", "sc*", "scale:x=1"])
def test_filter_rejects_unknown_names(tmp_path, correction_set, unknown):
    """A misspelled name or unsupported selector must not silently produce a subset."""
    result = run_filter(tmp_path, correction_set, "--keep", "scale", "--keep", unknown)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "Unknown" in result.stderr
    assert unknown in result.stderr


@pytest.mark.parametrize(
    "missing_from_source", [False, True], ids=["omitted", "missing"]
)
def test_filter_rejects_incomplete_compound(
    tmp_path, correction_set, missing_from_source
):
    """A retained compound needs all ordinary constituents explicitly selected."""
    if missing_from_source:
        correction_set["corrections"].pop()
        schemav2.CorrectionSet.model_validate(correction_set)
        with pytest.raises(RuntimeError, match="scale.*not found"):
            correctionlib.CorrectionSet.from_string(json.dumps(correction_set))
    result = run_filter(
        tmp_path, correction_set, "--keep", "pipeline", "--keep", "offset"
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "pipeline" in result.stderr
    assert "scale" in result.stderr


def test_filter_ignores_unselected_broken_compound(tmp_path, correction_set):
    """Discarded recipes must not prevent keeping an independent ordinary correction."""
    correction_set["compound_corrections"][0]["stack"] = ["absent"]
    with pytest.raises(RuntimeError, match="absent.*not found"):
        correctionlib.CorrectionSet.from_string(json.dumps(correction_set))
    result = run_filter(tmp_path, correction_set, "--keep", "scale")
    assert result.returncode == 0, result.stderr
    assert "\n" not in result.stdout
    selected = schemav2.CorrectionSet.model_validate_json(result.stdout)
    assert [corr.name for corr in selected.corrections] == ["scale"]
    assert selected.compound_corrections == []
    assert (
        correctionlib.CorrectionSet.from_string(result.stdout)["scale"].evaluate(2.0)
        == 4.0
    )


def test_filter_keeps_both_namespaces(tmp_path, correction_set):
    """A legal name shared by ordinary and compound corrections selects both objects."""
    correction_set["corrections"][1]["name"] = "shared"
    compound = correction_set["compound_corrections"][1]
    compound["name"] = "shared"
    compound["stack"] = ["scale", "shared"]
    result = run_filter(tmp_path, correction_set, "--keep", "shared", "--keep", "scale")
    assert result.returncode == 0, result.stderr
    selected = schemav2.CorrectionSet.model_validate_json(result.stdout)
    assert [corr.name for corr in selected.corrections] == ["shared", "scale"]
    assert [corr.name for corr in selected.compound_corrections] == ["shared"]
    evaluator = correctionlib.CorrectionSet.from_string(result.stdout)
    assert evaluator["shared"].evaluate(2.0) == 3.0
    assert evaluator.compound["shared"].evaluate(2.0) == 7.0


def test_filter_compound_name_does_not_satisfy_stack(tmp_path, correction_set):
    """Stack entries resolve only to ordinary corrections, even if a compound name matches."""
    correction_set["compound_corrections"][1]["name"] = "ghost"
    correction_set["compound_corrections"][2]["stack"] = ["ghost"]
    result = run_filter(
        tmp_path,
        correction_set,
        "--keep",
        "ghost",
        "--keep",
        "pipeline",
        "--keep",
        "scale",
        "--keep",
        "offset",
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "pipeline" in result.stderr
    assert "ghost" in result.stderr


@pytest.mark.parametrize("name", ["scale*", "path:name=1"])
def test_filter_names_are_literal(tmp_path, correction_set, name):
    """Punctuation is part of a correction name, not a pattern or a key selector."""
    correction_set["corrections"].append(
        {
            "name": name,
            "version": 1,
            "inputs": [],
            "output": {"name": "weight", "type": "real"},
            "data": 5.0,
        }
    )
    result = run_filter(tmp_path, correction_set, "--keep", name)
    assert result.returncode == 0, result.stderr
    evaluator = correctionlib.CorrectionSet.from_string(result.stdout)
    assert list(evaluator) == [name]
    assert evaluator[name].evaluate() == 5.0


def test_filter_requires_selection(tmp_path, correction_set):
    result = run_filter(tmp_path, correction_set)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "--keep" in result.stderr


@pytest.mark.parametrize("compressed", [False, True], ids=["json", "gzip"])
@pytest.mark.parametrize("output_format", ["compact", "indented", "pretty"])
def test_filter_schema_one(tmp_path, compressed, output_format):
    """Filtering remains available for schema1 files without invoking a schema2 evaluator."""
    source = {
        "schema_version": 1,
        "corrections": [
            {
                "name": name,
                "description": "Keep correction metadata",
                "version": 1,
                "inputs": [],
                "output": {"name": "weight", "type": "real"},
                "data": value,
            }
            for name, value in [("discard", 8.0), ("retain", 3.0)]
        ],
    }
    result = run_filter(
        tmp_path,
        source,
        "--keep",
        "retain",
        "--keep",
        "retain",
        "--format",
        output_format,
        compressed=compressed,
    )
    assert result.returncode == 0, result.stderr
    selected = schemav1.CorrectionSet.model_validate_json(result.stdout)
    original = schemav1.CorrectionSet.model_validate(source)
    assert selected.schema_version == 1
    assert selected.corrections == original.corrections[1:]
    assert "compound_corrections" not in json.loads(result.stdout)


@pytest.mark.parametrize("compound_field", ["absent", "null", "empty"])
@pytest.mark.parametrize("output_format", ["compact", "indented", "pretty"])
def test_filter_preserves_optional_compound_field(
    tmp_path, correction_set, compound_field, output_format
):
    """Preserve explicit null/empty metadata and the existing formats' unset-field conventions."""
    if compound_field == "absent":
        del correction_set["compound_corrections"]
    else:
        correction_set["compound_corrections"] = (
            None if compound_field == "null" else []
        )
    result = run_filter(
        tmp_path, correction_set, "--keep", "scale", "--format", output_format
    )
    assert result.returncode == 0, result.stderr
    raw = json.loads(result.stdout)
    if compound_field == "absent" and output_format == "pretty":
        assert "compound_corrections" not in raw
    else:
        assert raw["compound_corrections"] == (
            [] if compound_field == "empty" else None
        )
    schemav2.CorrectionSet.model_validate_json(result.stdout)
    evaluator = correctionlib.CorrectionSet.from_string(result.stdout)
    assert evaluator["scale"].evaluate(2.0) == 4.0
