"""Where the sample's filled sizes come from: the unit's other ads with a stated size.

Reads bedrooms and stated square feet of every ad of the sampled units (no rent), and
asks whether the size the fill used was stated on an ad with more bedrooms than this one.
"""

import pandas as pd
import pyarrow.parquet as pq

T = "/data1/apartments/tmp/big-small/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
s = pd.read_parquet(T + "sample.parquet").rename(columns={"kind": "dir"})
s = s[s.size_source == "unit"]
units = sorted(set(s.unit_id.astype(str)))
a = pq.read_table(
    ADS,
    columns=["listing_id", "unit_id", "bedrooms", "square_feet"],
    filters=[("unit_id", "in", units)],
).to_pandas()
a = a[a.square_feet.notna() & (a.square_feet > 0)]
rows = []
for r in s.itertuples():
    o = a[(a.unit_id == r.unit_id) & (a.listing_id.astype(str) != str(r.listing_id))]
    same = o[(o.square_feet - r.sqft).abs() < 1]
    rows.append(
        dict(
            dir=r.dir,
            stated_ads=len(o),
            size_beds=same.bedrooms.max() if len(same) else None,
            more_beds=bool(len(same) and same.bedrooms.max() > r.bd),
            sizes_differ=o.square_feet.nunique() > 1,
        )
    )
f = pd.DataFrame(rows)
print(len(f), "unit-filled ads in the sample")
print(f.groupby("dir")[["more_beds", "sizes_differ"]].agg(["sum", "count"]).to_string())
print(pd.crosstab(f.size_beds, f.dir).to_string())
