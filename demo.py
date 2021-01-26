import libcorrection

cset = libcorrection.CorrectionSet("data/examples.json")
for corr in cset:
    print(corr.name())

out = cset["DeepCSV_2016LegacySF"].evaluate(["central", 0, 1.2, 35., 0.01]);
print(out)
