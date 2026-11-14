"""S12's photo pilot, the sample: which photos to fetch, and the blind labels the raters see.

argv: DIR. The script reads the S12 read key's ads of roof rights, hardwood and live-in super
from `DIR/targets.parquet` and their stored records from `DIR/raw.jsonl` (written by the
unit-level reads' `pull.py`). For each ad it keeps up to 12 photo keys in the order of the
latest record, or of the latest record with photos when the last has none. It gives each ad
a random label, deals the labels into 6 batches, and draws 12 ads to rate again under new
labels in a seventh. It writes `DIR/photos.parquet` (label, order, key) for the fetch and
`DIR/blind.parquet` (label, listing_id, batch, repeat), which the raters never see."""

import json
import sys

import numpy as np
import pandas as pd

CAP = 12
BATCHES = 6
REPEATS = 12

out = sys.argv[1]
t = pd.read_parquet(f"{out}/targets.parquet")
recs = {}
for line in open(f"{out}/raw.jsonl"):
    x = json.loads(line)
    r = json.loads(x["raw_listing_json"])
    keys = [
        p["key"] for p in (r.get("media") or {}).get("photos") or [] if p.get("key")
    ]
    recs.setdefault(x["listing_id"], []).append(
        (x["collected_at"], x["snapshot_id"], keys)
    )
photos = {}
for lid, v in recs.items():
    v.sort()
    with_photos = [keys for _, _, keys in v if keys]
    photos[lid] = (v[-1][2] or (with_photos[-1] if with_photos else []))[:CAP]

rng = np.random.default_rng(20261113)
ids = t.listing_id.astype(str).to_numpy()[rng.permutation(len(t))]
blind = pd.DataFrame(
    {
        "label": [f"A{i + 1:02d}" for i in range(len(ids))],
        "listing_id": ids,
        "batch": np.arange(len(ids)) % BATCHES + 1,
        "repeat": False,
    }
)
again = rng.choice(ids[[len(photos[i]) > 0 for i in ids]], REPEATS, replace=False)
blind = pd.concat(
    [
        blind,
        pd.DataFrame(
            {
                "label": [f"B{i + 1:02d}" for i in range(REPEATS)],
                "listing_id": again,
                "batch": BATCHES + 1,
                "repeat": True,
            }
        ),
    ],
    ignore_index=True,
)
rows = [
    (lab, j + 1, k)
    for lab, lid in zip(blind.label, blind.listing_id)
    for j, k in enumerate(photos.get(lid, []))
]
p = pd.DataFrame(rows, columns=["label", "order", "key"])
p.to_parquet(f"{out}/photos.parquet")
blind.to_parquet(f"{out}/blind.parquet")
first = p[p.label.str.startswith("A")]
print(len(blind), "labels,", first.key.nunique(), "photos to fetch,", len(p), "to rate")
print(blind.groupby("batch").size().to_dict())
