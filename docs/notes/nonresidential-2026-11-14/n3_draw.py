"""N3: the draw of candidate rows for the precision reads, and the batches the readers take.

I leave out the candidates in S16's draw and split the rest into the cells the note lists. A
stratum with a signal of its own splits by whether the draft rule marks the row, and `words`
splits by whether the row's lot has no apartments. From each cell I draw the take below with
seed 20261114, and I weight each read by its cell's pool over its take.

For each drawn row I take the latest record of its listing from the sprint's copy of the feed
records: the description, the unit label, the room count and the stated size. I mask dollar
figures with S16's pattern (`blind-spots-2026-11-14/b2_fields.py`), shuffle the 60 rows, give
each a read id, and write them in batches of 10 to `reads/batch_K.md`. A batch shows no ask, no
prediction, no gap and no cell. The key from read id to listing, cell and weight goes to
`key.parquet`, and the files' SHA-256s to `draw.json`.
"""

import hashlib
import json
import os
import re

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = "/data1/apartments/tmp/nonresidential-2026-11-14/"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"
SEED = 20261114
MAXLEN = 4000
TAKE = {
    "label+": 4,
    "label-": 4,
    "sfz+": 3,
    "sfz-": 3,
    "build_out+": 4,
    "build_out-": 4,
    "medical_prof+": 4,
    "medical_prof-": 4,
    "offer+": 4,
    "offer-": 4,
    "live_work": 8,
    "ground_retail": 5,
    "words_lot": 4,
    "words_other": 5,
}
MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?\b|\bUSD\s?\d[\d,]*"
    r"|\b\d{1,2},?\d{3}(?:\.\d{2})?(?=\s*(?:/|per|a)\s*(?:mo\b|month))",
)


def cell(r):
    s = "sfz" if r.stratum in ("sf_year", "zoned") else r.stratum
    if s in ("label", "sfz", "build_out", "medical_prof", "offer"):
        return s + ("+" if r.rule_mark else "-")
    if s == "words":
        return "words_lot" if r.bk_lot else "words_other"
    return s


c = pd.read_parquet(OUT + "candidates.parquet")
c = c[~c.drawn16].copy()
c["cell"] = [cell(r) for r in c.itertuples()]
pool = c.cell.value_counts()
draws = []
for k, n in TAKE.items():
    g = c[c.cell == k].sort_values("listing_id")
    s = g.sample(n, random_state=SEED).copy()
    s["pool"] = len(g)
    s["weight"] = len(g) / n
    draws.append(s)
dr = pd.concat(draws)
dr = dr.iloc[np.random.default_rng(SEED).permutation(len(dr))].reset_index(drop=True)
dr["read_id"] = [f"R{i + 1:02d}" for i in range(len(dr))]
dr["batch"] = dr.index // 10 + 1

ids = list(dr.listing_id)
want = pa.array(ids, pa.string())
recs = {}
f = pq.ParquetFile(RECS)
cols = ["listing_id", "last_collected_at", "display_unit", "room_count", "living_area"]
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=[*cols, "description"])
    t = t.filter(pc.is_in(t["listing_id"], value_set=want))
    for r in t.to_pylist():
        k = r["listing_id"]
        if k not in recs or r["last_collected_at"] > recs[k]["last_collected_at"]:
            recs[k] = r
assert set(recs) == set(ids)


def num(v):
    if v is None or pd.isna(v) or (isinstance(v, str) and not v.strip()):
        return "not given"
    v = pd.to_numeric(v, errors="coerce")
    return "not given" if pd.isna(v) else f"{v:g}"


os.makedirs(OUT + "reads", exist_ok=True)
sha = {}
for b, g in dr.groupby("batch"):
    lines = [f"# Batch {b}", ""]
    for r in g.itertuples():
        rec = recs[r.listing_id]
        text = MONEY.sub("[amount]", rec["description"] or "")[:MAXLEN]
        lines += [
            f"## {r.read_id}",
            "",
            f"- unit label: {rec['display_unit'] or 'not given'}",
            f"- coded bedrooms: {num(r.bedrooms)}, full baths: {num(r.full_baths)}, "
            f"half baths: {num(r.half_baths)}",
            f"- room count: {num(rec['room_count'])}, stated size (sq ft): "
            f"{num(rec['living_area'])}",
            f"- last collected: {pd.to_datetime(rec['last_collected_at'], unit='s'):%Y-%m-%d}",
            "",
            "Description:",
            "",
            text if text.strip() else "(no description)",
            "",
        ]
    path = OUT + f"reads/batch_{b}.md"
    open(path, "w").write("\n".join(lines))
    sha[f"reads/batch_{b}.md"] = hashlib.sha256(open(path, "rb").read()).hexdigest()

key = dr[
    [
        "read_id",
        "batch",
        "listing_id",
        "cell",
        "stratum",
        "pool",
        "weight",
        "held",
        "rule_mark",
        "k_text",
        "k_label",
        "k_other",
        "k_lot",
    ]
]
key.to_parquet(OUT + "key.parquet", index=False)
res = {
    "seed": SEED,
    "pool_after_dropping_s16_draw": pool.to_dict(),
    "dropped_s16_draw": int(pd.read_parquet(OUT + "candidates.parquet").drawn16.sum()),
    "take": TAKE,
    "held_in_draw": int(dr.held.sum()),
    "sha256": sha,
}
json.dump(res, open(OUT + "draw.json", "w"), indent=1, default=int)
print(json.dumps(res, indent=1, default=int))
