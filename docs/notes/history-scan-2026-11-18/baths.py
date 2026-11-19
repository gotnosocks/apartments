"""Held-out errors by bath and bedroom count: over years, and apart from a unit's changed counts."""

import hashlib
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
run = sys.argv[1]
r = pd.read_parquet(
    DS,
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "neighbourhood",
        "price_at",
        "bedrooms",
        "full_baths",
        "half_baths",
    ],
)
s = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
r["held"] = s["heldout"]
r["day"] = pd.to_datetime(r.price_at)
r["baths"] = r.full_baths + 0.5 * r.half_baths.fillna(0)
r["apt"] = r.unit_id.str.replace(r"~\d+$", "", regex=True)
t = r[~r.held]
u = t.groupby(["building", "apt"]).agg(
    un=("day", "size"),
    bath_lo=("baths", "min"),
    bath_hi=("baths", "max"),
    bed_lo=("bedrooms", "min"),
    bed_hi=("bedrooms", "max"),
)
sc = pd.DataFrame(
    {"listing_id": s["listing"], "cdf": s["cdf"], "res": s["y"] - s["pred"]}
)
h = (
    r[r.held]
    .merge(sc, on="listing_id")
    .merge(u, left_on=["building", "apt"], right_index=True, how="left")
)
h["z"] = norm.ppf(h.cdf.clip(1e-6, 1 - 1e-6))
h["half"] = [
    hashlib.sha1(("history-scan-2026-11-18" + str(b)).encode()).digest()[0] % 2
    for b in h.building
]
h["year"] = h.day.dt.year
h["fb"] = h.full_baths.clip(upper=3)
h["bd"] = h.bedrooms.clip(upper=4)
h["same"] = (
    (h.un > 0)
    & (h.baths == h.bath_lo)
    & (h.baths == h.bath_hi)
    & (h.bedrooms == h.bed_lo)
    & (h.bedrooms == h.bed_hi)
)
h["kind"] = np.where(
    h.un.isna(),
    "no unit history",
    np.where(h.same, "counts as before", "counts changed"),
)
pd.set_option("display.width", 250)
LOW = norm.ppf(0.05)


def cell(g):
    bm = g.groupby("building").res.agg(["sum", "size"])
    se = np.sqrt(((bm["sum"] - bm["size"] * g.res.mean()) ** 2).sum()) / len(g)
    return pd.Series(
        {
            "n": len(g),
            "res": g.res.mean(),
            "se": se,
            "z": g.z.mean(),
            "low": (g.z < LOW).mean(),
            "high": (g.z > -LOW).mean(),
        }
    )


print(run)
print("\nfull baths by era (log residual, se clustered by building)")
h["era"] = pd.cut(
    h.year,
    [2013, 2017, 2019, 2021, 2023, 2026],
    labels=["2014-17", "2018-19", "2020-21", "2022-23", "2024-26"],
)
print(
    h.groupby(["fb", "era"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(0)[["n", "res", "se", "low"]]
    .to_string()
)
g = h[h.year >= 2022]
print("\n2022 on: bedrooms by full baths")
print(
    g.groupby(["bd", "fb"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .to_string()
)
print(
    "\n2022 on: full baths by whether the apartment's training ads carry the same counts, by half of buildings"
)
print(
    g.groupby(["kind", "fb", "half"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(-1)
    .to_string()
)
print("\n2022 on, counts as before: bedrooms 3+ by half")
print(
    g[g.same]
    .groupby(["bd", "half"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(-1)
    .to_string()
)
h.drop(columns=["era"]).to_parquet(
    f"/data1/apartments/tmp/history-scan/baths-{sys.argv[2]}.parquet"
)
