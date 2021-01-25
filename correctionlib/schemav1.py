from typing import (
    List,
    Optional,
    Union,
)
from pydantic import BaseModel
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


VERSION = 1


class Model(BaseModel):
    class Config:
        extra = "forbid"


class Variable(Model):
    name: str
    type: Literal["string", "int", "real"]
    "Implicitly 64 bit integer and double-precision floating point?"
    description: Optional[str]
    # TODO: clamping behavior for out of range?


class Formula(Model):
    expression: str
    parser: Literal["TFormula", "numexpr"]
    parameters: List[int]
    "Index to Correction.inputs[]"


# None = invalid phase space?
Value = Union[Formula, float]
# py3.7+: ForwardRef can be used instead of strings
Content = Union["Binning", "MultiBinning", "Category", Value]


class Binning(Model):
    nodetype: Literal["binning"]
    edges: List[float]
    "Edges of the binning, where edges[i] <= x < edges[i+1] => f(x, ...) = content[i](...)"
    content: List[Content]


class MultiBinning(Model):
    """N-dimensional rectangular binning"""

    nodetype: Literal["multibinning"]
    edges: List[List[float]]
    "Bin edges for each input"
    content: List[Content]


class Category(Model):
    nodetype: Literal["category"]
    keys: List[Union[str,int]]
    content: List[Content]


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
