"""Snippets around the n_month_lease match for half-A held-out ads (no asks printed)."""

import re
import duckdb
import sys

sys.path.insert(0, ".")
N = r"(?:[1-9]|1[01]|one|two|three|four|five|six|seven|eight|nine|ten|eleven)"
R = re.compile(
    rf"(?<![\d.-])\b{N}[- ]?(?:month|mo)s?[- ](?:lease|term|rental|stay|sublet)"
)
c = duckdb.connect()
import pyarrow.parquet as pq

c.sql("set threads=2")
ids = c.sql("""select listing_id, h.low from 'marks.parquet' m
  join '/data1/apartments/tmp/any-unit/heldout.parquet' h using (listing_id)
  where m.n_month_lease and h.half = 'A' order by hash(listing_id) limit 40""").df()
t = pq.read_table(
    "/data1/apartments/tmp/any-unit/texts.parquet",
    columns=["listing_id", "description"],
    filters=[("listing_id", "in", list(ids.listing_id))],
).to_pandas()
d = ids.merge(t, on="listing_id")
for r in d.itertuples():
    x = re.sub(r"\s+", " ", r.description.lower())
    mm = R.search(x)
    s = x[max(0, mm.start() - 70) : mm.end() + 50]
    s = re.sub(r"\$\s?[\d,]+", "$N", s)
    print(int(r.low), "|", s)
