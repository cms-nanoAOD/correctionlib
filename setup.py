#!/usr/bin/env python
# Copyright (c) 2021, Nick Smith
#
# Distributed under the 3-clause BSD license, see accompanying file LICENSE
# or https://github.com/nsmith-/correctionlib for details.

import shutil

from setuptools import find_packages
from setuptools_scm import get_version
from skbuild import setup

setup_requires = []
if shutil.which("cmake") is None:
    setup_requires += ["cmake>=3.11.0"]

setup(
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    cmake_install_dir="src",
    cmake_args=[f"-DCORRECTIONLIB_VERSION:STRING={get_version()}"],
    setup_requires=setup_requires,
)
