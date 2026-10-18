import awkward
import pytest

import correctionlib
import correctionlib.highlevel
from correctionlib import schemav2 as model
from correctionlib.highlevel import _isgraphed

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


@pytest.mark.parametrize(
    ("get", "syst"),
    [
        (lambda c: c["scale"], "nominal"),
        (lambda c: c["scale"], "up"),
        (lambda c: c.compound["stack"], "up"),
    ],
    ids=["nominal", "up", "compound"],
)
def test_correction_on_graphed(cset, events, get, syst):
    session, array, deferred = events
    out = get(cset).evaluate(syst, deferred.pt)
    assert _isgraphed(out)
    want = get(cset).evaluate(syst, array.pt)
    assert session.materialize(out).to_list() == want.to_list()


def test_correction_on_graphed_varied(cset, events):
    session, array, deferred = events
    varied = graphed.vary(deferred.pt, "pt", up=deferred.pt * 1.5)
    out = cset["scale"].evaluate("nominal", varied)
    assert graphed.labels(out) == graphed.labels(varied)
    for label, pt in (("nominal", array.pt), ("pt_up", array.pt * 1.5)):
        got = session.materialize(graphed.universe(out, label))
        assert got.to_list() == cset["scale"].evaluate("nominal", pt).to_list()


class SubclassedArray(graphed_awkward.AwkwardArray):
    pass


class SubclassingBackend(graphed_awkward.AwkwardBackend):
    def array_type(self):
        return SubclassedArray


def test_graphed_subclass_from_another_package(cset):
    array = awkward.Array({"pt": [[10.0, 20.0], [], [30.0]]})
    session = graphed.Session(SubclassingBackend())
    deferred = graphed_awkward.from_awkward(session, "events", array)
    assert type(deferred.pt) is SubclassedArray
    out = cset["scale"].evaluate("up", deferred.pt)
    assert session.materialize(out).to_list() == [[30.0, 60.0], [], [90.0]]


def test_graphed_named_package_is_not_graphed():
    lookalike = type("Lookalike", (), {"__module__": "graphed_tools.x"})
    assert not _isgraphed(lookalike())
    assert _isgraphed(SubclassedArray.__new__(SubclassedArray))


def test_one_payload_per_correction_set(cset, events, monkeypatch):
    session, _, deferred = events
    payloads = []
    apply_correction = graphed_awkward.gak.apply_correction

    def spy(payload, *args, **kwargs):
        payloads.append(payload)
        return apply_correction(payload, *args, **kwargs)

    monkeypatch.setattr(graphed_awkward.gak, "apply_correction", spy)
    cset["scale"].evaluate("up", deferred.pt)
    cset["offset"].evaluate(deferred.pt)
    assert len(payloads) == 2
    assert payloads[0] is payloads[1]


def test_old_graphed_is_refused(cset, events, monkeypatch):
    _, _, deferred = events
    monkeypatch.setattr(graphed, "__version__", "0.0.6")
    with pytest.raises(RuntimeError, match=r"graphed is version 0\.0\.6"):
        cset["scale"].evaluate("up", deferred.pt)
