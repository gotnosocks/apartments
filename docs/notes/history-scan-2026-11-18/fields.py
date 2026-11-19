"""Held-out low share and mean gap by coded ad fields no earlier check read.

Usage: fields.py TAG YEAR, with baths-TAG.parquet the scan's per-ad frame.
"""

import sys

import numpy as np
import pandas as pd

ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
tag, year = sys.argv[1], int(sys.argv[2])
h = pd.read_parquet(f"baths-{tag}.parquet")
h = h[h.year >= year]
cols = [
    "furnished",
    "short_term",
    "lease_term",
    "square_feet",
    "laundry_type",
    "hvac_type",
    "pet_policy",
    "view_exposures",
    "window_exposures",
    "break_status",
    "floor_plans",
    "conflicts",
    "from_text",
]
a = pd.read_parquet(ADS, columns=["listing_id", *cols]).drop_duplicates("listing_id")
t = h.merge(a, on="listing_id", how="left")
t["low"] = t.cdf < 0.05
t["high"] = t.cdf > 0.95
print("ads", len(t), "low", round(t.low.mean(), 4), "high", round(t.high.mean(), 4))
for c in cols:
    v = t[c]
    print("\n", c, v.dtype)
    if v.dtype == object:
        first = v.dropna().iloc[0] if v.notna().any() else None
        if isinstance(first, (list, np.ndarray)):
            v = v.map(lambda x: 0 if x is None else len(x)).clip(upper=3)
        else:
            v = v.fillna("(none)").astype(str)
            keep = v.value_counts().index[:8]
            v = v.where(v.isin(keep), "(other)")
    elif c == "square_feet":
        v = np.where(v.isna(), "none", "given")
    elif v.dtype.kind == "f" and v.nunique() > 8:
        v = pd.cut(v, [-np.inf, 5.5, 11.5, 12.5, 17.5, np.inf]).astype(str)
    else:
        v = v.astype(str)
    g = (
        t.assign(v=v)
        .groupby(["v"])
        .agg(
            n=("low", "size"),
            low=("low", "mean"),
            high=("high", "mean"),
            res=("res", "mean"),
        )
    )
    for hf in (0, 1):
        s = t.assign(v=v)[t.half == hf].groupby("v").low.mean()
        g[f"low_h{hf}"] = s
    print(g.round(4).to_string())
