"""Held-out errors by predicted-rent tier and year, and baths within tiers."""

import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

run, tag = sys.argv[1], sys.argv[2]
h = pd.read_parquet(f"baths-{tag}.parquet")
s = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
q = s["q"]
sc = pd.DataFrame(
    {
        "listing_id": s["listing"],
        "pred": s["pred"],
        "y": s["y"],
        "w90": q[:, 6] - q[:, 1],
    }
)
h = h.merge(sc, on="listing_id")
LOW = norm.ppf(0.05)
pd.set_option("display.width", 250)
h["tier"] = h.groupby("year").pred.transform(
    lambda x: pd.qcut(x, [0, 0.25, 0.5, 0.75, 0.9, 0.97, 1], labels=False)
)


def cell(g):
    bm = g.groupby("building").res.agg(["sum", "size"])
    se = np.sqrt(((bm["sum"] - bm["size"] * g.res.mean()) ** 2).sum()) / len(g)
    return pd.Series(
        {
            "n": len(g),
            "rent": np.exp(g.pred.median()),
            "res": g.res.mean(),
            "se": se,
            "z": g.z.mean(),
            "sdz": g.z.std(),
            "low": (g.z < LOW).mean(),
            "high": (g.z > -LOW).mean(),
            "w90": g.w90.median(),
            "mad": g.res.abs().median(),
        }
    )


print(run, "pred scale check: median exp(pred)", np.exp(h.pred.median()).round(0))
h["era"] = pd.cut(
    h.year,
    [2013, 2019, 2021, 2023, 2026],
    labels=["2014-19", "2020-21", "2022-23", "2024-26"],
)
print(
    "\ntier of predicted rent within year (0 = cheapest quarter .. 5 = top 3%) by era"
)
print(
    h.groupby(["tier", "era"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .to_string()
)
g = h[h.year >= 2022]
print("\n2022 on: tier by half of buildings")
print(
    g.groupby(["tier", "half"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)[["n", "res", "se", "z", "sdz", "low", "high"]]
    .unstack(-1)
    .to_string()
)
print("\n2022 on: full baths within tier")
print(
    g.groupby(["tier", "fb"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)[["n", "res", "se", "z", "sdz", "low", "high"]]
    .to_string()
)
print("\n2022 on: tier, apartments whose training ads carry the same counts")
print(
    g[g.same]
    .groupby(["tier"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .to_string()
)
