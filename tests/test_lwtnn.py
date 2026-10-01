import json
from pathlib import Path

import pytest

from correctionlib.highlevel import CorrectionSet, model_auto, open_auto

LWTNN_TEST_FIXTURE = Path(__file__).parent / "data" / "lwtnn_example.json"


def test_validate_lwtnn():
    model_auto(open_auto(str(LWTNN_TEST_FIXTURE)))


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


def test_lwtnn_example(ulp_report):
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
    # lwtnn's Eigen kernels sum in an order that depends on the vector ISA and the
    # Eigen version, so the last couple of ULPs are not reproducible across
    # platforms -- an aarch64 wheel build differed by one ULP here, see #348.
    ulp_report(sf, 0.95186825355646787, rel=1e-12)
