import math
import warnings
from collections import Counter
from collections.abc import Collection
from functools import partial
from typing import Annotated, Any, Callable, Literal, Optional, Union

from pydantic import (
    AfterValidator,
    AllowInfNan,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    Strict,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)
from rich.columns import Columns
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markup import escape
from rich.panel import Panel
from rich.tree import Tree

import correctionlib.highlevel

VERSION = 2

# See https://github.com/cms-nanoAOD/correctionlib/issues/255
IGNORE_FLOAT_INF = False


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)


class Variable(Model):
    """An input or output variable"""

    name: str
    type: Literal["string", "int", "real"] = Field(
        description="A string, a 64 bit integer, or a double-precision floating point value"
    )
    description: Optional[str] = Field(
        description="A nice description of what this variable means",
        default=None,
    )

    def __rich__(self) -> str:
        msg = f"[bold]{self.name}[/bold] ({self.type})\n"
        msg += self.description or "[i]No description[/i]"
        return msg


# py3.7+: ForwardRef can be used instead of strings
Content = Union[
    Annotated[
        Union[
            "Binning",
            "MultiBinning",
            "Category",
            "Formula",
            "FormulaRef",
            "Transform",
            "HashPRNG",
            "LWTNN",
        ],
        Field(discriminator="nodetype"),
    ],
    float,
]


class Formula(Model):
    """A general formula type"""

    nodetype: Literal["formula"]
    expression: str
    parser: Literal["TFormula"]
    variables: list[str] = Field(
        description="The names of the correction input variables this formula applies to"
    )
    parameters: Optional[list[float]] = Field(
        description="Parameters, if the parser supports them (e.g. [0] for TFormula)",
        default=None,
    )


class FormulaRef(Model):
    """A reference to one of the Correction generic_formula items, with specific parameters"""

    nodetype: Literal["formularef"]
    index: int = Field(
        description="Index into the Correction.generic_formulas list", ge=0
    )
    parameters: list[float] = Field(
        description="Same interpretation as Formula.parameters"
    )


class Transform(Model):
    """A node that rewrites one real or integer input according to a rule as given by a content node

    Any downstream nodes will see a different value for the rewritten input
    If the input is an integer type, the rule output will be cast from a
    double to integer type before using. These should be used sparingly and at
    high levels in the tree, since they require an allocation.
    """

    nodetype: Literal["transform"]
    input: str = Field(description="The name of the input to rewrite")
    rule: Content = Field(description="A subtree that implements the rewrite rule")
    content: Content = Field(
        description="A subtree that will be evaluated with transformed values"
    )


class HashPRNG(Model):
    """A node that generates a pseudorandom number deterministic in its inputs

    The output distribution can be chosen from a set of fixed values,
    downstream code could then shift and scale it as necessary.
    """

    nodetype: Literal["hashprng"]
    inputs: list[str] = Field(
        description="The names of the input variables to use as entropy sources",
        min_length=1,
    )
    distribution: Literal["stdflat", "stdnormal", "normal"] = Field(
        description="The output distribution to draw from"
    )

    @field_validator("distribution")
    @classmethod
    def validate_distribution(cls, distribution: str) -> str:
        if distribution == "stdnormal":
            warnings.warn(
                "'stdnormal' distribution is deprecated, use 'normal' instead (cms-nanoAOD/correctionlib#287)",
                DeprecationWarning,
                stacklevel=2,
            )
        return distribution


class LWTNNInput(Model):
    """An input variable for an LWTNN node"""

    model_config = ConfigDict(extra="allow")

    name: str


class LWTNNSchema(Model):
    """The expected schema for the opaque configuration of an LWTNN node

    This is not the entire LWTNN schema, just the parts that we need to
    validate and extract input/output variable names from. Full validation
    of the opaque blob is deferred to the C++ code.
    """

    model_config = ConfigDict(extra="allow")

    inputs: list[LWTNNInput] = Field(
        description="The input variables for the LWTNN model. "
        "These must match input variable names in the CorrectionSet."
    )
    outputs: list[str]


class LWTNN(Model):
    """A node that evaluates a lightweight neural network"""

    nodetype: Literal["lwtnn"]
    opaque: LWTNNSchema = Field(
        description="The opaque configuration for lwtnn, passed directly to the C++ code"
    )
    finalizer: Formula = Field(
        description="A formula to apply to the raw lwtnn outputs, with input variables matching the lwtnn outputs"
    )


class UniformBinning(Model):
    """Uniform binning description, to be used as the `edges` attribute of Binning or MultiBinning."""

    n: int = Field(description="Number of bins")
    low: float = Field(description="Lower edge of first bin")
    high: float = Field(description="Higher edge of last bin")

    @field_validator("n")
    @classmethod
    def validate_n(cls, n: int) -> int:
        if n <= 0:  # downstream C++ logic assumes there is at least one bin
            raise ValueError(f"Number of bins must be greater than 0, got {n}")
        return n

    @field_validator("high")
    @classmethod
    def validate_edges(cls, high: float, info: ValidationInfo) -> float:
        low = info.data["low"]
        if low >= high:
            raise ValueError(
                f"Higher bin edge must be larger than lower, got {[low, high]}"
            )
        return high


Infinity = Literal["inf", "+inf", "-inf"]
Edges = list[Union[float, Infinity]]


def validate_nonuniform_edges(edges: Edges) -> Edges:
    for edge in edges:
        if edge in ("inf", "+inf", "-inf"):
            continue
        if isinstance(edge, float):
            if not IGNORE_FLOAT_INF and not math.isfinite(edge):
                raise ValueError(
                    f"Edges array contains non-finite values: {edges}. Replace infinities with 'inf' or '-inf'. NaN is not allowed."
                )
    floatedges = [float(x) for x in edges]
    for lo, hi in zip(floatedges[:-1], floatedges[1:]):
        if lo >= hi:
            raise ValueError(f"Binning edges not monotonically increasing: {edges}")
    return edges


NonUniformBinning = Annotated[Edges, AfterValidator(validate_nonuniform_edges)]


class Binning(Model):
    """1-dimensional binning in an input variable"""

    nodetype: Literal["binning"]
    input: str = Field(
        description="The name of the correction input variable this binning applies to"
    )
    edges: Union[NonUniformBinning, UniformBinning] = Field(
        description="Edges of the binning, either as a list of monotonically increasing floats or as an instance of UniformBinning. edges[i] <= x < edges[i+1] => f(x, ...) = content[i](...)"
    )
    content: list[Content]
    flow: Union[Content, Literal["clamp", "error", "wrap"]] = Field(
        description="Overflow behavior for out-of-bounds values"
    )

    @field_validator("content")
    @classmethod
    def validate_content(
        cls, content: list[Content], info: ValidationInfo
    ) -> list[Content]:
        assert "edges" in info.data
        if isinstance(info.data["edges"], list):
            nbins = len(info.data["edges"]) - 1
        else:
            nbins = info.data["edges"].n
        if nbins != len(content):
            raise ValueError(
                f"Binning content length ({len(content)}) is not one less than edges ({nbins + 1})"
            )
        return content


class MultiBinning(Model):
    """N-dimensional rectangular binning"""

    nodetype: Literal["multibinning"]
    inputs: list[str] = Field(
        description="The names of the correction input variables this binning applies to",
        min_length=1,
    )
    edges: list[Union[NonUniformBinning, UniformBinning]] = Field(
        description="Bin edges for each input"
    )
    content: list[Content] = Field(
        description="""Bin contents as a flattened array
        This is a C-ordered array, i.e. content[d1*d2*d3*i0 + d2*d3*i1 + d3*i2 + i3] corresponds
        to the element at i0 in dimension 0, i1 in dimension 1, etc. and d0 = len(edges[0])-1, etc.
    """
    )
    flow: Union[Content, Literal["clamp", "error", "wrap"]] = Field(
        description="Overflow behavior for out-of-bounds values"
    )

    @field_validator("content")
    @classmethod
    def validate_content(
        cls, content: list[Content], info: ValidationInfo
    ) -> list[Content]:
        assert "edges" in info.data
        nbins = 1
        for dim in info.data["edges"]:
            if isinstance(dim, list):
                nbins *= len(dim) - 1
            else:
                nbins *= dim.n
        if nbins != len(content):
            raise ValueError(
                f"MultiBinning content length ({len(content)}) does not match the product of dimension sizes ({nbins})"
            )
        return content


class CategoryItem(Model):
    """A key-value pair

    The key type must match the type of the Category input variable
    """

    key: Union[StrictInt, StrictStr]
    value: Content


class Category(Model):
    """A categorical lookup"""

    nodetype: Literal["category"]
    input: str = Field(
        description="The name of the correction input variable this category node applies to"
    )
    content: list[CategoryItem]
    default: Optional[Content] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: list[CategoryItem]) -> list[CategoryItem]:
        if len(content):
            keytype = type(content[0].key)
            if not all(isinstance(item.key, keytype) for item in content):
                raise ValueError(
                    f"Keys in the Category node do not have a homogeneous type, expected all {keytype}"
                )

            keys = {item.key for item in content}
            if len(keys) != len(content):
                raise ValueError("Duplicate keys detected in Category node")
        return content


Transform.model_rebuild()
Binning.model_rebuild()
MultiBinning.model_rebuild()
CategoryItem.model_rebuild()
Category.model_rebuild()


def walk_content(content: Content, func: Callable[[Content], None]) -> None:
    """Visit all content nodes in a tree, applying func to each node."""
    func(content)
    if isinstance(content, (float, Formula, FormulaRef, HashPRNG, LWTNN)):
        pass
    elif isinstance(content, (Binning, MultiBinning)):
        for bin in content.content:
            walk_content(bin, func)
        if not isinstance(content.flow, str):
            walk_content(content.flow, func)
    elif isinstance(content, Category):
        for cat in content.content:
            walk_content(cat.value, func)
        if content.default:
            walk_content(content.default, func)
    elif isinstance(content, Transform):
        walk_content(content.rule, func)
        walk_content(content.content, func)
    else:
        raise RuntimeError(f"Unknown content node type: {type(content)}")


def _validate_input(allowed_names: set[str], node: Content) -> None:
    nodename = type(node).__name__
    if isinstance(node, (Binning, Category, Transform)):
        if node.input not in allowed_names:
            msg = f"{nodename} input {node.input!r} not found in Correction inputs {allowed_names}"
            raise ValueError(msg)
    elif isinstance(node, (MultiBinning, HashPRNG)):
        for inp in node.inputs:
            if inp not in allowed_names:
                msg = f"{nodename} input {inp!r} not found in Correction inputs {allowed_names}"
                raise ValueError(msg)
    elif isinstance(node, Formula):
        for inp in node.variables:
            if inp not in allowed_names:
                msg = f"{nodename} input {inp!r} not found in Correction inputs {allowed_names}"
                raise ValueError(msg)
    elif isinstance(node, LWTNN):
        if len(node.opaque.inputs) == 0:
            raise ValueError("LWTNN opaque configuration 'inputs' field is empty")
        for lwtinp in node.opaque.inputs:
            if lwtinp.name not in allowed_names:
                msg = f"{nodename} input {lwtinp.name!r} not found in Correction inputs {allowed_names}"
                raise ValueError(msg)
        lwtnn_outputs = node.opaque.outputs
        if len(lwtnn_outputs) == 0:
            raise ValueError("LWTNN opaque configuration 'outputs' field is empty")
        for var in node.finalizer.variables:
            if var not in lwtnn_outputs:
                msg = f"{nodename} finalizer variable {var!r} not found in lwtnn outputs {lwtnn_outputs}"
                raise ValueError(msg)
    # FormulaRef has no direct input names


def _binning_range(
    edges: Union[NonUniformBinning, UniformBinning],
) -> tuple[float, float]:
    if isinstance(edges, list):
        low = float(edges[0])
        high = float(edges[-1])
    else:
        low = edges.low
        high = edges.high
    return low, high


class _SummaryInfo:
    def __init__(self) -> None:
        self.values: set[Union[str, int]] = set()
        self.default: bool = False
        self.overflow: bool = True
        self.transform: bool = False
        self.used: bool = False
        self.min: float = float("inf")
        self.max: float = float("-inf")


def _summarize(
    nodecount: dict[str, int], inputstats: dict[str, _SummaryInfo], node: Content
) -> None:
    """Compile summary statistics for a content node."""
    if isinstance(node, float):
        return
    nodecount[type(node).__name__] += 1
    if isinstance(node, Binning):
        inputstats[node.input].overflow &= node.flow != "error"
        low, high = _binning_range(node.edges)
        inputstats[node.input].used = True
        inputstats[node.input].min = min(inputstats[node.input].min, low)
        inputstats[node.input].max = max(inputstats[node.input].max, high)
    elif isinstance(node, MultiBinning):
        for input, edges in zip(node.inputs, node.edges):
            inputstats[input].overflow &= node.flow != "error"
            low, high = _binning_range(edges)
            inputstats[input].used = True
            inputstats[input].min = min(inputstats[input].min, low)
            inputstats[input].max = max(inputstats[input].max, high)
    elif isinstance(node, Category):
        inputstats[node.input].used = True
        inputstats[node.input].values |= {item.key for item in node.content}
        inputstats[node.input].default |= node.default is not None
    elif isinstance(node, Transform):
        inputstats[node.input].used = True
        inputstats[node.input].transform = True
    elif isinstance(node, Formula):
        for var in node.variables:
            inputstats[var].used = True
    elif isinstance(node, LWTNN):
        for inp in node.opaque.inputs:
            inputstats[inp.name].used = True


class Correction(Model):
    name: str
    description: Optional[str] = Field(
        description="Detailed description of the correction",
        default=None,
    )
    version: int = Field(
        description="Some value that may increase over time due to bugfixes"
    )
    inputs: list[Variable] = Field(
        description="The function signature of the correction"
    )
    output: Variable = Field(description="Output type for this correction")
    generic_formulas: Optional[list[Formula]] = Field(
        description="""A list of common formulas that may be used

        For corrections with many parameterized formulas that follow a regular pattern,
        the expression and inputs can be declared once with a generic formula, deferring the parameter
        declaration to the more lightweight FormulaRef nodes. This can speed up both loading and evaluation
        of the correction object
        """,
        default=None,
    )
    data: Content = Field(description="The root content node")

    @field_validator("output")
    @classmethod
    def validate_output(cls, output: Variable) -> Variable:
        if output.type != "real":
            raise ValueError(
                "Output types other than real are not supported. See https://github.com/nsmith-/correctionlib/issues/12"
            )
        return output

    @model_validator(mode="after")
    def check_input_names(self) -> "Correction":
        input_names = {var.name for var in self.inputs}
        walk_content(self.data, partial(_validate_input, input_names))
        return self

    def summary(self) -> tuple[dict[str, int], dict[str, _SummaryInfo]]:
        nodecount: dict[str, int] = Counter()
        inputstats = {var.name: _SummaryInfo() for var in self.inputs}
        walk_content(self.data, partial(_summarize, nodecount, inputstats))
        if self.generic_formulas:
            for formula in self.generic_formulas:
                _summarize(nodecount, inputstats, formula)
        return nodecount, inputstats

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield f":chart_with_upwards_trend: [bold]{self.name}[/bold] (v{self.version})"
        yield self.description or "[i]No description[/i]"
        nodecount, inputstats = self.summary()
        yield "Node counts: " + ", ".join(
            f"[b]{key}[/b]: {val}" for key, val in nodecount.items()
        )

        def fmt_input(var: Variable, stats: _SummaryInfo) -> str:
            out = var.__rich__()
            if var.type == "real":
                if not stats.used:
                    out += "\nRange: [bold red]unused[/bold red]"
                else:
                    out += f"\nRange: [{stats.min}, {stats.max})"
                if stats.overflow:
                    out += ", overflow ok"
                if stats.transform:
                    out += "\n[bold red]has transform[/bold red]"
            else:
                out += "\nValues: " + ", ".join(str(v) for v in sorted(stats.values))
                if stats.default:
                    out += "\n[bold green]has default[/bold green]"
            return out

        inputs = (
            Panel(
                fmt_input(var, inputstats[var.name]),
                title=":arrow_forward: input",
            )
            for var in self.inputs
        )
        yield Columns(inputs)
        yield Panel(
            self.output.__rich__(),
            title=":arrow_backward: output",
            expand=False,
        )

    def to_evaluator(self) -> correctionlib.highlevel.Correction:
        # TODO: consider refactoring highlevel.Correction to be independent
        cset = CorrectionSet(schema_version=2, corrections=[self])
        return correctionlib.highlevel.CorrectionSet(cset)[self.name]


class CompoundCorrection(Model):
    """A compound correction

    This references other Correction objects in a CorrectionSet and can
    provide a canned recipe for serial application of dependent corrections.
    For example, given corrections corr1(x, y) and corr2(x', z), where
    x' = corr1(x, y) * x, the compound correction
    corr(x, y, z) = corr2(x * corr1(x, y), z)
    can be expressed with reference to its component corrections.
    """

    name: str
    description: Optional[str] = Field(
        description="Detailed description of the correction stack",
        default=None,
    )
    inputs: list[Variable] = Field(
        description="The function signature of the correction"
    )
    output: Variable = Field(description="Output type for this correction")
    inputs_update: list[str] = Field(
        description="Names of the input variables to update with the output of the previous correction"
    )
    input_op: Literal["+", "*", "/"] = Field(
        description="How to accumulate changes in the input variables"
    )
    output_op: Literal["+", "*", "/", "last"] = Field(
        description="How to accumulate changes in the output variable"
    )
    stack: list[str] = Field(
        description="Names of the component corrections. Each component should have a subset of the inputs listed in this object."
    )

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield f":chart_with_upwards_trend::chart_with_upwards_trend: [bold]{self.name}[/bold]"
        yield self.description or "[i]No description[/i]"
        yield Panel("\n".join(self.stack), title=":input_numbers: stack", expand=False)

        def fmt_input(var: Variable) -> str:
            out = var.__rich__()
            if var.name in self.inputs_update:
                out += f"\n[bold green]updated by stack using ({self.input_op})[/bold green]"
            return out

        inputs = (
            Panel(
                fmt_input(var),
                title=":arrow_forward: input",
            )
            for var in self.inputs
        )
        yield Columns(inputs)
        yield Panel(
            self.output.__rich__() + f"\nUpdate operation: ({self.output_op})",
            title=":arrow_backward: output",
            expand=False,
        )


class FrozenInputSpec(Model):
    """A frozen input value to a correction, for use in uncertainty sources"""

    name: str = Field(description="The name of the correction input variable")
    value: Union[
        StrictInt, StrictStr, Annotated[float, Strict(), AllowInfNan(False)]
    ] = Field(description="The value to use for this input variable")


class UncertaintySpec(Model):
    """An uncertainty source specification"""

    nuisance_name: str = Field(
        description="Name of the nuisance parameter associated with this uncertainty source (i.e. combine name in datacard)"
    )
    correction: str = Field(
        description="Name of the Correction or CompoundCorrection (in this CorrectionSet) which defines this uncertainty source"
    )
    inputs: list[FrozenInputSpec] = Field(
        description="Frozen input values to use in the correction evaluation"
    )
    direction: Optional[Literal["up", "down"]] = Field(
        description="""\
Which side of a two-sided variation this source describes. If not specified,
this source is the only variation for its nuisance (e.g. a symmetric shift).
""",
        default=None,
    )
    operation: Optional[Literal["shift", "scale", "replace", "relative"]] = Field(
        description="""\
How the correction output (out) relates to the nominal value. The nominal value
is provided by the analyzer.

shift: nominal + out (additive)
scale: nominal * out (multiplicative)
replace: out (full alternative evaluation)
relative: nominal * (1 + out) (relative uncertainty, as stored e.g. for JES sources)

If not specified, the relation is left to the analyzer.
""",
        default=None,
    )

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, items: list[FrozenInputSpec]) -> list[FrozenInputSpec]:
        seen = set()
        dupe = set()
        for item in items:
            if item.name in seen:
                dupe.add(item.name)
            seen.add(item.name)
        if len(dupe):
            raise ValueError(
                f"Frozen inputs must have unique names, found duplicates for {dupe}"
            )
        return items


class UncertaintySet(Model):
    """A set of uncertainty sources

    This is metadata only: it is not used by the correction evaluator.
    """

    name: str = Field(description="Uncertainty set name")
    description: Optional[str] = Field(
        description="Detailed description of the uncertainty set",
        default=None,
    )
    uncertainties: list[UncertaintySpec] = Field(
        description="List of uncertainty sources in this set"
    )

    @field_validator("uncertainties")
    @classmethod
    def validate_uncertainties(
        cls, items: list[UncertaintySpec]
    ) -> list[UncertaintySpec]:
        seen = set()
        dupe = set()
        directions: dict[str, set[Optional[str]]] = {}
        counts: Counter[tuple[str, Optional[str]]] = Counter()
        for item in items:
            inputs = tuple(sorted((inp.name, inp.value) for inp in item.inputs))
            key = (item.nuisance_name, item.direction, inputs)
            if key in seen:
                dupe.add(key)
            seen.add(key)
            directions.setdefault(item.nuisance_name, set()).add(item.direction)
            counts[item.nuisance_name, item.direction] += 1
        if len(dupe):
            raise ValueError(
                f"Uncertainty sources must have unique (nuisance_name, direction, inputs) triples, found duplicates for {dupe}"
            )
        mixed = {
            name for name, dirs in directions.items() if None in dirs and len(dirs) > 1
        }
        if len(mixed):
            raise ValueError(
                f"Uncertainty sources cannot mix entries with and without a direction for the same nuisance, found {mixed}"
            )
        unpaired = {
            name
            for name, dirs in directions.items()
            if dirs == {"up", "down"} and counts[name, "up"] != counts[name, "down"]
        }
        if len(unpaired):
            raise ValueError(
                f"Uncertainty sources must have as many 'up' as 'down' entries for each nuisance, found {unpaired}"
            )
        return items

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield f":left_right_arrow: [bold]{self.name}[/bold]"
        yield self.description or "[i]No description[/i]"

        def fmt_spec(spec: UncertaintySpec) -> str:
            inputs = ", ".join(f"{inp.name}={inp.value!r}" for inp in spec.inputs)
            out = f"[bold]{spec.nuisance_name}[/bold]"
            if spec.direction is not None:
                out += escape(f" [{spec.direction}]")
            out += f": {spec.correction}({inputs})"
            if spec.operation is not None:
                out += f" ({spec.operation})"
            return out

        yield Panel(
            "\n".join(fmt_spec(spec) for spec in self.uncertainties),
            title=":input_numbers: uncertainties",
            expand=False,
        )


def _frozen_reachable(node: Content, frozen: dict[str, Union[int, str, float]]) -> bool:
    """Check if some values of the free inputs lead to a result, given the frozen ones

    A Category on a frozen input must contain that value as a key (or have a
    default). Other nodes are assumed to accept any frozen value.
    """
    if isinstance(node, Category):
        if node.input in frozen:
            for item in node.content:
                if item.key == frozen[node.input]:
                    return _frozen_reachable(item.value, frozen)
            return node.default is not None and _frozen_reachable(node.default, frozen)
        children = [item.value for item in node.content]
        if node.default is not None:
            children.append(node.default)
        return any(_frozen_reachable(child, frozen) for child in children)
    if isinstance(node, (Binning, MultiBinning)):
        children = list(node.content)
        if not isinstance(node.flow, str):
            children.append(node.flow)
        return any(_frozen_reachable(child, frozen) for child in children)
    if isinstance(node, Transform):
        # the content sees a rewritten value, so that input is no longer frozen
        inner = {name: val for name, val in frozen.items() if name != node.input}
        return _frozen_reachable(node.rule, frozen) and _frozen_reachable(
            node.content, inner
        )
    return True


FrozenValue = Union[int, str, float]
Combination = frozenset[tuple[str, FrozenValue]]


def _frozen_combinations(
    node: Content, axes: frozenset[str], assigned: dict[str, FrozenValue]
) -> set[Combination]:
    """List the Category keys on the axes inputs that lead to a result

    Each returned combination maps the axes inputs met along a path to the
    Category key taken. Category defaults on an axis do not assign a key, as
    they stand for any other value, but their content is still walked.
    """
    if isinstance(node, Category):
        if node.input in axes:
            if node.input in assigned:
                for item in node.content:
                    if item.key == assigned[node.input]:
                        return _frozen_combinations(item.value, axes, assigned)
                if node.default is None:
                    return set()
                return _frozen_combinations(node.default, axes, assigned)
            out: set[Combination] = set()
            for item in node.content:
                out |= _frozen_combinations(
                    item.value, axes, {**assigned, node.input: item.key}
                )
            if node.default is not None:
                out |= _frozen_combinations(node.default, axes, assigned)
            return out
        children = [item.value for item in node.content]
        if node.default is not None:
            children.append(node.default)
    elif isinstance(node, (Binning, MultiBinning)):
        children = list(node.content)
        if not isinstance(node.flow, str):
            children.append(node.flow)
    elif isinstance(node, Transform):
        # the content sees a rewritten value, so that input is no longer an axis
        return _frozen_combinations(node.rule, axes, assigned) | _frozen_combinations(
            node.content, axes - {node.input}, assigned
        )
    else:
        return {frozenset(assigned.items())}
    out = set()
    for child in children:
        out |= _frozen_combinations(child, axes, assigned)
    return out


def _check_frozen_input(var: Variable, value: Union[int, str, float]) -> bool:
    """Check if a frozen input value is compatible with the variable type"""
    if var.type == "string":
        return isinstance(value, str)
    if var.type == "int":
        return isinstance(value, int)
    return isinstance(value, (int, float))


class CorrectionSet(Model):
    schema_version: Literal[2] = Field(description="The overall schema version")
    description: Optional[str] = Field(
        description="A nice description of what is in this CorrectionSet means",
        default=None,
    )
    corrections: list[Correction]
    compound_corrections: Optional[list[CompoundCorrection]] = None
    uncertainty_sets: Optional[list[UncertaintySet]] = Field(
        description="Sets of uncertainty sources defined in terms of the corrections in this CorrectionSet",
        default=None,
    )
    schema_url: Optional[str] = Field(
        default="https://cms-nanoaod.github.io/correctionlib/_downloads/87e1187fe70c7ee30d50bbacaa2b2cb5/schemav2.json",
        alias="$schema",
        description="""\
A URL to the schema. This is published in the correctionlib documentation
at https://cms-nanoaod.github.io/correctionlib/schemav2.html and some IDEs
may use it to provide autocompletion and validation against the schema.
""",
    )

    @field_validator("corrections")
    @classmethod
    def validate_corrections(cls, items: list[Correction]) -> list[Correction]:
        seen = set()
        dupe = set()
        for item in items:
            if item.name in seen:
                dupe.add(item.name)
            seen.add(item.name)
        if len(dupe):
            raise ValueError(
                f"Corrections must have unique names, found duplicates for {dupe}"
            )
        return items

    @field_validator("compound_corrections")
    @classmethod
    def validate_compound(
        cls, items: Optional[list[CompoundCorrection]]
    ) -> Optional[list[CompoundCorrection]]:
        if items is None:
            return items
        seen = set()
        dupe = set()
        for item in items:
            if item.name in seen:
                dupe.add(item.name)
            seen.add(item.name)
        if len(dupe):
            raise ValueError(
                f"CompoundCorrection objects must have unique names, found duplicates for {dupe}"
            )
        return items

    @field_validator("uncertainty_sets")
    @classmethod
    def validate_uncertainty_sets(
        cls, items: Optional[list[UncertaintySet]]
    ) -> Optional[list[UncertaintySet]]:
        if items is None:
            return items
        seen = set()
        dupe = set()
        for item in items:
            if item.name in seen:
                dupe.add(item.name)
            seen.add(item.name)
        if len(dupe):
            raise ValueError(
                f"UncertaintySet objects must have unique names, found duplicates for {dupe}"
            )
        return items

    @model_validator(mode="after")
    def check_uncertainty_sets(self) -> "CorrectionSet":
        if self.uncertainty_sets is None:
            return self
        signatures = {corr.name: corr.inputs for corr in self.corrections}
        corrections = {corr.name: corr for corr in self.corrections}
        compounds = {ccorr.name: ccorr for ccorr in self.compound_corrections or []}
        ambiguous = set()
        for ccorr in self.compound_corrections or []:
            if ccorr.name in signatures:
                ambiguous.add(ccorr.name)
            signatures[ccorr.name] = ccorr.inputs
        for uset in self.uncertainty_sets:
            for spec in uset.uncertainties:
                where = f"UncertaintySet {uset.name!r} source {spec.nuisance_name!r}"
                if spec.correction not in signatures:
                    raise ValueError(
                        f"{where} references unknown correction {spec.correction!r}"
                    )
                if spec.correction in ambiguous:
                    raise ValueError(
                        f"{where} correction {spec.correction!r} is ambiguous: it names both a Correction and a CompoundCorrection"
                    )
                variables = {var.name: var for var in signatures[spec.correction]}
                for inp in spec.inputs:
                    if inp.name not in variables:
                        raise ValueError(
                            f"{where} input {inp.name!r} not found in {spec.correction!r} inputs {set(variables)}"
                        )
                    var = variables[inp.name]
                    if not _check_frozen_input(var, inp.value):
                        raise ValueError(
                            f"{where} input {inp.name!r} value {inp.value!r} does not match variable type {var.type!r}"
                        )
                frozen = {inp.name: inp.value for inp in spec.inputs}
                updated: set[str] = set()
                if spec.correction in compounds:
                    ccorr = compounds[spec.correction]
                    stack = [corrections[n] for n in ccorr.stack if n in corrections]
                    updated = set(ccorr.inputs_update)
                else:
                    stack = [corrections[spec.correction]]
                for i, corr in enumerate(stack):
                    if i > 0:
                        # inputs updated by the stack no longer hold the frozen value
                        frozen = {n: v for n, v in frozen.items() if n not in updated}
                    if not _frozen_reachable(corr.data, frozen):
                        raise ValueError(
                            f"{where} input values {frozen} do not match any category of correction {corr.name!r}"
                        )
        return self

    def uncovered_uncertainty_inputs(
        self, nominal_keys: Collection[FrozenValue] = ("central", "nominal")
    ) -> list[tuple[str, dict[str, FrozenValue]]]:
        """List the uncertainty variations not referenced by any UncertaintySpec

        For each Correction referenced in the uncertainty sets, directly or
        through a CompoundCorrection stack, the inputs frozen by its sources
        are taken as uncertainty axes, and every combination of Category keys
        on these axes that leads to a result should match some source.
        Coverage is pooled over all uncertainty sets, and over the Correction
        and the CompoundCorrections that use it. Combinations with any value in
        ``nominal_keys`` are not reported. Some variations may be intentionally
        left out (e.g. for internal validation), so this is meant for warnings
        only.

        Returns a sorted list of (Correction name, uncovered combination).
        """
        if self.uncertainty_sets is None:
            return []
        if isinstance(nominal_keys, str):
            nominal_keys = (nominal_keys,)
        corrections = {corr.name: corr for corr in self.corrections}
        compounds = {ccorr.name: ccorr for ccorr in self.compound_corrections or []}
        # frozen inputs of the sources, as seen by each Correction they evaluate
        specs: dict[str, list[dict[str, FrozenValue]]] = {}
        for uset in self.uncertainty_sets:
            for spec in uset.uncertainties:
                frozen = {inp.name: inp.value for inp in spec.inputs}
                if spec.correction not in compounds:
                    specs.setdefault(spec.correction, []).append(frozen)
                    continue
                ccorr = compounds[spec.correction]
                stack = [n for n in ccorr.stack if n in corrections]
                for i, name in enumerate(stack):
                    if i > 0:
                        # inputs updated by the stack no longer hold the frozen value
                        frozen = {
                            n: v
                            for n, v in frozen.items()
                            if n not in ccorr.inputs_update
                        }
                    specs.setdefault(name, []).append(frozen)

        out = []
        for name, frozens in specs.items():
            corr = corrections[name]
            axes = frozenset(n for frozen in frozens for n in frozen) & {
                var.name for var in corr.inputs
            }
            if not axes:
                continue
            for combo in _frozen_combinations(corr.data, axes, {}):
                values = dict(sorted(combo))
                if any(v in nominal_keys for v in values.values()):
                    continue
                if not any(
                    all(n not in values or values[n] == v for n, v in frozen.items())
                    for frozen in frozens
                ):
                    out.append((name, values))
        out.sort(key=lambda item: (item[0], repr(item[1])))
        return out

    @model_serializer(mode="wrap")
    def drop_unset_uncertainty_sets(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        # older correctionlib versions reject any uncertainty_sets key, even null
        data: dict[str, Any] = handler(self)
        if "uncertainty_sets" in data and data["uncertainty_sets"] is None:
            del data["uncertainty_sets"]
        return data

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        tree = Tree(
            f"[b]CorrectionSet[/b] ([i]schema v{self.schema_version}[/i])\n"
            + (self.description or "[i]No description[/i]")
            + "\n"
            + ":open_file_folder:"
        )
        for corr in self.corrections:
            tree.add(corr)
        if self.compound_corrections:
            for ccorr in self.compound_corrections:
                tree.add(ccorr)
        if self.uncertainty_sets:
            for uset in self.uncertainty_sets:
                tree.add(uset)
        yield tree

    def to_evaluator(self) -> correctionlib.highlevel.CorrectionSet:
        return correctionlib.highlevel.CorrectionSet(self)


if __name__ == "__main__":
    import os
    import sys

    dirname = sys.argv[-1]
    with open(os.path.join(dirname, f"schemav{VERSION}.json"), "w") as fout:
        fout.write(CorrectionSet.schema_json(indent=4))
