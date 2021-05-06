# correctionlib

[![Actions Status][actions-badge]][actions-link]
[![Documentation Status][rtd-badge]][rtd-link]
[![Code style: black][black-badge]][black-link]

[![PyPI version][pypi-version]][pypi-link]
[![PyPI platforms][pypi-platforms]][pypi-link]

[![GitHub Discussion][github-discussions-badge]][github-discussions-link]

## Introduction
The purpose of this library is to provide a well-structured JSON data format for a
wide variety of ad-hoc correction factors encountered in a typical HEP analysis and
a companion evaluation tool suitable for use in C++ and python programs.
Here we restrict our definition of correction factors to a class of functions with
scalar inputs that produce a scalar output.

In python, the function signature is:

```python
from typing import Union

def f(*args: Union[str,int,float]) -> float:
    return ...
```

In C++, the evaluator implements this currently as:
```cpp
double Correction::evaluate(const std::vector<std::variant<int, double, std::string>>& values) const;
```

The supported function classes include:

  * multi-dimensional binned lookups;
  * binned lookups pointing to multi-argument formulas with a restricted
    math function set (`exp`, `sqrt`, etc.);
  * categorical (string or integer enumeration) maps;
  * input transforms (updating one input value in place); and
  * compositions of the above.

Each function type is represented by a "node" in a call graph and holds all
of its parameters in a JSON structure, described by the JSON schema.
Possible future extension nodes might include weigted sums (which, when composed with
the others, could represent a BDT) and perhaps simple MLPs.

The tool should provide:

  * standardized, versioned [JSON schemas](https://json-schema.org/);
  * forward-porting tools (to migrate data written in older schema versions); and
  * a well-optimized C++ evaluator and python bindings (with numpy vectorization support).

This tool will definitely not provide:

  * support for `TLorentzVector` or other object-type inputs (such tools should be written
    as a higher-level tool depending on this library as a low-level tool)

Formula support currently includes a mostly-complete subset of the ROOT library `TFormula` class,
and is implemented in a threadsafe standalone manner. The parsing grammar is formally defined
and parsed through the use of a header-only [PEG parser library](https://github.com/yhirose/cpp-peglib).
The supported features mirror CMSSW's [reco::formulaEvaluator](https://github.com/cms-sw/cmssw/pull/11516)
and fully passes the test suite for that utility with the purposeful exception of the `TMath::` namespace.
The python bindings may be able to call into [numexpr](https://numexpr.readthedocs.io/en/latest/user_guide.html),
though, due to the tree-like structure of the corrections, it may prove difficult to exploit vectorization
at levels other than the entrypoint.

## Installation

The build process is based on setuptools, with CMake (through scikit-build)
for the C++ evaluator and its python bindings module.
Builds have been tested in Windows, OS X, and Linux, and python bindings can be compiled against both
python2 and python3, as well as from within a CMSSW environment. The python bindings are distributed as a
pip-installable package. Note that CMSSW 11_2_X and above has ROOT accessible from python 3.

To install in an environment that has python 3, you can simply
```bash
python3 -m pip install correctionlib
```
(possibly with `--user`, or in a virtualenv, etc.)
If you wish to install the latest development version,
```bash
python3 -m pip install git+https://github.com/cms-nanoAOD/correctionlib.git
```
should work.

The C++ evaluator library is distributed as part of the python package, and it can be
linked to directly without using python. If you are using CMake you can depend on it by including
the output of `correction config --cmake` in your cmake invocation. A complete cmake
example that builds a user C++ application against correctionlib and ROOT RDataFrame
can be [found here](https://gist.github.com/pieterdavid/a560e65658386d70a1720cb5afe4d3e9).

For manual compilation, include and linking definitions can similarly be found via `correction config --cflags --ldflags`.
For example, the demo application can be compiled with:
```bash
wget https://raw.githubusercontent.com/cms-nanoAOD/correctionlib/master/src/demo.cc
g++ $(correction config --cflags --ldflags --rpath) demo.cc -o demo
```

If the `correction` command-line utility is not on your path for some reason, it can also be invoked via `python -m correctionlib.cli`.

To compile with python2 support, consider using python 3 :) If you considered that and still
want to use python2, the following recipe may work:
```bash
git clone --recursive git@github.com:cms-nanoAOD/correctionlib.git
cd correctionlib
make PYTHON=python2 correctionlib
```
Inside CMSSW you should use `make PYTHON=python correctionlib` assuming `python` is the name of the scram tool you intend to link against.
This will output a `correctionlib` directory that acts as a python package, and can be moved where needed.
This package will only provide the `correctionlib._core` evaluator module, as the schema tools and high-level bindings are python3-only.

## Creating new corrections

The `correctionlib.schemav2` module provides a helpful framework for defining correction objects
and `correctionlib.convert` includes select conversion routines for common types. Nodes can be type-checked as they are
constructed using the [parse_obj](https://pydantic-docs.helpmanual.io/usage/models/#helper-functions)
class method or by directly constructing them using keyword arguments.
Some examples can be found in `data/conversion.py`. The `tests/` directory may also be helpful.

## Developing
See CONTRIBUTING.md

[actions-badge]:            https://github.com/cms-nanoAOD/correctionlib/workflows/CI/badge.svg
[actions-link]:             https://github.com/cms-nanoAOD/correctionlib/actions
[black-badge]:              https://img.shields.io/badge/code%20style-black-000000.svg
[black-link]:               https://github.com/psf/black
[conda-badge]:              https://img.shields.io/conda/vn/conda-forge/correctionlib
[conda-link]:               https://github.com/conda-forge/correctionlib-feedstock
[github-discussions-badge]: https://img.shields.io/static/v1?label=Discussions&message=Ask&color=blue&logo=github
[github-discussions-link]:  https://github.com/cms-nanoAOD/correctionlib/discussions
[gitter-badge]:             https://badges.gitter.im/https://github.com/cms-nanoAOD/correctionlib/community.svg
[gitter-link]:              https://gitter.im/https://github.com/cms-nanoAOD/correctionlib/community?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge
[pypi-link]:                https://pypi.org/project/correctionlib/
[pypi-platforms]:           https://img.shields.io/pypi/pyversions/correctionlib
[pypi-version]:             https://badge.fury.io/py/correctionlib.svg
[rtd-badge]:                https://github.com/cms-nanoAOD/correctionlib/actions/workflows/docs.yml/badge.svg
[rtd-link]:                 https://cms-nanoAOD.github.io/correctionlib/
