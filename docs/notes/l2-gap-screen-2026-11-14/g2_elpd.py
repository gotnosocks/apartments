"""elpd of cross-fitted shifts for the screen of L2's held-out gap.

For each partition of the held-out ads (`h.parquet` from `g1_tables.py`) the script takes the
median gap of each cell on one half of the buildings (half = crc32 of the building name mod 2),
moves the predictive location of the other half's ads by it, and rescores L2's exact predictive
over its 432 kept draws. A cell with under 30 ads in the estimating half takes that half's overall
median. The script reports each gain over L2 and over the plain constant with building-clustered
SEs, and writes them to `g2.json` and the per-ad gains to `g2_gains.parquet`.

    systemd-run --user --scope -q -p MemoryMax=3G --setenv=OMP_NUM_THREADS=2 \
        --setenv=PYTHONPATH=<worktree>/frontier/src \
        /data1/apartments/venvs/bridge-frontier/bin/python g2_elpd.py <worktree>
"""

import json
import sys

import numpy as np
import pandas as pd

WT = sys.argv[1]
sys.path.insert(0, WT + "/docs/notes/causal-screens-2026-11-13")
import common as c  # noqa: E402

c.RUN = (
    "/data1/apartments/frontier/runs/"
    "drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn/"
)
OUT = "/data1/apartments/tmp/sprint-20261114/gap-screen/"
h = pd.read_parquet(OUT + "h.parquet")
dr = c.Draws()
assert len(h) == len(dr.y)
gap, fold, b = h.gap.to_numpy(), h.fold.to_numpy(), h.building.to_numpy()
idx = np.arange(len(h))
h["m10"] = (
    pd.qcut(h.m, 10, labels=False).astype("float").fillna(-1).astype(int).astype(str)
)
h["one"] = "all"

PARTS = {
    "constant": ["one"],
    "phase": ["phase"],
    "a ending": ["prev_ending"],
    "a phase x ending": ["phase", "prev_ending"],
    "a path": ["path"],
    "a phase x path": ["phase", "path"],
    "c unit record (7 bins)": ["m_bin"],
    "c unit record (deciles)": ["m10"],
    "c last training change": ["chg_bin"],
    "c record x last change": ["m_bin", "chg_bin"],
    "d training ads": ["n_bin"],
    "d unit sd": ["usd_bin"],
    "d months since previous": ["since_bin"],
    "c,d record x training ads": ["m_bin", "n_bin"],
    "e year": ["yr"],
    "e half-year": ["half"],
    "e years to snapshot": ["expo_bin"],
    "e year x training ads": ["yrs", "n_bin"],
    "c,e record x year": ["m_bin", "yrs"],
    "a,c,e record x year x ending": ["m_bin", "yrs", "end2"],
    "a,e year x ending": ["yrs", "end2"],
    "b cuts (reads the ad's rents)": ["cuts"],
    "b cuts x raises (reads the ad's rents)": ["cuts", "raises"],
    "b days on market": ["dom"],
    "b own ending": ["own_end"],
    "b days x own ending": ["dom", "own_end"],
    "b,e days x year": ["dom", "yrs"],
    "b,c,e days x record x year": ["dom", "m_bin", "yrs"],
}


def shift(cols):
    key = h[cols[0]].astype(object).map(str)
    for col in cols[1:]:
        key = key + "|" + h[col].astype(object).map(str)
    key = key.to_numpy()
    out = np.zeros(len(h))
    for f in (0, 1):
        est = fold != f
        g = pd.Series(gap[est]).groupby(key[est])
        med, n = g.median(), g.size()
        med = med.where(n >= 30, np.median(gap[est]))
        out[fold == f] = (
            med.reindex(key[fold == f]).fillna(np.median(gap[est])).to_numpy()
        )
    return out, len(np.unique(key))


# optional partition names after the worktree rerun only those, merging into g2.json
ONLY = sys.argv[2:]
if ONLY:
    PARTS = {k: v for k, v in PARTS.items() if k == "constant" or k in ONLY}
res, gains = {}, {}
for name, cols in PARTS.items():
    delta, cells = shift(cols)
    g = dr.gain(idx, delta=delta)
    gains[name] = g
    r = {"cells": cells, "gain": float(g.sum()), "se": c.cluster_se(g, b)}
    if name != "constant":
        dlt = g - gains["constant"]
        r["over_constant"] = float(dlt.sum())
        r["over_constant_se"] = c.cluster_se(dlt, b)
    res[name] = r
    print(name, json.dumps(r), flush=True)
for a_, b_ in [
    ("a phase x ending", "phase"),
    ("c,e record x year", "e year"),
    ("c,e record x year", "c unit record (7 bins)"),
    ("a,c,e record x year x ending", "c,e record x year"),
    ("c,d record x training ads", "c unit record (7 bins)"),
    ("b,c,e days x record x year", "c,e record x year"),
]:
    if a_ not in gains or b_ not in gains:
        continue
    dlt = gains[a_] - gains[b_]
    res[a_ + " over " + b_] = [float(dlt.sum()), c.cluster_se(dlt, b)]
    print(a_, "over", b_, res[a_ + " over " + b_], flush=True)
if ONLY:
    full = json.load(open(OUT + "g2.json"))
    full.update(res)
    res = full
    old = pd.read_parquet(OUT + "g2_gains.parquet")
    for k, v in gains.items():
        old[k] = v
    gains = old
json.dump(res, open(OUT + "g2.json", "w"), indent=1)
pd.DataFrame(gains).to_parquet(OUT + "g2_gains.parquet")
