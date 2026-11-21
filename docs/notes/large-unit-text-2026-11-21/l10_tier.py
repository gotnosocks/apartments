"""3+ bedroom held-out ads: gap by the building's finish share within tiers of predicted rent."""

import duckdb, numpy as np, pandas as pd, pyarrow.parquet as pq

RUN = "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
D = "/data1/apartments/tmp/any-unit/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
h = pq.read_table(D + "heldout.parquet").to_pandas()
a = (
    pq.read_table(
        ADS,
        columns=["listing_id", "bedrooms"],
        filters=[("listing_id", "in", sorted(set(h.listing_id)))],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
m = pd.read_parquet("l8_marks.parquet")
s = np.load(f"/data1/apartments/frontier/runs/{RUN}/pred_scores.npz", allow_pickle=True)
p = pd.DataFrame({"listing_id": s["listing"], "pred": s["pred"]})
p["listing_id"] = p.listing_id.astype(h.listing_id.dtype)
x = h.merge(a, on="listing_id").merge(m, on="listing_id").merge(p, on="listing_id")
print("joined", len(x))
x["high"] = ~x.cover90 & ~x.low
x["year"] = pd.to_datetime(x.day).dt.year
g = x.groupby("building").spec
n = g.transform("size")
k = g.transform("sum")
x["share"] = ((k - x.spec) / (n - 1)).where(n >= 4)
x = x[(x.bedrooms >= 3) & x.share.notna()].copy()
x["tier"] = (
    x.groupby("year")
    .pred.transform(lambda v: pd.qcut(v, 4, labels=["q1", "q2", "q3", "q4"]))
    .astype(str)
)
x["band"] = np.where(x.share == 0, "0", np.where(x.share <= 0.2, "<.2", ">.2"))
print(
    duckdb.sql("""select tier, band, half, count(*) n, round(avg(gap),4) gap, round(stddev(gap)/sqrt(count(distinct building)),4) se,
  round(avg(high::int),3) high from x group by all order by all""")
    .df()
    .pivot_table(
        index=["tier", "band"], columns="half", values=["n", "gap", "se", "high"]
    )
    .round(4)
    .to_string()
)
