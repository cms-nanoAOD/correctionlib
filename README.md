correctionlib
=============

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

Eventually, the supported function classes may include:

  * multi-dimensional binned lookups;
  * binned lookups pointing to multi-argument formulas with a restricted
    math function set (`exp`, `sqrt`, etc., TBD);
  * categorical (string or integer enumeration) maps; and
  * compositions of the above.

Each function type is represented by a "node" in a call graph and holds all
of its parameters in a JSON structure, described by the JSON schema.
Possible future extension nodes might include weigted sums (which, when composed with
the others, could represent a BDT) and perhaps simple MLPs.

Eventually, the tool should provide:

  * standardized, versioned [JSON schemas](https://json-schema.org/);
  * forward-porting tools (to migrate data written in older schema versions); and
  * a well-optimized C++ evaluator and python bindings (with numpy vectorization support).

This tool will definitely not provide:

  * support for `TLorentzVector` or other object-type inputs (such tools should be written
    as a higher-level tool depending on this library as a low-level tool)

Formula support is implemented using the [cpp-peglib](https://github.com/yhirose/cpp-peglib)
PEG parser and an AST evaluator. Grammars are currently available for:

  * a decently sized subset of ROOT::TFormula expressions

# Installation

Currently, the build process is entirely Makefile-based. Eventually it would be nice to use
CMake or possibly setuptools in the context of the python bindings. Builds have been tested
in OS X and Linux, and python bindings can be compiled against both python2 and python3, as
well as from within a CMSSW environment. The python bindings should be distributable as a
pip-installable package, but we haven't decided exactly how that will look.

To build in most environments (tested in CMSSW 10_2 and 10_6):
```bash
git clone --recursive git@github.com:nsmith-/correctionlib.git
cd correctionlib
python3 -m pip install -r requirements.txt
make
# demo C++ binding, main function at src/demo.cc
./demo data/examples.json
# demo python binding
python3 demo.py
```

To compile with python2 support, use `make PYTHON=python2 all` (don't forget to `make clean` first).
The pydantic schema tools only support python3, however the evaluator can still be used with JSON files
that conform to the schema.

# Creating new corrections

The `correctionlib` python package (as opposed to the `libcorrection` evaluator package) provides a helpful
framework for defining correction objects. Nodes can be type-checked as they are constructed using the
[parse_obj](https://pydantic-docs.helpmanual.io/usage/models/#helper-functions) class method.
Some examples can be found in `convert.ipynb`.
