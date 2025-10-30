import numpy as np
import pytest

from correctionlib.schemav2 import Correction, HashPRNG, Variable


def test_issue_298():
    corr = Correction(
        name="test",
        version=1,
        inputs=[
            Variable(name="x", type="int"),
        ],
        output=Variable(name="out", type="real"),
        data=HashPRNG(nodetype="hashprng", inputs=["x"], distribution="normal"),
    ).to_evaluator()

    a = corr.evaluate(np.array([2**30 + 42], dtype=np.int32))
    b = corr.evaluate(2**30 + 42)
    assert a == b

    a = corr.evaluate(np.array([2**34 + 42], dtype=np.int64))
    b = corr.evaluate(2**34 + 42)
    assert a == b

    corr.evaluate(2**63 - 1)

    with pytest.raises(RuntimeError, match="Unable to cast Python instance"):
        corr.evaluate(2**63)

    with pytest.raises(RuntimeError, match="Input x has wrong type"):
        corr.evaluate(2.0**63)
