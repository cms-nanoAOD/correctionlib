import awkward as ak
import numpy as np

import correctionlib.schemav2 as cs


def test_issue_296():
    corr = cs.Correction(
        name="test",
        version=1,
        inputs=[
            cs.Variable(name="x", type="int"),
        ],
        output=cs.Variable(name="out", type="real"),
        data=cs.HashPRNG(nodetype="hashprng", inputs=["x"], distribution="normal"),
    ).to_evaluator()

    x = ak.Array([1, 2, 3, 4, 5])
    result = corr.evaluate(x)
    assert isinstance(result, ak.Array)

    x = np.array([1, 2, 3, 4, 5])
    result = corr.evaluate(x)
    assert isinstance(result, np.ndarray)
