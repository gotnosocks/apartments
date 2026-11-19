"""Does a unit rented at a low ask go longer before its next ad? Model-free, on the ads table.

For each ad with an earlier ad of the unit: the change in log latest ask from that earlier
ad, less the median change of ads opened in the same quarter with the same gap in years
(rounded). Then, by year the ad opened, whether the unit has a later ad, by fifths of that
relative change.
"""

import numpy as np
import pandas as pd

ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
a = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "unit_id",
        "first_day",
        "off_day",
        "latest_ask",
        "status",
        "in_rows",
    ],
)
a = a.dropna(subset=["unit_id", "first_day", "latest_ask"]).drop_duplicates(
    "listing_id"
)
a = a[a.latest_ask > 0].sort_values(["unit_id", "first_day"])
a["day"] = pd.to_datetime(a.first_day, utc=True)
g = a.groupby("unit_id")
a["prev_ask"] = g.latest_ask.shift(1)
a["prev_day"] = g.day.shift(1)
a["next_day"] = g.day.shift(-1)
a = a.dropna(subset=["prev_ask"])
a["chg"] = np.log(a.latest_ask / a.prev_ask)
a["gap"] = ((a.day - a.prev_day).dt.days / 365.25).round().clip(0, 6)
a = a[(a.day - a.prev_day).dt.days >= 150]
a["q"] = a.day.dt.year * 10 + a.day.dt.quarter
a["rel"] = a.chg - a.groupby(["q", "gap"]).chg.transform("median")
a = a[a.rel.abs() < 0.5]
a["year"] = a.day.dt.year
end = a.day.max()
a["wait"] = (a.next_day.fillna(end) - a.day).dt.days / 365.25
a["again2"] = a.next_day.notna() & ((a.next_day - a.day).dt.days <= 730)
a["again"] = a.next_day.notna()
print("ads", len(a), "last day", end.date())
for y in range(2017, 2025):
    s = a[a.year == y].copy()
    s["fifth"] = pd.qcut(s.rel, 5, labels=False)
    t = s.groupby("fifth").agg(
        n=("rel", "size"),
        rel=("rel", "median"),
        again2=("again2", "mean"),
        again=("again", "mean"),
        wait=("wait", "median"),
    )
    print(y)
    print(t.round(3).to_string())
