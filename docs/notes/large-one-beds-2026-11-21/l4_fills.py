"""Where the sample's filled sizes come from: the unit's other ads with a stated size.

Reads bedrooms and stated square feet of every ad of the sampled units (no rent). A fill is
traced when it equals one of those sizes or their median, and then asks whether it came
from an ad with more bedrooms than this one.
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
    if len(same):
        src = same
    elif len(o) and abs(o.square_feet.median() - r.sqft) < 1:
        src = o  # the fill is the median of the unit's other stated sizes
    else:
        src = o.iloc[:0]
    rows.append(
        dict(
            dir=r.dir,
            stated_ads=len(o),
            traced=len(src) > 0,
            more_beds=bool(len(src) and src.bedrooms.max() > r.bd),
            size_beds=src.bedrooms.max() if len(src) else None,
        )
    )
f = pd.DataFrame(rows)
print(len(f), "unit-filled ads in the sample")
print("traced: the fill equals one of the unit's other stated sizes or their median")
print(f.groupby("dir")[["traced", "more_beds"]].sum().assign(n=f.groupby("dir").size()))
print(
    "no other ad of the unit states a size:",
    f[f.stated_ads == 0].groupby("dir").size().to_dict(),
)
print(pd.crosstab(f.size_beds, f.dir).to_string())
