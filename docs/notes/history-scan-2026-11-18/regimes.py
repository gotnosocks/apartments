"""Tail shares of held-out ads by how much history the model has, and by coded fields."""

import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
run = sys.argv[1]
y0 = int(sys.argv[2])
r = pd.read_parquet(
    DS,
    columns=["listing_id", "building", "unit_id", "price_at", "bedrooms", "full_baths"],
)
s = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
assert len(s["heldout"]) == len(r)
r["held"] = s["heldout"]
r["day"] = pd.to_datetime(r.price_at)
t = r[~r.held]
bn = t.groupby("building").agg(
    bn=("day", "size"), blast=("day", "max"), bfirst=("day", "min")
)
un = (
    t[t.unit_id.notna()]
    .groupby(["building", "unit_id"])
    .agg(un=("day", "size"), ulast=("day", "max"))
)
sc = pd.DataFrame(
    {
        "listing_id": s["listing"],
        "cdf": s["cdf"],
        "res": s["y"] - s["pred"],
        "usd": s["unit_sd"],
        "w": s["q"][:, -2] - s["q"][:, 1],
    }
)
print("quantiles", s["quantiles"])
h = (
    r[r.held]
    .merge(sc, on="listing_id")
    .merge(bn, left_on="building", right_index=True, how="left")
    .merge(un, left_on=["building", "unit_id"], right_index=True, how="left")
)
f = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "label_floor",
        "elevator",
        "square_feet",
        "doorman_type",
        "days_on_market",
        "status",
        "from_text",
        "floors_above_ground",
    ],
)
h = h.merge(f, on="listing_id", how="left")
h = h[h.day.dt.year >= y0]
h["z"] = norm.ppf(h.cdf.clip(1e-6, 1 - 1e-6))
h["bn"] = h.bn.fillna(0)
h["un"] = h.un.fillna(0)
h["ugap"] = (h.day - h.ulast).dt.days / 365.25
h["bgap"] = (h.day - h.blast).dt.days / 365.25
print(
    run,
    "held-out ads from",
    y0,
    len(h),
    "low",
    (h.cdf < 0.05).mean().round(4),
    "high",
    (h.cdf > 0.95).mean().round(4),
    "sd z",
    h.z.std().round(3),
)


def tab(name, key):
    g = h.groupby(key, observed=True).agg(
        n=("z", "size"),
        bld=("building", "nunique"),
        mean_z=("z", "mean"),
        sd_z=("z", "std"),
        low=("cdf", lambda c: (c < 0.05).mean()),
        high=("cdf", lambda c: (c > 0.95).mean()),
        low1=("cdf", lambda c: (c < 0.01).mean()),
        res=("res", "mean"),
        abs_res=("res", lambda x: x.abs().median()),
        width=("w", "median"),
    )
    print(f"\n{name}")
    print(g.round(3).to_string())


tab("training ads in the building", pd.cut(h.bn, [-1, 0, 2, 5, 10, 30, 100, 300, 1e6]))
tab("training ads of the unit", pd.cut(h.un, [-1, 0, 1, 2, 4, 8, 1e6]))
tab(
    "years since the unit's last training ad",
    pd.cut(h.ugap, [-50, 0, 0.25, 1, 2, 4, 8, 50])
    .cat.add_categories("no unit history")
    .fillna("no unit history"),
)
tab(
    "years since the building's last training ad",
    pd.cut(h.bgap, [-50, 0, 0.25, 1, 2, 4, 50])
    .cat.add_categories("none")
    .fillna("none"),
)
tab("unit id known", h.unit_id.notna())
tab("bedrooms", h.bedrooms.clip(upper=5))
tab("full baths", h.full_baths.clip(upper=4))
tab("elevator", h.elevator.astype(str))
tab("doorman", h.doorman_type.astype(str))
tab("size known", h.square_feet.notna())
tab(
    "floor",
    pd.cut(h.label_floor, [-5, 0, 1, 2, 3, 5, 10, 20, 40, 200])
    .cat.add_categories("unknown")
    .fillna("unknown"),
)
tab("year", h.day.dt.year)
h.to_parquet(f"/data1/apartments/tmp/history-scan/regimes-{sys.argv[3]}.parquet")
