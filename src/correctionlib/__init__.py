from .version import version as __version__

__all__ = ("__version__",)

import sys
if sys.platform.startswith("win32"):
    import ctypes
    import os, os.path
    try:
        ctypes.CDLL(os.path.join(os.path.dirname(__file__), "lib", "correctionlib.dll"))
    except Exception as ex:
        print(f'Failed to load {os.path.join(os.path.dirname(__file__), "lib", "correctionlib.dll")}')
        print(f'Contents of "correctionlib/lib": {os.listdir(os.path.join(os.path.dirname(__file__), "lib"))}')
