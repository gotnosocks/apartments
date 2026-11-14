"""Rebuild label_units' inputs for L1's build from its parquet snapshots: the ledger rows (the
rows file plus the ads label_months dropped), the history pairs and the unit pages."""

import time

import duckdb

D = "/data1/apartments/pipeline/datasets"
S = "/data1/apartments/tmp/sprint-20261113/label-join"
ADS = f"{D}/ads-3775f6d9b3e028ca.parquet"
ROWS = f"{D}/rows-b3ddebf19af1dc1e.parquet"
PAGE = r"^(?:[A-Za-z][A-Za-z0-9+.-]*:)?(?://[^/?#]*)?/building/([^/?#]+)/([^/?#]+)(?:[?#].*)?$"
c = duckdb.connect()
c.execute(
    "set memory_limit='2000MB'; set threads=3; set preserve_insertion_order=false;"
    f"set temp_directory='{S}/duck'"
)
t = time.time()
c.execute(f"""
CREATE TABLE placed AS
SELECT listing_id::VARCHAR AS listing_id, unit_id,
    regexp_replace(unit_id, '~review-.*$', '') AS page_unit, building, page, bedrooms,
    label_fate, in_rows
FROM read_parquet('{ADS}')
""")
print(
    c.execute(
        "select count(*), count(page_unit), count(label_fate), count(*) filter (in_rows) from placed"
    ).fetchall()
)
print(c.execute("select label_fate, count(*) from placed group by 1").fetchall())
# The ledger rows: each row of the rows file, and each ad label_months dropped.
c.execute(f"""
CREATE TABLE ledger AS
SELECT r.listing_id::VARCHAR AS listing_id, r.unit_id, p.page_unit, r.building, r.page,
    r.bedrooms, r.price_at, r.period, r.label_unit, r.split_unit, false AS dropped
FROM read_parquet('{ROWS}') r JOIN placed p ON p.listing_id = r.listing_id::VARCHAR
""")
print("rows", c.execute("select count(*) from ledger").fetchall())
c.execute(f"""
INSERT INTO ledger
SELECT listing_id, unit_id, page_unit, building, page, bedrooms, NULL, NULL, NULL, NULL, true
FROM placed WHERE label_fate IS NOT NULL
""")
print(
    "ledger",
    c.execute("select count(*), count(*) filter (dropped) from ledger").fetchall(),
)
c.execute(
    f"COPY (SELECT * FROM ledger ORDER BY listing_id) TO '{S}/ledger.parquet' (FORMAT parquet)"
)
c.execute(f"""
COPY (
    SELECT least(a.page_unit, b.page_unit) AS unit_id, greatest(a.page_unit, b.page_unit) AS other_unit_id,
        count(DISTINCT (h.listing_id, h.listed_id)) AS links,
        first(h.listing_id ORDER BY h.listing_id, h.listed_id) AS listing_id,
        first(h.listed_id ORDER BY h.listing_id, h.listed_id) AS listed_id
    FROM read_parquet('{S}/history_links.parquet') h
    JOIN placed a ON a.listing_id = h.listing_id
    JOIN placed b ON b.listing_id = h.listed_id
    WHERE a.page_unit IS NOT NULL AND b.page_unit IS NOT NULL AND a.page_unit <> b.page_unit
    GROUP BY 1, 2
) TO '{S}/pairs.parquet' (FORMAT parquet)
""")
print("pairs", c.execute(f"select count(*) from '{S}/pairs.parquet'").fetchall())
c.execute(f"""
COPY (
    SELECT unit_id, nullif(regexp_extract(page, '{PAGE}', 1), '') AS building,
        nullif(regexp_extract(page, '{PAGE}', 2), '') AS label, pages
    FROM (
        SELECT page_unit AS unit_id, min(page) AS page, list(DISTINCT page) AS pages FROM placed
        WHERE page_unit IS NOT NULL GROUP BY page_unit
    )
) TO '{S}/pages.parquet' (FORMAT parquet)
""")
print(
    "pages",
    c.execute(f"select count(*), count(label) from '{S}/pages.parquet'").fetchall(),
)
print("seconds", time.time() - t)
