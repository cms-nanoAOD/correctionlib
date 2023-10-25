# Correctionlib architecture

This document briefly describes the architecture of correctionlib.
It is meant to provide a good starting point for new contributors to find their way around the codebase.
It assumes some familiarity with correctionlib as a user.

## Python modules

- `schemav2` module: Pydantic models for correctionlib's data structures
	- `CorrectionSet` is a list of `Correction`s
	- `Correction` represents a single correction. Its `data` attribute is of `Content` type and represents the root node of the computation graph for this correction. Corrections also have a list of inputs as well as one output of type `Variable` (basically a pair of a name and a type, int/float/string) and
	- `Content` is the type of a node in the computation graph of a `Correction`. It's a `Union` of the various types of corrections available: `Binning`, `MultiBinning`, `Category`, `Formula`, `FormulaRef`, `Transform`, `HashPRNG`, float
- `highlevel` module: user-facing types (`correctionlib.Correction` resolves to `correctionlib.highlevel.Correction`, etc.)
	- `CorrectionSet` is a list of `Correction`s (same as in `schemav2` but focus is on user API rather than defining the schema/structure of the corrections)
	- `Correction` and `CompoundCorrection` wrap the corresponding C++ evaluator and expose the `evaluate` method
- `_core` module: a small module that contains the Python facades for the corresponding C++ types, in `__init__.pyi`.
	- types are `CorrectionSet`, `Correction`, `CompoundCorrection` and `Variable`
	- the bindings are declared in `src/python.cc`

## C++ sources

`include/correction.h` and `src/correction.cc` contain the the C++ types that perform the actual computations:

- a `Variable` type with a name and a type (string, integer, real)
- a `CorrectionSet` builds a list of `Corrections`
- the `Correction` type, which builds a compute graph of correction nodes
- types for the different types of nodes in a correction's compute graph, e.g. `Binning`, `Formula`, each with its `evaluate` method. They are constructed by deserializing a JSON object. `Formula::Formula`, for example, parses a `TFormula` expression in the JSON and builds the corresponding `FormulaAST`

## Typical call sequence to evaluate a correction

![Diagram describing the call sequence that starts with `Correction.evaluate`](./docs/evaluate_call_sequence.png).

## Building a Correction object

In short, the C++ correction objects that perform the actual correction evaluations are constructed from the JSON representations of the Pydantic types defined in `schemav2`.

Let's say the user calls `schemav2.Correction.to_evaluator`. This:
- constructs a `schemav2.CorrectionSet` (the pydantic model)
- constructs a `highlevel.CorrectionSet` from it and immediately extracts the right `highlevel.Correction` from it, returning it

The actual construction of the internal C++ correction evaluators happens in the construction of the `highlevel.CorrectionSet`, which converts the Pydantic `CorrectionSet` to JSON and uses it to construct a `_core.CorrectionSet` (using `CorrectionSet.from_string`)
- `_core.CorrectionSet.from_string` constructs a rapidjson JSONObject and calls `CorrectionSet(const JSONObject &)`
- then for each object in JSONObject it constructs a Correction (`Correction(const JSONObject&)`), and puts it in `CorrectionSet::corrections_`
- `Correction::Correction(const JSONObject&)` sets `data_` to the output of `resolve_content`, passing the json
- `resolve_content` (defined in correction.cc) constructs the appropriate type depending on the JSON input (if/else-ing over the known correction types)
