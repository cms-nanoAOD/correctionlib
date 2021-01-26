import libcorrection

cset = libcorrection.CorrectionSet("data/examples.json")
for corr in cset:
    print(corr.name())

sf = cset["DeepCSV_2016LegacySF"]
out = sf.evaluate("central", 0, 1.2, 35., 0.01)
print(out)
out = sf.evaluate("central", 0, 1.2, 35., 0.3)
print(out)
