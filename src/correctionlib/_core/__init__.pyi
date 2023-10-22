from typing import Any, Dict, Iterator, List, Type, TypeVar, Union

import numpy

class Variable:
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def type(self) -> str: ...
    @staticmethod
    def from_string(json: str) -> Variable: ...

class CompoundCorrection:
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def inputs(self) -> List[Variable]: ...
    @property
    def output(self) -> Variable: ...
    def evaluate(self, *args: Union[str, int, float]) -> float: ...
    def evalv(
        self, *args: Union[numpy.ndarray[Any, Any], str, int, float]
    ) -> numpy.ndarray[Any, numpy.dtype[numpy.float64]]: ...

class Correction:
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def version(self) -> int: ...
    @property
    def inputs(self) -> List[Variable]: ...
    @property
    def output(self) -> Variable: ...
    def evaluate(self, *args: Union[str, int, float]) -> float: ...
    def evalv(
        self, *args: Union[numpy.ndarray[Any, Any], str, int, float]
    ) -> numpy.ndarray[Any, numpy.dtype[numpy.float64]]: ...

T = TypeVar("T", bound="CorrectionSet")

class CorrectionSet:
    @classmethod
    def from_file(cls: Type[T], filename: str) -> T: ...
    @classmethod
    def from_string(cls: Type[T], data: str) -> T: ...
    @property
    def schema_version(self) -> int: ...
    def __getitem__(self, key: str) -> Correction: ...
    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[str]: ...
    @property
    def compound(self) -> Dict[str, CompoundCorrection]: ...

class FormulaAst:
    class NodeType:
        name: str
        value: int

    class UnaryOp:
        name: str
        value: int

    class BinaryOp:
        name: str
        value: int
    @property
    def nodetype(self) -> NodeType: ...
    @property
    def data(self) -> Union[None, float, int, UnaryOp, BinaryOp]: ...
    @property
    def children(self) -> list[FormulaAst]: ...

class Formula:
    @property
    def expression(self) -> str: ...
    @property
    def ast(self) -> FormulaAst: ...
