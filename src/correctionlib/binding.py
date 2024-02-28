def register_pyroot_binding() -> None:
    import sys

    from cppyy import gbl

    from .util import this_module_path

    base_path = this_module_path()
    lib = base_path / "lib"

    # maybe not the most robust solution?
    if sys.platform.startswith("win32"):
        lib = lib / "correctionlib.dll"
    elif sys.platform.startswith("darwin"):
        lib = lib / "libcorrectionlib.dylib"
    else:
        lib = lib / "libcorrectionlib.so"
    gbl.gSystem.Load(str(lib))
    gbl.gInterpreter.AddIncludePath(str(base_path / "include"))
    gbl.gROOT.ProcessLine('#include "correction.h"')
