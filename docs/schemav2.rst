Schema v2
---------
Second iteration of the schema

Numeric fields require real numbers or integers as appropriate; quoted numbers,
booleans, and complex numbers are rejected during model validation. Integer
values remain valid in real-valued fields, and Python numeric authoring inputs
such as NumPy scalars are supported. The explicit infinity strings in bin edges
remain valid. Category keys must match the referenced input's integer or string
type, including categories nested inside other nodes.

These checks apply when constructing or validating models. Models remain mutable
for authoring; bypassing validation or modifying an existing model does not
guarantee that the evaluator can load it. Schema v1 validation is unchanged.

:download:`Download json <_generated/schemav2.json>`.

.. jsonschema:: _generated/schemav2.json
    :lift_description:
    :lift_definitions:
    :auto_target:
    :auto_reference:
