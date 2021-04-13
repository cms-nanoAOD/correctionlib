from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr, validator
from rich.columns import Columns
from rich.console import Console, ConsoleOptions, RenderResult
from rich.panel import Panel
from rich.tree import Tree

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal


VERSION = 2


class Model(BaseModel):
    class Config:
        extra = "forbid"


class _SummaryInfo:
    def __init__(self) -> None:
        self.values: Set[Union[str, int]] = set()
        self.default: bool = False
        self.overflow: bool = True
        self.transform: bool = False
        self.min: float = float("inf")
        self.max: float = float("-inf")


class Variable(Model):
    """An input or output variable"""

    name: str
    type: Literal["string", "int", "real"] = Field(
        description="A string, a 64 bit integer, or a double-precision floating point value"
    )
    description: Optional[str] = Field(
        description="A nice description of what this variable means"
    )

    def __rich__(self) -> str:
        msg = f"[bold]{self.name}[/bold] ({self.type})\n"
        msg += self.description or "[i]No description[/i]"
        return msg


# py3.7+: ForwardRef can be used instead of strings
Content = Union[
    "Binning", "MultiBinning", "Category", "Formula", "FormulaRef", "Transform", float
]


class Formula(Model):
    """A general formula type"""

    nodetype: Literal["formula"]
    expression: str
    parser: Literal["TFormula"]
    variables: List[str] = Field(
        description="The names of the correction input variables this formula applies to"
    )
    parameters: Optional[List[float]] = Field(
        description="Parameters, if the parser supports them (e.g. [0] for TFormula)"
    )

    def summarize(
        self, nodecount: Dict[str, int], inputstats: Dict[str, _SummaryInfo]
    ) -> None:
        nodecount["Formula"] += 1


class FormulaRef(Model):
    """A reference to one of the Correction generic_formula items, with specific parameters"""

    nodetype: Literal["formularef"]
    index: int = Field(
        description="Index into the Correction.generic_formulas list", ge=0
    )
    parameters: List[float] = Field(
        description="Same interpretation as Formula.parameters"
    )

    def summarize(
        self, nodecount: Dict[str, int], inputstats: Dict[str, _SummaryInfo]
    ) -> None:
        nodecount["FormulaRef"] += 1


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

    def summarize(
        self, nodecount: Dict[str, int], inputstats: Dict[str, _SummaryInfo]
    ) -> None:
        nodecount["Transform"] += 1
        inputstats[self.input].transform = True
        if not isinstance(self.content, float):
            self.content.summarize(nodecount, inputstats)


class Binning(Model):
    """1-dimensional binning in an input variable"""

    nodetype: Literal["binning"]
    input: str = Field(
        description="The name of the correction input variable this binning applies to"
    )
    edges: List[float] = Field(
        description="Edges of the binning, where edges[i] <= x < edges[i+1] => f(x, ...) = content[i](...)"
    )
    content: List[Content]
    flow: Union[Content, Literal["clamp", "error"]] = Field(
        description="Overflow behavior for out-of-bounds values"
    )

    @validator("edges")
    def validate_edges(cls, edges: List[float], values: Any) -> List[float]:
        for lo, hi in zip(edges[:-1], edges[1:]):
            if hi <= lo:
                raise ValueError(f"Binning edges not monotone increasing: {edges}")
        return edges

    @validator("content")
    def validate_content(cls, content: List[Content], values: Any) -> List[Content]:
        if "edges" in values:
            nbins = len(values["edges"]) - 1
            if nbins != len(content):
                raise ValueError(
                    f"Binning content length ({len(content)}) is not one larger than edges ({nbins + 1})"
                )
        return content

    def summarize(
        self, nodecount: Dict[str, int], inputstats: Dict[str, _SummaryInfo]
    ) -> None:
        nodecount["Binning"] += 1
        inputstats[self.input].overflow &= self.flow != "error"
        inputstats[self.input].min = min(inputstats[self.input].min, self.edges[0])
        inputstats[self.input].max = max(inputstats[self.input].max, self.edges[-1])
        for item in self.content:
            if not isinstance(item, float):
                item.summarize(nodecount, inputstats)
        if not isinstance(self.flow, (float, str)):
            self.flow.summarize(nodecount, inputstats)


class MultiBinning(Model):
    """N-dimensional rectangular binning"""

    nodetype: Literal["multibinning"]
    inputs: List[str] = Field(
        description="The names of the correction input variables this binning applies to",
        min_items=1,
    )
    edges: List[List[float]] = Field(description="Bin edges for each input")
    content: List[Content] = Field(
        description="""Bin contents as a flattened array
        This is a C-ordered array, i.e. content[d1*d2*d3*i0 + d2*d3*i1 + d3*i2 + i3] corresponds
        to the element at i0 in dimension 0, i1 in dimension 1, etc. and d0 = len(edges[0]), etc.
    """
    )
    flow: Union[Content, Literal["clamp", "error"]] = Field(
        description="Overflow behavior for out-of-bounds values"
    )

    @validator("edges")
    def validate_edges(cls, edges: List[List[float]], values: Any) -> List[List[float]]:
        for i, dim in enumerate(edges):
            for lo, hi in zip(dim[:-1], dim[1:]):
                if hi <= lo:
                    raise ValueError(
                        f"MultiBinning edges for axis {i} are not monotone increasing: {dim}"
                    )
        return edges

    @validator("content")
    def validate_content(cls, content: List[Content], values: Any) -> List[Content]:
        if "edges" in values:
            nbins = 1
            for dim in values["edges"]:
                nbins *= len(dim) - 1
            if nbins != len(content):
                raise ValueError(
                    f"MultiBinning content length ({len(content)}) does not match the product of dimension sizes ({nbins})"
                )
        return content

    def summarize(
        self, nodecount: Dict[str, int], inputstats: Dict[str, _SummaryInfo]
    ) -> None:
        nodecount["MultiBinning"] += 1
        for input, edges in zip(self.inputs, self.edges):
            inputstats[input].overflow &= self.flow != "error"
            inputstats[input].min = min(inputstats[input].min, edges[0])
            inputstats[input].max = max(inputstats[input].max, edges[-1])
        for item in self.content:
            if not isinstance(item, float):
                item.summarize(nodecount, inputstats)
        if not isinstance(self.flow, (float, str)):
            self.flow.summarize(nodecount, inputstats)


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
    content: List[CategoryItem]
    default: Optional[Content]

    @validator("content")
    def validate_content(cls, content: List[CategoryItem]) -> List[CategoryItem]:
        if len(content):
            keytype = type(content[0].key)
            if not all(isinstance(item.key, keytype) for item in content):
                raise ValueError(
                    f"Keys in the Category node do not have a homogenous type, expected all {keytype}"
                )

            keys = {item.key for item in content}
            if len(keys) != len(content):
                raise ValueError("Duplicate keys detected in Category node")
        return content

    def summarize(
        self, nodecount: Dict[str, int], inputstats: Dict[str, _SummaryInfo]
    ) -> None:
        nodecount["Category"] += 1
        inputstats[self.input].values |= {item.key for item in self.content}
        inputstats[self.input].default |= self.default is not None
        for item in self.content:
            if not isinstance(item.value, float):
                item.value.summarize(nodecount, inputstats)
        if self.default and not isinstance(self.default, float):
            self.default.summarize(nodecount, inputstats)


Transform.update_forward_refs()
Binning.update_forward_refs()
MultiBinning.update_forward_refs()
CategoryItem.update_forward_refs()
Category.update_forward_refs()


class Correction(Model):
    name: str
    description: Optional[str] = Field(
        description="Detailed description of the correction"
    )
    version: int = Field(
        description="Some value that may increase over time due to bugfixes"
    )
    inputs: List[Variable] = Field(
        description="The function signature of the correction"
    )
    output: Variable = Field(description="Output type for this correction")
    generic_formulas: Optional[List[Formula]] = Field(
        description="""A list of common formulas that may be used

        For corrections with many parameterized formulas that follow a regular pattern,
        the expression and inputs can be declared once with a generic formula, deferring the parameter
        declaration to the more lightweight FormulaRef nodes. This can speed up both loading and evaluation
        of the correction object
        """
    )
    data: Content = Field(description="The root content node")

    @validator("output")
    def validate_output(cls, output: Variable) -> Variable:
        if output.type != "real":
            raise ValueError(
                "Output types other than real are not supported. See https://github.com/nsmith-/correctionlib/issues/12"
            )
        return output

    def summary(self) -> Tuple[Dict[str, int], Dict[str, _SummaryInfo]]:
        nodecount: Dict[str, int] = defaultdict(int)
        inputstats = {var.name: _SummaryInfo() for var in self.inputs}
        if not isinstance(self.data, float):
            self.data.summarize(nodecount, inputstats)
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


class CorrectionSet(Model):
    schema_version: Literal[VERSION] = Field(description="The overall schema version")
    corrections: List[Correction]

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        tree = Tree(
            f":open_file_folder: CorrectionSet ([i]schema v{self.schema_version}[/i])"
        )
        for corr in self.corrections:
            tree.add(corr)
        yield tree


if __name__ == "__main__":
    import os
    import sys

    dirname = sys.argv[-1]
    with open(os.path.join(dirname, f"schemav{VERSION}.json"), "w") as fout:
        fout.write(CorrectionSet.schema_json(indent=4))
