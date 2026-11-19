"""Do the high-turnover backtest ads below the 5% point look like net-of-concession asks?

Usage: turn_net.py FRAME TURNOVER_DATASET
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import drift_deals

ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
h = pd.read_parquet(sys.argv[1])
h["listing_id"] = h.listing_id.astype(str)
cols = ["listing_id", "price_at", "bld_opened_730", "res_units_asof"]
t = pq.read_table(f"{sys.argv[2]}/rows.parquet", columns=cols).to_pandas()
t["listing_id"] = t.listing_id.astype(str)
h = h.merge(t, on=["listing_id", "price_at"], how="left", validate="1:1")
a = drift_deals._ads(ADS, h.listing_id)
print("ad fields", list(a.columns))
n = h.bld_opened_730.to_numpy(float)
u = h.res_units_asof.to_numpy(float)
known = np.isfinite(u) & (u > 0)
rate = np.where(known, n / 2 / np.where(known, u, 1), np.nan)
h["band"] = np.select(
    [n == 0, ~known, rate <= 0.123, rate <= 0.223, rate <= 0.417],
    ["none", "units unknown", "Q1", "Q2", "Q3"],
    "Q4",
)
h["low"] = h.cdf < 0.05
ask = h.latest_ask.to_numpy(float)
h["free"] = np.nan_to_num(a.months_free.to_numpy(float))
h["coded"] = h.free > 0
h["round25"] = np.abs(ask - np.round(ask / 25) * 25) < 0.01
h["odd"] = ~np.isin(np.round(ask) % 10, (0, 5, 9))
h["page"] = a.page_price.to_numpy(float)
h["first"] = a.first_ask.to_numpy(float)
h["page_below"] = h.page < h.latest_ask - 1
pd.set_option("display.width", 220)
agg = dict(
    n=("low", "size"),
    coded=("coded", "mean"),
    free=("free", "mean"),
    round25=("round25", "mean"),
    odd=("odd", "mean"),
    page_below=("page_below", "mean"),
    res=("res", "mean"),
)
print("\nall held-out ads by band")
print(h.groupby("band").agg(**agg).round(3).to_string())
print("\nads below the 5% point by band")
print(h[h.low].groupby("band").agg(**agg).round(3).to_string())
print("\nby coded free months: res and tails")
h["fb_"] = pd.cut(h.free, [-1, 0, 0.99, 1.49, 2.49, 12])
print(
    h.groupby("fb_", observed=True)
    .agg(
        n=("low", "size"),
        res=("res", "mean"),
        low=("low", "mean"),
        high=("cdf", lambda x: (x > 0.95).mean()),
        odd=("odd", "mean"),
    )
    .round(4)
    .to_string()
)
print("\nby band and coded free months: res, low")
print(
    h.groupby(["band", "coded"])
    .agg(n=("low", "size"), res=("res", "mean"), low=("low", "mean"))
    .round(4)
    .to_string()
)
print("\nby odd last digit of the ask and coded: res, low")
print(
    h.groupby(["coded", "odd"])
    .agg(n=("low", "size"), res=("res", "mean"), low=("low", "mean"))
    .round(4)
    .to_string()
)
print("\nQ4 and units unknown, ads below the 5% point, largest buildings")
lo = h[h.low & h.band.isin(["Q4", "units unknown"])]
print(
    lo.sort_values("building")[
        ["building", "bedrooms", "latest_ask", "first", "page", "free", "res"]
    ]
    .head(45)
    .round(2)
    .to_string()
)
