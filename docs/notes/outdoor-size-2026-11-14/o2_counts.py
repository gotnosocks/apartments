"""Outdoor size, step 2: the extractor over the latest description of every row of L1's
dataset, before I build the dataset copy.

Text flags step 1 (`text-flags-2026-11-13/t1_texts.py`) wrote each row's latest description to
`texts.parquet`, in the order of L1's rows. I run `b0outdoorsize.areas` on each text with an
area in it, keep the area and code `combine` gives, and count the areas each check drops. I
then count the rows by code and by size, and cross them with S7's parse (`out_sqft`, the
source of S16's `outdoor_large`) and with the private-outdoor codes L1 reads (`po_coded`, as
`b5_patterns.py` builds it). For reading, I write 6 random rows per code and 6 random dropped
areas per check, each with the text around the area.

    python o2_counts.py   # inside systemd-run --user --scope -p MemoryMax=3G
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier.b0data import MIN_DESCRIPTION  # noqa: E402
from rentfrontier.b0outdoorsize import (  # noqa: E402
    AREA,
    DROPS,
    areas,
    combine,
    plain,
)

TEXTS = Path("/data1/apartments/tmp/text-flags-2026-11-13/texts.parquet")
ROWS = Path("/data1/apartments/tmp/text-flags-2026-11-13/rows.parquet")
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
S7 = "/data1/apartments/tmp/sprint-20261113/s7_text.parquet"
OUT = Path("/data1/apartments/tmp/outdoor-size-2026-11-14/")
SEED = 20261114

f = pq.ParquetFile(TEXTS)
rows, drops, snips = [], [], []
for g in range(f.num_row_groups):
    t = f.read_row_group(g).to_pandas()
    for lid, text in zip(t.listing_id, t.text):
        if not isinstance(text, str) or len(text.lower()) <= MIN_DESCRIPTION:
            rows.append((lid, math.nan, "", 0))
            continue
        low = plain(text)
        if not AREA.search(low):
            rows.append((lid, math.nan, "", 0))
            continue
        found = areas(low)
        value, src = combine(found)
        rows.append((lid, value, src, sum(a["drop"] == "implausible" for a in found)))
        for a in found:
            if a["drop"] is not None:
                drops.append((lid, a["drop"], a["value"], a["kind"]))
        if found:
            snips.append((lid, low))
x = pd.DataFrame(rows, columns=["listing_id", "outdoor_sqft", "src", "n_implausible"])
r = pd.read_parquet(ROWS, columns=["listing_id", "building", "held"])
assert (r.listing_id.to_numpy() == x.listing_id.to_numpy()).all()
x["building"], x["held"] = r.building.to_numpy(), r.held.to_numpy()
po = [c for c in pq.read_schema(CODES).names if c.startswith("private_outdoor:")]
codes = pd.read_parquet(
    CODES, columns=["listing_id", "feat:PRIVATE_OUTDOOR_SPACE", *po]
)
codes["po_coded"] = codes[["feat:PRIVATE_OUTDOOR_SPACE", *po]].fillna(0).max(axis=1) > 0
codes["listing_id"] = codes.listing_id.astype(str)
x = x.merge(codes[["listing_id", "po_coded"]], on="listing_id", how="left")
s7 = pd.read_parquet(S7, columns=["listing_id", "out_sqft"])
s7["listing_id"] = s7.listing_id.astype(str)
x = x.merge(s7, on="listing_id", how="left")
assert len(x) == len(r)
x["po_coded"] = x.po_coded.fillna(False).astype(bool)
x.to_parquet(OUT / "o2_areas.parquet")
dr = pd.DataFrame(drops, columns=["listing_id", "drop", "value", "kind"])
dr.to_parquet(OUT / "o2_drops.parquet")

has = x.outdoor_sqft.notna()
large = x.out_sqft >= 300
res = {
    "rows": len(x),
    "rows_with_area": int(has.sum()),
    "rows_by_code": {k: int(v) for k, v in x.src.value_counts().items() if k},
    "rows_with_an_area_dropped_as_implausible": int((x.n_implausible > 0).sum()),
    "areas_dropped_by_check": {k: int((dr["drop"] == k).sum()) for k in DROPS},
    "rows_with_area_po_coded": int((has & x.po_coded).sum()),
    "rows_with_area_held": int((has & x.held).sum()),
    "area_quantiles": {
        str(q): float(x.outdoor_sqft[has].quantile(q))
        for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)
    },
    "area_bins": {
        str(k): int(v)
        for k, v in pd.cut(
            x.outdoor_sqft[has],
            [20, 100, 200, 300, 500, 1000, 5000],
            include_lowest=True,
        )
        .value_counts()
        .sort_index()
        .items()
    },
    "s7_out_sqft": int(x.out_sqft.notna().sum()),
    "s16_outdoor_large": int(large.sum()),
    "s16_outdoor_large_with_area": int((large & has).sum()),
    "s16_outdoor_large_with_area_300": int((large & (x.outdoor_sqft >= 300)).sum()),
    "area_300_not_s16_large": int((~large & (x.outdoor_sqft >= 300)).sum()),
    "area_300": int((x.outdoor_sqft >= 300).sum()),
    "area_300_po_coded": int(((x.outdoor_sqft >= 300) & x.po_coded).sum()),
}
print(json.dumps(res, indent=1), flush=True)
(OUT / "o2_counts.json").write_text(json.dumps(res, indent=1))

# Rows and dropped areas to read, with the text around each area.
rng = np.random.default_rng(SEED)
text = dict(snips)
out = []
for code in [c for c in x.src.unique() if c]:
    ids = x.listing_id[x.src == code].to_numpy()
    for lid in rng.choice(ids, min(6, len(ids)), replace=False):
        out.append({"what": code, "listing_id": lid, "text": text[lid][:2500]})
for k in DROPS:
    ids = dr.listing_id[dr["drop"] == k].unique()
    for lid in rng.choice(ids, min(6, len(ids)), replace=False):
        out.append({"what": "drop:" + k, "listing_id": lid, "text": text[lid][:2500]})
with open(OUT / "o2_samples.jsonl", "w") as fh:
    for o in out:
        fh.write(json.dumps(o) + "\n")
