import pandas as pd, numpy as np, pyarrow.parquet as pq, json

L = pd.concat([pd.read_parquet(f"levels_{t}.parquet") for t in ("live", "back")])
u = sorted(set(L[L.rhat > 1.05].building))
D = {
    "live": "/data1/apartments/frontier/datasets/b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext/rows.parquet",
    "back": "/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-bedtext/rows.parquet",
}
ids = {}
for t, pth in D.items():
    x = pq.read_table(
        pth, columns=["listing_id", "building"], filters=[("building", "in", u)]
    ).to_pandas()
    ids[t] = set(x.listing_id.astype(str))
p = pd.read_parquet("packet.parquet")
p = p[p.grp == "rhat"]
p["in_live"] = p.listing_id.isin(ids["live"])
p["in_back"] = p.listing_id.isin(ids["back"])
print(len(p), len(ids["live"] | ids["back"]), p.in_live.sum(), p.in_back.sum())
print(p[~p.in_live].groupby(["building", "src"]).size().to_string())
# why absent in live? look in ads file
A = pd.read_parquet("sel_ads.parquet").drop_duplicates("listing_id")
A["listing_id"] = A.listing_id.astype(str)
m = p[~p.in_live].merge(
    A[["listing_id", "in_rows", "fate", "exclusion_reasons", "ledger_entries"]],
    on="listing_id",
    how="left",
)
m["er"] = m.exclusion_reasons.map(
    lambda v: ",".join(v) if v is not None and len(v) else ""
)
print(m.groupby(["in_rows", "er"], dropna=False).size())
print(
    m[["listing_id", "building", "bedrooms", "latest_ask", "er", "ledger_entries_y"]]
    .head(12)
    .to_string()
)
p.to_parquet("union_rows.parquet")
