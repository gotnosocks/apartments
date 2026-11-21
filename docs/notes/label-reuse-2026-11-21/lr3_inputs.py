"""Step 3a: label_units' inputs for the live build, rebuilt from its parquet files as
`label-join-2026-11-13/extract_history.py` and `inputs.py` did for L1's build.

1. The history links: each (listing_id, listed_id) where an ad's record lists another ad in its
   StreetEasy property history, as ads.history_events parses it.
2. The ledger rows: each row of the rows file, and each ad label_months dropped.
3. The history pairs of page units and the unit pages, with every page of each page unit.

Only IDs, pages and bedroom counts are written.
"""

import time

import duckdb

D = "/data1/apartments/pipeline/datasets"
S = "/data1/apartments/tmp/label-reuse"
REC = f"{D}/records-941f4a6588cbd8cc.parquet"
ADS = f"{D}/ads-417bbdf5ed03f5d3.parquet"
ROWS = f"{D}/rows-4f487ef77bb6ca61.parquet"
PAGE = r"^(?:[A-Za-z][A-Za-z0-9+.-]*:)?(?://[^/?#]*)?/building/([^/?#]+)/([^/?#]+)(?:[?#].*)?$"
c = duckdb.connect()
c.execute(
    "set memory_limit='2000MB'; set threads=3; set preserve_insertion_order=false;"
    f"set temp_directory='{S}/duck'"
)
t = time.time()
c.execute(f"""
COPY (
  SELECT DISTINCT listing_id::VARCHAR AS listing_id, coalesce(e.listingId, e.id) AS listed_id
  FROM (
    SELECT listing_id, unnest(from_json(raw_listing_json -> '$.propertyHistory',
      '[{{"id": "VARCHAR", "listingId": "VARCHAR", "rentalEventsOfInterest": [{{"date": "VARCHAR"}}]}}]')) AS e
    FROM read_parquet('{REC}')
  )
  WHERE len(e.rentalEventsOfInterest) > 0
) TO '{S}/history_links.parquet' (FORMAT parquet)
""")
print(
    "history links",
    c.execute(
        f"select count(*), count(distinct listing_id) from '{S}/history_links.parquet'"
    ).fetchall(),
    round(time.time() - t),
)
c.execute(f"""
CREATE TABLE placed AS
SELECT listing_id::VARCHAR AS listing_id, unit_id,
    regexp_replace(unit_id, '~review-.*$', '') AS page_unit, building, page, bedrooms,
    label_fate, in_rows
FROM read_parquet('{ADS}')
""")
c.execute(f"""
CREATE TABLE ledger AS
SELECT r.listing_id::VARCHAR AS listing_id, r.unit_id, p.page_unit, r.building, r.page,
    r.bedrooms, r.price_at, r.period, r.label_unit, r.split_unit, r.square_feet,
    false AS dropped
FROM read_parquet('{ROWS}') r JOIN placed p ON p.listing_id = r.listing_id::VARCHAR
""")
c.execute("""
INSERT INTO ledger
SELECT listing_id, unit_id, page_unit, building, page, bedrooms, NULL, NULL, NULL, NULL, NULL,
    true
FROM placed WHERE label_fate IS NOT NULL
""")
print(
    "ledger rows, dropped",
    c.execute("select count(*), count(*) filter (dropped) from ledger").fetchall(),
)
c.execute(
    f"COPY (SELECT * FROM ledger ORDER BY listing_id) TO '{S}/ledger.parquet' (FORMAT parquet)"
)
c.execute(f"""
COPY (
    SELECT least(a.page_unit, b.page_unit) AS unit_id,
        greatest(a.page_unit, b.page_unit) AS other_unit_id,
        count(DISTINCT (h.listing_id, h.listed_id)) AS links
    FROM read_parquet('{S}/history_links.parquet') h
    JOIN placed a ON a.listing_id = h.listing_id
    JOIN placed b ON b.listing_id = h.listed_id
    WHERE a.page_unit IS NOT NULL AND b.page_unit IS NOT NULL AND a.page_unit <> b.page_unit
    GROUP BY 1, 2
) TO '{S}/pairs.parquet' (FORMAT parquet)
""")
print(
    "history pairs", c.execute(f"select count(*) from '{S}/pairs.parquet'").fetchall()
)
c.execute(f"""
COPY (
    SELECT unit_id, nullif(regexp_extract(page, '{PAGE}', 1), '') AS building,
        nullif(regexp_extract(page, '{PAGE}', 2), '') AS "label", pages
    FROM (
        SELECT page_unit AS unit_id, min(page) AS page, list(DISTINCT page) AS pages
        FROM placed WHERE page_unit IS NOT NULL GROUP BY page_unit
    )
) TO '{S}/pages.parquet' (FORMAT parquet)
""")
print("unit pages", c.execute(f"select count(*) from '{S}/pages.parquet'").fetchall())
print("seconds", round(time.time() - t))
