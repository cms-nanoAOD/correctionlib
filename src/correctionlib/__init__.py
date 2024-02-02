import sys

if sys.platform.startswith("win32"):
    import ctypes

    from .util import this_module_path

    ctypes.CDLL(str(this_module_path() / "lib" / "correctionlib.dll"))


from .binding import register_pyroot_binding
from .highlevel import Correction, CorrectionSet
from .version import version as __version__

__all__ = ("__version__", "CorrectionSet", "Correction", "register_pyroot_binding")
