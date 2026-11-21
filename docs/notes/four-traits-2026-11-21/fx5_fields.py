"""Four traits from the Deals top read, on the latest split's l2bt held-out errors by half.

- walkup: the coded elevator field is False, by borough (the first entry of `regions`).
- doorman: the coded doorman type, virtual against full-time.
- owner_unit: text naming a condo or co-op, with and without owner wording.
- garden: garden, ground-floor or lower-level wording, against the coded label floor (physical_floor is empty in this build).

Each mark reads coded fields or the text, never the ask. Both halves print at once.
"""

import re

import duckdb
import pandas as pd
import pyarrow.parquet as pq

D = "/data1/apartments/tmp/any-unit/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
h = pq.read_table(D + "heldout.parquet").to_pandas()
ids = sorted(set(h.listing_id))
a = (
    pq.read_table(
        ADS,
        columns=["listing_id", "regions", "elevator", "doorman_type", "label_floor"],
        filters=[("listing_id", "in", ids)],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
print("regions sample", a.regions.dropna().head(3).tolist())
a["borough"] = a.regions.map(
    lambda r: str(r[0]) if r is not None and len(r) else "(none)"
)
t = pq.read_table(
    D + "texts.parquet",
    columns=["listing_id", "description"],
    filters=[("listing_id", "in", ids)],
).to_pandas()
CONDO = re.compile(r"\b(?:condo(?:minium)?|co-?op)\b")
OWNER = re.compile(r"\b(?:owner|owned by|privately owned|my (?:apartment|unit|home))\b")
GARDEN = re.compile(
    r"\bgarden[- ](?:level|floor|apartment|unit|duplex)\b|\bground[- ]floor (?:apartment|unit)\b"
    r"|\blower[- ]level (?:apartment|unit)\b|\bbelow[- ]grade\b|\bbasement (?:apartment|unit)\b"
)
low = t.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
t["condo"] = [bool(CONDO.search(x)) for x in low]
t["owner"] = [bool(OWNER.search(x)) for x in low]
t["garden"] = [bool(GARDEN.search(x)) for x in low]
x = h.merge(a, on="listing_id", how="left").merge(
    t.drop(columns="description"), on="listing_id", how="left"
)
x["floor"] = pd.cut(
    x.label_floor, [-99, 0.5, 1.5, 3.5, 99], labels=["0 or below", "1", "2-3", "4+"]
).astype(str)
c = duckdb.connect()
S = """round(avg(gap), 3) gap, round(stddev(gap) / sqrt(count(*)), 3) se,
    round(avg(low::int), 3) low, round(avg((not cover90 and not low)::int), 3) high"""


def show(title, by):
    print(title)
    print(
        c.sql(f"""select {by}, half, count(*) n, {S} from x
        group by {by}, half having count(*) >= 30 order by {by}, half""")
        .df()
        .to_string()
    )


show("elevator by borough", "borough, elevator")
show("doorman type", "doorman_type")
show("condo text and owner text", "condo, owner")
show("garden text by floor", "garden, floor")
