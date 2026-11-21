import pandas as pd, pyarrow.parquet as pq

h = pd.read_parquet("/data1/apartments/tmp/history-scan/baths-l2bt.parquet")
print(list(h.columns)[:40])
h["listing_id"] = h.listing_id.astype(str)
UF = "/data1/apartments/external/unit-features/20261021-16cea7c/unit_features.parquet"
ids = sorted(set(h.listing_id))
sz = pq.read_table(
    UF,
    columns=["listing_id", "sqft", "size_source"],
    filters=[("listing_id", "in", ids)],
).to_pandas()
sz["listing_id"] = sz.listing_id.astype(str)
h = h.merge(sz.drop_duplicates("listing_id"), on="listing_id", how="left")
yr = pd.to_datetime(h.price_at).dt.year
g = h[
    (yr >= 2022)
    & (h.bedrooms <= 1)
    & h.size_source.fillna("none").ne("none")
    & (h.sqft > 1000)
]
print("ads", len(g))
print(pd.crosstab(g.size_source, g.bedrooms, margins=True))
print(g.sqft.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(0).to_dict())
allsmall = h[(yr >= 2022) & (h.bedrooms <= 1) & h.size_source.fillna("none").ne("none")]
print("share of sized 0-1 bd from 2022 over 1,000:", round(len(g) / len(allsmall), 4))
print(allsmall.size_source.value_counts(normalize=True).round(3).to_dict())
