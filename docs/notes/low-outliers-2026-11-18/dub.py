import pandas as pd, json, pyarrow.parquet as pq
A = pd.read_json("answers_joined.jsonl", lines=True, dtype={"listing_id": str})
ds = ["/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market-bedtext/rows.parquet",
      "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet"]
F = pd.concat([pq.read_table(d, columns=["listing_id", "bed_flex_at", "bed_text_fewer", "bedrooms"]).to_pandas() for d in ds])
F["listing_id"] = F.listing_id.astype(str); F = F.drop_duplicates("listing_id").set_index("listing_id")
A["flag"] = (F.bed_flex_at.reindex(A.listing_id).fillna(False) | F.bed_text_fewer.reindex(A.listing_id).fillna(False)).to_numpy()
A["found"] = A.listing_id.isin(F.index); A["beds"] = F.bedrooms.reindex(A.listing_id).to_numpy()
A["dub"] = A.reasons.map(lambda r: "beds_dubious" in r)
print(pd.crosstab([A.set, A.dub], A.flag))
pd.set_option("display.width", 250, "display.max_colwidth", 330)
for _, r in A[A.dub & ~A.flag].iterrows(): print(r.set, r.listing_id, r.beds, "|", r.note[:330])
