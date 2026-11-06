import io
import json
import subprocess

import pytest
from pydantic import ValidationError
from rich.console import Console

import correctionlib
from correctionlib import schemav2 as model


def make_cset(uncertainty_sets=None, prefix=""):
    data = {
        "schema_version": 2,
        "corrections": [
            {
                "name": f"{prefix}btag",
                "version": 1,
                "inputs": [
                    {"name": "working_point", "type": "string"},
                    {"name": "systematic", "type": "string"},
                    {"name": "pt", "type": "real"},
                ],
                "output": {"name": "sf", "type": "real"},
                "data": {
                    "nodetype": "category",
                    "input": "systematic",
                    "content": [
                        {"key": "central", "value": 1.0},
                        {"key": "up_correlated", "value": 1.1},
                        {"key": "down_correlated", "value": 0.9},
                        {"key": "up_uncorrelated", "value": 1.2},
                        {"key": "down_uncorrelated", "value": 0.8},
                    ],
                },
            },
            {
                "name": f"{prefix}jes",
                "version": 1,
                "inputs": [
                    {"name": "eta", "type": "real"},
                    {"name": "run", "type": "int"},
                ],
                "output": {"name": "unc", "type": "real"},
                "data": 0.02,
            },
        ],
        "compound_corrections": [
            {
                "name": f"{prefix}stack",
                "inputs": [
                    {"name": "eta", "type": "real"},
                    {"name": "run", "type": "int"},
                ],
                "output": {"name": "unc", "type": "real"},
                "inputs_update": [],
                "input_op": "*",
                "output_op": "*",
                "stack": [f"{prefix}jes"],
            }
        ],
    }
    if uncertainty_sets is not None:
        data["uncertainty_sets"] = uncertainty_sets
    return data


def btag_set(name="btagDDBvLV2_L_comb", prefix=""):
    return {
        "name": name,
        "uncertainties": [
            {
                "nuisance_name": "CMS_Xbbtag_comb_correlated",
                "correction": f"{prefix}btag",
                "inputs": [
                    {"name": "working_point", "value": "L"},
                    {"name": "systematic", "value": "up_correlated"},
                ],
                "direction": "up",
                "operation": "replace",
            },
            {
                "nuisance_name": "CMS_Xbbtag_comb_correlated",
                "correction": f"{prefix}btag",
                "inputs": [
                    {"name": "working_point", "value": "L"},
                    {"name": "systematic", "value": "down_correlated"},
                ],
                "direction": "down",
                "operation": "replace",
            },
            {
                "nuisance_name": "CMS_Xbbtag_comb_uncorrelated_2016postVFP",
                "correction": f"{prefix}btag",
                "inputs": [
                    {"name": "working_point", "value": "L"},
                    {"name": "systematic", "value": "up_uncorrelated"},
                ],
            },
        ],
    }


def jes_set(prefix=""):
    return {
        "name": "JESFull_AK4PFchs",
        "description": "Full set of JES uncertainty sources",
        "uncertainties": [
            {
                "nuisance_name": "CMS_scale_j_AbsoluteScale",
                "correction": f"{prefix}jes",
                "inputs": [],
                "operation": "relative",
            },
            {
                "nuisance_name": "CMS_scale_j_Stack",
                "correction": f"{prefix}stack",
                "inputs": [
                    {"name": "eta", "value": 1},
                    {"name": "run", "value": 1},
                ],
            },
        ],
    }


def test_uncertainty_set_roundtrip():
    cset = model.CorrectionSet.model_validate(make_cset([btag_set(), jes_set()]))
    assert [uset.name for uset in cset.uncertainty_sets] == [
        "btagDDBvLV2_L_comb",
        "JESFull_AK4PFchs",
    ]
    frozen = cset.uncertainty_sets[1].uncertainties[1].inputs
    assert isinstance(frozen[0].value, int)
    assert isinstance(cset.uncertainty_sets[0].uncertainties[0].inputs[0].value, str)
    specs = [spec for uset in cset.uncertainty_sets for spec in uset.uncertainties]
    assert [spec.operation for spec in specs] == [
        "replace",
        "replace",
        None,
        "relative",
        None,
    ]
    assert [spec.direction for spec in specs] == ["up", "down", None, None, None]

    cset2 = model.CorrectionSet.model_validate_json(cset.model_dump_json())
    assert cset2 == cset

    # files without uncertainty sets are serialized as before
    plain = model.CorrectionSet.model_validate(make_cset())
    assert plain.uncertainty_sets is None
    assert "uncertainty_sets" not in plain.model_dump()
    assert "uncertainty_sets" not in json.loads(plain.model_dump_json())
    assert "uncertainty_sets" not in plain.model_dump(exclude_unset=True)


def test_uncertainty_set_empty():
    cset = model.CorrectionSet.model_validate(make_cset([]))
    assert cset.uncertainty_sets == []
    assert json.loads(cset.model_dump_json())["uncertainty_sets"] == []
    cset = model.CorrectionSet.model_validate(
        make_cset([{"name": "a", "uncertainties": []}])
    )
    assert cset.uncertainty_sets[0].uncertainties == []


def test_uncertainty_set_evaluation_unaffected():
    plain = correctionlib.CorrectionSet.from_string(json.dumps(make_cset()))
    cset = model.CorrectionSet.model_validate(make_cset([btag_set(), jes_set()]))
    for evaluator in (
        correctionlib.CorrectionSet(cset),
        correctionlib.CorrectionSet.from_string(cset.model_dump_json()),
    ):
        assert set(evaluator) == set(plain)
        assert set(evaluator.compound) == set(plain.compound)
        for args in [("L", "central", 30.0), ("L", "up_correlated", 30.0)]:
            assert evaluator["btag"].evaluate(*args) == plain["btag"].evaluate(*args)
        assert evaluator.compound["stack"].evaluate(1.0, 1) == 0.02


@pytest.mark.parametrize(
    "uncertainty_sets",
    [
        # unknown correction
        [
            {
                "name": "a",
                "uncertainties": [
                    {"nuisance_name": "n", "correction": "nope", "inputs": []}
                ],
            }
        ],
        # unknown input
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "btag",
                        "inputs": [{"name": "nope", "value": "L"}],
                    }
                ],
            }
        ],
        # input frozen twice
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "btag",
                        "inputs": [
                            {"name": "working_point", "value": "L"},
                            {"name": "working_point", "value": "M"},
                        ],
                    }
                ],
            }
        ],
        # wrong value type for a string input
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "btag",
                        "inputs": [{"name": "working_point", "value": 1}],
                    }
                ],
            }
        ],
        # wrong value type for an int input
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [{"name": "run", "value": 1.5}],
                    }
                ],
            }
        ],
        # wrong value type for a real input
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [{"name": "eta", "value": "1.5"}],
                    }
                ],
            }
        ],
        # bool value
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [{"name": "eta", "value": True}],
                    }
                ],
            }
        ],
        # non-finite value
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [{"name": "eta", "value": float("nan")}],
                    }
                ],
            }
        ],
        # duplicate set names
        [btag_set(), btag_set()],
        # duplicate nuisance names
        [
            {
                "name": "a",
                "uncertainties": [
                    {"nuisance_name": "n", "correction": "jes", "inputs": []},
                    {"nuisance_name": "n", "correction": "btag", "inputs": []},
                ],
            }
        ],
        # duplicate (nuisance name, direction)
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [],
                        "direction": "up",
                    },
                    {
                        "nuisance_name": "n",
                        "correction": "btag",
                        "inputs": [],
                        "direction": "up",
                    },
                ],
            }
        ],
        # mixing entries with and without a direction for one nuisance
        [
            {
                "name": "a",
                "uncertainties": [
                    {"nuisance_name": "n", "correction": "jes", "inputs": []},
                    {
                        "nuisance_name": "n",
                        "correction": "btag",
                        "inputs": [],
                        "direction": "down",
                    },
                ],
            }
        ],
        # unknown direction
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [],
                        "direction": "sideways",
                    }
                ],
            }
        ],
        # unknown operation
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [],
                        "operation": "add",
                    }
                ],
            }
        ],
        # extra field
        [
            {
                "name": "a",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "jes",
                        "inputs": [],
                        "variation": "up",
                    }
                ],
            }
        ],
    ],
)
def test_uncertainty_set_invalid(uncertainty_sets):
    with pytest.raises(ValidationError):
        model.CorrectionSet.model_validate(make_cset(uncertainty_sets))


def test_uncertainty_set_ambiguous_correction():
    data = make_cset(
        [
            {
                "name": "a",
                "uncertainties": [
                    {"nuisance_name": "n", "correction": "jes", "inputs": []}
                ],
            }
        ]
    )
    data["compound_corrections"][0]["name"] = "jes"
    with pytest.raises(ValidationError, match="ambiguous"):
        model.CorrectionSet.model_validate(data)
    # the clash itself is allowed if no uncertainty source references it
    del data["uncertainty_sets"]
    model.CorrectionSet.model_validate(data)


def test_uncertainty_set_summary():
    cset = model.CorrectionSet.model_validate(make_cset([btag_set(), jes_set()]))
    console = Console(file=io.StringIO(), width=200)
    console.print(cset)
    out = console.file.getvalue()
    assert "btagDDBvLV2_L_comb" in out
    assert "CMS_Xbbtag_comb_uncorrelated_2016postVFP" in out
    assert "CMS_Xbbtag_comb_correlated [down]" in out
    assert "(relative)" in out
    assert "Full set of JES uncertainty sources" in out


def test_uncertainty_set_merge(tmp_path):
    file1 = tmp_path / "btag.json"
    file1.write_text(json.dumps(make_cset([btag_set(prefix="a_")], prefix="a_")))
    file2 = tmp_path / "jes.json"
    file2.write_text(json.dumps(make_cset([jes_set(prefix="b_")], prefix="b_")))
    file3 = tmp_path / "btag_dupe.json"
    file3.write_text(json.dumps(make_cset([btag_set(prefix="c_")], prefix="c_")))

    ret = subprocess.run(
        ["correction", "merge", str(file1), str(file2)],
        capture_output=True,
        check=True,
    )
    merged = model.CorrectionSet.model_validate_json(ret.stdout)
    assert [uset.name for uset in merged.uncertainty_sets] == [
        "btagDDBvLV2_L_comb",
        "JESFull_AK4PFchs",
    ]

    ret = subprocess.run(
        ["correction", "merge", str(file1), str(file3)],
        capture_output=True,
    )
    assert ret.returncode == 1

    # pretty format goes through JSONEncoder
    ret = subprocess.run(
        ["correction", "merge", "-f", "pretty", str(file1), str(file2)],
        capture_output=True,
        check=True,
    )
    assert model.CorrectionSet.model_validate_json(ret.stdout) == merged


def test_uncertainty_set_merge_without_sets(tmp_path):
    file1 = tmp_path / "plain1.json"
    file1.write_text(json.dumps(make_cset(prefix="a_")))
    file2 = tmp_path / "plain2.json"
    file2.write_text(json.dumps(make_cset(prefix="b_")))
    file3 = tmp_path / "btag.json"
    file3.write_text(json.dumps(make_cset([btag_set(prefix="c_")], prefix="c_")))

    # older correctionlib versions reject the key, so it must not appear at all
    for fmt in ("compact", "indented", "pretty"):
        ret = subprocess.run(
            ["correction", "merge", "-f", fmt, str(file1), str(file2)],
            capture_output=True,
            check=True,
        )
        assert "uncertainty_sets" not in json.loads(ret.stdout)

    # sets from a later file are kept when the first file has none
    ret = subprocess.run(
        ["correction", "merge", str(file1), str(file3)],
        capture_output=True,
        check=True,
    )
    merged = model.CorrectionSet.model_validate_json(ret.stdout)
    assert [uset.name for uset in merged.uncertainty_sets] == ["btagDDBvLV2_L_comb"]


def test_uncertainty_set_validate_cli(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_cset([btag_set(), jes_set()])))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(make_cset([btag_set(prefix="nope_")])))

    ret = subprocess.run(["correction", "validate", str(good)], capture_output=True)
    assert ret.returncode == 0
    ret = subprocess.run(["correction", "validate", str(bad)], capture_output=True)
    assert ret.returncode == 1


def flavor_cset(uncertainties, pt_low=20.0):
    """A btag-like correction: flavor -> systematic -> pt binning (flow=error)"""
    pt = {
        "nodetype": "binning",
        "input": "pt",
        "edges": [pt_low, 100.0, 1000.0],
        "content": [1.0, 1.0],
        "flow": "error",
    }
    systs = {
        0: ["central", "up_light", "down_light"],
        4: ["central", "up_as", "down_as"],
        5: ["central", "up_as", "down_as"],
    }
    return {
        "schema_version": 2,
        "corrections": [
            {
                "name": "btag",
                "version": 1,
                "inputs": [
                    {"name": "flavor", "type": "int"},
                    {"name": "systematic", "type": "string"},
                    {"name": "pt", "type": "real"},
                ],
                "output": {"name": "sf", "type": "real"},
                "data": {
                    "nodetype": "category",
                    "input": "flavor",
                    "content": [
                        {
                            "key": flavor,
                            "value": {
                                "nodetype": "category",
                                "input": "systematic",
                                "content": [{"key": s, "value": pt} for s in syst],
                            },
                        }
                        for flavor, syst in systs.items()
                    ],
                },
            }
        ],
        "uncertainty_sets": [{"name": "btag_bc", "uncertainties": uncertainties}],
    }


def bc_spec(flavor, systematic, direction=None):
    spec = {
        "nuisance_name": "CMS_btag_bc_as",
        "correction": "btag",
        "inputs": [
            {"name": "flavor", "value": flavor},
            {"name": "systematic", "value": systematic},
        ],
    }
    if direction is not None:
        spec["direction"] = direction
    return spec


def test_uncertainty_set_shared_nuisance():
    # one correlated nuisance spread over several frozen flavors
    model.CorrectionSet.model_validate(
        flavor_cset(
            [
                bc_spec(4, "up_as", "up"),
                bc_spec(5, "up_as", "up"),
                bc_spec(4, "down_as", "down"),
                bc_spec(5, "down_as", "down"),
            ]
        )
    )
    # flavor 5 has no down variation
    with pytest.raises(ValidationError, match="as many 'up' as 'down'"):
        model.CorrectionSet.model_validate(
            flavor_cset(
                [
                    bc_spec(4, "up_as", "up"),
                    bc_spec(5, "up_as", "up"),
                    bc_spec(4, "down_as", "down"),
                ]
            )
        )


@pytest.mark.parametrize(
    "spec",
    [
        bc_spec(6, "up_as"),  # flavor not in the correction
        bc_spec(4, "up_typo"),  # systematic not in the correction
        bc_spec(0, "up_as"),  # systematic only exists for other flavors
    ],
)
def test_uncertainty_set_frozen_value_unknown(spec):
    with pytest.raises(ValidationError, match="do not match any category"):
        model.CorrectionSet.model_validate(flavor_cset([spec]))


def test_uncertainty_set_free_inputs_not_evaluated():
    # pt is free and the binning starts at 20 with flow=error: still valid
    model.CorrectionSet.model_validate(flavor_cset([bc_spec(4, "up_as")]))
    # flavor is free: valid as long as some flavor has the systematic
    model.CorrectionSet.model_validate(
        flavor_cset(
            [
                {
                    "nuisance_name": "n",
                    "correction": "btag",
                    "inputs": [{"name": "systematic", "value": "up_light"}],
                }
            ]
        )
    )


BC_SPECS = [
    bc_spec(4, "up_as", "up"),
    bc_spec(5, "up_as", "up"),
    bc_spec(4, "down_as", "down"),
    bc_spec(5, "down_as", "down"),
]


def light_spec(systematic, direction):
    return {
        "nuisance_name": "CMS_btag_light",
        "correction": "btag",
        "inputs": [{"name": "systematic", "value": systematic}],
        "direction": direction,
    }


def test_uncertainty_set_uncovered_inputs():
    cset = model.CorrectionSet.model_validate(flavor_cset(BC_SPECS))
    assert cset.uncovered_uncertainty_inputs() == [
        ("btag", {"flavor": 0, "systematic": "down_light"}),
        ("btag", {"flavor": 0, "systematic": "up_light"}),
    ]
    # nominal values are reported only on request
    assert cset.uncovered_uncertainty_inputs(nominal_keys=()) == [
        ("btag", {"flavor": 0, "systematic": "central"}),
        ("btag", {"flavor": 0, "systematic": "down_light"}),
        ("btag", {"flavor": 0, "systematic": "up_light"}),
        ("btag", {"flavor": 4, "systematic": "central"}),
        ("btag", {"flavor": 5, "systematic": "central"}),
    ]
    # a source freezing only systematic covers it for every flavor
    cset = model.CorrectionSet.model_validate(
        flavor_cset(
            [*BC_SPECS, light_spec("up_light", "up"), light_spec("down_light", "down")]
        )
    )
    assert cset.uncovered_uncertainty_inputs() == []


def test_uncertainty_set_uncovered_inputs_mixed_sets():
    cset = model.CorrectionSet.model_validate(make_cset([btag_set(), jes_set()]))
    # working_point is frozen but never branched on; jes and stack have no categories
    assert cset.uncovered_uncertainty_inputs() == [
        ("btag", {"systematic": "down_uncorrelated"}),
    ]
    # coverage is pooled over all uncertainty sets
    other = {
        "name": "other",
        "uncertainties": [
            {
                "nuisance_name": "n",
                "correction": "btag",
                "inputs": [{"name": "systematic", "value": "down_uncorrelated"}],
            }
        ],
    }
    cset = model.CorrectionSet.model_validate(make_cset([btag_set(), jes_set(), other]))
    assert cset.uncovered_uncertainty_inputs() == []
    assert (
        model.CorrectionSet.model_validate(make_cset()).uncovered_uncertainty_inputs()
        == []
    )


def test_uncertainty_set_uncovered_inputs_default_and_transform():
    data = make_cset(
        [
            {
                "name": "s",
                "uncertainties": [
                    {
                        "nuisance_name": "n",
                        "correction": "btag",
                        "inputs": [{"name": "systematic", "value": "up"}],
                    }
                ],
            }
        ]
    )
    data["corrections"][0]["data"] = {
        "nodetype": "transform",
        "input": "working_point",
        "rule": 1.0,
        "content": {
            "nodetype": "category",
            "input": "systematic",
            "content": [
                {"key": "up", "value": 1.1},
                {"key": "down", "value": 0.9},
            ],
            "default": {
                "nodetype": "category",
                "input": "systematic",
                "content": [{"key": "hidden", "value": 1.0}],
            },
        },
    }
    cset = model.CorrectionSet.model_validate(data)
    # the default branch assigns no key, but the categories below it are listed
    assert cset.uncovered_uncertainty_inputs() == [
        ("btag", {"systematic": "down"}),
        ("btag", {"systematic": "hidden"}),
    ]


def test_uncertainty_set_uncovered_inputs_flavor_default():
    # light flavour as the default of the flavor category, as in BTV files
    data = flavor_cset(BC_SPECS)
    flavor = data["corrections"][0]["data"]
    flavor["default"] = flavor["content"].pop(0)["value"]
    cset = model.CorrectionSet.model_validate(data)
    assert cset.uncovered_uncertainty_inputs() == [
        ("btag", {"systematic": "down_light"}),
        ("btag", {"systematic": "up_light"}),
    ]
    # a bare string is one nominal key, not a collection of characters
    assert cset.uncovered_uncertainty_inputs(nominal_keys="central") == [
        ("btag", {"systematic": "down_light"}),
        ("btag", {"systematic": "up_light"}),
    ]


def test_uncertainty_set_uncovered_inputs_compound():
    data = flavor_cset(BC_SPECS)
    btag = data["corrections"][0]
    data["compound_corrections"] = [
        {
            "name": "btag_stack",
            "inputs": btag["inputs"],
            "output": btag["output"],
            "inputs_update": [],
            "input_op": "*",
            "output_op": "*",
            "stack": ["btag"],
        }
    ]
    light = [light_spec("up_light", "up"), light_spec("down_light", "down")]
    for spec in light:
        spec["correction"] = "btag_stack"
    data["uncertainty_sets"].append({"name": "light", "uncertainties": light})
    cset = model.CorrectionSet.model_validate(data)
    # sources on the compound correction cover its components, and vice versa
    assert cset.uncovered_uncertainty_inputs() == []
    # without the b/c sources, flavor is no longer frozen and so not an axis
    data["uncertainty_sets"].pop(0)
    cset = model.CorrectionSet.model_validate(data)
    assert cset.uncovered_uncertainty_inputs() == [
        ("btag", {"systematic": "down_as"}),
        ("btag", {"systematic": "up_as"}),
    ]


def test_uncertainty_set_uncovered_inputs_cli(tmp_path):
    path = tmp_path / "btag.json"
    path.write_text(json.dumps(flavor_cset(BC_SPECS)))

    ret = subprocess.run(["correction", "validate", str(path)], capture_output=True)
    assert ret.returncode == 0
    lines = [line for line in ret.stdout.decode().splitlines() if "Warning" in line]
    assert len(lines) == 2
    assert "flavor=0, systematic='up_light'" in lines[1]

    ret = subprocess.run(
        ["correction", "validate", "--nominal-keys", "", str(path)],
        capture_output=True,
    )
    assert ret.returncode == 0
    assert ret.stdout.decode().count("Warning") == 5

    ret = subprocess.run(
        ["correction", "validate", "--quiet", str(path)], capture_output=True
    )
    assert ret.returncode == 0
    assert ret.stdout == b""
