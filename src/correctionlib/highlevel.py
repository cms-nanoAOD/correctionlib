"""High-level correctionlib objects

"""
import json
from numbers import Integral
from typing import Any, Iterator, Mapping, Optional, Union

import correctionlib._core
import correctionlib.version


def open_auto(filename: str) -> Any:
    """Open a file and return a deserialized json object"""
    if filename.endswith(".json.gz"):
        import gzip

        with gzip.open(filename, "r") as gzfile:
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
    def __init__(self, base: correctionlib._core.Correction):
        self._base = base

    @property
    def name(self) -> str:
        return self._base.name

    @property
    def description(self) -> str:
        return self._base.description

    @property
    def version(self) -> int:
        return self._base.version

    def evaluate(self, *args: Union[str, int, float]) -> float:
        return self._base.evaluate(*args)


class CorrectionSet(Mapping[str, Correction]):
    def __init__(self, model: Any, *, schema_version: Optional[int] = None):
        if schema_version is None:
            this_version = correctionlib.version.version_tuple[0]
            if model.schema_version < this_version:
                # TODO: upgrade schema automatically
                raise NotImplementedError(
                    "Cannot read CorrectionSet models older than {this_version}"
                )
        elif schema_version != model.schema_version:
            raise ValueError(
                f"CorrectionSet schema version ({model.schema_version}) differs from desired version ({schema_version})"
            )
        self._model = model
        self._base = correctionlib._core.CorrectionSet.from_string(model.json())

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

    @property
    def schema_version(self) -> int:
        return self._base.schema_version

    def __getitem__(self, key: str) -> Correction:
        corr = self._base.__getitem__(key)
        return Correction(corr)

    def __len__(self) -> int:
        return len(self._base)

    def __iter__(self) -> Iterator[str]:
        return iter(self._base)
