"""The Deals model's backtest (run range-j, fitted as of 2025-11-10): errors of the later ads by counts."""

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from rentfrontier import drift_deals, drift_score

run = Path("/data1/apartments/frontier/runs") / sys.argv[1]
frame, h, held = drift_deals._held_frame(run)
print("rows", len(frame), "held", len(h))
print([c for c in frame.columns if "bed" in c or "bath" in c or "unit" in c])
res = drift_score.score_run(run)
h["cdf"] = res["cdf"]
h["pred"] = res["pred"]
h["res"] = np.log(h.latest_ask.to_numpy(float)) - h.pred
h["z"] = norm.ppf(h.cdf.clip(1e-6, 1 - 1e-6))
h["half"] = [
    hashlib.sha1(("history-scan-2026-11-18" + str(b)).encode()).digest()[0] % 2
    for b in h.building
]
t = frame[~held]
for d in (t, h):
    d["baths"] = d.full_baths + 0.5 * d.half_baths.fillna(0)
u = t.groupby(["building", "unit_id"]).agg(
    un=("baths", "size"),
    bath_lo=("baths", "min"),
    bath_hi=("baths", "max"),
    bed_lo=("bedrooms", "min"),
    bed_hi=("bedrooms", "max"),
)
h = h.merge(u, left_on=["building", "unit_id"], right_index=True, how="left")
h["kind"] = np.where(
    h.un.isna(),
    "no unit history",
    np.where(
        (h.baths == h.bath_lo)
        & (h.baths == h.bath_hi)
        & (h.bedrooms == h.bed_lo)
        & (h.bedrooms == h.bed_hi),
        "counts as before",
        "counts changed",
    ),
)
h["fb"] = h.full_baths.clip(upper=3)
h["bd"] = h.bedrooms.clip(upper=4)
h["tier"] = pd.qcut(h.pred, [0, 0.25, 0.5, 0.75, 0.9, 0.97, 1], labels=False)
LOW = norm.ppf(0.05)
pd.set_option("display.width", 250)


def cell(g):
    bm = g.groupby("building").res.agg(["sum", "size"])
    se = np.sqrt(((bm["sum"] - bm["size"] * g.res.mean()) ** 2).sum()) / len(g)
    return pd.Series(
        {
            "n": len(g),
            "res": g.res.mean(),
            "se": se,
            "z": g.z.mean(),
            "sdz": g.z.std(),
            "low": (g.z < LOW).mean(),
            "high": (g.z > -LOW).mean(),
        }
    )


print("all")
print(cell(h).round(4).to_string())
for by in (
    ["kind"],
    ["fb"],
    ["bd"],
    ["tier"],
    ["kind", "fb"],
    ["kind", "fb", "half"],
    ["kind", "tier"],
    ["tier", "fb"],
):
    print("\nby", by)
    print(
        h.groupby(by, observed=True)
        .apply(cell, include_groups=False)
        .round(4)
        .to_string()
    )
h.to_parquet("/data1/apartments/tmp/history-scan/backtest-range-j.parquet")
