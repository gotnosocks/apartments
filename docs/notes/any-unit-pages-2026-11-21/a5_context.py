"""Words around each candidate phrase on half A, eight random ads a phrase, no ask loaded."""

import re
import sys

import duckdb

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from a4_text import PHRASES  # noqa: E402

OUT = "/data1/apartments/tmp/any-unit"
c = duckdb.connect()
for k, v in PHRASES.items():
    rows = c.sql(
        f"select description from '{OUT}/texts.parquet' where half = 'A' and {k} "
        f"order by hash(listing_id || 'ctx') limit 8"
    ).fetchall()
    print(f"\n== {k}")
    rx = re.compile(v, re.I)
    for (d,) in rows:
        m = rx.search(d)
        s = d[max(0, m.start() - 90) : m.end() + 60].replace("\n", " ")
        print(" -", re.sub(r"\$\s?[\d,.]+k?", "$[masked]", s))
