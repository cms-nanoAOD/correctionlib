import pytest

import correctionlib
import correctionlib.schemav2


def _make_hashprng_cset(distribution: str):
    cset = correctionlib.schemav2.CorrectionSet.model_validate(
        {
            "schema_version": 2,
            "corrections": [
                {
                    "name": "prng",
                    "version": 1,
                    "inputs": [
                        {"name": "var1", "type": "real"},
                        {"name": "var2", "type": "real"},
                        {"name": "var3", "type": "int"},
                    ],
                    "output": {"name": "rand", "type": "real"},
                    "data": {
                        "nodetype": "hashprng",
                        "inputs": ["var1", "var2", "var3"],
                        "distribution": distribution,
                    },
                },
            ],
        }
    )
    return cset.to_evaluator()["prng"]


def test_hashprng():
    corr = _make_hashprng_cset("normal")
    assert corr.evaluate(1.2, 2.3, 5) == -1.263776278956304

    corr = _make_hashprng_cset("stdflat")
    assert corr.evaluate(1.2, 2.3, 5) == 0.5312947726732237

    with pytest.warns(DeprecationWarning):
        corr = _make_hashprng_cset("stdnormal")

    # we already see two implementations of stdnormal in the CI (the latter on ubuntu)
    assert corr.evaluate(1.2, 2.3, 5) in (0.5320038585132821, 2.227655564267796)
