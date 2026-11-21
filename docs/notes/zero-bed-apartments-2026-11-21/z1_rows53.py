"""Question 1: the 165 apartment reads coded 0 bed in the ratio read, and the 53 that cite 2 to 5
beds, against the 2026-11-12 classes and decisions.

The 53 are the rows of `commercial-sweep-2026-11-20/reads_ratio_all.csv` with final code
`apartment`, coded 0 bed, whose quotes or reasons name a count of 2 to 5 bedrooms (`CITE`).
For each row I join:
- its coded fields and unit in the live build's ads file (`ads-417bbdf5ed03f5d3`, the build
  the ratio read drew from), and its bedrooms in the older build `ads-14f9e88d75290a0f`;
- the 2026-11-12 class and decision of `outlier-sprint/s2/Z` (`classes.parquet` holds every
  kept ad of that day, `decisions_final.parquet` the 14,537 ads of the three classes);
- the unit's other ads in the live ads file: how many code 2 or more, 1 and 0;
- the live dataset's `bed_text` columns (`rentfrontier.b0bedtext`).
No ask is read.
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

HERE = Path(__file__).resolve().parent
SWEEP = HERE.parent / "commercial-sweep-2026-11-20"
Z = Path("/data1/apartments/tmp/outlier-sprint/s2/Z")
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
OLD = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
LIVE_ROWS = (
    "/data1/apartments/frontier/datasets/"
    "b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext/rows.parquet"
)
N = r"(?:two|three|four|five|2|3|4|5)"
CITE = re.compile(
    rf"\b{N}(?:\s*(?:to|-|or|and)\s*{N})?[\s-]*(?:bed(?:room)?s?|br|bd|bdrm)s?\b", re.I
)

pd.set_option("display.width", 220)
r = pd.read_csv(SWEEP / "reads_ratio_all.csv", dtype=str)
a = r[(r.final == "apartment") & (r.bed.astype(float) == 0)].copy()
txt = (
    a[["quote1", "why1", "quote2", "why2", "hand_why"]]
    .fillna("")
    .agg(" | ".join, axis=1)
)
a["cite"] = txt.str.contains(CITE)
print("apartment reads coded 0 bed", len(a), "citing 2 to 5 beds", int(a.cite.sum()))

c = duckdb.connect()
c.execute("set memory_limit='2GB'")
c.execute("set threads=2")
c.register("a", a[["listing_id", "cite", "read_id", "half"]])
D = c.execute(f"""
  select a.*, d.unit_id, d.page, d.building, d.bedrooms, d.full_baths, d.half_baths,
    d.square_feet, d.first_day, d.fate, d.in_rows, len(d.ledger_entries) n_ledger,
    o.bedrooms old_bed
  from a join '{ADS}' d using (listing_id)
  left join (select listing_id, bedrooms from '{OLD}') o using (listing_id)""").df()
U = c.execute(f"""
  select a.listing_id, count(o.listing_id) n_other,
    sum((o.bedrooms >= 2)::int) n2, sum((o.bedrooms = 1)::int) n1,
    sum((o.bedrooms = 0)::int) n0,
    sum((o.bedrooms >= 2 and abs(date_diff('day', d.first_day, o.first_day)) <= 730)::int) n2_near,
    sum((o.bedrooms < 2 and abs(date_diff('day', d.first_day, o.first_day)) <= 730)::int) nlt2_near
  from a join '{ADS}' d using (listing_id)
  left join '{ADS}' o on o.unit_id = d.unit_id and o.listing_id <> d.listing_id
  group by 1""").df()
B = c.execute(f"""select listing_id, bed_text, bed_text_more from '{LIVE_ROWS}'
  where listing_id in (select listing_id from a)""").df()
D = D.merge(U, on="listing_id", how="left").merge(B, on="listing_id", how="left")
K = pd.read_parquet(
    Z / "classes.parquet",
    columns=[
        "listing_id",
        "cls",
        "lister",
        "rooms",
        "n",
        "names2",
        "studio",
        "decided",
    ],
)
K["listing_id"] = K.listing_id.astype(str)
K = K[K.listing_id.isin(D.listing_id)]
F = pd.read_parquet(
    Z / "decisions_final.parquet",
    columns=["listing_id", "g", "act", "a_fail", "u_fail", "verdict"],
)
F["listing_id"] = F.listing_id.astype(str)
D = D.merge(K, on="listing_id", how="left").merge(F, on="listing_id", how="left")
D["in_1112_kept"] = D.cls.notna()
D["in_1112_classes"] = D.g.notna()
D["blank_default"] = (
    (D.full_baths == 1) & (D.half_baths == 0) & D.square_feet.isna() & (D.rooms == 1)
)
D.to_parquet("/data1/apartments/tmp/zero-bed/rows165.parquet")

for name, g in [("53 citing", D[D.cite]), ("112 others", D[~D.cite])]:
    print(f"\n== {name}: {len(g)} rows, half {g.half.value_counts().to_dict()}")
    print(
        "in rows", int(g.in_rows.sum()), "ledger entries", int((g.n_ledger > 0).sum())
    )
    print("old build bedrooms", g.old_bed.value_counts(dropna=False).to_dict())
    print("2026-11-12 class", g.cls.value_counts(dropna=False).to_dict())
    print("2026-11-12 group", g.g.value_counts(dropna=False).to_dict())
    print("act", g.act.value_counts(dropna=False).to_dict())
    print("page-rule fail (u_fail)", g.u_fail.value_counts(dropna=False).to_dict())
    print("building-rule fail (a_fail)", g.a_fail.value_counts(dropna=False).to_dict())
    print("rooms", g.rooms.value_counts(dropna=False).sort_index().to_dict())
    print("full baths", g.full_baths.value_counts(dropna=False).sort_index().to_dict())
    print("square feet stated", int(g.square_feet.notna().sum()))
    print(
        "blank-form defaults (1 bath, 0 half, no size, 1 room)",
        int(g.blank_default.sum()),
    )
    print(
        "text length under 30",
        int((g.n < 30).sum()),
        "80 or more",
        int((g.n >= 80).sum()),
    )
    print(
        "text names 2-5 bed",
        int(g.names2.fillna(False).sum()),
        "says studio",
        int(g.studio.fillna(False).sum()),
    )
    print(
        "bed_text_more with bed_text >= 2",
        int((g.bed_text_more.fillna(False) & (g.bed_text >= 2)).sum()),
        "bed_text values",
        g.bed_text.value_counts(dropna=False).to_dict(),
    )
    print(
        "unit other ads: any",
        int((g.n_other > 0).sum()),
        "some 2+",
        int((g.n2 > 0).sum()),
        "all 2+",
        int(((g.n2 > 0) & (g.n1 == 0) & (g.n0 == 0)).sum()),
        "2+ within 730 days",
        int((g.n2_near > 0).sum()),
        "2+ near and none below 2 near",
        int(((g.n2_near > 0) & (g.nlt2_near == 0)).sum()),
    )
    print("listers", g.lister.value_counts().head(8).to_dict())
    print("buildings", g.building.nunique(), "units", g.unit_id.nunique())
    print(
        "first year",
        pd.to_datetime(g.first_day).dt.year.value_counts().sort_index().to_dict(),
    )

S = D[D.cite]
print("\nwhy the 2026-11-12 pass left the 53 (group / act / page fail / building fail)")
print(S.groupby(["g", "act", "u_fail", "a_fail"], dropna=False).size().to_string())
