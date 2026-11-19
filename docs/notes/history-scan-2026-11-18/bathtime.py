"""Held-out errors of 2 and 3+ bath ads against 1 bath ads by year, and by the date of the unit's last training ad."""

import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
run, tag = sys.argv[1], sys.argv[2]
h = pd.read_parquet(f"baths-{tag}.parquet")
r = pd.read_parquet(DS, columns=["building", "unit_id", "price_at"])
s = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
r["day"] = pd.to_datetime(r.price_at)
r["apt"] = r.unit_id.str.replace(r"~\d+$", "", regex=True)
last = r[~s["heldout"]].groupby(["building", "apt"]).day.max().rename("last")
h = h.merge(last, left_on=["building", "apt"], right_index=True, how="left")
h["gap"] = (h.day - h["last"]).dt.days / 365.25
h["lasty"] = h["last"].dt.year
LOW = norm.ppf(0.05)
pd.set_option("display.width", 250)


def cell(g):
    bm = g.groupby("building").res.agg(["sum", "size"])
    se = np.sqrt(((bm["sum"] - bm["size"] * g.res.mean()) ** 2).sum()) / len(g)
    return pd.Series(
        {"n": len(g), "res": g.res.mean(), "se": se, "low": (g.z < LOW).mean()}
    )


k = h[h.same]
print(run, "\ncounts as before: by year and full baths")
print(
    k.groupby(["year", "fb"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(-1)[["n", "res", "se", "low"]]
    .to_string()
)
g = k[k.year >= 2022].copy()
g["hist"] = pd.cut(
    g.lasty,
    [2000, 2019, 2021, 2030],
    labels=["last training ad to 2019", "2020-21", "2022 on"],
)
print("\n2022 on, counts as before: by the year of the unit's last training ad")
print(
    g.groupby(["hist", "fb"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(-1)[["n", "res", "se", "low"]]
    .to_string()
)
g["gapb"] = pd.cut(g.gap, [-1, 0.5, 1.5, 2.5, 4, 30])
print("\n2022 on, counts as before: by years since the unit's last training ad")
print(
    g.groupby(["gapb", "fb"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(-1)[["n", "res", "se", "low"]]
    .to_string()
)
print("\n2024 on, counts as before, unit's last training ad 2022 on: by half")
print(
    g[(g.year >= 2024) & (g.lasty >= 2022)]
    .groupby(["fb", "half"], observed=True)
    .apply(cell, include_groups=False)
    .round(4)
    .unstack(-1)
    .to_string()
)
