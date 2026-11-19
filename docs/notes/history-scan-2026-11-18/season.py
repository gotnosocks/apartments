"""Held-out low share by calendar month and by quarter.

Usage: season.py FRAME, the per-ad frame of the scan (columns day, cdf, res, half, year).
"""

import sys

import pandas as pd

t = pd.read_parquet(sys.argv[1], columns=["day", "cdf", "res", "half", "year"])
t = t[t.year >= 2022]
t["low"] = t.cdf < 0.05
t["high"] = t.cdf > 0.95
d = pd.to_datetime(t.day)
t["m"] = d.dt.month
t["q"] = d.dt.to_period("Q").astype(str)
for k in ["m", "q"]:
    g = t.groupby(k).agg(
        n=("low", "size"),
        low=("low", "mean"),
        high=("high", "mean"),
        res=("res", "mean"),
    )
    for h in (0, 1):
        g[f"low_h{h}"] = t[t.half == h].groupby(k).low.mean()
    print(g.round(4).to_string())
