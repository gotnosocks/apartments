"""Held-out backtest ads against the unit's own last training ad, by turnover band and tail.
Usage: turn_prev.py FRAME_WITH_TEXTS DATASET"""

import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

h = pd.read_parquet(sys.argv[1]).drop(columns=["description"])
pf = pq.ParquetFile(f"{sys.argv[2]}/rows.parquet")
names = pf.schema_arrow.names
print([c for c in names if not c.startswith(("ad:", "x:"))][:60])
rent = "rent" if "rent" in names else [c for c in names if "rent" in c or "ask" in c][0]
print("rent column", rent)
r = pf.read(columns=["listing_id", "unit_id", "price_at", rent]).to_pandas()
r["listing_id"] = r.listing_id.astype(str)
held = set(h.listing_id)
tr = r[~r.listing_id.isin(held) & r.unit_id.notna()].sort_values("price_at")
last = tr.groupby("unit_id").tail(1).set_index("unit_id")
cnt = tr.groupby("unit_id").listing_id.nunique()
h["prev_rent"] = h.unit_id.map(last[rent])
h["prev_at"] = h.unit_id.map(last.price_at)
h["n_prev"] = h.unit_id.map(cnt).fillna(0)
mine = (
    r[r.listing_id.isin(held)]
    .sort_values("price_at")
    .groupby("listing_id")
    .tail(1)
    .set_index("listing_id")
)
h["rent_now"] = h.listing_id.map(mine[rent])
v = h.rent_now.to_numpy(float)
if np.nanmedian(v) < 100:
    h["chg"] = h.rent_now - h.prev_rent
else:
    h["chg"] = np.log(h.rent_now / h.prev_rent)
h["gap"] = (pd.to_datetime(h.price_at) - pd.to_datetime(h.prev_at)).dt.days
h["tail"] = np.select([h.cdf < 0.05, h.cdf > 0.95], ["low", "high"], "mid")
h["hot"] = np.where(h.band.isin(["Q4", "units unknown"]), "Q4/unk", "other")
pd.set_option("display.width", 200)
g = h.groupby(["hot", "tail"])
print(
    g.agg(
        n=("cdf", "size"),
        has_prev=("prev_rent", lambda x: x.notna().mean()),
        n_prev=("n_prev", "median"),
        chg=("chg", "median"),
        chg_q25=("chg", lambda x: x.quantile(0.25)),
        gap=("gap", "median"),
        gap_lt120=("gap", lambda x: (x < 120).sum() / x.notna().sum()),
        down=("chg", lambda x: (x < -0.02).sum() / x.notna().sum()),
    )
    .round(3)
    .to_string()
)
h["gapb"] = pd.cut(h.gap, [-1, 60, 180, 420, 800, 99999])
print(
    h[h.hot == "Q4/unk"]
    .groupby("gapb", observed=True)
    .agg(
        n=("cdf", "size"),
        res=("res", "mean"),
        low=("cdf", lambda x: (x < 0.05).mean()),
        chg=("chg", "median"),
    )
    .round(3)
    .to_string()
)
print(
    h[h.hot == "other"]
    .groupby("gapb", observed=True)
    .agg(
        n=("cdf", "size"),
        res=("res", "mean"),
        low=("cdf", lambda x: (x < 0.05).mean()),
        chg=("chg", "median"),
    )
    .round(3)
    .to_string()
)
