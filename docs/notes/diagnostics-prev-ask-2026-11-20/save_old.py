"""Save the columns of the published diagnostics that the fix changes, before the next
publish replaces them. Run once, on 2026-11-20: `python save_old.py old-prev.parquet`."""

import sys

import pandas as pd

LIVE = "/data1/apartments/site/diagnostics/ads.parquet"
t = pd.read_parquet(
    LIVE,
    columns=[
        "listing_id",
        "model_median",
        "prev_ask",
        "prev_day",
        "prev_bedrooms",
        "flags",
    ],
)
codes = t.pop("flags").apply(list)
for f in ("beds_jump", "ask_jump"):
    t[f] = codes.apply(lambda v, f=f: f in v)
t.to_parquet(sys.argv[1], index=False, compression="zstd")
print(len(t), "rows")
