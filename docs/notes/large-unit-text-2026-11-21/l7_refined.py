"""Named finishes (marble lobby wording dropped) on every held-out ad: gap and tails by size and half.

Its second table demeans the gap over all sizes in a building, so it mixes size classes;
`l8_within.py` does the within-building test by building and size class instead.
"""

import re
import duckdb, numpy as np, pandas as pd, pyarrow.parquet as pq

D = "/data1/apartments/tmp/any-unit/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
h = pq.read_table(D + "heldout.parquet").to_pandas()
ids = sorted(set(h.listing_id))
a = (
    pq.read_table(
        ADS, columns=["listing_id", "bedrooms"], filters=[("listing_id", "in", ids)]
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
t = (
    pq.read_table(
        D + "texts.parquet",
        columns=["listing_id", "description"],
        filters=[("listing_id", "in", ids)],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
R = re.compile(
    r"\bmarble\b(?! (?:lobby|lobbies|hallways?|halls?|entry|entrance|foyer of the building))|\bchef'?s kitchen\b|\bsub[- ]?zero\b|\bmiele\b|\bwine (?:fridge|cooler|refrigerator)\b|\bviking\b|\bwolf (?:range|stove)\b|\bbosch\b"
)
LOBBY = re.compile(r"marble (?:lobby|lobbies|hallways?|halls?|entry|entrance)")
s = t.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
t["fin"] = [bool(R.search(LOBBY.sub("", v))) for v in s]
t["has_text"] = s.str.len() > 40
x = h.merge(a, on="listing_id").merge(
    t[["listing_id", "fin", "has_text"]], on="listing_id"
)
x = x[x.has_text]
x["size"] = np.where(x.bedrooms >= 3, "3+", np.where(x.bedrooms >= 1, "1-2", "0"))
x["high"] = ~x.cover90 & ~x.low
# within building: demean gap by building among buildings with both marked and unmarked held-out ads
g = x.groupby("building").fin.transform("mean")
w = x[(g > 0) & (g < 1)].copy()
w["dg"] = w.gap - w.groupby("building").gap.transform("mean")
S = """count(*) n, round(avg(gap),4) gap, round(stddev(gap)/sqrt(count(*)),4) se,
 round(avg(low::int),3) low, round(avg(high::int),3) high"""
c = duckdb.connect()
print(
    c.sql(f"select size, half, fin, {S} from x group by all order by all")
    .df()
    .to_string()
)
print("within building")
print(
    c.sql("""select size, half, fin, count(*) n, round(avg(dg),4) dgap, round(stddev(dg)/sqrt(count(*)),4) se,
 round(avg(high::int),3) high from w group by all order by all""")
    .df()
    .to_string()
)
