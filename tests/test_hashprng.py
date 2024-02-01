import correctionlib
import correctionlib.schemav2


def test_hashprng():
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
                        "distribution": "normal",
                    },
                },
            ],
        }
    )
    cset = cset.to_evaluator()
    corr = cset["prng"]
    assert corr.evaluate(1.2, 2.3, 5) == -1.263776278956304
