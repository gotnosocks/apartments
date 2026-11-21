"""Where the floor-1 excess of low asks lies: the model's own floor snapshot, by elevator and by
the garden and lower flags, on the latest split's l2bt held-out errors by half.

The snapshot (`unit-floor/20261021-d84914c0`) is what the served model's floor curve reads.
Floor 1 is the curve's zero; a garden label on floor 1 adds `unit:garden`, a basement or
lower-level label `unit:lower`. Each mark reads coded fields, never the ask.
"""

import duckdb
import pandas as pd
import pyarrow.parquet as pq

D = "/data1/apartments/tmp/any-unit/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
SNAP = "/data1/apartments/external/unit-floor/20261021-d84914c0/floor.parquet"
h = pq.read_table(D + "heldout.parquet").to_pandas()
ids = sorted(set(h.listing_id))
a = (
    pq.read_table(
        ADS, columns=["listing_id", "elevator"], filters=[("listing_id", "in", ids)]
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
f = pq.read_table(SNAP, filters=[("listing_id", "in", ids)]).to_pandas()
x = h.merge(a, on="listing_id", how="left").merge(f, on="listing_id", how="left")
x["fl"] = pd.cut(
    x.floor,
    [-99, 0.5, 1.5, 2.5, 3.5, 5.5, 99],
    labels=["0-", "1", "2", "3", "4-5", "6+"],
).astype(str)
x["flag"] = x.garden.fillna(0).astype(int).astype(str) + x.lower.fillna(0).astype(
    int
).astype(str)
c = duckdb.connect()
S = """count(*) n, round(avg(gap), 3) gap, round(stddev(gap) / sqrt(count(*)), 3) se,
    round(avg(low::int), 3) low, round(avg((not cover90 and not low)::int), 3) high"""


def show(title, by, where="true"):
    print(title)
    print(
        c.sql(f"""select {by}, half, {S} from x where {where}
        group by {by}, half having count(*) >= 30 order by {by}, half""")
        .df()
        .to_string()
    )


show("snapshot floor by elevator", "elevator, fl")
show("floor 1 by garden/lower flag (garden, lower)", "elevator, flag", "fl = '1'")
