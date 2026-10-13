"""Splits the residual-target gain of held_data_ceiling.py: an intercept, year, C's own
columns, and C's own columns plus each group of as-of columns (WLS, lot folds).

    python docs/analysis/scripts/held_data_ceiling_split.py PER_ROW_FILE
"""

import sys, json, numpy as np, pandas as pd

sys.path.insert(0, "docs/analysis/scripts")
import held_data_ceiling as h
from rentfrontier import features

R = sys.argv[1]
_, frame, heldout = h._load_frame()
base = features.build(h.BASE, frame, ~heldout)
own = pd.DataFrame(base.values, index=frame.audit_id.to_numpy())
per = pd.read_parquet(R)
per = per[per.rung == "new building"].reset_index(drop=True)
tab = (
    pd.read_parquet(h.OUT / "features.parquet")
    .set_index("audit_id")
    .loc[per.audit_id]
    .reset_index()
)
fam = json.loads((h.OUT / "families.json").read_text())
xo = own.loc[per.audit_id].to_numpy(float)
y, med = per.y.to_numpy(), per["median"].to_numpy()
r = y - med
lots = per.bbl.where(per.bbl.notna() & (per.bbl != "")).to_numpy()
folds, groups = h.lot_folds(
    per.building.to_numpy(), lots, np.random.default_rng(h.SEED)
)
zero = np.zeros(len(r))
miss = lambda p, i: 100 * np.median(np.abs(np.exp(med[i] + p[i] - y[i]) - 1))
print(
    "mean residual", r.mean().round(4), "bpart mean", per.building_part.mean().round(4)
)
yr = pd.get_dummies(per.year).to_numpy(float)


def cols(*f):
    return tab[[c for c, g in fam.items() if g in f]].to_numpy(float)


ad = ("coded", "finish", "description", "history")
ext = (
    "hpd",
    "elevfill",
    "lines",
    "lister",
    "stabilized",
    "predsize",
    "retail",
    "noise",
    "trees",
    "crime",
    "petsfill",
)
designs = {
    "intercept": np.zeros((len(r), 0)),
    "year": yr,
    "own": xo,
    "own+year": np.column_stack([xo, yr]),
    "own+ad-means": np.column_stack([xo, cols(*ad)]),
    "own+external": np.column_stack([xo, cols(*ext)]),
    "own+all as-of": np.column_stack([xo, cols(*h.AS_OF)]),
}
fits = {}
for k, x in designs.items():
    if x.shape[1] == 0:
        p = np.empty_like(r)
        for f in np.unique(folds):
            p[folds == f] = r[folds != f].mean()
    else:
        p = h.wls_oof(r, zero, x, folds)
    fits[k] = p
    print(
        f"{k:16s} miss {miss(p, np.arange(len(r))) - miss(zero, np.arange(len(r))):+.3f} pp  SLE drop {np.mean(r**2 - (r - p) ** 2):.5f}",
        flush=True,
    )
for a, b in (
    ("own+ad-means", "own"),
    ("own+external", "own"),
    ("own+all as-of", "own"),
):
    d = h.boot(
        lambda i: miss(fits[a], i) - miss(fits[b], i),
        groups,
        np.random.default_rng(7),
        200,
    )
    print(f"{a} over {b}: {d[0]:+.3f} [{d[1]:+.3f}, {d[2]:+.3f}]", flush=True)
