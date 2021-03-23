"""Tools to convert other formats to correctionlib

Mostly TODO right now
"""
from numbers import Real
from typing import TYPE_CHECKING, Any, Iterable, List, Sequence

from .schemav2 import Binning, Category, Content, Correction, MultiBinning, Variable

if TYPE_CHECKING:
    from numpy import ndarray
    from uhi.typing.plottable import PlottableAxis, PlottableHistogram


def from_uproot_THx(path: str) -> Correction:
    """Convert a ROOT histogram

    This function attempts to open a ROOT file with uproot
    and extract the TH1 or TH2 as specified by the object path

    Example::

        corr = convert.from_uproot_THx(
            "testSF2d.histo.root:scalefactors_Tight_Electron"
        )

    """
    import uproot

    return from_histogram(uproot.open(path))


def from_histogram(hist: "PlottableHistogram") -> Correction:
    """Read any object with PlottableHistogram interface protocol

    Interface as defined in
    https://github.com/scikit-hep/uhi/blob/v0.1.1/src/uhi/typing/plottable.py
    """

    def read_axis(axis: "PlottableAxis", pos: int) -> Variable:
        axtype = "real"
        if len(axis) == 0:
            raise ValueError(f"Zero-length axis {axis}, what to do?")
        elif isinstance(axis[0], str):
            axtype = "str"
        elif isinstance(axis[0], int):
            axtype = "integer"
        return Variable.parse_obj(
            {
                "type": axtype,
                "name": getattr(axis, "name", f"axis{pos}"),
                "description": getattr(axis, "label", None),
            }
        )

    variables = [read_axis(ax, i) for i, ax in enumerate(hist.axes)]
    # Here we could try to optimize the ordering

    def edges(axis: "PlottableAxis") -> List[float]:
        out = []
        for i, b in enumerate(axis):
            assert isinstance(b, tuple)
            out.append(b[0])
            if i == len(axis) - 1:
                out.append(b[1])
        return out

    def flatten_to(values: "ndarray", depth: int) -> Iterable[Any]:
        for value in values:
            if depth > 0:
                yield from flatten_to(value, depth - 1)
            else:
                yield value

    def build_data(
        values: "ndarray", axes: Sequence["PlottableAxis"], variables: List[Variable]
    ) -> Content:
        vartype = variables[0].type
        if vartype in {"string", "int"}:
            return Category.parse_obj(
                {
                    "nodetype": "category",
                    "input": variables[0].name,
                    "content": [
                        {
                            "key": axes[0][i],
                            "value": value
                            if isinstance(value, Real)
                            else build_data(value, axes[1:], variables[1:]),
                        }
                        for i, value in enumerate(values)
                    ],
                }
            )
        # else it is real, check if we can multibin some axes
        i = 0
        for var in variables:
            if var.type != "real":
                break
            i += 1
        if i > 1:
            return MultiBinning.parse_obj(
                {
                    "nodetype": "multibinning",
                    "edges": [edges(ax) for ax in axes[:i]],
                    "inputs": [var.name for var in variables[:i]],
                    "content": [
                        value
                        if isinstance(value, Real)
                        else build_data(value, axes[i:], variables[i:])
                        for value in flatten_to(values, i - 1)
                    ],
                    "flow": "error",  # TODO: can also produce overflow guard bins and clamp
                }
            )
        return Binning.parse_obj(
            {
                "nodetype": "binning",
                "input": variables[0].name,
                "edges": edges(axes[0]),
                "content": [
                    value
                    if isinstance(value, Real)
                    else build_data(value, axes[1:], variables[1:])
                    for value in values
                ],
                "flow": "error",  # TODO: can also produce overflow guard bins and clamp
            }
        )

    return Correction.parse_obj(
        {
            "version": 0,
            "name": getattr(hist, "name", "unknown"),
            "inputs": variables,
            "output": {"name": getattr(hist, "label", "out"), "type": "real"},
            "data": build_data(hist.values(), hist.axes, variables),
        }
    )
