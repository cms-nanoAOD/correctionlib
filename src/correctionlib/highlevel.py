"""High-level correctionlib objects

"""
import json
from numbers import Integral
from typing import Any, Callable, Dict, Iterator, List, Mapping, Union

import numpy
from packaging import version

import correctionlib._core
import correctionlib.version

_min_version_ak = version.parse("2.0.0")
_min_version_dak = version.parse("2024.1.1")


def open_auto(filename: str) -> str:
    """Open a file and return its contents"""
    if filename.endswith(".json.gz"):
        import gzip

        with gzip.open(filename, "rt") as gzfile:
            return gzfile.read()
    elif filename.endswith(".json"):
        with open(filename) as file:
            return file.read()
    raise ValueError(f"{filename}: unrecognized file format, expected .json, .json.gz")


def model_auto(data: str) -> Any:
    """Read schema version from json object and construct appropriate model"""
    data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError("CorrectionSet is not a dictionary!")
    version = data.get("schema_version", None)
    if version is None:
        raise ValueError("CorrectionSet has no schema version!")
    if not isinstance(version, Integral):
        raise ValueError(f"CorrectionSet schema version ({version}) is not an integer!")
    if version == 1:
        import correctionlib.schemav1

        return correctionlib.schemav1.CorrectionSet.model_validate(data)
    elif version == 2:
        import correctionlib.schemav2

        return correctionlib.schemav2.CorrectionSet.model_validate(data)
    raise ValueError(f"Unknown CorrectionSet schema version ({version})")


# TODO: create a ufunc with numpy.vectorize in constructor?
def _call_as_numpy(
    array_args: Any,
    func: Callable[..., Any] = lambda: None,
    non_array_args: Any = tuple(),
    arg_indices: Any = tuple(),
    **kwargs: Any,
) -> Any:
    import awkward

    if version.parse(awkward.__version__) < _min_version_ak:
        raise RuntimeError(
            f"""imported awkward is version {awkward.__version__} < {str(_min_version_ak)}
            If you cannot upgrade, try doing: ak.flatten(arrays) -> result = correction(arrays) -> ak.unflatten(result, counts)
            """
        )

    if not isinstance(array_args, (list, tuple)):
        array_args = (array_args,)

    if all(
        x.is_numpy or not isinstance(x, awkward.contents.Content) for x in array_args
    ):
        vargs = [
            awkward.to_numpy(awkward.typetracer.length_zero_if_typetracer(arg))
            for arg in array_args
        ]
        bargs = numpy.broadcast_arrays(*vargs)
        oshape = bargs[0].shape
        fargs = (arg.flatten() for arg in bargs)

        repacked_args = [None] * len(arg_indices)
        array_args_len = len(array_args)
        for i in range(len(arg_indices)):
            if i < array_args_len:
                repacked_args[arg_indices[i]] = next(fargs)
            else:
                repacked_args[arg_indices[i]] = non_array_args[i - array_args_len]

        out = func(*repacked_args)
        out = awkward.contents.NumpyArray(out.reshape(oshape))
        if awkward.backend(*array_args) == "typetracer":
            out = out.to_typetracer(forget_length=True)
        return out
    return None


def _wrap_awkward(
    func: Callable[..., Any],
    *args: Union["numpy.ndarray[Any, Any]", str, int, float],
) -> Any:
    from functools import partial

    import awkward

    array_args = []
    non_array_args = []
    array_indices = []
    non_array_indices = []

    for iarg, arg in enumerate(args):
        if not isinstance(arg, (str, int, float)):
            array_args.append(arg)
            array_indices.append(iarg)
        else:
            non_array_args.append(arg)
            non_array_indices.append(iarg)

    array_args = awkward.broadcast_arrays(*array_args)

    arg_indices = array_indices + non_array_indices

    tocall = partial(
        _call_as_numpy,
        func=func,  # type: ignore
        non_array_args=non_array_args,
        arg_indices=arg_indices,
    )

    return awkward.transform(tocall, *array_args)


def _call_dask_correction(
    correction: Any,
    *args: Union["numpy.ndarray[Any, Any]", str, int, float],
):
    return _wrap_awkward(correction._base.evalv, *args)


def _wrap_dask_awkward(
    correction: Any,
    *args: Union["numpy.ndarray[Any, Any]", str, int, float],
) -> Any:
    import dask.delayed
    import dask_awkward

    if version.parse(dask_awkward.__version__) < _min_version_dak:
        raise RuntimeError(
            f"""imported dask_awkward is version {dask_awkward.__version__} < {str(_min_version_dak)}
            This version of dask_awkward includes several useful bugfixes and functionality extensions.
            Please upgrade dask_awkward.
            """
        )

    if not hasattr(correction, "_delayed_correction"):
        setattr(  # noqa: B010
            correction,
            "_delayed_correction",
            dask.delayed(correction),
        )

    correction_meta = _wrap_awkward(
        correction._base.evalv,
        *(arg._meta if isinstance(arg, dask_awkward.Array) else arg for arg in args),
    )

    return dask_awkward.map_partitions(
        _call_dask_correction,
        correction._delayed_correction,
        *args,
        meta=correction_meta,
        label=correction._name,
    )


class Correction:
    """High-level correction evaluator object

    This class is typically instantiated by accessing a named correction from
    a CorrectionSet object, rather than directly by construction.
    """

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

    @property
    def inputs(self) -> List[correctionlib._core.Variable]:
        return self._base.inputs

    @property
    def output(self) -> correctionlib._core.Variable:
        return self._base.output

    def evaluate(
        self, *args: Union["numpy.ndarray[Any, Any]", str, int, float]
    ) -> Union[float, "numpy.ndarray[Any, numpy.dtype[numpy.float64]]"]:
        # TODO: create a ufunc with numpy.vectorize in constructor?
        if any(str(type(arg)).startswith("<class 'dask.array.") for arg in args):
            raise TypeError(
                "Correctionlib does not yet handle dask.array collections. "
                "If you require this functionality (i.e. you cannot or do "
                "not want to use dask_awkward/awkward arrays) please open an "
                "issue at https://github.com/cms-nanoAOD/correctionlib/issues."
            )
        try:
            vargs = [
                numpy.asarray(arg)
                for arg in args
                if not isinstance(arg, (str, int, float))
            ]
        except NotImplementedError:
            if any(str(type(arg)).startswith("<class 'dask_awkward.") for arg in args):
                return _wrap_dask_awkward(self, *args)  # type: ignore
        except (ValueError, TypeError):
            if any(str(type(arg)).startswith("<class 'awkward.") for arg in args):
                return _wrap_awkward(self._base.evalv, *args)  # type: ignore
        except Exception as err:
            raise err

        if vargs:
            bargs = numpy.broadcast_arrays(*vargs)
            oshape = bargs[0].shape
            fargs = (arg.flatten() for arg in bargs)
            out = self._base.evalv(
                *(
                    next(fargs) if not isinstance(arg, (str, int, float)) else arg
                    for arg in args
                )
            )
            return out.reshape(oshape)
        return self._base.evaluate(*args)  # type: ignore


class CompoundCorrection:
    """High-level compound correction evaluator object

    This class is typically instantiated by accessing a named correction from
    a CorrectionSet object, rather than directly by construction.
    """

    def __init__(
        self, base: correctionlib._core.CompoundCorrection, context: "CorrectionSet"
    ):
        self._base = base
        self._name = base.name
        self._context = context

    def __getstate__(self) -> Dict[str, Any]:
        return {"_context": self._context, "_name": self._name}

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self._context = state["_context"]
        self._name = state["_name"]
        self._base = self._context.compound[self._name]._base

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._base.description

    @property
    def inputs(self) -> List[correctionlib._core.Variable]:
        return self._base.inputs

    @property
    def output(self) -> correctionlib._core.Variable:
        return self._base.output

    def evaluate(
        self, *args: Union["numpy.ndarray[Any, Any]", str, int, float]
    ) -> Union[float, "numpy.ndarray[Any, numpy.dtype[numpy.float64]]"]:
        # TODO: create a ufunc with numpy.vectorize in constructor?
        if any(str(type(arg)).startswith("<class 'dask.array.") for arg in args):
            raise TypeError(
                "Correctionlib does not yet handle dask.array collections. "
                "if you require this functionality (i.e. you cannot or do "
                "not want to use dask_awkward/awkward arrays) please open an "
                "issue at https://github.com/cms-nanoAOD/correctionlib/issues."
            )
        try:
            vargs = [
                numpy.asarray(arg)
                for arg in args
                if not isinstance(arg, (str, int, float))
            ]
        except NotImplementedError:
            if any(str(type(arg)).startswith("<class 'dask_awkward.") for arg in args):
                return _wrap_dask_awkward(self, *args)  # type: ignore
        except (ValueError, TypeError):
            if any(str(type(arg)).startswith("<class 'awkward.") for arg in args):
                return _wrap_awkward(self._base.evalv, *args)  # type: ignore
        except Exception as err:
            raise err

        if vargs:
            bargs = numpy.broadcast_arrays(*vargs)
            oshape = bargs[0].shape
            fargs = (arg.flatten() for arg in bargs)
            out = self._base.evalv(
                *(
                    next(fargs) if not isinstance(arg, (str, int, float)) else arg
                    for arg in args
                )
            )
            return out.reshape(oshape)
        return self._base.evaluate(*args)  # type: ignore


class _CompoundMap(Mapping[str, CompoundCorrection]):
    def __init__(
        self,
        base: Mapping[str, correctionlib._core.CompoundCorrection],
        context: "CorrectionSet",
    ):
        self._base = base
        self._context = context

    def __getitem__(self, key: str) -> CompoundCorrection:
        corr = self._base.__getitem__(key)
        return CompoundCorrection(corr, self._context)

    def __len__(self) -> int:
        return len(self._base)

    def __iter__(self) -> Iterator[str]:
        return iter(self._base)


class CorrectionSet(Mapping[str, Correction]):
    """High-level correction set evaluator object

    This class can be initialized directly from a string or model with compatible
    schema version, or can be initialized via the ``from_file`` or
    ``from_string`` factory methods. Corrections can be accessed
    via getitem syntax, e.g. ``cset["some correction"]``.
    """

    def __init__(self, data: Any):
        if isinstance(data, str):
            self._data = data
        else:
            self._data = data.model_dump_json(exclude_unset=True)
        self._base = correctionlib._core.CorrectionSet.from_string(self._data)

    @classmethod
    def from_file(cls, filename: str) -> "CorrectionSet":
        return cls(open_auto(filename))

    @classmethod
    def from_string(cls, data: str) -> "CorrectionSet":
        return cls(data)

    def __getstate__(self) -> Dict[str, Any]:
        return {"_data": self._data}

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self._data = state["_data"]
        self._base = correctionlib._core.CorrectionSet.from_string(self._data)

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

    @property
    def compound(self) -> _CompoundMap:
        return _CompoundMap(self._base.compound, self)
