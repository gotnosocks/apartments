"""S12, part B's lister gain: what would a shift of each held-out ad by its lister's mean
gap, estimated on the other half of the buildings, gain on L1's draws?

The script reads `f_lister.py`'s lister for each held-out ad and scores a crossfitted shift
by lister, and by lister and phase, against a constant shift and a shift by phase."""

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "causal-screens-2026-11-13"))
import common as c  # noqa: E402

PHASES = ("10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+")
h = c.heldout()
who = pd.read_parquet(c.OUT + "s12f_lister.parquet")
assert (
    who.listing_id.astype(str).to_numpy() == h.listing_id.astype(str).to_numpy()
).all()
h["lister"] = who.lister.to_numpy()
dr = c.Draws()
h["phase"] = np.asarray(PHASES)[dr.ph]
gap, fold, sub, b = (
    h.gap.to_numpy(),
    h.fold.to_numpy(),
    c.subfold(h.building),
    h.building.to_numpy(),
)
idx = np.arange(len(h))
res = {"n": len(h), "listers": int(h.lister.nunique())}
e = {}
for name, key in (
    ("constant", np.zeros(len(h))),
    ("phase", h.phase.to_numpy()),
    ("lister", h.lister.to_numpy()),
    ("phase_lister", (h.phase + "|" + h.lister).to_numpy()),
):
    dl, picked = c.crossfit_shift(gap, key, fold, sub)
    e[name] = dr.gain(idx, delta=dl)
    res[name] = [round(float(e[name].sum()), 1), round(c.cluster_se(e[name], b), 1)]
    res[name + "_k"] = picked
    print(name, res[name], picked, flush=True)
for a, z in (("lister", "constant"), ("phase_lister", "phase")):
    inc = e[a] - e[z]
    res[f"{a}_over_{z}"] = [round(float(inc.sum()), 1), round(c.cluster_se(inc, b), 1)]
    print(a, "over", z, res[f"{a}_over_{z}"])
# The listers with the largest shares of the held-out ads, with their mean gaps.
top = h.groupby("lister").gap.agg(["size", "mean"]).sort_values("size").tail(15)
res["top_listers"] = [
    [k, int(r["size"]), round(100 * r["mean"], 2)] for k, r in top.iterrows()
]
json.dump(res, open(c.OUT + "s12g.json", "w"), indent=1, default=str)
