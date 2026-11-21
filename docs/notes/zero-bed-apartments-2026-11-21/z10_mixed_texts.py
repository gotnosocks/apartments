"""The 19 kept bedroom-set rows whose blind read judged the unit's other ads mixed: the row's
own ad text with dollar figures masked, for a second read blind to the ask."""

import re

import pandas as pd
import pyarrow.parquet as pq

N = "docs/notes/zero-bed-apartments-2026-11-21/"
r = pd.read_csv(N + "full_reads.csv", dtype={"listing_id": str})
m = r[r.keep.astype(str).eq("True") & r.same_apartment.ne("yes")]
print(len(m), m.same_apartment.value_counts().to_dict())
ids = sorted(m.listing_id)
t = pq.read_table(
    "/data1/apartments/tmp/any-unit/texts.parquet",
    columns=["listing_id", "description"],
    filters=[("listing_id", "in", ids)],
).to_pandas()
x = m.merge(t, on="listing_id", how="left")
with open("/data1/apartments/tmp/mixed19/texts.md", "w") as f:
    for i, row in enumerate(x.itertuples(), 1):
        s = row.description if isinstance(row.description, str) else "(no text)"
        s = re.sub(r"\$\s?[\d,.]+k?", "$X", s)
        s = re.sub(r"\b\d{1,2},\d{3}\b", "N", s)
        f.write(
            f"## M{i:02d} (listing {row.listing_id}, coded 0 bed, text count {row.text_count})\n\n{s}\n\n"
        )
x[["listing_id", "building", "half", "text_count", "same_apartment", "reason"]].to_csv(
    "/data1/apartments/tmp/mixed19/rows.csv", index=False
)
print(x.description.str.len().describe().round())
