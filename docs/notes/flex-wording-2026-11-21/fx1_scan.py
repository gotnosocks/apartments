"""Flex-bedroom wording on the latest split's held-out ads, by kind, against l2bt's errors.

l2bt already carries `ad:bed_text_smaller` (bed_flex_at or bed_text_fewer from b0bedtext),
so a kind with an excess of low asks here is one the term does not price in full. The new
kinds are wording the reader misses: an ordinal flex room ("flexible 5th bedroom") and a
wall not yet built ("wall is not yet installed", "wall installation"). Half A of buildings
chooses; half B checks. Marks read the text and the coded bedrooms only.
"""

import re

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import b0bedtext as bt

D = "/data1/apartments/tmp/any-unit/"
h = pq.read_table(D + "heldout.parquet").to_pandas()
ids = sorted(set(h.listing_id))
a = pq.read_table(
    D + "ads.parquet",
    columns=["listing_id", "bedrooms"],
    filters=[("listing_id", "in", ids)],
).to_pandas()
t = pq.read_table(
    D + "texts.parquet",
    columns=["listing_id", "description"],
    filters=[("listing_id", "in", ids)],
).to_pandas()
t = t.merge(a.drop_duplicates("listing_id"), on="listing_id", how="left")

ORD = r"(?:2nd|second|3rd|third|4th|fourth|5th|fifth|6th|sixth)"
NEW = {
    "ordinal_flex": re.compile(
        rf"\bflex(?:ible)? {ORD} (?:bed|br\b|room)|\b{ORD} (?:bed ?room|br|room) (?:is |remains |"
        r"can be |could be )?(?:a )?flex"
    ),
    "wall_to_build": re.compile(
        r"\bwall (?:is |has )?not (?:yet )?(?:been )?(?:installed|built|up)\b|\bwall installation\b"
        r"|\b(?:install|add|put up|build) an? (?:pressurized |temporary |partition )?wall\b"
    ),
}
STUDIO = re.compile(r"\balcove studio\b|\bstudio (?:alcove|convertible)\b")

rows = []
for lid, text, beds in zip(t.listing_id, t.description, t.bedrooms):
    if not isinstance(text, str) or len(text) < 40:
        continue
    own, flex, found = bt.read(text)
    c = bt.code(own, flex, found, beds if beds == beds else 0.0)
    low = bt.plain(text)
    r = {
        "listing_id": lid,
        "beds": beds,
        "flag": bool(c["bed_flex_at"] or c["bed_text_fewer"]),
        "flex_at": bool(c["bed_flex_at"]),
        "fewer": bool(c["bed_text_fewer"]),
        "studio_word": bool(STUDIO.search(low)),
    }
    for k, rx in NEW.items():
        r[k] = bool(rx.search(low))
    rows.append(r)
m = pd.DataFrame(rows)
m.to_parquet("fx_marks.parquet")
x = h.merge(m, on="listing_id")
x["studio_on_bed"] = x.studio_word & (x.beds >= 1)
x["new_unflagged"] = (x.ordinal_flex | x.wall_to_build) & ~x.flag
c = duckdb.connect()
K = {
    "flag": "flag",
    "flex_at": "flex_at",
    "fewer": "fewer",
    "flag_studio_on_bed": "flag and studio_on_bed",
    "flag_other": "flag and not studio_on_bed",
    "ordinal_flex": "ordinal_flex",
    "wall_to_build": "wall_to_build",
    "new_unflagged": "new_unflagged",
    "none": "not flag and not ordinal_flex and not wall_to_build",
}
for k, cond in K.items():
    print(k)
    print(
        c.sql(f"""select half, count(*) n, round(avg(gap), 3) gap,
        round(stddev(gap) / sqrt(count(*)), 3) se, round(avg(low::int), 3) low,
        round(avg((not cover90 and not low)::int), 3) high, round(avg(cover90::int), 3) cover90
        from x where {cond} group by rollup(half) order by half""")
    )
