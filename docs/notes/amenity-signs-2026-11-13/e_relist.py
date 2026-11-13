"""S12, part A's held-out check: does L1's held-out gap fall with the count of the unit's
earlier ads, and what would a shift by that count gain?

For each ad of a unit with a `unit_id`, the script counts the unit's ads priced before it,
reading dates alone. On L1's held-out ads it takes the mean gap by the count's cell, the
gap's slope on the count, and the elpd of a crossfitted shift by cell over a constant shift
and over a shift by L1's phase, scored on L1's kept draws."""

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "causal-screens-2026-11-13"))
import common as c  # noqa: E402

PHASES = ("10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+")
BINS = [-1, 0, 1, 2, 3, 5, 9, 10**6]
NAMES = ["0", "1", "2", "3", "4-5", "6-9", "10+"]

d = c.rows()
unit = d.unit_id.notna().to_numpy()
order = d.sort_values(["ukey", "priced", "listing_id"]).index
d.loc[order, "earlier"] = d.loc[order].groupby("ukey").cumcount().to_numpy()
cell = pd.cut(d.earlier, BINS, labels=NAMES).astype(str)
d["cell"] = np.where(unit, cell, "no unit")
h = c.heldout(d)
dr = c.Draws()
assert len(h) == len(dr.ph)
h["phase"] = np.asarray(PHASES)[dr.ph]
gap, fold, sub, b = (
    h.gap.to_numpy(),
    h.fold.to_numpy(),
    c.subfold(h.building),
    h.building.to_numpy(),
)
idx = np.arange(len(h))
res = {"n": len(h), "cells": []}
for k, v in h.groupby("cell"):
    res["cells"].append(
        {
            "cell": k,
            "n": len(v),
            "gap": round(100 * float(v.gap.mean()), 3),
            "se": round(100 * c.cluster_se(v.gap.to_numpy(), v.building) / len(v), 3),
            "in80": round(float(v.in80.mean()), 4),
        }
    )
mid = (h.cell != "no unit") & h.earlier.between(1, 10)
s, se, _ = c.wls_slope(gap[mid], h.earlier[mid], b[mid])
res["slope_1_10"] = [round(100 * s, 3), round(100 * se, 3)]
within = h.cell != "no unit"
g = c.within(gap[within], h.phase[within])
s, se, _ = c.wls_slope(g, h.earlier[within].clip(upper=15), b[within])
res["slope_within_phase_cap15"] = [round(100 * s, 3), round(100 * se, 3)]

e = {}
for name, key in (
    ("constant", np.zeros(len(h))),
    ("phase", h.phase.to_numpy()),
    ("count", h.cell.to_numpy()),
    ("phase_count", (h.phase + "|" + h.cell).to_numpy()),
):
    dl, picked = c.crossfit_shift(gap, key, fold, sub)
    e[name] = dr.gain(idx, delta=dl)
    res[name] = [round(float(e[name].sum()), 1), round(c.cluster_se(e[name], b), 1)]
    res[name + "_k"] = picked
    print(name, res[name], picked, flush=True)
for a, z in (
    ("count", "constant"),
    ("phase", "constant"),
    ("phase_count", "phase"),
):
    inc = e[a] - e[z]
    res[f"{a}_over_{z}"] = [round(float(inc.sum()), 1), round(c.cluster_se(inc, b), 1)]
for k, v in res.items():
    if k != "cells":
        print(k, v)
print(pd.DataFrame(res["cells"]).to_string())
json.dump(res, open(c.OUT + "s12e.json", "w"), indent=1, default=str)
