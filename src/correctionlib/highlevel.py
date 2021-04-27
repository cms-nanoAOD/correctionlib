"""High-level correctionlib objects

"""
import json
from numbers import Integral
from typing import Any, Dict, Iterator, List, Mapping, Optional, Union

import numpy

import correctionlib._core
import correctionlib.version


def open_auto(filename: str) -> Any:
    """Open a file and return a deserialized json object"""
    if filename.endswith(".json.gz"):
        import gzip

        with gzip.open(filename, "rt") as gzfile:
            return json.load(gzfile)
    elif filename.endswith(".json"):
        with open(filename) as file:
            return json.load(file)
    raise ValueError(f"{filename}: unrecognized file format, expected .json, .json.gz")


def model_auto(data: Any) -> Any:
    """Read schema version from json object and construct appropriate model"""
    if not isinstance(data, dict):
        raise ValueError("CorrectionSet is not a dictionary!")
    version = data.get("schema_version", None)
    if version is None:
        raise ValueError("CorrectionSet has no schema version!")
    if not isinstance(version, Integral):
        raise ValueError(f"CorrectionSet schema version ({version}) is not an integer!")
    if version == 1:
        import correctionlib.schemav1

        return correctionlib.schemav1.CorrectionSet.parse_obj(data)
    elif version == 2:
        import correctionlib.schemav2

        return correctionlib.schemav2.CorrectionSet.parse_obj(data)
    raise ValueError(f"Unknown CorrectionSet schema version ({version})")


class Correction:
    def __init__(self, base: correctionlib._core.Correction, context: "CorrectionSet"):
        self._base = base
        self._name = base.name
        self._context = context

    def __getstate__(self) -> Dict[str, Any]:
        return {"_context": self._context, "_name": self._name}

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self._context = state["_context"]
        self._name = state["_name"]
        self._base = self._context[self._name]._base

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._base.description

    @property
    def version(self) -> int:
        return self._base.version

    def evaluate(
        self, *args: Union[numpy.ndarray, str, int, float]
    ) -> Union[float, numpy.ndarray]:
        # TODO: create a ufunc with numpy.vectorize in constructor?
        vargs = [arg for arg in args if isinstance(arg, numpy.ndarray)]
        if vargs:
            bargs = numpy.broadcast_arrays(*vargs)
            oshape = bargs[0].shape
            bargs = (arg.flatten() for arg in bargs)
            out = self._base.evalv(
                *(
                    next(bargs) if isinstance(arg, numpy.ndarray) else arg
                    for arg in args
                )
            )
            return out.reshape(oshape)
        return self._base.evaluate(*args)  # type: ignore


class CorrectionSet(Mapping[str, Correction]):
    def __init__(self, model: Any, *, schema_version: Optional[int] = None):
        if schema_version is None:
            this_version = correctionlib.version.version_tuple[0]
            if model.schema_version < this_version:
                # TODO: upgrade schema automatically
                raise NotImplementedError(
                    f"Cannot read CorrectionSet models older than {this_version}"
                )
        elif schema_version != model.schema_version:
            raise ValueError(
                f"CorrectionSet schema version ({model.schema_version}) differs from desired version ({schema_version})"
            )
        self._model = model
        self._base = correctionlib._core.CorrectionSet.from_string(self._model.json())

    @classmethod
    def from_file(
        cls, filename: str, *, schema_version: Optional[int] = None
    ) -> "CorrectionSet":
        return cls(model_auto(open_auto(filename)), schema_version=schema_version)

    @classmethod
    def from_string(
        cls, data: str, *, schema_version: Optional[int] = None
    ) -> "CorrectionSet":
        return cls(model_auto(json.loads(data)), schema_version=schema_version)

    def __getstate__(self) -> Dict[str, Any]:
        return {"_model": self._model}

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self._model = state["_model"]
        self._base = correctionlib._core.CorrectionSet.from_string(self._model.json())

    def _ipython_key_completions_(self) -> List[str]:
        return list(self.keys())

    @property
    def schema_version(self) -> int:
        return self._base.schema_version

    def __getitem__(self, key: str) -> Correction:
        corr = self._base.__getitem__(key)
        return Correction(corr, self)

    def __len__(self) -> int:
        return len(self._base)

    def __iter__(self) -> Iterator[str]:
        return iter(self._base)
