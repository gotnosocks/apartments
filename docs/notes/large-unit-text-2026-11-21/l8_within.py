"""Finish wording, within building and size class, on held-out ads by half. Two patterns:
`spec` (named finishes and appliances, lobby uses dropped) and `lux` (spec or the word luxury)."""

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
SPEC = re.compile(
    r"\bmarble\b|\bchef'?s kitchen\b|\bsub[- ]?zero\b|\bmiele\b|\bwine (?:fridge|cooler|refrigerator)\b|\bviking\b|\bwolf (?:range|stove)\b|\bbosch\b"
)
LOBBY = re.compile(r"marble (?:lobby|lobbies|hallways?|halls?|entry|entrance)")
LUX = re.compile(r"\bluxury\b")
s = t.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
t["spec"] = [bool(SPEC.search(LOBBY.sub("", v))) for v in s]
t["lux"] = t.spec | np.array([bool(LUX.search(v)) for v in s])
t["has_text"] = s.str.len() > 40
x = h.merge(a, on="listing_id").merge(t.drop(columns="description"), on="listing_id")
x = x[x.has_text].copy()
x["size"] = np.where(x.bedrooms >= 3, "3+", np.where(x.bedrooms >= 1, "1-2", "0"))
x["high"] = ~x.cover90 & ~x.low
c = duckdb.connect()
for m in ["spec", "lux"]:
    k = x.groupby(["building", "size"])[m].transform("mean")
    w = x[(k > 0) & (k < 1)].copy()
    w["dg"] = w.gap - w.groupby(["building", "size"]).gap.transform("mean")
    w["dh"] = w.high.astype(float) - w.groupby(["building", "size"]).high.transform(
        "mean"
    )
    w["dl"] = w.low.astype(float) - w.groupby(["building", "size"]).low.transform(
        "mean"
    )
    w["fin"] = w[m]
    print(m, "within building and size")
    print(
        c.sql("""select size, half, fin, count(*) n, count(distinct building) blds, round(avg(dg),4) dgap,
     round(stddev(dg)/sqrt(count(distinct building)),4) se_bld, round(avg(dh),4) dhigh, round(avg(dl),4) dlow
     from w group by all order by all""")
        .df()
        .to_string()
    )
x[["listing_id", "spec", "lux"]].to_parquet("l8_marks.parquet")
