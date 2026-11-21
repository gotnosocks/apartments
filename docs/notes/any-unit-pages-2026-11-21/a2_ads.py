"""The ads frame: every candidate ad of the pipeline dataset with its page, dates and half.

A candidate is an ad the chain accepts before its unit-month check (`fate` set: kept,
superseded in its unit-month, or dropped for a conflicting layout in its unit-month). A page
is a `unit_id`. An ad runs from its first day to its off day (the fetch day while it is
active). `ask_lo` and `ask_hi` bound its first and latest asks; they feed only the overlap
mark's test of whether two ads at once ask different amounts. Buildings are cut in halves
by the hash of `commercial-sweep-2026-11-20/sw3_counts.py`, with that note's seed.
"""

import hashlib

import duckdb

ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
OUT = "/data1/apartments/tmp/any-unit"
SEED = "commercial-sweep-2026-11-20"


def half(b: str) -> str:
    return "AB"[hashlib.sha1((SEED + (b or "")).encode()).digest()[0] & 1]


c = duckdb.connect()
c.create_function("half", half, ["VARCHAR"], "VARCHAR")
c.sql(f"""
copy (
  select listing_id::varchar listing_id, unit_id, building, half(building) half,
         first_day::date first_day,
         coalesce(off_day::date, fetched::date) end_day,
         bedrooms, full_baths, square_feet,
         least(first_ask, latest_ask) ask_lo, greatest(first_ask, latest_ask) ask_hi,
         fate, in_rows, status
  from '{ADS}'
  where fate is not null and unit_id is not null and first_day is not null
) to '{OUT}/ads.parquet' (format parquet)
""")
print(
    c.sql(
        f"select half, count(*) ads, count(distinct unit_id) pages, "
        f"count(distinct building) buildings, sum(in_rows::int) in_rows "
        f"from '{OUT}/ads.parquet' group by 1 order by 1"
    ).df()
)
print(
    c.sql(
        f"select count(*) from '{OUT}/ads.parquet' where end_day < first_day"
    ).fetchall()
)
