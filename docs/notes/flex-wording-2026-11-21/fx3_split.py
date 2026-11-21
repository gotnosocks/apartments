"""Held-out ads with bed_text_fewer, split by the stated size: a studio (0) or a count of 1 or more.

A studio reading can come from amenity wording the reader does not mask ("workout studio");
a count of 1 or more names a bedroom count outright ("1 bed + home office" coded 2).
"""

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import b0bedtext as bt

D = "/data1/apartments/tmp/any-unit/"
m = pd.read_parquet("fx_marks.parquet")
ids = sorted(m.listing_id[m.fewer])
t = pq.read_table(
    D + "texts.parquet",
    columns=["listing_id", "description"],
    filters=[("listing_id", "in", ids)],
).to_pandas()
t = t.merge(m[["listing_id", "beds"]], on="listing_id")
t["stated"] = [
    bt.code(*bt.read(s), b)["bed_text"] for s, b in zip(t.description, t.beds)
]
h = (
    pq.read_table(D + "heldout.parquet")
    .to_pandas()
    .merge(t[["listing_id", "stated"]], on="listing_id")
)
h["kind"] = h.stated.map(lambda s: "studio" if s == 0 else "count")
print(
    duckdb.sql("""select kind, half, count(*) n, round(avg(gap), 3) gap,
    round(stddev(gap) / sqrt(count(*)), 3) se, round(avg(low::int), 3) low,
    round(avg((not cover90 and not low)::int), 3) high, round(avg(cover90::int), 3) cover90
    from h group by kind, rollup(half) order by kind, half""")
)
