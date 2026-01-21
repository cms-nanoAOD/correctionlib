import json

import correctionlib
import correctionlib.schemav2 as cs

# 1. Define a Correction using the NEW 'Switch' node
#    Logic: IF eta <= 3.0 THEN return 1.0 (Pass) ELSE return 0.0 (Fail)
#    This tests the specific inclusive boundary that 'Binning' failed to handle.
corr = cs.Correction(
    name="boundary_test",
    version=1,
    inputs=[cs.Variable(name="eta", type="real")],
    output=cs.Variable(name="weight", type="real"),
    data=cs.Switch(
        nodetype="switch",
        inputs=["eta"],
        selections=[
            cs.Comparison(
                variable="eta",
                op="<=",  # <--- The operator you couldn't use before!
                value=3.0,
                content=1.0,
            )
        ],
        default=0.0,
    ),
)

# 2. Serialize to JSON (using Pydantic v2 method)
json_str = corr.model_dump_json(exclude_unset=True)
print(f"Generated JSON with Switch node:\n{json_str}\n")

# 3. Load it back into the C++ Evaluator
#    We wrap it in a CorrectionSet object manually for loading
cset_json = json.dumps({"schema_version": 2, "corrections": [json.loads(json_str)]})
cset = correctionlib.CorrectionSet.from_string(cset_json)
evaluator = cset["boundary_test"]

# 4. Evaluate the Edge Case
print("-" * 40)
print("TESTING C++ EVALUATOR")
print("-" * 40)

# Case A: 3.0 exactly (The Problem Child)
# With Binning [2.7, 3.0), this failed. With Switch (eta <= 3.0), this MUST pass.
val_inclusive = 3.0
res_inclusive = evaluator.evaluate([val_inclusive])
print(f"Input: {val_inclusive:<10} | Expected: 1.0 | Got: {res_inclusive}")

# Case B: 3.00001 (Just above)
val_exclusive = 3.00001
res_exclusive = evaluator.evaluate([val_exclusive])
print(f"Input: {val_exclusive:<10} | Expected: 0.0 | Got: {res_exclusive}")

if res_inclusive == 1.0 and res_exclusive == 0.0:
    print("\n[SUCCESS] The Switch node correctly handles inclusive boundaries!")
else:
    print("\n[FAIL] Logic error in Switch node implementation.")
