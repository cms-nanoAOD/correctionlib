import pytest

import correctionlib
from correctionlib import schemav2 as model


def test_highlevel():
    cset = correctionlib.CorrectionSet(
        model.CorrectionSet(
            schema_version=model.VERSION,
            corrections=[
                model.Correction(
                    name="test corr",
                    version=2,
                    inputs=[],
                    output=model.Variable(name="a scale", type="real"),
                    data=1.234,
                )
            ],
        )
    )
    assert set(cset) == {"test corr"}
    sf = cset["test corr"]
    assert sf.version == 2
    assert sf.description == ""

    with pytest.raises(RuntimeError):
        sf.evaluate(0, 1.2, 35.0, 0.01)

    assert sf.evaluate() == 1.234
