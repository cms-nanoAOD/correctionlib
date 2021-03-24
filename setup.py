#!/usr/bin/env python
# Copyright (c) 2021, Nick Smith
#
# Distributed under the 3-clause BSD license, see accompanying file LICENSE
# or https://github.com/nsmith-/correctionlib for details.

import sys

from setuptools import setup  # isort:skip

# Available at setup time due to pyproject.toml
from pybind11.setup_helpers import Pybind11Extension  # isort:skip

# Note:
#   Sort input source files if you glob sources to ensure bit-for-bit
#   reproducible builds (https://github.com/pybind/python_example/pull/53)

if sys.platform.startswith("win"):
    extra_compile_args = ["/Zc:__cplusplus", "/O2"]
else:
    extra_compile_args = ["-O3"]

ext_modules = [
    Pybind11Extension(
        "correctionlib._core",
        ["src/python.cc", "src/correction.cc", "src/formula_ast.cc"],
        cxx_std=17,
        include_pybind11=False,
        include_dirs=["rapidjson/include", "pybind11/include", "cpp-peglib", "include"],
        extra_compile_args=extra_compile_args,
    ),
]


setup(
    ext_modules=ext_modules,
)
