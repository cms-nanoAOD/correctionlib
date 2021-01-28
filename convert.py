#!/usr/bin/env python
# # Converting other formats to correctionlib json
# An attempt to convert some of the correction types known to CMS coffea `lookup_tools`.
import uproot
import pandas
import requests
import gzip
from correctionlib.schemav2 import CorrectionSet, Correction, Binning, Category, Formula

examples = "https://raw.githubusercontent.com/CoffeaTeam/coffea/master/tests/samples"

# `sf` is a binned event weight to be applied as a function of $\eta$ and $p_T$
sf = uproot.open(
    f"{examples}/testSF2d.histo.root:scalefactors_Tight_Electron"
).to_boost()


corr1 = Correction.parse_obj(
    {
        "version": 0,
        "name": "scalefactors_Tight_Electron",
        "inputs": [
            {
                "type": "real",
                "name": "eta",
                "description": "possibly supercluster eta?",
            },
            {"name": "pt", "type": "real"},
        ],
        "output": {"name": "weight", "type": "real"},
        "data": {
            "nodetype": "multibinning",
            "edges": [
                list(sf.axes[0].edges),
                list(sf.axes[1].edges),
            ],
            "content": list(sf.view().value.flatten()),
        },
    }
)


sf = pandas.read_csv(
    f"{examples}/DeepCSV_2016LegacySF_V1_TuneCP5.btag.csv.gz", skipinitialspace=True
)


def build_formula(sf):
    if len(sf) != 1:
        raise ValueError(sf)

    value = sf.iloc[0]["formula"]
    if "x" in value:
        return Formula.parse_obj(
            {
                "nodetype": "formula",
                "expression": value,
                "parser": "TFormula_v1",
                # For this case, since this is a "reshape" SF, we know the parameter is the discriminant
                "variables": ["discriminant"],
                "parameters": [],
            }
        )
    else:
        return float(value)


def build_discrbinning(sf):
    edges = sorted(set(sf["discrMin"]) | set(sf["discrMax"]))
    return Binning.parse_obj(
        {
            "nodetype": "binning",
            "edges": edges,
            "content": [
                build_formula(sf[(sf["discrMin"] >= lo) & (sf["discrMax"] <= hi)])
                for lo, hi in zip(edges[:-1], edges[1:])
            ],
        }
    )


def build_ptbinning(sf):
    edges = sorted(set(sf["ptMin"]) | set(sf["ptMax"]))
    return Binning.parse_obj(
        {
            "nodetype": "binning",
            "edges": edges,
            "content": [
                build_discrbinning(sf[(sf["ptMin"] >= lo) & (sf["ptMax"] <= hi)])
                for lo, hi in zip(edges[:-1], edges[1:])
            ],
        }
    )


def build_etabinning(sf):
    edges = sorted(set(sf["etaMin"]) | set(sf["etaMax"]))
    return Binning.parse_obj(
        {
            "nodetype": "binning",
            "edges": edges,
            "content": [
                build_ptbinning(sf[(sf["etaMin"] >= lo) & (sf["etaMax"] <= hi)])
                for lo, hi in zip(edges[:-1], edges[1:])
            ],
        }
    )


def build_flavor(sf):
    keys = sorted(sf["jetFlavor"].unique())
    return Category.parse_obj(
        {
            "nodetype": "category",
            "content": {
                key: build_etabinning(sf[sf["jetFlavor"] == key]) for key in keys
            },
        }
    )


def build_systs(sf):
    keys = list(sf["sysType"].unique())
    return Category.parse_obj(
        {
            "nodetype": "category",
            "content": {key: build_flavor(sf[sf["sysType"] == key]) for key in keys},
        }
    )


corr2 = Correction.parse_obj(
    {
        "version": 1,
        "name": "DeepCSV_2016LegacySF",
        "description": "A btagging scale factor",
        "inputs": [
            {"name": "systematic", "type": "string"},
            {
                "name": "flavor",
                "type": "int",
                "description": "BTV flavor definiton: 0=b, 1=c, 2=udsg",
            },
            {"name": "abseta", "type": "real"},
            {"name": "pt", "type": "real"},
            {
                "name": "discriminant",
                "type": "real",
                "description": "DeepCSV output value",
            },
        ],
        "output": {"name": "weight", "type": "real"},
        "data": build_systs(sf),
    }
)


sf = requests.get(f"{examples}/EIDISO_WH_out.histo.json").json()


def build_syst(sf):
    return Category.parse_obj(
        {
            "nodetype": "category",
            "content": {
                "nominal": sf["value"],
                "up": sf["value"] + sf["error"],
                "down": sf["value"] - sf["error"],
            },
        }
    )


def parse_str(key, prefix="eta:"):
    if not key.startswith(prefix + "["):
        raise ValueError(f"{key} missing prefix {prefix}")
    lo, hi = map(float, key[len(prefix + "[") : -1].split(","))
    return lo, hi


def build_pts(sf):
    edges = []
    content = []
    for binstr, data in sf.items():
        if not binstr.startswith("pt:["):
            raise ValueError
        lo, hi = map(float, binstr[len("pt:[") : -1].split(","))
        if len(edges) == 0:
            edges.append(lo)
        if edges[-1] != lo:
            raise ValueError
        edges.append(hi)
        content.append(build_syst(data))

    return Binning.parse_obj(
        {
            "nodetype": "binning",
            "edges": edges,
            "content": content,
        }
    )


def build_etas(sf):
    bins = [parse_str(s, "eta:") for s in sf]
    edges = sorted(set(edge for bin in bins for edge in bin))
    content = [None] * (len(edges) - 1)
    for s, data in sf.items():
        lo, hi = parse_str(s, "eta:")
        found = False
        for i, bin in enumerate(bins):
            if bin[0] >= lo and bin[1] <= hi:
                content[i] = build_pts(data)
                found = True

    return Binning.parse_obj(
        {
            "nodetype": "binning",
            "edges": edges,
            "content": content,
        }
    )


corr3 = Correction.parse_obj(
    {
        "version": 1,
        "name": "EIDISO_WH_out",
        "description": "An electron scale factor",
        "inputs": [
            {"name": "eta", "type": "real"},
            {"name": "pt", "type": "real"},
            {"name": "systematic", "type": "string"},
        ],
        "output": {"name": "weight", "type": "real"},
        "data": build_etas(sf["EIDISO_WH"]["eta_pt_ratio"]),
    }
)


cset = CorrectionSet.parse_obj(
    {
        "schema_version": 2,
        "corrections": [
            corr1,
            corr2,
            corr3,
        ],
    }
)

with gzip.open("data/examples.json.gz", "wt") as fout:
    fout.write(cset.json(exclude_unset=True))
