import os
import shutil
import subprocess
import tempfile

import pytest

import correctionlib
import correctionlib.schemav2 as cs


@pytest.fixture(scope="module")
def csetstr():
    ptweight = cs.Correction(
        name="ptweight",
        version=1,
        inputs=[
            cs.Variable(name="pt", type="real", description="Muon transverse momentum")
        ],
        output=cs.Variable(
            name="weight", type="real", description="Multiplicative event weight"
        ),
        data=cs.Binning(
            nodetype="binning",
            input="pt",
            edges=[10, 20, 30, 40, 50, 80, 120],
            content=[1.1, 1.08, 1.06, 1.04, 1.02, 1.0],
            flow="clamp",
        ),
    )
    cset = cs.CorrectionSet(schema_version=2, corrections=[ptweight])
    return cset.model_dump_json().replace('"', r"\"")


def test_pyroot_binding(csetstr: str):
    ROOT = pytest.importorskip("ROOT")
    correctionlib.register_pyroot_binding()
    assert ROOT.correction.CorrectionSet

    ROOT.gInterpreter.Declare(
        f'auto cset = correction::CorrectionSet::from_string("{csetstr}");'  # noqa: B907
    )
    ROOT.gInterpreter.Declare('auto corr = cset->at("ptweight");')
    assert ROOT.corr.evaluate([1.2]) == 1.1


CMAKELIST_SRC = """\
cmake_minimum_required(VERSION 3.21 FATAL_ERROR)
project(test)
find_package(correctionlib)
add_executable(test test.cc)
target_link_libraries(test PRIVATE correctionlib)
# Because windows has no RPATH, we need to copy the DLLs to the executable directory
add_custom_command(TARGET test POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy -t $<TARGET_FILE_DIR:test> $<TARGET_RUNTIME_DLLS:test>
  COMMAND_EXPAND_LISTS
)
"""

TESTPROG_SRC = """\
#include <iostream>
#include "correction.h"

using correction::CorrectionSet;

int main(int argc, char** argv) {
  constexpr std::string_view expected_version = "%s";
  if (correction::correctionlib_version != expected_version) {
    std::cerr << "correctionlib version mismatch: expected "
        << expected_version << ", got " <<
        correction::correctionlib_version << std::endl;
    return 1;
  }
  auto cset = CorrectionSet::from_string("%s");
  auto corr = cset->at("ptweight");
  if (corr->evaluate({1.2}) != 1.1) {
    return 1;
  }
  return 0;
}
"""


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not found")
@pytest.mark.skipif(os.name == "nt", reason="there is a segfault I cannot debug")
def test_cmake_static_compilation(csetstr: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        cmake = os.path.join(tmpdir, "CMakeLists.txt")
        with open(cmake, "w") as f:
            f.write(CMAKELIST_SRC)
        testprog = os.path.join(tmpdir, "test.cc")
        # SKBUILD_PROJECT_VERSION only includes major.minor.patch
        versionstr = ".".join(correctionlib.__version__.split(".")[:3])
        with open(testprog, "w") as f:
            f.write(TESTPROG_SRC % (versionstr, csetstr))
        flags = (
            subprocess.check_output(["correction", "config", "--cmake"])
            .decode()
            .split()
        )
        ret = subprocess.run(["cmake", "."] + flags, capture_output=True, cwd=tmpdir)
        if ret.returncode != 0:
            print(ret.stdout.decode())
            print(ret.stderr.decode())
            raise RuntimeError(f"cmake configuration failed (args: {ret.args})")
        ret = subprocess.run(["cmake", "--build", "."], capture_output=True, cwd=tmpdir)
        if ret.returncode != 0:
            print(ret.stdout.decode())
            print(ret.stderr.decode())
            raise RuntimeError(f"cmake build failed (args: {ret.args})")
        prog = r"Debug\test.exe" if os.name == "nt" else "test"
        subprocess.run(
            [os.path.join(tmpdir, prog)], capture_output=True, check=True, cwd=tmpdir
        )
