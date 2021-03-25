#!/usr/bin/env python
# Copyright (c) 2021, Nick Smith
#
# Distributed under the 3-clause BSD license, see accompanying file LICENSE
# or https://github.com/nsmith-/correctionlib for details.

from skbuild import setup
from setuptools import find_packages
setup(packages=find_packages(where="src"), package_dir={"": "src"}, cmake_install_dir="src")
