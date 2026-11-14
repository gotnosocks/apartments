"""Unit history calibration on L1 and L1T: the held-out gap of an ad against the record its unit
left among the training ads.

The script reads the dataset's rows with the columns it uses, and the saved held-out predictions
(`pred_scores.npz`) of the L1 and L1T pools. Neither pool saved fitted values for training rows,
so the script builds a stand-in for the unit's training record the way
`unit-level-reads-2026-11-12/rank.py` does, from the training rows alone:

1. it takes the log ask of each training ad and subtracts a monthly index, the mean over the
   month's ads of the log ask less the unit's own mean log ask;
2. within each cell of building, bedrooms and year holding at least 3 training ads of other
   units, it subtracts the mean of those other units' adjusted asks from the unit's mean;
3. it averages the unit's cells, weighted by the unit's ads in each, into the measure `m`.

For each model it then computes, on the same held-out ads:

1. the slope of the held-out gap (log ask less the predictive median) on `m`, over all ads, by
   the unit's number of training ads, and by the months from the unit's last training ad to the
   held-out ad, plus the slope of L1T's gap less L1's;
2. the mean gap and 80% coverage for units with `m` under -0.15 or over +0.15 and at least 2
   training ads;
3. the duplex ads' excess in the squared gap clipped at 0.4, as `w1_within.py` computes it.

SEs are clustered by building. Inputs are read only.

    TMPDIR=/data1/apartments/tmp/unit-history-calibration-2026-11-14/tmp \
        systemd-run --user --scope -q -p MemoryMax=3G \
        /data1/apartments/venvs/nj-frontier/bin/python \
        docs/notes/unit-history-calibration-2026-11-14/h1_history.py
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

RUNS = {
    "l1": "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/",
    "l1t": (
        "/data1/apartments/frontier/runs/"
        "drift-building-phase-unitt-b0-latest-bc8e7b95-l1t/"
    ),
}
OUT = "/data1/apartments/tmp/unit-history-calibration-2026-11-14/"
os.makedirs(OUT, exist_ok=True)
N_BINS = [0, 1, 2, 5, 9, np.inf]
N_LABELS = ["1", "2", "3-5", "6-9", "10+"]
MO_BINS = [-np.inf, 0, 6, 12, 24, 48, np.inf]
MO_LABELS = ["before", "0-6", "6-12", "12-24", "24-48", "48+"]
TAIL = 0.15

d = pd.read_parquet(
    c.DATA,
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        "latest_ask",
        "bedrooms",
    ],
)
d["listing_id"] = d.listing_id.astype(str)
sc = {k: np.load(p + "pred_scores.npz") for k, p in RUNS.items()}
assert (sc["l1"]["heldout"] == sc["l1t"]["heldout"]).all()
assert (sc["l1"]["listing"] == sc["l1t"]["listing"]).all()
d["held"] = sc["l1"]["heldout"]
d["priced"] = d.price_at.dt.tz_convert(None)
d["ukey"] = np.where(
    d.unit_id.isna(),
    "row:" + d.listing_id,
    d.building.astype(str) + "|" + d.unit_id.astype(str),
)
d["ly"] = np.log(d.latest_ask.astype(float))

# the stand-in, from the training rows alone
t = d[~d.held & (d.latest_ask > 0)].copy()
t["mon"] = t.priced.dt.year * 12 + t.priced.dt.month
t["yr"] = t.priced.dt.year
dev = t.ly - t.groupby("ukey").ly.transform("mean")
idx = dev.groupby(t.mon).mean()
idx = idx.reindex(range(t.mon.min(), t.mon.max() + 1)).interpolate().bfill().ffill()
t["adj"] = t.ly - idx.reindex(t.mon).to_numpy()
cell = ["building", "bedrooms", "yr"]
G = t.groupby(cell).adj.agg(["sum", "size"])
U = (
    t.groupby(["ukey", *cell])
    .adj.agg(["sum", "size"])
    .reset_index()
    .join(G, on=cell, rsuffix="_g")
)
U["others"] = U.size_g - U["size"]
U = U[U.others >= 3].copy()
U["w_dev"] = U["sum"] - U["size"] * (U.sum_g - U["sum"]) / U.others
m = U.groupby("ukey")[["w_dev", "size"]].sum()
m["m"] = m.w_dev / m["size"]
unit = t.groupby("ukey").agg(n_train=("ly", "size"), last=("priced", "max"))
unit = unit.join(m[["m"]].join(m["size"].rename("n_in_cells")))
del t, U, G

h = d[d.held.to_numpy()].reset_index(drop=True)
del d
assert (h.listing_id.to_numpy() == sc["l1"]["listing"]).all()
assert np.allclose(h.ly, sc["l1"]["y"], atol=1e-6)
for k, a in sc.items():
    qs = list(a["quantiles"])
    h["gap_" + k] = a["y"] - a["pred"]
    lo, hi = a["q"][:, qs.index(0.1)], a["q"][:, qs.index(0.9)]
    h["in80_" + k] = (a["y"] >= lo) & (a["y"] <= hi)
h = h.join(unit, on="ukey")
h["months"] = (h.priced - h["last"]).dt.days / 30.44
h["n_bin"] = pd.cut(h.n_train, N_BINS, labels=N_LABELS).astype(str)
h["mo_bin"] = pd.cut(h.months, MO_BINS, labels=MO_LABELS).astype(str)
res = {
    "heldout": len(h),
    "with_training_ads": int(h.n_train.notna().sum()),
    "with_measure": int(h.m.notna().sum()),
    "after_last_training_ad": float((h.months > 0).mean()),
}
x = h[h.m.notna()].copy()
res["m_quantiles"] = x.m.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).to_dict()
res["m_sd"] = float(x.m.std())
res["gap_with_measure"] = {k: float(x["gap_" + k].mean()) for k in RUNS}
res["gap_without_measure"] = {k: float(h["gap_" + k][h.m.isna()].mean()) for k in RUNS}


def mean_se(v, b):
    """Mean of `v` with its building-clustered SE."""
    v = np.asarray(v, float)
    s = pd.Series(v - v.mean()).groupby(np.asarray(b)).sum()
    se = np.sqrt(len(s) / (len(s) - 1) * (s**2).sum()) / len(v)
    return [float(v.mean()), float(se)]


def slopes(v):
    """Slopes on `m` of each model's gap and of L1T's gap less L1's, over the ads `v`."""
    b = v.building.to_numpy()
    return {
        "n": len(v),
        "buildings": int(v.building.nunique()),
        "m_sd": float(v.m.std()),
        "l1": list(c.wls_slope(v.gap_l1, v.m, b)[:2]),
        "l1t": list(c.wls_slope(v.gap_l1t, v.m, b)[:2]),
        "l1t_less_l1": list(c.wls_slope(v.gap_l1t - v.gap_l1, v.m, b)[:2]),
    }


res["slope_all"] = slopes(x)
res["slope_by_n"] = {k: slopes(x[x.n_bin == k]) for k in N_LABELS}
res["slope_by_months"] = {
    k: slopes(x[x.mo_bin == k]) for k in MO_LABELS if (x.mo_bin == k).sum() >= 200
}
res["slope_by_n_and_months"] = {
    f"{k} | {j}": slopes(x[(x.n_bin == k) & (x.mo_bin == j)])
    for k in N_LABELS
    for j in MO_LABELS
    if ((x.n_bin == k) & (x.mo_bin == j)).sum() >= 500
}
print(json.dumps(res, indent=1), flush=True)

# the tails
res["tail"] = {}
for name, sel in (
    ("low", (x.m < -TAIL) & (x.n_train >= 2)),
    ("high", (x.m > TAIL) & (x.n_train >= 2)),
    ("middle", (x.m.abs() <= TAIL) & (x.n_train >= 2)),
    ("low_one_ad", (x.m < -TAIL) & (x.n_train == 1)),
    ("high_one_ad", (x.m > TAIL) & (x.n_train == 1)),
):
    v = x[sel]
    r = {
        "n": len(v),
        "units": int(v.ukey.nunique()),
        "buildings": int(v.building.nunique()),
        "m_mean": float(v.m.mean()),
    }
    for k in RUNS:
        r["gap_" + k] = mean_se(v["gap_" + k], v.building)
        r["gap_median_" + k] = float(v["gap_" + k].median())
        r["in80_" + k] = mean_se(v["in80_" + k].astype(float), v.building)
        r["abs_gap_" + k] = float(v["gap_" + k].abs().mean())
    r["gap_l1t_less_l1"] = mean_se(v.gap_l1t - v.gap_l1, v.building)
    res["tail"][name] = r
print(json.dumps(res["tail"], indent=1), flush=True)

# coverage over all held-out ads, for reference
res["in80_all"] = {k: float(h["in80_" + k].mean()) for k in RUNS}

# the duplex ads' excess squared gap, clipped as in w1_within.py
tx = pd.read_parquet(c.OUT + "s7_text.parquet", columns=["listing_id", "dup_unit"])
tx["listing_id"] = tx.listing_id.astype(str)
n_h = len(h)
h = h.merge(tx, on="listing_id", how="left")
assert len(h) == n_h
on = h.dup_unit.fillna(False).astype(bool).to_numpy()
b = h.building.to_numpy()
sq = {k: (h["gap_" + k].clip(-0.4, 0.4) ** 2).to_numpy() for k in RUNS}
res["duplex"] = {
    "dup": int(on.sum()),
    "l1": list(c.cluster_mean_diff(sq["l1"], on, b)),
    "l1t": list(c.cluster_mean_diff(sq["l1t"], on, b)),
    "l1_less_l1t": list(c.cluster_mean_diff(sq["l1"] - sq["l1t"], on, b)),
    "sq_on": {k: float(sq[k][on].mean()) for k in RUNS},
    "sq_off": {k: float(sq[k][~on].mean()) for k in RUNS},
    "in80_on": {k: float(h["in80_" + k][on].mean()) for k in RUNS},
}
res["duplex"]["remaining"] = res["duplex"]["l1t"][0] / res["duplex"]["l1"][0]
print(json.dumps(res["duplex"], indent=1), flush=True)
json.dump(res, open(OUT + "h1_history.json", "w"), indent=1, default=float)
