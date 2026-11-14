"""Text flags, step 5: the rows the rewrite changes, and L1's gaps on them.

I read the copy of L1's dataset that `rentfrontier.b0textflags` writes (L1's dataset path with
`-textflags` added) and check its new columns against the flags `t3_eval.py` matched. For each
rewritten flag I count the rows each version marks, and the rows the new one gains and loses,
over all rows and over L1's held-out ads of the latest split.

On the held-out ads, in dataset order, I take the gap of the log ask from L1's predictive
median, from L1's `pred_scores.npz` (`rentfrontier.drift_score` on L1's saved draws). I split
the ads into four cells by the two versions: both mark, only the old marks, only the new
marks, neither marks. For each cell I give the mean gap with its SE clustered by building:

    t = (x - x.mean()).groupby(b).sum(); se = sqrt(G / (G - 1) * (t**2).sum()) / n

For the difference of two cells' means I sum each ad's term, (x - mean) / n with the sign of
its cell, by building, and take the same root. The counts and gaps go to `OUT/t5_gap.json`.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from common import OUT

DATA = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
)
COPY = Path(str(DATA) + "-textflags")
RUN = Path("/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1")
PAIRS = {"income_restricted": "income_restricted_v2", "shared_space": "shared_space_v2"}
T3 = {"income_restricted_v2": "income_v2", "shared_space_v2": "shared_v2"}


def mean_se(x, b):
    x = pd.Series(np.asarray(x, float))
    t = (x - x.mean()).groupby(np.asarray(b)).sum()
    g = len(t)
    return float(x.mean()), float(np.sqrt(g / (g - 1) * (t**2).sum()) / len(x))


def diff_se(x, on, off, b):
    """Mean of `x` over `on` less its mean over `off`, with the building-clustered SE."""
    x, b = np.asarray(x, float), np.asarray(b)
    m1, m0 = x[on].mean(), x[off].mean()
    r = np.where(on, (x - m1) / on.sum(), 0.0) - np.where(
        off, (x - m0) / off.sum(), 0.0
    )
    keep = on | off
    t = pd.Series(r[keep]).groupby(b[keep]).sum()
    g = len(t)
    return float(m1 - m0), float(np.sqrt(g / (g - 1) * (t**2).sum()))


manifest = json.loads((COPY / "manifest.json").read_text())
d = pd.read_parquet(
    COPY / "rows.parquet", columns=["listing_id", "building", *PAIRS, *T3]
)
d["listing_id"] = d.listing_id.astype(str)
t3 = pd.read_parquet(OUT / "t3_flags.parquet", columns=["listing_id", *T3.values()])
both = d.merge(t3, on="listing_id", how="left", validate="one_to_one")
out = {
    "copy": str(COPY),
    "rows": len(d),
    "manifest_textflags": manifest["textflags"]["columns"],
    "differs_from_t3": {
        new: int((both[new] != both[old].fillna(False).astype(bool)).sum())
        for new, old in T3.items()
    },
}
a = np.load(RUN / "pred_scores.npz", allow_pickle=True)
held = a["heldout"]
h = d[held].reset_index(drop=True)
assert (h.listing_id.to_numpy() == a["listing"]).all()
gap = a["y"] - a["pred"]
b = h.building.astype(str).to_numpy()
out["heldout"] = len(h)
out["heldout_buildings"] = int(pd.Series(b).nunique())
for old, new in PAIRS.items():
    o, n = d[old].to_numpy(bool), d[new].to_numpy(bool)
    rows = {
        "old": int(o.sum()),
        "new": int(n.sum()),
        "gained": int((n & ~o).sum()),
        "lost": int((o & ~n).sum()),
        "heldout_old": int(o[held].sum()),
        "heldout_new": int(n[held].sum()),
        "heldout_gained": int((n & ~o)[held].sum()),
        "heldout_lost": int((o & ~n)[held].sum()),
    }
    ho, hn = o[held], n[held]
    cells = {
        "both": ho & hn,
        "old only": ho & ~hn,
        "new only": ~ho & hn,
        "neither": ~ho & ~hn,
    }
    gaps = {}
    for name, on in cells.items():
        if on.sum() < 2:
            gaps[name] = {"n": int(on.sum())}
            continue
        m, se = mean_se(gap[on], b[on])
        gaps[name] = {
            "n": int(on.sum()),
            "buildings": int(pd.Series(b[on]).nunique()),
            "mean_gap": m,
            "se": se,
        }
    diffs = {}
    for name, base in (
        ("old only - both", "both"),
        ("new only - neither", "neither"),
        ("old only - neither", "neither"),
        ("new only - both", "both"),
    ):
        cell = name.split(" - ")[0]
        if cells[cell].sum() >= 2 and cells[base].sum() >= 2:
            dm, se = diff_se(gap, cells[cell], cells[base], b)
            diffs[name] = {"diff": dm, "se": se, "z": dm / se}
    out[old] = {"rows": rows, "gaps": gaps, "diffs": diffs}
    print(f"\n{old}: {rows}")
    for name, g in gaps.items():
        if "mean_gap" in g:
            print(
                f"  {name}: n {g['n']:,} in {g['buildings']:,} buildings,"
                f" mean gap {g['mean_gap']:+.4f} (SE {g['se']:.4f})"
            )
        else:
            print(f"  {name}: n {g['n']}")
    for name, s in diffs.items():
        print(f"  {name}: {s['diff']:+.4f} (SE {s['se']:.4f}, z {s['z']:+.1f})")
changed = np.zeros(len(d), bool)
for old, new in PAIRS.items():
    changed |= d[old].to_numpy(bool) != d[new].to_numpy(bool)
out["rows_changed"] = int(changed.sum())
print(
    f"\nrows with a changed flag {changed.sum():,}; differs from t3 {out['differs_from_t3']}"
)
(OUT / "t5_gap.json").write_text(json.dumps(out, indent=2))
