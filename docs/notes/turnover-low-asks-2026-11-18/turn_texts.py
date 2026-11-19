"""Texts of the backtest ads, and reading packets: Q4 / units-unknown ads below the 5% point
against Q4 ads between the 30% and 70% points. Usage: turn_texts.py FRAME TURNOVER_DATASET"""

import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import api_records, descriptions

h = pd.read_parquet(sys.argv[1])
h["listing_id"] = h.listing_id.astype(str)
t = pq.read_table(
    f"{sys.argv[2]}/rows.parquet",
    columns=["listing_id", "price_at", "bld_opened_730", "res_units_asof"],
).to_pandas()
t["listing_id"] = t.listing_id.astype(str)
h = h.merge(t, on=["listing_id", "price_at"], how="left", validate="1:1")
d = descriptions.record_descriptions(api_records.records_file(), set(h.listing_id))
d = d.rename_axis("listing_id").reset_index()
print("texts", len(d), d.description.notna().sum(), list(d.columns))
h = h.merge(d[["listing_id", "description"]], on="listing_id", how="left")
n, u = h.bld_opened_730.to_numpy(float), h.res_units_asof.to_numpy(float)
known = np.isfinite(u) & (u > 0)
rate = np.where(known, n / 2 / np.where(known, u, 1), np.nan)
h["band"] = np.select(
    [n == 0, ~known, rate <= 0.123, rate <= 0.223, rate <= 0.417],
    ["none", "units unknown", "Q1", "Q2", "Q3"],
    "Q4",
)
h.to_parquet("backtest-range-j-texts.parquet")
ok = h.description.fillna("").str.len() >= 40
hot = h.band.isin(["Q4", "units unknown"])
low = (
    h[ok & hot & (h.cdf < 0.05)]
    .drop_duplicates("building")
    .sample(frac=1, random_state=1)
    .head(60)
)
mid = (
    h[ok & hot & h.cdf.between(0.3, 0.7)]
    .drop_duplicates("building")
    .sample(frac=1, random_state=1)
    .head(60)
)
both = (
    pd.concat([low.assign(g="L"), mid.assign(g="M")])
    .sample(frac=1, random_state=2)
    .reset_index(drop=True)
)
both["code"] = [f"A{i:03d}" for i in range(len(both))]
both[["code", "g", "listing_id", "building", "cdf", "res"]].to_csv(
    "turn-read-key.csv", index=False
)
with open("turn-read-packet.txt", "w") as f:
    for r in both.itertuples():
        f.write(
            f"=== {r.code} | {r.building} | {r.bedrooms:g} bed | opened {str(r.price_at)[:10]}\n{r.description.strip()}\n\n"
        )
print(len(low), len(mid))
