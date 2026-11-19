"""Who are the high-turnover backtest ads below the 5% point? Usage: turn_who.py FRAME TURNOVER_DATASET"""

import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

h = pd.read_parquet(sys.argv[1])
h["listing_id"] = h.listing_id.astype(str)
cols = ["listing_id", "building", "price_at", "bld_opened_730", "res_units_asof"]
t = pq.read_table(f"{sys.argv[2]}/rows.parquet", columns=cols).to_pandas()
t["listing_id"] = t.listing_id.astype(str)
first = t.groupby("building").price_at.min().rename("bld_first")
rows = t.groupby("building").size().rename("bld_rows")
h = h.merge(
    t.drop(columns="building"),
    on=["listing_id", "price_at"],
    how="left",
    validate="1:1",
)
h = h.join(first, on="building").join(rows, on="building")
n = h.bld_opened_730.to_numpy(float)
u = h.res_units_asof.to_numpy(float)
known = np.isfinite(u) & (u > 0)
rate = np.where(known, n / 2 / np.where(known, u, 1), np.nan)
h["rate"] = rate
h["band"] = np.select(
    [n == 0, ~known, rate <= 0.123, rate <= 0.223, rate <= 0.417],
    ["none", "units unknown", "Q1", "Q2", "Q3"],
    "Q4",
)
h["low"] = h.cdf < 0.05
h["age"] = (h.price_at - h.bld_first).dt.days / 365.25
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 60)
flags = [
    "furnished",
    "short_term",
    "shared_space",
    "income_restricted",
    "rent_stabilized",
]
print("flag shares by band, all ads and low ads")
for b, g in h.groupby("band"):
    lo = g[g.low]
    print(
        f"{b:14s} n {len(g):5d} low {len(lo):4d} | "
        + " ".join(
            f"{f[:8]} {g[f].fillna(False).astype(bool).mean():.2f}/{lo[f].fillna(False).astype(bool).mean():.2f}"
            for f in flags
        )
        + f" | units med {g.res_units_asof.median():.0f}/{lo.res_units_asof.median():.0f}"
        + f" | yrs in data med {g.age.median():.1f}/{lo.age.median():.1f}"
        + f" | rate med {g.rate.median():.2f}/{lo.rate.median():.2f}"
    )
print("\nlow share by years the building has been in the data")
h["ageb"] = pd.cut(h.age, [-1, 1, 2, 3, 5, 8, 30])
print(
    h.groupby("ageb", observed=True)
    .agg(
        n=("low", "size"),
        res=("res", "mean"),
        low=("low", "mean"),
        high=("cdf", lambda x: (x > 0.95).mean()),
    )
    .round(4)
    .to_string()
)
print("\nQ4: low share by years in the data")
q = h[h.band == "Q4"]
print(
    q.groupby("ageb", observed=True)
    .agg(n=("low", "size"), res=("res", "mean"), low=("low", "mean"))
    .round(4)
    .to_string()
)
print("\nQ4: low share by rate")
q = q.assign(rb=pd.cut(q.rate, [0.417, 0.6, 0.9, 1.5, 3, 1000]))
print(
    q.groupby("rb", observed=True)
    .agg(
        n=("low", "size"),
        bld=("building", "nunique"),
        res=("res", "mean"),
        low=("low", "mean"),
        units=("res_units_asof", "median"),
    )
    .round(4)
    .to_string()
)
print("\nQ4: low share by residential units")
q = q.assign(ub=pd.cut(q.res_units_asof, [0, 2, 4, 9, 19, 49, 199, 100000]))
print(
    q.groupby("ub", observed=True)
    .agg(
        n=("low", "size"),
        bld=("building", "nunique"),
        res=("res", "mean"),
        low=("low", "mean"),
        rate=("rate", "median"),
    )
    .round(4)
    .to_string()
)
print("\nQ4 and units unknown: buildings with the most low ads")
lo = h[h.low & h.band.isin(["Q4", "units unknown"])]
top = lo.groupby("building").agg(
    low=("low", "size"),
    band=("band", "first"),
    units=("res_units_asof", "first"),
    opened=("bld_opened_730", "first"),
    yrs=("age", "first"),
    nb=("neighbourhood", "first"),
    res=("res", "mean"),
)
allb = h.groupby("building").size().rename("held")
print(top.join(allb).sort_values("low", ascending=False).head(40).round(2).to_string())
print(
    "\nlow Q4 ads: buildings",
    lo[lo.band == "Q4"].building.nunique(),
    "ads",
    int((lo.band == "Q4").sum()),
)
