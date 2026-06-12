import importlib.resources
import pathlib
import sys


def this_module_path() -> pathlib.Path:
    # TODO: this package could be a zipball, in which case these paths are temporary
    # We could warn but there is an almost negligible chance this is the case
    if sys.version_info < (3, 9):
        # use deprecated API
        import pkg_resources

        return pathlib.Path(pkg_resources.resource_filename("correctionlib", ""))

    traversable = importlib.resources.files("correctionlib")
    with importlib.resources.as_file(traversable) as fspath:
        return fspath


def artifact_base_dir() -> pathlib.Path:
    """Find the base directory containing built artifacts (include, lib, cmake).

    In editable installs the artifacts live next to the compiled extension module,
    not in the source tree. Falls back to this_module_path() for regular installs.
    """
    import correctionlib._core as _core

    base = pathlib.Path(_core.__file__).resolve().parent
    if (base / "cmake").exists() and (base / "include").exists():
        return base

    return this_module_path()
