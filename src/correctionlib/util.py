import pathlib
import sys


def this_module_path() -> pathlib.Path:
    # TODO: this package could be a zipball, in which case these paths are temporary
    # We could warn but there is an almost negligible chance this is the case
    if sys.version_info < (3, 9):
        # use deprecated API
        import pkg_resources

        return pathlib.Path(pkg_resources.resource_filename("correctionlib", ""))
    import importlib.resources

    return importlib.resources.files("correctionlib")
