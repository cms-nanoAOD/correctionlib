#!/usr/bin/env python
# Copyright (c) 2021, Nick Smith
#
# Distributed under the 3-clause BSD license, see accompanying file LICENSE
# or https://github.com/nsmith-/correctionlib for details.

from setuptools import find_packages
from setuptools_scm import get_version
from skbuild import setup

setup(
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    cmake_install_dir="src",
    cmake_args=[
        "-DCORRECTIONLIB_VERSION={}".format(".".join(get_version().split(".")[:2]))
    ],
)
