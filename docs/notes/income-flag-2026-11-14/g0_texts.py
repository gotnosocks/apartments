"""S15b, step 0: the descriptions of the listings `income_restricted_v2` marks, for writing
the negation guard and the tier patterns.

The script takes the listings the flag marks in the `-textflags` copy of L1's dataset and
copies their descriptions out of the text-flag screen's `texts.parquet`, a row group at a
time, as `cautions.plain` leaves them. They go to `OUT/v2_texts.parquet`.

    systemd-run --user --scope -q -p MemoryMax=3G python g0_texts.py
"""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import cautions

COPY = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags"
)
TEXTS = Path("/data1/apartments/tmp/text-flags-2026-11-13/texts.parquet")
OUT = Path("/data1/apartments/tmp/income-flag-2026-11-14")

d = pd.read_parquet(
    COPY / "rows.parquet", columns=["listing_id", "income_restricted_v2"]
)
ids = set(d.listing_id[d.income_restricted_v2.astype(bool)].astype(str))
keep = []
file = pq.ParquetFile(TEXTS)
for g in range(file.num_row_groups):
    t = file.read_row_group(g).to_pandas()
    t["listing_id"] = t.listing_id.astype(str)
    t = t[t.listing_id.isin(ids)]
    keep.append(t.assign(text=[cautions.plain(x or "") for x in t.text]))
out = pd.concat(keep, ignore_index=True)
out.to_parquet(OUT / "v2_texts.parquet")
print(len(ids), "listings marked,", len(out), "texts kept")
