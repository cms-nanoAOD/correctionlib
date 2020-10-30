from typing import (
    List,
    Optional,
    Union,
    ForwardRef,
    Literal,
)
from pydantic import BaseModel


VERSION = 1


class Model(BaseModel):
    class Config:
        extra = "forbid"


class Variable(Model):
    name: str
    type: Literal["string", "int", "real"]
    description: Optional[str]


class Formula(Model):
    expression: str
    parser: Literal["TFormula", "numexpr"]
    variables: List[int]
    "Index to Correction.inputs[]"


Value = Union[Formula, float]
Binning = ForwardRef("Binning")
MultiBinning = ForwardRef("MultiBinning")
Category = ForwardRef("Category")
Content = Union[Binning, MultiBinning, Category, Value]


class ContentNode(Model):
    nodetype: str
    content: List[Content]


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
    keys: List[str]
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
    output: Union[Variable, List[Variable]]
    data: Content


class CorrectionSet(Model):
    schema_version: Literal[VERSION]
    "Schema version"
    corrections: List[Correction]


if __name__ == "__main__":
    with open(f"data/schemav{VERSION}.json", "w") as fout:
        fout.write(CorrectionSet.schema_json(indent=4))
