import sys

if sys.platform.startswith("win32"):
    import ctypes
    import os.path

    ctypes.CDLL(os.path.join(os.path.dirname(__file__), "lib", "correctionlib.dll"))


from .highlevel import Correction, CorrectionSet
from .version import version as __version__

__all__ = ("__version__", "CorrectionSet", "Correction")
