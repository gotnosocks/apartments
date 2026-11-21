"""Gap by size against the building's share of held-out ads with finish wording (text only)."""

import duckdb, numpy as np, pandas as pd, pyarrow.parquet as pq

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
x = h.merge(a, on="listing_id").merge(m, on="listing_id")
x["size"] = np.where(x.bedrooms >= 3, "3+", np.where(x.bedrooms >= 1, "1-2", "0"))
x["high"] = ~x.cover90 & ~x.low
for k in ["spec", "lux"]:
    # leave the ad's own mark out of its building's share
    g = x.groupby("building")[k]
    n = g.transform("size")
    s = g.transform("sum")
    x["share"] = ((s - x[k]) / (n - 1)).where(n >= 4)
    x["band"] = pd.cut(
        x.share, [-0.01, 0.0001, 0.2, 0.5, 1.01], labels=["0", "<.2", ".2-.5", ">.5"]
    ).astype(str)
    print(k)
    print(
        duckdb.sql("""select size, band, half, count(*) n, count(distinct building) b, round(avg(gap),4) gap,
      round(avg(high::int),3) high, round(avg(low::int),3) low from x where band != 'nan'
      group by all order by size, band, half""")
        .df()
        .pivot_table(
            index=["size", "band"], columns="half", values=["n", "gap", "high", "low"]
        )
        .round(4)
        .to_string()
    )
