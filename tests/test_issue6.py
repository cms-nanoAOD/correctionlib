import pytest

from correctionlib import schemav2 as cs


def test_input_names_valid():
    bin0 = cs.MultiBinning(
        nodetype="multibinning",
        inputs=["eta", "phi"],
        edges=[
            [-2.5, 0.0, 2.5],  # eta edges
            [-3.14, 0.0, 3.14],  # phi edges
        ],
        content=[0.9, 1.0, 1.1, 1.2],
        flow="error",
    )

    bin1 = cs.Category(
        nodetype="category",
        input="eta",
        content=[
            cs.CategoryItem(key="central", value=1.05),
            cs.CategoryItem(key="forward", value=1.15),
        ],
        default=1.0,
    )

    bin2 = cs.HashPRNG(
        nodetype="hashprng",
        inputs=["pt", "eta", "phi", "evt"],
        distribution="normal",
    )

    def try_name(ptname: str, etaname: str, phiname: str, evtname: str):
        return cs.Correction(
            version=2,
            name="test_issue6",
            description="Test issue 6",
            inputs=[
                cs.Variable(name=ptname, type="real"),
                cs.Variable(name=etaname, type="real"),
                cs.Variable(name=phiname, type="real"),
                cs.Variable(name=evtname, type="int"),
            ],
            output=cs.Variable(name="weight", type="real", description="event weight"),
            data=cs.Binning(
                nodetype="binning",
                input="pt",
                edges=[0.0, 50.0, 100.0, 150.0],
                content=[bin0, bin1, bin2],
                flow="error",
            ),
        )

    try_name("pt", "eta", "phi", "evt")  # should work

    with pytest.raises(ValueError):
        try_name("pt_wrong", "eta", "phi", "evt")
    with pytest.raises(ValueError):
        try_name("pt", "eta_wrong", "phi", "evt")
    with pytest.raises(ValueError):
        try_name("pt", "eta", "phi_wrong", "evt")
    with pytest.raises(ValueError):
        try_name("pt", "eta", "phi", "evt_wrong")
    try_name("pt", "eta", "phi", "evt_wrong")
