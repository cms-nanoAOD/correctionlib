from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr, validator

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal


VERSION = 2


class Model(BaseModel):
    class Config:
        extra = "forbid"


class Variable(Model):
    """An input or output variable"""

    name: str
    type: Literal["string", "int", "real"] = Field(
        description="A string, a 64 bit integer, or a double-precision floating point value"
    )
    description: Optional[str] = Field(
        description="A nice description of what this variable means"
    )


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


class FormulaRef(Model):
    """A reference to one of the Correction generic_formula items, with specific parameters"""

    nodetype: Literal["formularef"]
    index: int = Field(
        description="Index into the Correction.generic_formulas list", ge=0
    )
    parameters: List[float] = Field(
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


class CorrectionSet(Model):
    schema_version: Literal[VERSION] = Field(description="The overall schema version")
    corrections: List[Correction]


if __name__ == "__main__":
    import os
    import sys

    dirname = sys.argv[-1]
    with open(os.path.join(dirname, f"schemav{VERSION}.json"), "w") as fout:
        fout.write(CorrectionSet.schema_json(indent=4))
