import correctionlib._core as core


def test_examples():
    cset = core.CorrectionSet("data/examples.json")
    for corr in cset:
        print(corr.name())

    sf = cset["DeepCSV_2016LegacySF"]
    out = sf.evaluate("central", 0, 1.2, 35.0, 0.01)
    print(out)
    out = sf.evaluate("central", 0, 1.2, 35.0, 0.3)
    print(out)
