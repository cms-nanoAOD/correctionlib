import json
import math
from pathlib import Path

from correctionlib import schemav2
from correctionlib.highlevel import CorrectionSet

LWTNN_TEST_FIXTURE = Path(__file__).parent / "data" / "lwtnn_example.json"


def test_lwtnn_example():
    cset = CorrectionSet.from_file(str(LWTNN_TEST_FIXTURE))
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


# Analysts should choose the payload matching their object and ID working point.
FASTSIM_ELECTRON_LOOSE_PAYLOAD = Path("tests/data/lwtnn_example.json")

FASTSIM_EXAMPLE_PAYLOAD = LWTNN_TEST_FIXTURE


def evaluate_lwtnn_fastsim_scale_factor(validate_schema=True):
    payload = json.loads(FASTSIM_EXAMPLE_PAYLOAD.read_text())
    corr_payload = payload["corrections"][0]
    corr_payload["name"] = "electron_fastsim_sf"
    corr_payload["description"] = (
        "FastSim-to-FullSim object scale factor evaluator for reco Electrons. "
        "Inputs are generator-level pt, eta, phi, and isolation for the "
        "matched generator particle. For reco electron index my_index in "
        "NanoAOD, Electron_genPartIdx[my_index] points to the matched GenPart "
        "for pt/eta/phi. "
        "The evaluator applies log10(max(pt, 1e-4)) and "
        "log10(max(iso, 1e-6)) internally; eta and phi are unchanged."
    )

    corr_payload["inputs"][0]["name"] = "pt"
    corr_payload["inputs"][0]["description"] = (
        "Matched gen pt, e.g. GenPart_pt[Electron_genPartIdx[my_index]]"
    )
    corr_payload["inputs"][1]["description"] = (
        "Matched gen eta, e.g. GenPart_eta[Electron_genPartIdx[my_index]]"
    )
    corr_payload["inputs"][2]["description"] = (
        "Matched gen phi, e.g. GenPart_phi[Electron_genPartIdx[my_index]]"
    )
    corr_payload["inputs"][3]["name"] = "iso"
    corr_payload["inputs"][3]["description"] = (
        "Matched-particle generator isolation, computed for the GenPart "
        "referenced by Electron_genPartIdx[my_index] using the same definition "
        "as training"
    )

    lwtnn = corr_payload["data"]
    # The original LWTNN JSON uses pt_log10/iso_log10 names. After adding
    # Transform nodes, the LWTNN should consume the transformed pt/iso values.
    # eta and phi already have the public input names, so they are unchanged.
    lwtnn["opaque"]["inputs"][0]["name"] = "pt"
    lwtnn["opaque"]["inputs"][3]["name"] = "iso"
    corr_payload["data"] = {
        "nodetype": "transform",
        "input": "pt",
        "rule": {
            "nodetype": "formula",
            "expression": "log10(max(x, 1e-4))",
            "parser": "TFormula",
            "variables": ["pt"],
        },
        "content": {
            "nodetype": "transform",
            "input": "iso",
            "rule": {
                "nodetype": "formula",
                "expression": "log10(max(x, 1e-6))",
                "parser": "TFormula",
                "variables": ["iso"],
            },
            "content": lwtnn,
        },
    }

    if validate_schema:
        schemav2.CorrectionSet.model_validate(payload)
    cset = CorrectionSet.from_string(json.dumps(payload))
    corr = cset["electron_fastsim_sf"]

    # Hard-coded feature vector: (pt, eta, phi, iso), e.g.
    # pt = GenPart_pt[Electron_genPartIdx[my_index]].
    PT, ETA, PHI, ISO = 15.0, 0.4, 2.1, 1e-3
    sf = corr.evaluate(PT, ETA, PHI, ISO)
    assert sf == 0.95186825355646787
    return sf


def test_lwtnn_fastsim_scale_factor():
    assert evaluate_lwtnn_fastsim_scale_factor() == 0.95186825355646787


if __name__ == "__main__":
    test_lwtnn_example()
    sf = evaluate_lwtnn_fastsim_scale_factor(validate_schema=False)
    print("FastSim->FullSim scale factor evaluation", sf)
