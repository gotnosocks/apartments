"""Are the held-out low misses gathered in a few buildings?

Usage: bybuilding.py FRAME, the per-ad frame of the scan (columns building, cdf, res).
"""

import sys

import numpy as np
import pandas as pd

t = pd.read_parquet(sys.argv[1])
t["low"] = t.cdf < 0.05
g = t.groupby("building").agg(n=("low", "size"), k=("low", "sum"), res=("res", "mean"))
print("ads", len(t), "buildings", len(g), "low share", round(t.low.mean(), 4))
for lo, hi in [(1, 1), (2, 4), (5, 9), (10, 29), (30, 99), (100, 10**6)]:
    s = g[(g.n >= lo) & (g.n <= hi)]
    print(
        lo,
        hi,
        "buildings",
        len(s),
        "ads",
        s.n.sum(),
        "low share",
        round(s.k.sum() / s.n.sum(), 4),
    )
s = g[(g.n >= 10) & (g.k / g.n >= 0.25)]
print(
    "ten or more ads, a quarter low: buildings",
    len(s),
    "ads",
    s.n.sum(),
    "low",
    s.k.sum(),
)
print("of", t.low.sum(), "low ads; mean gap of those buildings", round(s.res.mean(), 3))
rng = np.random.default_rng(0)
n = g.n.to_numpy()
draws = []
for _ in range(200):
    k = rng.binomial(n, t.low.mean())
    draws.append(k[(n >= 10) & (k / n >= 0.25)].sum())
print("binomial null: mean", round(np.mean(draws), 1), "largest", np.max(draws))
