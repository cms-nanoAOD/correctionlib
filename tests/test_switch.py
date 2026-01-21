import json

import correctionlib
import correctionlib.schemav2 as cs

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
                op="<=", 
                value=3.0,
                content=1.0,
            )
        ],
        default=0.0,
    ),
)

json_str = corr.model_dump_json(exclude_unset=True)
print(f"Generated JSON with Switch node:\n{json_str}\n")

cset_json = json.dumps({"schema_version": 2, "corrections": [json.loads(json_str)]})
cset = correctionlib.CorrectionSet.from_string(cset_json)
evaluator = cset["boundary_test"]

print("-" * 40)
print("TESTING C++ EVALUATOR")
print("-" * 40)

val_inclusive = 3.0
res_inclusive = evaluator.evaluate([val_inclusive])
print(f"Input: {val_inclusive:<10} | Expected: 1.0 | Got: {res_inclusive}")

val_exclusive = 3.00001
res_exclusive = evaluator.evaluate([val_exclusive])
print(f"Input: {val_exclusive:<10} | Expected: 0.0 | Got: {res_exclusive}")

if res_inclusive == 1.0 and res_exclusive == 0.0:
    print("\n[SUCCESS] The Switch node correctly handles inclusive boundaries!")
else:
    print("\n[FAIL] Logic error in Switch node implementation.")
