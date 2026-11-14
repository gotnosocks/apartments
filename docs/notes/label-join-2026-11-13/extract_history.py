"""Each (listing_id, listed_id) pair: an ad's record lists the ad listed_id in its unit history.
Read from the records file of L1's pipeline build, as ads.history_events parses propertyHistory."""

import time

import duckdb

REC = "/data1/apartments/pipeline/datasets/records-086e22e48969b098.parquet"
OUT = "/data1/apartments/tmp/sprint-20261113/label-join/history_links.parquet"
c = duckdb.connect()
c.execute(
    "set memory_limit='2000MB'; set threads=3; set preserve_insertion_order=false;"
    "set temp_directory='/data1/apartments/tmp/sprint-20261113/label-join/duck'"
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
) TO '{OUT}' (FORMAT parquet)
""")
print("seconds", time.time() - t)
print(c.execute(f"select count(*), count(distinct listing_id) from '{OUT}'").fetchall())
