"""Text marks on the latest record of every listing in the live build's records file.

Reads `raw_listing_json` row group by row group, parses each record's description and unit
label, and flags the TODO's words (word-bounded, case-insensitive) and texts of a few
characters. The description is kept only for records that match a mark or are 0 or 1 bed
ads over three times the area median (from `sw1_ads.py`), so the output stays small. The
latest record of each listing wins, as in `building-level-read-2026-11-20/s3.py`.
"""

import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

OUT = Path("/data1/apartments/tmp/commercial-sweep")
REC = "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
TERMS = {
    "retail": r"\bretail\b",
    "storefront": r"\bstore[\s-]?fronts?\b",
    "office": r"\boffices?\b",
    "per_sf": r"\bper\s+(?:sf|sq\.?\s*f(?:t|eet|oot)\.?|sqft|square\s+f(?:oo|ee)t)\b",
    "warehouse": r"\bwarehouses?\b",
}
RX = {k: re.compile(v, re.I) for k, v in TERMS.items()}
SHORT_WORDS = {"draft", "desc", "tbd"}


def short(desc: str) -> bool:
    s = desc.strip()
    return len(s) <= 5 or s.lower().strip(".") in SHORT_WORDS


A = pd.read_parquet(OUT / "ads.parquet", columns=["listing_id", "bed", "ratio"])
ratio_ids = set(A.listing_id[(A.bed.isin([0, 1])) & (A.ratio > 3)].astype(int).tolist())
print("ratio-mark listings", len(ratio_ids), flush=True)
del A
f = pq.ParquetFile(REC)
parts = []
for g in range(f.metadata.num_row_groups):
    t = f.read_row_group(
        g, columns=["listing_id", "collected_at", "listing_type", "raw_listing_json"]
    )
    ids = t.column("listing_id").to_pylist()
    raw = t.column("raw_listing_json").to_pylist()
    rows = []
    for lid, s in zip(ids, raw):
        j = json.loads(s) if s else {}
        d = j.get("description") or ""
        ad = (j.get("propertyDetails") or {}).get("address") or {}
        r = {"dlen": len(d.strip()), "short": short(d), "label": ad.get("unit")}
        hit = r["short"]
        for k, rx in RX.items():
            r[f"t_{k}"] = bool(rx.search(d))
            hit |= r[f"t_{k}"]
        r["desc"] = d if (hit or lid in ratio_ids) else None
        rows.append(r)
    p = pd.DataFrame(rows)
    p["listing_id"] = ids
    p["collected_at"] = t.column("collected_at").to_pylist()
    p["listing_type"] = t.column("listing_type").to_pylist()
    parts.append(p)
    if g % 20 == 0:
        print("group", g, len(p), int(p.desc.notna().sum()), flush=True)
P = pd.concat(parts, ignore_index=True)
del parts
P = P.sort_values("collected_at").groupby("listing_id").tail(1)
P["listing_id"] = P.listing_id.astype(str)
print("listings", len(P), "with a kept text", int(P.desc.notna().sum()))
print(P[[c for c in P if c.startswith("t_")] + ["short"]].sum().to_dict())
P.to_parquet(OUT / "texts.parquet")
