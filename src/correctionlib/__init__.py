import sys

if sys.platform.startswith("win32"):
    import ctypes
    import os.path

    import pkg_resources

    ctypes.CDLL(
        pkg_resources.resource_filename(
            "correctionlib", os.path.join("lib", "correctionlib.dll")
        )
    )


from .binding import register_pyroot_binding
from .highlevel import Correction, CorrectionSet
from .version import version as __version__

__all__ = ("__version__", "CorrectionSet", "Correction", "register_pyroot_binding")
