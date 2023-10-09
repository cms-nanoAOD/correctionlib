def register_pyroot_binding() -> None:
    import sys

    import importlib.resources
    from cppyy import gbl

    base_path = importlib.resources.files("correctionlib")
    lib = base_path / "lib"

    # maybe not the most robust solution?
    if sys.platform.startswith("win32"):
        lib = lib / "correctionlib.dll"
    elif sys.platform.startswith("darwin"):
        lib = lib / "libcorrectionlib.dylib"
    else:
        lib = lib / "libcorrectionlib.so"
    gbl.gSystem.Load(lib)
    gbl.gInterpreter.AddIncludePath(base_path / "include")
    gbl.gROOT.ProcessLine('#include "correction.h"')
