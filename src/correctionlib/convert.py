"""Tools to convert other formats to correctionlib

"""
from numbers import Real
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

import numpy

from .schemav2 import (
    Binning,
    Category,
    Content,
    Correction,
    Formula,
    MultiBinning,
    Variable,
)

if TYPE_CHECKING:
    from numpy import ndarray
    from typing_extensions import Literal
    from uhi.typing.plottable import PlottableAxis, PlottableHistogram
else:
    # py3.8+: no longer necessary
    try:
        from typing import Literal
    except ImportError:
        from typing_extensions import Literal


def from_uproot_THx(
    path: str,
    axis_names: Optional[List[str]] = None,
    flow: Literal["clamp", "error"] = "error",
) -> Correction:
    """Convert a ROOT histogram

    This function attempts to open a ROOT file with uproot
    and extract the TH1 or TH2 as specified by the object path

    Example::

        corr = convert.from_uproot_THx(
            "testSF2d.histo.root:scalefactors_Tight_Electron"
        )

    """
    import uproot

    return from_histogram(uproot.open(path), axis_names, flow)


def from_histogram(
    hist: "PlottableHistogram",
    axis_names: Optional[List[str]] = None,
    flow: Optional[Union[Content, Literal["clamp", "error"]]] = "error",
) -> Correction:
    """Read any object with PlottableHistogram interface protocol

    Interface as defined in
    https://github.com/scikit-hep/uhi/blob/v0.1.1/src/uhi/typing/plottable.py
    """

    def read_axis(axis: "PlottableAxis", pos: int) -> Variable:
        axtype = "real"
        if len(axis) == 0:
            raise ValueError(f"Zero-length axis {axis}, what to do?")
        elif isinstance(axis[0], str):
            axtype = "string"
        elif isinstance(axis[0], int):
            axtype = "int"
        axname = getattr(
            axis, "name", f"axis{pos}" if axis_names is None else axis_names[pos]
        )
        return Variable.model_validate(
            {
                "type": axtype,
                "name": axname,
                "description": getattr(axis, "label", None),
            }
        )

    variables = [read_axis(ax, i) for i, ax in enumerate(hist.axes)]
    # Here we could try to optimize the ordering

    def edges(axis: "PlottableAxis") -> List[float]:
        out = []
        for i, b in enumerate(axis):
            if isinstance(b, (str, int)):
                raise ValueError(
                    "cannot auto-convert string or integer category axes (yet)"
                )
            b = cast(Tuple[float, float], b)
            out.append(b[0])
            if i == len(axis) - 1:
                out.append(b[1])
        return out

    def flatten_to(values: "ndarray[Any, Any]", depth: int) -> Iterable[Any]:
        for value in values:
            if depth > 0:
                yield from flatten_to(value, depth - 1)
            else:
                yield value

    def build_data(
        values: "ndarray[Any, Any]",
        axes: Sequence["PlottableAxis"],
        variables: List[Variable],
    ) -> Content:
        vartype = variables[0].type
        if vartype in {"string", "int"}:
            return Category.model_validate(
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
            return MultiBinning.model_validate(
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
                    "flow": flow,
                }
            )
        return Binning.model_validate(
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
                "flow": flow,
            }
        )

    return Correction.model_validate(
        {
            "version": 0,
            "name": getattr(hist, "name", "unknown"),
            "inputs": variables,
            "output": {"name": getattr(hist, "label", "out"), "type": "real"},
            "data": build_data(hist.values(), hist.axes, variables),
        }
    )


def ndpolyfit(
    points: List["ndarray[Any, Any]"],
    values: "ndarray[Any, Any]",
    weights: "ndarray[Any, Any]",
    varnames: List[str],
    degree: Tuple[int],
) -> Tuple[Correction, Any]:
    """Fit an n-dimensional polynomial to data points with weight

    Example::

        corr, fitresult = convert.ndpolyfit(
            points=[np.array([0.0, 1.0, 0.0, 1.0]), np.array([10., 20., 10., 20.])],
            values=np.array([0.9, 0.95, 0.94, 0.98]),
            weights=np.array([0.1, 0.1, 0.1, 0.1]),
            varnames=["abseta", "pt"],
            degree=(1, 1),
        )

    Returns a Correction object along with the least squares fit result
    """
    from scipy.optimize import lsq_linear
    from scipy.stats import chi2

    if len(values.shape) != 1:
        raise ValueError("Expecting flat array of values")
    if not all(x.shape == values.shape for x in points):
        raise ValueError("Incompatible shapes for points and values")
    if values.shape != weights.shape:
        raise ValueError("Incompatible shapes for values and weights")
    if len(points) != len(varnames):
        raise ValueError("Dimension mismatch between points and varnames")
    if len(degree) != len(varnames):
        raise ValueError("Dimension mismatch between varnames and degree")
    if len(degree) > 4:
        raise NotImplementedError(
            "correctionlib Formula not available for more than 4 variables"
        )
    _degree: "ndarray[Any, Any]" = numpy.array(degree, dtype=int)
    npoints = len(values)
    powergrid = numpy.ones(shape=(npoints, *(_degree + 1)))
    for i, (x, deg) in enumerate(zip(points, _degree)):
        shape = [1 for _ in range(1 + len(_degree))]
        shape[0] = npoints
        shape[i + 1] = deg + 1
        powergrid *= numpy.power.outer(x, numpy.arange(deg + 1)).reshape(shape)
    fit = lsq_linear(
        A=powergrid.reshape(npoints, -1) * weights[:, None],
        b=values * weights,
    )
    dof = npoints - numpy.prod(_degree + 1)
    prob = chi2.sf(fit.cost, df=dof)
    fitstatus = fit.message + f"\nchi2 = {fit.cost}, P(dof={dof}) = {prob:.3f}"
    params = fit.x.reshape(_degree + 1)
    # TODO: n-dimensional Horner form
    expr = []
    for index in numpy.ndindex(*(_degree + 1)):
        term = [str(params[index])] + [
            f"{var}^{p}" if p > 1 else var for var, p in zip("xyzt", index) if p > 0
        ]
        expr.append("*".join(term))
    degreestr = ",".join(map(str, degree))
    return (
        Correction(
            name="formula",
            description=f"Fit to polynomial of order {degreestr}\nFit status: {fitstatus}",
            version=1,
            inputs=[Variable(name=name, type="real") for name in varnames],
            output=Variable(name="output", type="real"),
            data=Formula(
                nodetype="formula",
                expression="+".join(expr),
                parser="TFormula",
                variables=varnames,
            ),
        ),
        fit,
    )
