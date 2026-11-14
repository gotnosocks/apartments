"""Outdoor size, step 3: the precision draw.

The pool is every row of the dataset copy with an `outdoor_sqft`, less the ads I developed the
extractor on (S7's 400 reads and S16's 60 precision reads) and less S16's 400 drawn ads. I cut
the pool into parts by code and by size and draw from each part:

- `number_first` and `noun_first`, each in the six size bins of step 2, 3 ads from each
  `number_first` bin and 2 from each `noun_first` bin;
- `range` 2 ads, `total` 4 and `sum` 4, any size.

That makes 40 ads. I shuffle them into 4 batches of 10, mask every dollar figure the way S16
did, and keep the whole description, so the stated area is always in the reader's text.
The batches leave out the extractor's area. Each part's size in the pool goes to
`strata.json` for the weights of step 4.

    python o3_draw.py   # inside systemd-run --user --scope -p MemoryMax=3G
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

DATA = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-outdoorsize/rows.parquet"
)
TEXTS = Path("/data1/apartments/tmp/text-flags-2026-11-13/texts.parquet")
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
S7 = Path("/data1/apartments/tmp/sprint-20261113/s7_picks.parquet")
S16 = Path("/data1/apartments/tmp/blind-spots-2026-11-14/")
OUT = Path("/data1/apartments/tmp/outdoor-size-2026-11-14/reads/")
SEED, BATCH = 20261114, 10
BINS = [20, 100, 200, 300, 500, 1000, 5000]
TAKE = {"number_first": 3, "noun_first": 2}
TAKE_ANY = {"range": 2, "total": 4, "sum": 4}
# S16's mask (`blind-spots-2026-11-14/b5_patterns.py`).
MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?\b|\bUSD\s?\d[\d,]*"
    r"|\b\d{1,2},?\d{3}(?:\.\d{2})?(?=\s*(?:/|per|a)\s*(?:mo\b|month))",
)

d = pd.read_parquet(
    DATA,
    columns=[
        "listing_id",
        "building",
        "bedrooms",
        "full_baths",
        "outdoor_sqft",
        "outdoor_sqft_src",
    ],
)
d = d[d.outdoor_sqft.notna()].copy()
dev = set(pd.read_parquet(S7, columns=["listing_id"]).listing_id)
for name in ("outdoor_large", "outdoor_uncoded"):
    dev |= set(pd.read_parquet(S16 / f"prec/{name}_key.parquet").listing_id)
drawn = set(pd.read_parquet(S16 / "draw.parquet", columns=["listing_id"]).listing_id)
pool = d[~d.listing_id.isin(dev | drawn)].copy()
pool["bin"] = pd.cut(pool.outdoor_sqft, BINS, include_lowest=True).astype(str)
pool["stratum"] = np.where(
    pool.outdoor_sqft_src.isin(list(TAKE)),
    pool.outdoor_sqft_src + " " + pool.bin,
    pool.outdoor_sqft_src,
)
sizes = pool.stratum.value_counts().to_dict()
print(f"rows with an area {len(d)}, pool {len(pool)}")

rng = np.random.default_rng(SEED)
picks = []
for stratum, g in pool.groupby("stratum", sort=True):
    src = g.outdoor_sqft_src.iloc[0]
    n = TAKE.get(src, TAKE_ANY.get(src, 0))
    for lid in rng.choice(g.listing_id.to_numpy(), size=min(n, len(g)), replace=False):
        picks.append((lid, stratum))
picks = pd.DataFrame(picks, columns=["listing_id", "stratum"])
picks = picks.iloc[rng.permutation(len(picks))].reset_index(drop=True)
picks["read_id"] = range(len(picks))
picks = picks.merge(pool.drop(columns="stratum"), on="listing_id")
print(f"drawn {len(picks)}")

f = pq.ParquetFile(TEXTS)
picked = pc.cast(list(picks.listing_id), "string")
texts = {}
for g in range(f.num_row_groups):
    t = f.read_row_group(g)
    for r in t.filter(pc.is_in(t["listing_id"], value_set=picked)).to_pylist():
        texts[r["listing_id"]] = r["text"]
assert set(texts) == set(picks.listing_id)

codes = pd.read_parquet(CODES, filters=[("listing_id", "in", list(picks.listing_id))])
po = [c for c in codes.columns if c.startswith("private_outdoor:")]
codes["po_coded"] = codes[["feat:PRIVATE_OUTDOOR_SPACE", *po]].fillna(0).max(axis=1) > 0
po_coded = dict(zip(codes.listing_id.astype(str), codes.po_coded))

OUT.mkdir(parents=True, exist_ok=True)
picks = picks.sort_values("read_id").reset_index(drop=True)
for b in range(int(np.ceil(len(picks) / BATCH))):
    with open(OUT / f"batch_{b}.jsonl", "w") as fh:
        for _, r in picks.iloc[b * BATCH : (b + 1) * BATCH].iterrows():
            fields = {
                "bedrooms": None if pd.isna(r.bedrooms) else int(r.bedrooms),
                "full_baths": None if pd.isna(r.full_baths) else float(r.full_baths),
                "private_outdoor_coded": bool(po_coded.get(r.listing_id, False)),
            }
            fh.write(
                json.dumps(
                    {
                        "read_id": int(r.read_id),
                        "address": r.building,
                        "coded_fields": fields,
                        "description": MONEY.sub("[amount]", texts[r.listing_id]),
                    }
                )
                + "\n"
            )
picks[
    ["read_id", "listing_id", "stratum", "outdoor_sqft_src", "bin", "outdoor_sqft"]
].to_parquet(OUT / "key.parquet")
json.dump(
    {
        "pool": len(pool),
        "strata": sizes,
        "drawn": picks.stratum.value_counts().to_dict(),
        "longest_description": max(len(t) for t in texts.values()),
    },
    open(OUT / "strata.json", "w"),
    indent=1,
)
print(json.dumps(picks.stratum.value_counts().sort_index().to_dict(), indent=1))
