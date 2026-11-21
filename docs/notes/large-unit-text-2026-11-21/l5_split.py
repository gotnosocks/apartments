"""Finish wording on 3+ bedroom held-out ads: by baths, by word, by bedrooms, by year, by half."""

import re
import duckdb, numpy as np, pandas as pd, pyarrow.parquet as pq

D = "/data1/apartments/tmp/any-unit/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
h = pq.read_table(D + "heldout.parquet").to_pandas()
ids = sorted(set(h.listing_id))
a = (
    pq.read_table(
        ADS,
        columns=["listing_id", "bedrooms", "full_baths", "square_feet"],
        filters=[("listing_id", "in", ids)],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
x = h.merge(a, on="listing_id")
x = x[x.bedrooms >= 3]
t = (
    pq.read_table(
        D + "texts.parquet",
        columns=["listing_id", "description"],
        filters=[("listing_id", "in", sorted(set(x.listing_id)))],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
s = t.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
W = {
    "luxury": r"\bluxury\b",
    "marble": r"\bmarble\b",
    "chef": r"\bchef'?s kitchen\b",
    "appliance": r"\bsub[- ]?zero\b|\bmiele\b|\bwine (?:fridge|cooler|refrigerator)\b|\bviking\b|\bwolf (?:range|stove)\b|\bbosch\b",
}
for k, p in W.items():
    r = re.compile(p)
    t[k] = [bool(r.search(v)) for v in s]
t["has_text"] = s.str.len() > 40
x = x.merge(t.drop(columns="description"), on="listing_id")
x = x[x.has_text].copy()
x["fin"] = x.luxury | x.marble | x.chef | x.appliance
x["hi_fin"] = x.marble | x.chef | x.appliance
x["baths"] = np.where(x.full_baths >= 3, "3+", np.where(x.full_baths >= 2, "2", "0-1"))
x["yr"] = pd.to_datetime(x.day).dt.year.clip(upper=2026)
x["era"] = np.where(x.yr < 2020, "-2019", np.where(x.yr < 2023, "2020-22", "2023-"))
x["high"] = ~x.cover90 & ~x.low
S = "count(*) n, round(avg(gap),4) gap, round(stddev(gap)/sqrt(count(*)),4) se, round(avg(high::int),3) high, round(avg(low::int),3) low"
c = duckdb.connect()
for by in ["baths", "luxury, hi_fin", "least(bedrooms,4)", "era"]:
    print(by)
    print(
        c.sql(
            f"select {by}, half, fin, {S} from x group by all having count(*)>=50 order by all"
        )
        .df()
        .to_string()
    )
