import sys

if sys.platform.startswith("win32"):
    import ctypes

    import importlib.resources

    ctypes.CDLL(
        str(importlib.resources.files("correctionlib") / "lib" / "correctionlib.dll")
    )


from .binding import register_pyroot_binding
from .highlevel import Correction, CorrectionSet
from .version import version as __version__

__all__ = ("__version__", "CorrectionSet", "Correction", "register_pyroot_binding")
