import pickle

import awkward
import numpy
import pytest

import correctionlib
from correctionlib import schemav2 as model


@pytest.fixture
def cset():
    return correctionlib.CorrectionSet(
        model.CorrectionSet(
            schema_version=model.VERSION,
            corrections=[
                model.Correction(
                    name="test corr",
                    version=2,
                    inputs=[
                        model.Variable(name="a", type="real"),
                        model.Variable(name="b", type="real"),
                    ],
                    output=model.Variable(name="a scale", type="real"),
                    data=1.234,
                )
            ],
        )
    )


def test_highlevel(cset):
    assert set(cset) == {"test corr"}
    sf = cset["test corr"]
    assert sf.version == 2
    assert sf.description == ""

    with pytest.raises(RuntimeError):
        sf.evaluate(0, 1.2, 35.0, 0.01)

    assert sf.evaluate(1.0, 1.0) == 1.234
    numpy.testing.assert_array_equal(
        sf.evaluate(numpy.ones((3, 4)), 1.0),
        numpy.full((3, 4), 1.234),
    )
    numpy.testing.assert_array_equal(
        sf.evaluate(numpy.ones((3, 4)), numpy.ones(4)),
        numpy.full((3, 4), 1.234),
    )

    sf2 = pickle.loads(pickle.dumps(sf))
    assert sf2.evaluate(1.0, 1.0) == 1.234


def test_highlevel_flatawkward(cset):
    sf = cset["test corr"]
    numpy.testing.assert_array_equal(
        sf.evaluate(awkward.Array(numpy.ones((3, 4))), numpy.ones(4)),
        numpy.full((3, 4), 1.234),
    )
    numpy.testing.assert_array_equal(
        sf.evaluate(numpy.ones((3, 4)), awkward.Array(numpy.ones(4))),
        numpy.full((3, 4), 1.234),
    )


@pytest.mark.skipif(
    awkward.__version__.startswith("1."),
    reason="Complex awkward array support only for ak v2+",
)
def test_highlevel_awkward(cset):
    sf = cset["test corr"]
    numpy.testing.assert_array_equal(
        awkward.flatten(sf.evaluate(awkward.unflatten(numpy.ones(6), [3, 2, 1]), 1.0)),
        numpy.full(6, 1.234),
    )
    numpy.testing.assert_array_equal(
        awkward.flatten(
            sf.evaluate(awkward.unflatten(numpy.ones(6), [3, 2, 1]), numpy.ones(1))
        ),
        numpy.full(6, 1.234),
    )
    numpy.testing.assert_array_equal(
        awkward.flatten(
            sf.evaluate(awkward.unflatten(numpy.ones(6), [3, 2, 1]), numpy.ones(3))
        ),
        numpy.full(6, 1.234),
    )


def test_highlevel_dask(cset):
    sf = cset["test corr"]

    dask_awkward = pytest.importorskip("dask_awkward")

    x = awkward.unflatten(numpy.ones(6), [3, 2, 1])
    dx = dask_awkward.from_awkward(x, 3)

    evaluate = sf.evaluate(
        dx,
        1.0,
    )

    numpy.testing.assert_array_equal(
        awkward.flatten(evaluate).compute(),
        numpy.full(6, 1.234),
    )


def test_model_to_evaluator():
    m = model.CorrectionSet(
        schema_version=model.VERSION,
        corrections=[
            model.Correction(
                name="test corr",
                version=2,
                inputs=[
                    model.Variable(name="a", type="real"),
                    model.Variable(name="b", type="real"),
                ],
                output=model.Variable(name="a scale", type="real"),
                data=1.234,
            )
        ],
    )
    cset = m.to_evaluator()
    assert set(cset) == {"test corr"}

    sf = m.corrections[0].to_evaluator()
    assert sf.version == 2
    assert sf.description == ""
    assert sf.evaluate(1.0, 1.0) == 1.234
