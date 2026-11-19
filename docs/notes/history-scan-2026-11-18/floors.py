"""Held-out errors by the unit label's floor, with and without an elevator, by half of buildings."""

import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
tag, y0 = sys.argv[1], int(sys.argv[2])
h = pd.read_parquet(f"baths-{tag}.parquet")
a = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "label_floor",
        "advertised_floor",
        "elevator",
        "floors_above_ground",
    ],
).drop_duplicates("listing_id")
h = h.merge(a, on="listing_id", how="left")
h = h[h.year >= y0]
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


print(
    "label_floor known",
    h.label_floor.notna().mean().round(3),
    "advertised known",
    h.advertised_floor.notna().mean().round(3),
    "elevator",
    h.elevator.value_counts(dropna=False).to_dict(),
)
h["fl"] = pd.cut(h.label_floor, [-50, 0, 1, 2, 3, 5, 10, 20, 40, 200]).astype(str)
h["el"] = h.elevator.fillna(False).astype(bool)
print("\nby floor and half")
print(
    h.groupby(["fl", "half"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(-1)[["n", "res", "se", "low", "high"]]
    .to_string()
)
print("\nby elevator and floor")
print(
    h.groupby(["el", "fl"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .to_string()
)
top = h.label_floor >= h.floors_above_ground
print(
    "\ntop floor of the building (label floor at or above the building's floors), by elevator and half"
)
print(
    h[top & (h.floors_above_ground >= 3)]
    .groupby(["el", "half"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .to_string()
)
d = h.advertised_floor - h.label_floor
print("\nadvertised floor less label floor")
print(
    h.assign(d=pd.cut(d, [-100, -1.5, -0.5, 0.5, 1.5, 100]).astype(str))
    .groupby(["d"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .to_string()
)
