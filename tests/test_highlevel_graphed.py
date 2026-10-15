import awkward
import pytest

import correctionlib
from correctionlib import schemav2 as model

graphed = pytest.importorskip("graphed")
graphed_awkward = pytest.importorskip("graphed.awkward")


@pytest.fixture
def cset():
    return correctionlib.CorrectionSet(
        model.CorrectionSet(
            schema_version=model.VERSION,
            corrections=[
                model.Correction(
                    name="scale",
                    version=1,
                    inputs=[
                        model.Variable(name="syst", type="string"),
                        model.Variable(name="pt", type="real"),
                    ],
                    output=model.Variable(name="sf", type="real"),
                    data=model.Category(
                        nodetype="category",
                        input="syst",
                        content=[
                            model.CategoryItem(
                                key=key,
                                value=model.Formula(
                                    nodetype="formula",
                                    expression=f"{factor}*x",
                                    parser="TFormula",
                                    variables=["pt"],
                                ),
                            )
                            for key, factor in (("nominal", 2), ("up", 3))
                        ],
                    ),
                ),
                model.Correction(
                    name="offset",
                    version=1,
                    inputs=[model.Variable(name="pt", type="real")],
                    output=model.Variable(name="sf", type="real"),
                    data=model.Formula(
                        nodetype="formula",
                        expression="x+1",
                        parser="TFormula",
                        variables=["pt"],
                    ),
                ),
            ],
            compound_corrections=[
                model.CompoundCorrection(
                    name="stack",
                    inputs=[
                        model.Variable(name="syst", type="string"),
                        model.Variable(name="pt", type="real"),
                    ],
                    output=model.Variable(name="sf", type="real"),
                    inputs_update=["pt"],
                    input_op="*",
                    output_op="*",
                    stack=["scale", "offset"],
                )
            ],
        )
    )


@pytest.fixture
def events():
    session = graphed.Session(graphed_awkward.AwkwardBackend())
    array = awkward.Array({"pt": [[10.0, 20.0], [], [30.0]]})
    return session, array, graphed_awkward.from_awkward(session, "events", array)


@pytest.mark.parametrize("syst", ["nominal", "up"])
def test_correction_on_graphed(cset, events, syst):
    session, array, deferred = events
    out = cset["scale"].evaluate(syst, deferred.pt)
    assert _isgraphed(out)
    assert (
        session.materialize(out).to_list()
        == cset["scale"].evaluate(syst, array.pt).to_list()
    )


def test_compound_correction_on_graphed(cset, events):
    session, array, deferred = events
    out = cset.compound["stack"].evaluate("up", deferred.pt)
    assert _isgraphed(out)
    want = cset.compound["stack"].evaluate("up", array.pt)
    assert session.materialize(out).to_list() == want.to_list()


def test_correction_on_graphed_varied(cset, events):
    session, array, deferred = events
    varied = graphed.vary(deferred.pt, "pt", up=deferred.pt * 1.5)
    out = cset["scale"].evaluate("nominal", varied)
    assert graphed.labels(out) == graphed.labels(varied)
    for label, pt in (("nominal", array.pt), ("pt_up", array.pt * 1.5)):
        got = session.materialize(graphed.universe(out, label))
        assert got.to_list() == cset["scale"].evaluate("nominal", pt).to_list()


def _isgraphed(out):
    return type(out).__module__.startswith("graphed.")
