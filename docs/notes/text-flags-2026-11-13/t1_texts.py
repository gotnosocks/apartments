"""Text flags, step 1: the latest description of each listing in L1's dataset.

I read the records file of the dataset's pipeline build (the manifest's `build.records`) twice.
The first pass picks each listing's latest record, by the later of `collected_at` and
`last_collected_at`, as `b0data` and `rentfrontier.b0duplex` pick it. The second pass pulls
the description of the picked record and appends it to `texts.parquet`, a row group at a time,
so the texts never all sit in memory.

To check that I picked the records `b0data` picked, I recompute the three old flags on each
lowercased description with pyarrow's RE2 and count the rows where they differ from the
dataset's columns. The table keeps the dataset's own old flags, L1's held-out mask and each
row's building in `rows.parquet`, and the texts in `texts.parquet`.

    python t1_texts.py   # inside systemd-run --user --scope -p MemoryMax=3G
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier.b0data import MIN_DESCRIPTION, TEXT_FLAGS  # noqa: E402

DATA = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
)
RUN = Path("/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1")
OUT = Path("/data1/apartments/tmp/text-flags-2026-11-13")
OUT.mkdir(parents=True, exist_ok=True)

manifest = json.loads((DATA / "manifest.json").read_text())
records = Path(manifest["build"]["records"]["path"])
frame = pd.read_parquet(
    DATA / "rows.parquet",
    columns=["listing_id", "building", "description_known", *TEXT_FLAGS],
)
frame["listing_id"] = frame.listing_id.astype(str)
frame["held"] = np.load(RUN / "pred_scores.npz", allow_pickle=True)["heldout"]
ids = set(frame.listing_id)

# Pass 1: the latest record of each listing, as (time, row group, row).
file = pq.ParquetFile(records)
best: dict[str, tuple[float, int, int]] = {}
for g in range(file.num_row_groups):
    head = file.read_row_group(
        g, columns=["listing_id", "collected_at", "last_collected_at"]
    )
    lid = [str(x) for x in head["listing_id"].to_pylist()]
    for r, (i, a, b) in enumerate(
        zip(
            lid, head["collected_at"].to_pylist(), head["last_collected_at"].to_pylist()
        )
    ):
        t = max((x for x in (a, b) if x is not None), default=None)
        if i in ids and t is not None and (i not in best or best[i][0] < t):
            best[i] = (t, g, r)
print("listings with a record", len(best), "of", len(ids), flush=True)

by_group: dict[int, list[tuple[int, str]]] = {}
for i, (_, g, r) in best.items():
    by_group.setdefault(g, []).append((r, i))

# Pass 2: the picked records' descriptions.
tmp = OUT / "texts.tmp.parquet"
schema = pa.schema([("listing_id", pa.string()), ("text", pa.string())])
with pq.ParquetWriter(tmp, schema) as w:
    for g in sorted(by_group):
        pick = sorted(by_group[g])
        raws = file.read_row_group(g, columns=["raw_listing_json"])["raw_listing_json"]
        raws = raws.take(pa.array([r for r, _ in pick])).to_pylist()
        texts = [
            str((json.loads(x) if x else {}).get("description") or "") for x in raws
        ]
        w.write_table(
            pa.table({"listing_id": [i for _, i in pick], "text": texts}, schema=schema)
        )
        del raws, texts

# Check the old flags a row group of texts at a time.
parts = []
texts = pq.ParquetFile(tmp)
for g in range(texts.num_row_groups):
    t = texts.read_row_group(g)
    low = pc.utf8_lower(t["text"])
    part = pd.DataFrame({"listing_id": t["listing_id"].to_numpy(zero_copy_only=False)})
    part["known_re"] = (
        pc.utf8_length(low).to_numpy(zero_copy_only=False) > MIN_DESCRIPTION
    )
    for f, pattern in TEXT_FLAGS.items():
        part[f + "_re"] = part.known_re & pc.match_substring_regex(
            low, pattern
        ).to_numpy(zero_copy_only=False)
    parts.append(part)
    del t, low
check = pd.concat(parts, ignore_index=True)
m = frame.merge(check, on="listing_id", how="left")
summary = {"rows": len(frame), "with_record": int(m.known_re.notna().sum())}
m["known_re"] = m.known_re.fillna(False).astype(bool)
summary["known_differs"] = int((m.known_re != m.description_known).sum())
for f in TEXT_FLAGS:
    m[f + "_re"] = m[f + "_re"].fillna(False).astype(bool)
    summary[f + "_differs"] = int((m[f + "_re"] != m[f]).sum())
print(json.dumps(summary, indent=2))
m[["listing_id", "building", "held", "description_known", *TEXT_FLAGS]].to_parquet(
    OUT / "rows.parquet", index=False
)
os.replace(tmp, OUT / "texts.parquet")
(OUT / "t1_summary.json").write_text(json.dumps(summary, indent=2))
