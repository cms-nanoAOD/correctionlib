from correctionlib.schemav1 import CorrectionSet
import gzip

x = CorrectionSet.parse_file("data/corrections.json")

with gzip.open("data/examples.json.gz") as fin:
    y = CorrectionSet.parse_raw(fin.read())
