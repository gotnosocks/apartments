"""Write each L1 listing's latest description, where it mentions free rent, to texts.parquet.

    python extract.py

The latest record is picked as `rentfrontier.b0freetext` picks it. A description is kept only
when it matches PRE, and every listing keeps its record time and description length. The
reader samples and the price-basis counts in compare.py read this file. Run it in a 3G scope.
"""

import json
import re
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SRC = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
REC = json.load(open(SRC + "/manifest.json"))["build"]["records"]["path"]
PRE = re.compile(r"(?i)free|concession|net[- ]?effective|\bnet rent|\bNER\b|\bOP\b")
t0 = time.time()
ids = set(
    pd.read_parquet(SRC + "/rows.parquet", columns=["listing_id"]).listing_id.astype(
        str
    )
)
seen = {}
f = pq.ParquetFile(REC)
for g in range(f.num_row_groups):
    head = f.read_row_group(
        g, columns=["listing_id", "collected_at", "last_collected_at"]
    )
    lid = [str(x) for x in head["listing_id"].to_pylist()]
    at = [
        max((t for t in ts if t is not None), default=None)
        for ts in zip(
            head["collected_at"].to_pylist(), head["last_collected_at"].to_pylist()
        )
    ]
    keep = [
        i in ids and t is not None and (i not in seen or seen[i][0] < t)
        for i, t in zip(lid, at)
    ]
    if not any(keep):
        continue
    raws = (
        f.read_row_group(g, columns=["raw_listing_json"])
        .filter(pa.array(keep))["raw_listing_json"]
        .to_pylist()
    )
    rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
    for (i, t), raw in zip(rows, raws):
        d = str((json.loads(raw) if raw else {}).get("description") or "")
        if i not in seen or seen[i][0] < t:
            seen[i] = (t, len(d), d if PRE.search(d) else None)
    print(g, len(seen), round(time.time() - t0), flush=True)
out = pd.DataFrame(
    [(i, t, n, d) for i, (t, n, d) in seen.items()],
    columns=["listing_id", "t", "n", "description"],
)
out.to_parquet(
    "/data1/apartments/tmp/sprint-20261113/free-months/texts.parquet", index=False
)
print(len(out), out.description.notna().sum(), time.time() - t0)
