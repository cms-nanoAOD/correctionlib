from .version import version as __version__

__all__ = ("__version__",)

import sys

if sys.platform.startswith("win32"):
    import ctypes
    import os
    import os.path

    ctypes.CDLL(os.path.join(os.path.dirname(__file__), "lib", "correctionlib.dll"))
