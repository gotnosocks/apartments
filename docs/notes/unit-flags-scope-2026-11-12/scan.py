"""Scan every captured ad description for duplex or triplex wording and a stated size of
private outdoor space. Writes one row per listing with the flags from any capture."""

import json
import re

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REC = "/data1/apartments/pipeline/datasets/records-0d20eb92b9f08c7d.parquet"
OUT = "/data1/apartments/tmp/sprint-20261112/flags/scan.parquet"
DUP = re.compile(r"\b(duplex|triplex|two[- ]level|two[- ]story|multi[- ]level)\b", re.I)
OUTW = r"(terrace|patio|balcony|garden|roof ?deck|roof|outdoor|deck|yard)"
NUM = r"(\d{1,2},\d{3}|\d{2,4})\s*(?:\+\s*)?(?:sq\.?\s?ft\.?|sf\b|ft2|square[- ]f(?:ee|oo)t)"
SIZE = re.compile(rf"{NUM}[^.,\n]{{0,15}}?\b{OUTW}|\b{OUTW}[^.,\n]{{0,25}}?{NUM}", re.I)

flags = {}
pf = pq.ParquetFile(REC)
for rg in range(pf.num_row_groups):
    for batch in pf.iter_batches(
        batch_size=2000,
        row_groups=[rg],
        columns=["listing_id", "raw_listing_json"],
        use_threads=False,
    ):
        ids = batch.column(0).to_pylist()
        raws = batch.column(1).to_pylist()
        for lid, raw in zip(ids, raws):
            try:
                d = json.loads(raw) if isinstance(raw, str) else raw
                text = (d or {}).get("description") or ""
            except Exception:
                continue
            dup = bool(DUP.search(text))
            sqft = None
            for m in SIZE.finditer(text):
                n = m.group(1) or m.group(4)
                v = int(n.replace(",", ""))
                if 20 <= v <= 5000:
                    sqft = max(sqft or 0, v)
            old = flags.get(lid, (False, None, False))
            flags[lid] = (
                old[0] or dup,
                max(old[1] or 0, sqft or 0) or None,
                old[2] or bool(text),
            )
    pa.default_memory_pool().release_unused()
f = pd.DataFrame(
    [(k, *v) for k, v in flags.items()],
    columns=["listing_id", "duplex", "outdoor_sqft", "has_text"],
)
f["listing_id"] = f["listing_id"].astype(str)
f.to_parquet(OUT)
print(len(f), f.has_text.mean(), f.duplex.mean(), f.outdoor_sqft.notna().mean())
