"""Added after `h1_history.py` was scored: the held-out gap against the distance from the model's
median to the unit's own training asks.

`h1_history.py` measures a unit's record against its building's other units. The false deals
were found another way, as units the fit priced far above their own earlier asks. This script
measures that distance directly. For each held-out ad it carries the unit's training asks to
the held-out month with the monthly index of `h1_history.py`, takes their mean, and computes
r = the model's predictive median less that mean. It then reports, for L1 and L1T, by band of r
and by the unit's number of training ads: the count of ads, the mean gap, the 80% coverage and
the slope of the gap on r. The ask is in the gap and absent from r, so a calibrated median
gives a mean gap of zero in every band.

    TMPDIR=/data1/apartments/tmp/unit-history-calibration-2026-11-14/tmp \
        systemd-run --user --scope -q -p MemoryMax=3G \
        /data1/apartments/venvs/nj-frontier/bin/python \
        docs/notes/unit-history-calibration-2026-11-14/h2_own_record.py
"""

import json
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
R_BINS = [-np.inf, -0.14, -0.07, -0.03, 0.03, 0.07, 0.14, np.inf]
R_LABELS = ["<-.14", "-.14:-.07", "-.07:-.03", "-.03:.03", ".03:.07", ".07:.14", ">.14"]

d = pd.read_parquet(
    c.DATA, columns=["listing_id", "building", "unit_id", "price_at", "latest_ask"]
)
d["listing_id"] = d.listing_id.astype(str)
sc = {k: np.load(p + "pred_scores.npz") for k, p in RUNS.items()}
d["held"] = sc["l1"]["heldout"]
d["priced"] = d.price_at.dt.tz_convert(None)
d["ukey"] = np.where(
    d.unit_id.isna(),
    "row:" + d.listing_id,
    d.building.astype(str) + "|" + d.unit_id.astype(str),
)
d["ly"] = np.log(d.latest_ask.astype(float))
d["mon"] = d.priced.dt.year * 12 + d.priced.dt.month
t = d[~d.held & (d.latest_ask > 0)].copy()
dev = t.ly - t.groupby("ukey").ly.transform("mean")
idx = dev.groupby(t.mon).mean()
idx = idx.reindex(range(d.mon.min(), d.mon.max() + 1)).interpolate().bfill().ffill()
t["adj"] = t.ly - idx.reindex(t.mon).to_numpy()
unit = t.groupby("ukey").agg(
    n_train=("adj", "size"), own=("adj", "mean"), last=("priced", "max")
)
del t
h = d[d.held.to_numpy()].reset_index(drop=True).join(unit, on="ukey")
del d
assert (h.listing_id.to_numpy() == sc["l1"]["listing"]).all()
h["record"] = h.own + idx.reindex(h.mon).to_numpy()
h["months"] = (h.priced - h["last"]).dt.days / 30.44
for k, a in sc.items():
    qs = list(a["quantiles"])
    h["gap_" + k] = a["y"] - a["pred"]
    h["r_" + k] = a["pred"] - h.record
    lo, hi = a["q"][:, qs.index(0.1)], a["q"][:, qs.index(0.9)]
    h["in80_" + k] = (a["y"] >= lo) & (a["y"] <= hi)


def mean_se(v, b):
    """Mean of `v` with its building-clustered SE."""
    v = np.asarray(v, float)
    s = pd.Series(v - v.mean()).groupby(np.asarray(b)).sum()
    se = np.sqrt(len(s) / (len(s) - 1) * (s**2).sum()) / len(v)
    return [float(v.mean()), float(se)]


def table(v, k):
    """Bands of r under model `k` over the ads `v`, and the slope of the gap on r."""
    band = pd.cut(v["r_" + k], R_BINS, labels=R_LABELS).astype(str)
    out = {
        "n": len(v),
        "r_sd": float(v["r_" + k].std()),
        "slope": list(c.wls_slope(v["gap_" + k], v["r_" + k], v.building)[:2]),
        "bands": {},
    }
    for lab in R_LABELS:
        w = v[band == lab]
        if len(w) < 50:
            continue
        out["bands"][lab] = {
            "n": len(w),
            "gap": mean_se(w["gap_" + k], w.building),
            "in80": float(w["in80_" + k].mean()),
            "ask_less_record": float((w["gap_" + k] + w["r_" + k]).mean()),
        }
    return out


sets = {
    "all": h,
    "1 ad": h[h.n_train == 1],
    "2+ ads": h[h.n_train >= 2],
    "2+ ads, within 24 months": h[(h.n_train >= 2) & (h.months <= 24)],
    "3+ ads, within 24 months": h[(h.n_train >= 3) & (h.months <= 24)],
}
res = {s: {k: table(v, k) for k in RUNS} for s, v in sets.items()}
for s, r in res.items():
    for k, tb in r.items():
        print(s, k, "n", tb["n"], "r_sd %.3f" % tb["r_sd"], "slope", tb["slope"])
        print(pd.DataFrame(tb["bands"]).T.to_string(), flush=True)
json.dump(res, open(OUT + "h2_own_record.json", "w"), indent=1, default=float)
