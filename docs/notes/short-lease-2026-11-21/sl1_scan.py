"""Short-lease wording over every listing's text, and the latest split's held-out errors by mark.

Texts: one per listing (the last ACTIVE record's description, else the last record's), from
`any-unit/texts.parquet`. Held-out: the l2bt run's 189,629 ads (`any-unit/heldout.parquet`).
Each variant is a Python regex on the lowercased text with runs of white space as one
space, as `cautions.plain` leaves it. Half A of buildings chooses; half B checks. No ask is
read by the marks.
"""

import re

import duckdb
import pandas as pd
import pyarrow.parquet as pq

T = "/data1/apartments/tmp/any-unit/texts.parquet"
H = "/data1/apartments/tmp/any-unit/heldout.parquet"
N = r"(?:[1-9]|1[01]|one|two|three|four|five|six|seven|eight|nine|ten|eleven)"
V = {
    "n_month_lease": rf"(?<![\d.-])\b{N}[- ]?(?:month|mo)s?[- ](?:lease|term|rental|stay|sublet)",
    "lease_of_n": rf"(?:lease|term)s? (?:of |for )?(?:only )?{N} months?\b",
    "short_term": r"(?<!no )(?<!not )short[- ]term (?:lease|rental|stay|sublet|furnished)",
    "month_to_month": r"month[- ]to[- ]month",
}
RX = {k: re.compile(p) for k, p in V.items()}

parts = []
cols = ["listing_id", "building", "half", "has_text", "description"]
for batch in pq.ParquetFile(T).iter_batches(columns=cols, batch_size=50_000):
    b = batch.to_pandas()
    d = b.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
    for k, r in RX.items():
        b[k] = [bool(r.search(x)) for x in d]
    parts.append(b.drop(columns="description"))
m = pd.concat(parts, ignore_index=True)
m.to_parquet("marks.parquet")

c = duckdb.connect()
print(
    c.sql(
        "select count(*) n, sum(has_text::int) with_text, "
        + ", ".join(f"sum({k}::int) {k}" for k in V)
        + " from m"
    )
)
c.sql(
    "create table h as select h.*, "
    + ", ".join(f"m.{k}" for k in V)
    + f" from '{H}' h join m using (listing_id)"
)
for k in [*V, "none"]:
    cond = " and ".join(f"not {j}" for j in V) if k == "none" else k
    print(k)
    print(
        c.sql(f"""select half, count(*) n, round(avg(gap), 3) gap,
        round(stddev(gap) / sqrt(count(*)), 3) se,
        round(avg(low::int), 3) low, round(avg((not cover90 and not low)::int), 3) high,
        round(avg(cover90::int), 3) cover90
        from h where {cond} group by rollup(half) order by half""")
    )
