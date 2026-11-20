import pandas as pd, json, pyarrow.parquet as pq, re

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)
R = pd.read_parquet("rows_live.parquet")
M = pd.read_parquet("nb_medians.parquet")
bl = [
    "350-east-84-street-new_york",
    "131-east-70-street-new_york",
    "115-east-62-street-manhattan",
    "14-spencer-place-brooklyn",
    "bouwerie-lane-theatre-former-bond",
    "11-essex-street-new_york",
]
x = R[R.building.isin(bl)].copy()
x["year"] = pd.to_datetime(x.latest_day).dt.year
x = x.merge(M, on=["neighbourhood", "year", "bedrooms"], how="left")
x["ratio"] = x.latest_ask / x.nb_median
S = pd.read_parquet("sel_records.parquet")
want = set(x.listing_id.astype(int)) - set(S.listing_id.astype(int))
rec = pq.ParquetFile(
    "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
)
parts = [S[S.listing_id.isin(set(x.listing_id.astype(int)))]]
for g in range(rec.metadata.num_row_groups):
    if not want:
        break
    ids = rec.read_row_group(g, columns=["listing_id"]).column(0).to_numpy()
    if not want.intersection(ids.tolist()):
        continue
    p = rec.read_row_group(
        g, columns=["listing_id", "collected_at", "raw_listing_json"]
    ).to_pandas()
    parts.append(p[p.listing_id.isin(want)])
T = (
    pd.concat(parts)
    .sort_values("collected_at")
    .groupby("listing_id")
    .tail(1)
    .set_index("listing_id")
)
for b, g in x.sort_values("latest_day").groupby("building"):
    print("\n##", b)
    for r in g.itertuples():
        try:
            j = json.loads(T.loc[int(r.listing_id), "raw_listing_json"])
            desc = re.sub(r"\s+", " ", j.get("description") or "")
            unit = (j.get("propertyDetails") or {}).get("address", {}).get("unit")
        except Exception as e:
            desc = "[NO RECORD]"
            unit = None
        print(
            f"- {r.listing_id} {str(r.latest_day)[:10]} {r.bedrooms:.0f}bd/{r.full_baths:.0f}ba ${r.latest_ask:,.0f} x{r.ratio:.1f} unit={unit} held={int(r.heldout)}\n  TEXT: {desc[:700]}"
        )
