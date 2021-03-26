from .version import version as __version__

__all__ = ("__version__",)

import sys
if sys.platform.startswith("win32"):
    import ctypes
    import pkg_resources
    import os, os.path
    try:
        ctypes.CDLL(pkg_resources.resource_filename(__name__, os.path.join("lib", "correctionlib.dll")))
    except Exception as ex:
        print(f'Failed to load {pkg_resources.resource_filename(__name__, os.path.join("lib", "correctionlib.dll"))}')
        print(f'Contents of "correctionlib/lib": {os.listdir(pkg_resources.resource_filename("correctionlib", "lib"))}')
