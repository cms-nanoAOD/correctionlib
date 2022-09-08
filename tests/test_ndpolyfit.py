import numpy as np
import pytest

from correctionlib import convert


def test_ndpoly():
    corr, _ = convert.ndpolyfit(
        points=[np.array([0.0, 1.0, 0.0, 1.0]), np.array([10.0, 20.0, 10.0, 20.0])],
        values=np.array([0.9, 0.95, 0.94, 0.98]),
        weights=np.array([0.1, 0.1, 0.1, 0.1]),
        varnames=["abseta", "pt"],
        degree=(1, 1),
    )
    ceval = corr.to_evaluator()
    assert ceval.evaluate(0.2, 13.0) == pytest.approx(1.0801881480751705)
