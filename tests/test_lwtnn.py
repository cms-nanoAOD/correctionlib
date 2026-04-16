import math
from pathlib import Path

from correctionlib.highlevel import CorrectionSet

EXAMPLE = Path(__file__).parent / "data" / "lwtnn_example.json"


def test_lwtnn_example():
    cset = CorrectionSet.from_file(str(EXAMPLE))
    corr = cset["electron_sf"]

    gen_pt = 15.0
    gen_eta = 0.4
    gen_phi = 2.1
    gen_iso = 1e-3
    sf = corr.evaluate(
        math.log10(max(gen_pt, 1e-4)),
        gen_eta,
        gen_phi,
        math.log10(max(gen_iso, 1e-6)),
    )
    assert sf == 0.95186825355646787
