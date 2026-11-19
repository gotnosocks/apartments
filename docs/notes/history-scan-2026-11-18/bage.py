"""Held-out low share by years since the building's first training ad.

Usage: bage.py TAG, with regimes-TAG.parquet and baths-TAG.parquet from the scan.
"""

import sys

import numpy as np
import pandas as pd

tag = sys.argv[1]
r = pd.read_parquet(f"regimes-{tag}.parquet")
b = pd.read_parquet(f"baths-{tag}.parquet", columns=["listing_id", "half", "same"])
t = r.merge(b, on="listing_id")
t["age"] = (t.day - t.bfirst).dt.days / 365.25
t["band"] = (
    pd.cut(t.age, [-50, 0, 1, 2, 5, 8, 50]).astype(str).replace("nan", "no training ad")
)
t["low"] = t.cdf < 0.05
t["high"] = t.cdf > 0.95
print("ads", len(t), "low", round(t.low.mean(), 4))
for name, s in [
    ("all", t),
    ("counts as before", t[t.same]),
    ("30 or more training ads", t[t.bn >= 30]),
]:
    g = s.groupby("band").agg(
        n=("low", "size"),
        low=("low", "mean"),
        high=("high", "mean"),
        res=("res", "mean"),
    )
    for hf in (0, 1):
        g[f"low_h{hf}"] = s[s.half == hf].groupby("band").low.mean()
    g["se"] = np.sqrt(g.low * (1 - g.low) / g.n)
    print("\n", name)
    print(g.round(4).to_string())
