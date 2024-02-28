import pytest

import correctionlib
import correctionlib.schemav2 as cs


def test_pyroot_binding():
    ROOT = pytest.importorskip("ROOT")
    correctionlib.register_pyroot_binding()
    assert ROOT.correction.CorrectionSet

    ptweight = cs.Correction(
        name="ptweight",
        version=1,
        inputs=[
            cs.Variable(name="pt", type="real", description="Muon transverse momentum")
        ],
        output=cs.Variable(
            name="weight", type="real", description="Multiplicative event weight"
        ),
        data=cs.Binning(
            nodetype="binning",
            input="pt",
            edges=[10, 20, 30, 40, 50, 80, 120],
            content=[1.1, 1.08, 1.06, 1.04, 1.02, 1.0],
            flow="clamp",
        ),
    )
    cset = cs.CorrectionSet(schema_version=2, corrections=[ptweight])
    csetstr = cset.model_dump_json().replace('"', r"\"")

    ROOT.gInterpreter.Declare(
        f'auto cset = correction::CorrectionSet::from_string("{csetstr}");'  # noqa: B907
    )
    ROOT.gInterpreter.Declare('auto corr = cset->at("ptweight");')
    assert ROOT.corr.evaluate([1.2]) == 1.1
