from typing import (
    List,
    Dict,
    Optional,
    Union,
)
from pydantic import BaseModel

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


VERSION = 2


class Model(BaseModel):
    class Config:
        extra = "forbid"


class Variable(Model):
    name: str
    type: Literal["string", "int", "real"]
    "Implicitly 64 bit integer and double-precision floating point?"
    description: Optional[str]
    # TODO: clamping behavior for out of range?


# py3.7+: ForwardRef can be used instead of strings
Content = Union["Binning", "MultiBinning", "Category", "Formula", float]


class Formula(Model):
    nodetype: Literal["formula"]
    expression: str
    parser: Literal["TFormula_v1"]
    variables: List[str]
    parameters: List[float]


class Binning(Model):
    nodetype: Literal["binning"]
    edges: List[float]
    "Edges of the binning, where edges[i] <= x < edges[i+1] => f(x, ...) = content[i](...)"
    content: List[Content]


class MultiBinning(Model):
    """N-dimensional rectangular binning"""

    nodetype: Literal["multibinning"]
    edges: List[List[float]]
    """Bin edges for each input

    C-ordered array, e.g. content[d1*d2*d3*i0 + d2*d3*i1 + d3*i2 + i3] corresponds
    to the element at i0 in dimension 0, i1 in dimension 1, etc. and d0 = len(edges[0]), etc.
    """
    content: List[Content]


class Category(Model):
    nodetype: Literal["category"]
    content: Union[Dict[str, Content], Dict[int, Content]]


Binning.update_forward_refs()
MultiBinning.update_forward_refs()
Category.update_forward_refs()


class Correction(Model):
    name: str
    "A useful name"
    description: Optional[str]
    "Detailed description of the correction"
    version: int
    "Version"
    inputs: List[Variable]
    output: Variable
    data: Content


class CorrectionSet(Model):
    schema_version: Literal[VERSION]
    "Schema version"
    corrections: List[Correction]


if __name__ == "__main__":
    with open(f"data/schemav{VERSION}.json", "w") as fout:
        fout.write(CorrectionSet.schema_json(indent=4))
