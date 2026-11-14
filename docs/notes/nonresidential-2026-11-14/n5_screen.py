"""N5: the candidates against L1's held-out predictions.

I take L1's held-out predictions from `pred_scores.npz` and leave out the 400 ads S16 drew. As
in S16 (`blind-spots-2026-11-14/b5_patterns.py`), the gap is the log ask minus L1's median and
an ask counts as covered when it lies between the 0.1 and 0.9 quantiles. For each set of
held-out candidates I give:

- the mean gap, with its standard error clustered by building;
- the spread, the median absolute deviation of the set's gaps over that of all kept held-out
  ads, with a standard error from 400 resamples of the set's buildings;
- the share covered, with its standard error clustered by building.

The sets are every candidate, each stratum, the rows with an own signal, the draft rule's rows,
the unmarked rows with an own signal, and the high-precision subset the note fixed before the
reads: the union of the read cells whose reads came to 0.8 or more, which `n4_score.py` gives.
After the reads I also look at the `label` stratum as a whole and at the sprint's screen,
and the note marks those as post hoc.
"""

import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/nonresidential-2026-11-14/"
DATASET = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/"
)
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
S16 = "/data1/apartments/tmp/blind-spots-2026-11-14/"
SEED = 20261114

d = pd.read_parquet(DATASET + "rows.parquet", columns=["listing_id", "building"])
d["listing_id"] = d.listing_id.astype(str)
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
assert (d.listing_id[d.held].to_numpy() == a["listing"].astype(str)).all()
qs = list(a["quantiles"])
d["gap"], d["in80"] = np.nan, False
d.loc[d.held, "gap"] = a["y"] - a["pred"]
d.loc[d.held, "in80"] = (a["y"] >= a["q"][:, qs.index(0.1)]) & (
    a["y"] <= a["q"][:, qs.index(0.9)]
)
drawn = set(pd.read_parquet(S16 + "draw.parquet").listing_id.astype(str))
k = d[d.held & ~d.listing_id.isin(drawn)].reset_index(drop=True)


def mad(v):
    v = np.asarray(v, float)
    return float(np.median(np.abs(v - np.median(v))))


BASE = mad(k.gap)


def cluster_mean_se(v, b):
    v = np.asarray(v, float)
    t = pd.Series(v - v.mean()).groupby(np.asarray(b)).sum()
    if len(t) < 2:
        return float("nan")
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(v))


def spread_se(g):
    by = {b: x.gap.to_numpy() for b, x in g.groupby("building")}
    keys = list(by)
    if len(keys) < 2:
        return float("nan")
    rng = np.random.default_rng(SEED)
    out = []
    for _ in range(400):
        pick = rng.choice(len(keys), len(keys))
        out.append(mad(np.concatenate([by[keys[i]] for i in pick])) / BASE)
    return float(np.std(out, ddof=1))


def stats(ids):
    g = k[k.listing_id.isin(set(ids))]
    if len(g) == 0:
        return {"ads": 0}
    return {
        "ads": len(g),
        "buildings": int(g.building.nunique()),
        "mean_gap": round(float(g.gap.mean()), 4),
        "mean_gap_se": round(cluster_mean_se(g.gap, g.building), 4),
        "spread": round(mad(g.gap) / BASE, 3),
        "spread_se": round(spread_se(g), 3),
        "in80": round(float(g.in80.mean()), 3),
        "in80_se": round(cluster_mean_se(g.in80, g.building), 3),
    }


c = pd.read_parquet(OUT + "candidates.parquet")
c["base"] = c.stratum.replace({"sf_year": "sfz", "zoned": "sfz"})
prec = json.load(open(OUT + "precision.json"))["sets"]
high = [s[5:] for s, v in prec.items() if s.startswith("cell ") and v["share"] >= 0.8]
key = pd.read_parquet(OUT + "key.parquet")[["cell"]].drop_duplicates()


def cell(r):
    if r.base in ("label", "sfz", "build_out", "medical_prof", "offer"):
        return r.base + ("+" if r.rule_mark else "-")
    if r.base == "words":
        return "words_lot" if r.bk_lot else "words_other"
    return r.base


c["cell"] = [cell(r) for r in c.itertuples()]
assert set(key.cell) <= set(c.cell)
sets = {
    "all candidates": c,
    **{f"stratum {s}": c[c.base == s] for s in c.base.unique()},
    "own signal": c[c.own_signal],
    "draft rule": c[c.rule_mark],
    "own signal, unmarked": c[c.own_signal & ~c.rule_mark],
    "high-precision cells (" + ", ".join(high) + ")": c[c.cell.isin(high)],
}
prior = pd.read_parquet(OUT + "prior_ids.parquet")
post = {
    "post hoc: sprint screen": prior.listing_id[prior.set == "sprint_screen"],
    "post hoc: ledger, decided after L1's build": prior.listing_id[
        prior.set == "ledger"
    ],
}
res = {
    "kept_heldout": {
        "ads": len(k),
        "mad": round(BASE, 4),
        "in80": round(float(k.in80.mean()), 3),
        "mean_gap": round(float(k.gap.mean()), 4),
    },
    "high_precision_cells": high,
    "sets": {s: stats(g.listing_id) for s, g in sets.items()},
    "post_hoc": {s: stats(v) for s, v in post.items()},
}
json.dump(res, open(OUT + "screen.json", "w"), indent=1)
for part in ("sets", "post_hoc"):
    for s, v in res[part].items():
        if v["ads"] == 0:
            print(f"{s:42s} ads 0")
            continue
        print(
            f"{s:42s} ads {v['ads']:5d} gap {v['mean_gap']:+.4f} ± {v['mean_gap_se']:.4f} "
            f"spread {v['spread']:.2f} ± {v['spread_se']:.2f} "
            f"in80 {v['in80']:.3f} ± {v['in80_se']:.3f}"
        )
print(res["kept_heldout"])
