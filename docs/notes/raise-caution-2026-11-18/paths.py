"""The price path of each open ad of a backtest run, from the records file of its dataset.

A backtest dataset keeps each open ad's final ask (`rentfrontier.market`), so the ask on the
backtest day has to come from the ad's price changes. For each held-out ad this writes the
kept changes of its last capture (`latest_ask.record_latest`) as lists of days and prices.

Run from the repo root with PYTHONPATH=frontier/src:
python docs/notes/raise-caution-2026-11-18/paths.py BACKTEST_RUN OUT.parquet
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from rentfrontier import drift_deals
from rentfrontier import run as run_module
from rentfrontier.latest_ask import record_latest

run_dir = Path(run_module.RUNS) / sys.argv[1]
_, h, _ = drift_deals._held_frame(run_dir)
ids = set(h.listing_id.astype(str))
manifest = json.loads((drift_deals._dataset(run_dir) / "manifest.json").read_text())
file = pq.ParquetFile(manifest["build"]["records"]["path"])
seen = {}
for group in range(file.num_row_groups):
    head = file.read_row_group(
        group, columns=["listing_id", "listing_type", "last_collected_at"]
    )
    lid = [str(x) for x in head["listing_id"].to_pylist()]
    at = head["last_collected_at"].to_pylist()
    kinds = head["listing_type"].to_pylist()
    keep = [k == "rental" and i in ids for i, k in zip(lid, kinds)]
    if not any(keep):
        continue
    raws = file.read_row_group(group, columns=["raw_listing_json"]).filter(
        pa.array(keep)
    )
    rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
    for (i, t), raw in zip(rows, raws["raw_listing_json"].to_pylist()):
        if raw and (i not in seen or seen[i][0] < t):
            changes = record_latest(raw)["changes"]
            seen[i] = (t, [str(d) for d, _ in changes], [float(p) for _, p in changes])
    del raws
out = pd.DataFrame(
    [(i, d, p) for i, (_, d, p) in seen.items()],
    columns=["listing_id", "days", "prices"],
)
out.to_parquet(sys.argv[2])
print(
    "held-out ads",
    len(ids),
    "with a record",
    len(out),
    "with a change",
    (out.days.map(len) > 0).sum(),
)
