import json
from pathlib import Path

import pytest

from correctionlib.highlevel import CorrectionSet

LWTNN_TEST_FIXTURE = Path(__file__).parent / "data" / "lwtnn_example.json"


def test_lwtnn_bad_opaque():
    data = json.loads(LWTNN_TEST_FIXTURE.read_text())
    # Drill down to the lwtnn node and corrupt its opaque blob
    lwtnn_node = data["corrections"][0]["data"]["content"]["content"]
    assert lwtnn_node["nodetype"] == "lwtnn"
    lwtnn_node["opaque"] = {}
    with pytest.raises(
        RuntimeError, match="Failed to parse LWTNN model from 'opaque' field"
    ):
        CorrectionSet.from_string(json.dumps(data))


def test_lwtnn_example():
    cset = CorrectionSet.from_file(str(LWTNN_TEST_FIXTURE))
    corr = cset["electron_fastsim_sf"]

    gen_pt = 15.0
    gen_eta = 0.4
    gen_phi = 2.1
    gen_iso = 1e-3
    sf = corr.evaluate(
        gen_pt,
        gen_eta,
        gen_phi,
        gen_iso,
    )
    assert sf == 0.95186825355646787
