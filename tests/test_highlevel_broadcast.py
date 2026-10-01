"""awkward arguments are broadcast once, by awkward.transform itself

The wrapper used to call awkward.broadcast_arrays before awkward.transform; transform already
broadcasts its inputs, so the explicit pass only doubled the work. These tests pin that the
shapes the explicit pass handled still come out the same without it.
"""

import awkward
import numpy
import pytest

import correctionlib
from correctionlib import schemav2 as model


@pytest.fixture
def sf():
    """``2*a + b``, so every element's result depends on that element's own inputs"""
    return correctionlib.CorrectionSet(
        model.CorrectionSet(
            schema_version=model.VERSION,
            corrections=[
                model.Correction(
                    name="two",
                    version=1,
                    inputs=[
                        model.Variable(name="a", type="real"),
                        model.Variable(name="b", type="real"),
                    ],
                    output=model.Variable(name="o", type="real"),
                    data=model.Formula(
                        nodetype="formula",
                        expression="2.0*x + y",
                        parser="TFormula",
                        variables=["a", "b"],
                    ),
                )
            ],
        )
    )["two"]


def jagged(values, counts):
    return awkward.unflatten(numpy.asarray(values, dtype=numpy.float64), counts)


def assert_identical(left, right):
    """Values, None mask and type, all the way down"""
    assert awkward.to_list(left) == awkward.to_list(right)
    assert str(awkward.type(left)) == str(awkward.type(right))
    assert left.layout.form.to_json() == right.layout.form.to_json()


@pytest.mark.parametrize(
    "make_pair",
    [
        pytest.param(
            lambda: (
                jagged(numpy.arange(9), [4, 0, 3, 2]),
                awkward.Array(numpy.arange(4.0)),
            ),
            id="jagged-against-flat",
        ),
        pytest.param(
            lambda: (
                awkward.Array(numpy.arange(9.0)),
                awkward.Array(numpy.array([100.0])),
            ),
            id="length-one",
        ),
        pytest.param(
            lambda: (
                jagged(numpy.arange(9), [4, 0, 3, 2]),
                awkward.mask(
                    jagged(numpy.arange(100, 109), [4, 0, 3, 2]),
                    jagged(numpy.arange(9), [4, 0, 3, 2]) % 2 == 0,
                ),
            ),
            id="option-against-plain",
        ),
    ],
)
def test_arguments_needing_broadcast_match_the_explicit_pass(sf, make_pair):
    a, b = make_pair()
    direct = sf.evaluate(a, b)
    explicit = sf.evaluate(*awkward.broadcast_arrays(a, b))

    assert_identical(direct, explicit)
    assert awkward.to_list(direct) == awkward.to_list(2.0 * a + b)


@pytest.mark.parametrize(
    "make_pair",
    [
        pytest.param(
            lambda: (
                jagged(numpy.arange(9), [4, 0, 3, 2]),
                jagged(numpy.arange(9), [3, 2, 2, 2]),
            ),
            id="same-depth-different-offsets",
        ),
        pytest.param(
            lambda: (
                awkward.Array(numpy.arange(9.0)),
                awkward.Array(numpy.arange(8.0)),
            ),
            id="flat-different-lengths",
        ),
    ],
)
def test_unbroadcastable_still_raises(sf, make_pair):
    a, b = make_pair()
    with pytest.raises(ValueError):
        sf.evaluate(a, b)


def test_behavior_and_attrs_survive(sf):
    a = awkward.Array(
        jagged(numpy.arange(9), [4, 0, 3, 2]).layout,
        behavior={"__test__": 1},
        attrs={"key": "value"},
    )
    b = jagged(numpy.arange(100, 109), [4, 0, 3, 2])
    out = sf.evaluate(a, b)

    assert out.behavior == {"__test__": 1}
    assert dict(out.attrs) == {"key": "value"}
