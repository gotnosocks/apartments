"""Photo disagreement, part 1: the image keys of each drawn ad and the readers' blind labels.

The script takes groups A, B and R of the market disagreement draw and reads each ad's
stored records from the pipeline's records file. From the latest record with photos it keeps
up to 8 photo keys (all of a gallery of 8 or fewer, otherwise 8 evenly spaced places from the
first photo to the last) and the first floor plan key. It gives each ad a random label
(`P001` to `P300`), deals the labels into 20 batches of 15, draws 60 ads with photos for a
second read under new labels (`P301` to `P360`) in 4 more batches, and writes:

- `images.parquet`: listing_id, kind (photo or plan), order, key;
- `blind.parquet`: label, listing_id, batch, repeat, gallery (the record's photo count),
  plans, few_photos;
- `batches/batch_NN.json`: for each label of the batch, the bedrooms, baths and borough,
  the only facts the readers get beside the images."""

import json
import os
import sys

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, "/data1/apartments/serve/master/frontier/src")
from rentfrontier import api_records  # noqa: E402

DRAW = "/data1/apartments/tmp/market-disagreement-2026-11-14/draw.parquet"
OUT = "/data1/apartments/tmp/photo-disagreement-2026-11-14/"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
)
GROUPS = {"A_cheap_slow": "A", "B_cheap_fast": "B", "R_random": "R"}
BORO = {
    "1": "Manhattan",
    "2": "Bronx",
    "3": "Brooklyn",
    "4": "Queens",
    "5": "Staten Island",
}
CAP, BATCH, REPEATS, SEED = 8, 15, 60, 20261114

draw = pd.read_parquet(DRAW)
draw = draw[draw.group.isin(GROUPS)].reset_index(drop=True)
draw["listing_id"] = draw.listing_id.astype(str)
assert len(draw) == 300 and draw.listing_id.is_unique
ids = set(draw.listing_id)

latest = {}
source = api_records.records_file()
columns = ["listing_id", "collected_at", "snapshot_id", "raw_listing_json"]
for x in api_records.captures(source, columns):
    if x["listing_id"] not in ids:
        continue
    media = json.loads(x["raw_listing_json"]).get("media") or {}
    photos = [p["key"] for p in media.get("photos") or [] if p.get("key")]
    plans = [p["key"] for p in media.get("floorPlans") or [] if p.get("key")]
    stamp = (bool(photos), str(x["collected_at"]), str(x["snapshot_id"]))
    if x["listing_id"] not in latest or stamp > latest[x["listing_id"]][0]:
        latest[x["listing_id"]] = (stamp, photos, plans)

rows, counts = [], {}
for lid in draw.listing_id:
    _, photos, plans = latest.get(lid, (None, [], []))
    counts[lid] = (len(photos), len(plans))
    n = len(photos)
    places = range(n) if n <= CAP else np.round(np.linspace(0, n - 1, CAP)).astype(int)
    rows += [(lid, "photo", j + 1, photos[i]) for j, i in enumerate(places)]
    rows += [(lid, "plan", 1, k) for k in plans[:1]]
images = pd.DataFrame(rows, columns=["listing_id", "kind", "order", "key"])
images.to_parquet(OUT + "images.parquet")

f = pq.ParquetFile(DATA)
want = pa.array(sorted(ids), type=f.schema_arrow.field("listing_id").type)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "full_baths", "half_baths"])
    parts.append(t.filter(pc.is_in(t["listing_id"], value_set=want)).to_pandas())
baths = pd.concat(parts)
baths["listing_id"] = baths.listing_id.astype(str)
baths = baths.drop_duplicates("listing_id").set_index("listing_id")

rng = np.random.default_rng(SEED)
order = draw.listing_id.to_numpy()[rng.permutation(len(draw))]
blind = pd.DataFrame(
    {
        "label": [f"P{i + 1:03d}" for i in range(len(order))],
        "listing_id": order,
        "batch": np.arange(len(order)) // BATCH + 1,
        "repeat": False,
    }
)
with_photos = np.array([i for i in order if counts[i][0] > 0])
again = rng.choice(with_photos, REPEATS, replace=False)
blind = pd.concat(
    [
        blind,
        pd.DataFrame(
            {
                "label": [f"P{301 + i:03d}" for i in range(REPEATS)],
                "listing_id": again,
                "batch": 21 + np.arange(REPEATS) // BATCH,
                "repeat": True,
            }
        ),
    ],
    ignore_index=True,
)
blind["gallery"] = [counts[i][0] for i in blind.listing_id]
blind["plans"] = [counts[i][1] for i in blind.listing_id]
blind["few_photos"] = blind.gallery <= 3
blind.to_parquet(OUT + "blind.parquet")

facts = draw.set_index("listing_id")
os.makedirs(OUT + "batches", exist_ok=True)
for b, g in blind.groupby("batch"):
    ads = []
    for lab, lid in zip(g.label, g.listing_id):
        full = baths.full_baths.get(lid)
        half = baths.half_baths.get(lid)
        ads.append(
            {
                "label": lab,
                "bedrooms": int(facts.bedrooms[lid]),
                "full_baths": None if pd.isna(full) else int(full),
                "half_baths": None if pd.isna(half) else int(half),
                "borough": BORO.get(str(facts.boro[lid])),
            }
        )
    with open(f"{OUT}batches/batch_{b:02d}.json", "w") as sink:
        json.dump(ads, sink, indent=1)

first = blind[~blind.repeat].merge(draw[["listing_id", "group"]])
first["group"] = first.group.map(GROUPS)
print(len(images), "images:", images.kind.value_counts().to_dict())
print(
    first.groupby("group").agg(
        ads=("label", "size"),
        with_photo=("gallery", lambda s: (s > 0).sum()),
        with_plan=("plans", lambda s: (s > 0).sum()),
        few=("few_photos", "sum"),
        median_gallery=("gallery", "median"),
    )
)
