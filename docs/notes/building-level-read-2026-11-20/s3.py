import json, pandas as pd, numpy as np, pyarrow.parquet as pq

pd.set_option("display.width", 250, "display.max_rows", 500)
L = pd.concat([pd.read_parquet(f"levels_{t}.parquet") for t in ("live", "back")])
u = set(L[L.rhat > 1.05].building)
hi = set(L[(L.run == "live") & (L.level > 0.5) & (L.n_held > 0)].building)
lo = set(L[(L.run == "live") & (L.level < -0.3) & (L.n_held > 0)].building)
rl = pd.read_parquet("rows_live.parquet")
rb = pd.read_parquet("rows_back.parquet")
rows = pd.concat([rl, rb[~rb.listing_id.isin(rl.listing_id)]])
rows = rows[rows.building.isin(u | hi | lo)]
rows["grp"] = np.where(
    rows.building.isin(u), "rhat", np.where(rows.building.isin(hi), "hi", "lo")
)
print(rows.groupby("grp").agg(n=("listing_id", "size"), b=("building", "nunique")))
print(
    "union rows",
    rows[rows.building.isin(u)].shape,
    rows[rows.building.isin(u)].groupby("building").size().sort_values().tail(8),
)
rows.to_parquet("sel_rows.parquet")
# records for union buildings (all rows) and small hi buildings
bc = rows.groupby("building").size()
want = set(
    rows[(rows.grp == "rhat") & (rows.building.map(bc) <= 60)].listing_id.astype(int)
) | set(
    rows[(rows.grp != "rhat") & (rows.building.map(bc) <= 12)].listing_id.astype(int)
)
want |= set(rows[rows.heldout & (rows.run == "live")].listing_id.astype(int))
print("want", len(want))
REC = "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
rec = pq.ParquetFile(REC)
print(rec.schema_arrow.names, rec.metadata.num_row_groups)
parts = []
for g in range(rec.metadata.num_row_groups):
    ids = rec.read_row_group(g, columns=["listing_id"]).column(0).to_numpy()
    if not want.intersection(ids.tolist()):
        continue
    p = rec.read_row_group(
        g, columns=["listing_id", "collected_at", "raw_listing_json"]
    ).to_pandas()
    parts.append(p[p.listing_id.isin(want)])
R = pd.concat(parts).sort_values("collected_at").groupby("listing_id").tail(1)
print("found", len(R))
R.to_parquet("sel_records.parquet")
j = json.loads(R.raw_listing_json.iloc[0])
print(list(j.keys()))
print(json.dumps(j)[:1500])
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
cols = [
    "listing_id",
    "unit_id",
    "building",
    "page",
    "page_price",
    "months_free",
    "lease_term",
    "first_day",
    "off_day",
    "first_ask",
    "latest_ask",
    "bedrooms",
    "full_baths",
    "half_baths",
    "square_feet",
    "advertised_floor",
    "furnished",
    "short_term",
    "exclusion_reasons",
    "ledger_entries",
    "ask_check",
    "building_check",
    "in_rows",
    "fate",
]
A = pq.read_table(
    ADS, columns=cols, filters=[("building", "in", list(u | hi | lo))]
).to_pandas()
print(len(A))
A.to_parquet("sel_ads.parquet")
print(A.head(3).T)
