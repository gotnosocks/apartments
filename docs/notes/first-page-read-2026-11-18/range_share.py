"""Free check: the share of live Deals ads carrying each range mark of the layout-range model,
among the first 100 and 547 uncautioned ads, all uncautioned ads and the cautioned ones.

Run from the repo root with PYTHONPATH=frontier/src: python docs/notes/first-page-read-2026-11-18/range_share.py
"""

import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from rentfrontier import drift_building_bedtext_layout_range as R

D = "/data1/apartments/frontier/datasets/b0-c1761f182246962c-alldata-dense-nyc-market-bedtext/rows.parquet"
f = pq.read_table(
    D,
    columns=[
        "listing_id",
        "unit_id",
        "building",
        "price_at",
        "bedrooms",
        "full_baths",
        "half_baths",
    ],
).to_pandas()
d = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
d["listing_id"] = d.listing_id.astype(str)
lid = f.listing_id.astype(str)
held = lid.isin(set(d.listing_id)).to_numpy()
m = R.marks(f, ~held)
x = pd.DataFrame(m[held], columns=R.COLUMNS)
x["listing_id"] = lid[held].to_numpy()
x = x.groupby("listing_id").max().reset_index()
d = d.merge(x, on="listing_id", how="left")
d["unc"] = ~d.cautions.map(bool)
u = d[d.unc].reset_index(drop=True)
print("held rows", held.sum(), "ads", len(d), "uncautioned", len(u))
for n in (100, 547, len(u)):
    print(n, {c: round(100 * u[c][:n].mean(), 1) for c in R.COLUMNS})
print("cautioned", {c: round(100 * d[~d.unc][c].mean(), 1) for c in R.COLUMNS})
ids = "5199535 5205442 5204327 5202582 5197490 5201099 5200273 5203988".split()
print(
    d[d.listing_id.isin(ids)][
        ["listing_id", "bedrooms", "unit_ads", *R.COLUMNS]
    ].to_string()
)
