"""The changed-count and bath findings again, on 2022 to 2024 and on 2025 and 2026.

Usage: recent.py FRAME, the per-ad frame of the scan.
"""

import sys

import numpy as np
import pandas as pd

t = pd.read_parquet(sys.argv[1])
t["low"] = t.cdf < 0.05
t["high"] = t.cdf > 0.95
t["per"] = np.where(
    t.year >= 2025, "2025-26", np.where(t.year >= 2022, "2022-24", "before")
)
t["fbc"] = t.fb.clip(upper=3)
t = t[t.per != "before"]
for k in ["kind", "fbc"]:
    g = t.groupby(["per", k]).agg(
        n=("low", "size"),
        low=("low", "mean"),
        high=("high", "mean"),
        res=("res", "mean"),
    )
    for h in (0, 1):
        g[f"low_h{h}"] = t[t.half == h].groupby(["per", k]).low.mean()
    print(g.round(4).to_string())
g = (
    t[t.same]
    .groupby(["per", "fbc"])
    .agg(n=("low", "size"), low=("low", "mean"), res=("res", "mean"))
)
print("counts as before")
print(g.round(4).to_string())
