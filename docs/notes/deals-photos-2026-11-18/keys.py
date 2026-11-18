"""Image read of the low outliers, part 1: the draw, the image keys and the blind labels.

Pools, each of held-out ads:

- `b9`: the latest-split run of the base model, income-restricted ads left out. Low ads
  have a cdf under 0.01, candidates for controls a cdf of 0.25 to 0.75.
- `market` and `backtest`: the Deals tables of `range-m` and `range-j`, uncautioned ads.
  Low ads have a `below_share` under 0.02.

The script scans the records file once for the photo and floor plan keys of every low ad
and of a random 8,000 control candidates, and drops ads with no stored photo. It keeps at
most one low ad a building in `b9` (the lowest), every low ad of the two tables, and for
every two low ads a control drawn from `b9` in the same borough, bedroom count (capped at
3) and year. Each ad gets up to 6 photos (evenly spaced over the gallery) and the first
floor plan, a random label and a batch of 15. The first 60 labels are dealt again under
new labels for a second read.

Writes `draw.parquet`, `images.parquet`, `blind.parquet` and `batches/batch_NN.json`.
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/data1/apartments/serve/master/frontier/src")
from rentfrontier import api_records, drift_deals  # noqa: E402

OUT = "/data1/apartments/tmp/deals-photos-2026-11-18/"
HELD = "/data1/apartments/tmp/low-outliers-2026-11-18/held_b9.parquet"
ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
RUNS = Path("/data1/apartments/frontier/runs")
TABLES = {
    "market": "drift-building-bedtext-layout-range-b0-market-053c5aa1-range-m",
    "backtest": "drift-building-bedtext-layout-range-b0-market-d9028c57-range-j",
}
BORO = {
    "new_york": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "Bronx",
    "staten_island": "Staten Island",
}
CAP, BATCH, REPEATS, SEED = 6, 15, 60, 20261118
rng = np.random.default_rng(SEED)


def boro(building):
    for k, v in BORO.items():
        if building.endswith("-" + k):
            return v
    return None


cols = ["listing_id", "building", "bedrooms", "full_baths", "half_baths", "cdf", "year"]
h = pd.read_parquet(HELD)
h = h[~h.income_restricted.fillna(False).astype(bool)]
h["listing_id"] = h.listing_id.astype(str)
h["year"] = pd.to_datetime(h.price_at).dt.year
low = h[h.cdf < 0.01][cols].assign(pool="b9", group="low")
mid = h[(h.cdf > 0.25) & (h.cdf < 0.75)][cols]
mid = mid.sample(8000, random_state=SEED).assign(pool="b9", group="ctl")
parts = [low, mid]
for name, run in TABLES.items():
    t = drift_deals.deals(RUNS / run, ADS)
    t = t[~t.cautions.map(bool) & (t.below_share < 0.02)]
    t = t.assign(
        listing_id=t.listing_id.astype(str),
        cdf=t.below_share,
        year=pd.to_datetime(t.first_day).dt.year,
        pool=name,
        group="low",
    )
    parts.append(t[cols + ["pool", "group"]])
cand = pd.concat(parts, ignore_index=True)
cand["boro"] = cand.building.map(boro)
cand["beds3"] = cand.bedrooms.clip(upper=3).astype(int)
ids = set(cand.listing_id)

latest = {}
source = api_records.records_file()
for x in api_records.captures(
    source, ["listing_id", "collected_at", "snapshot_id", "raw_listing_json"]
):
    lid = str(x["listing_id"])
    if lid not in ids:
        continue
    media = json.loads(x["raw_listing_json"]).get("media") or {}
    photos = [p["key"] for p in media.get("photos") or [] if p.get("key")]
    plans = [p["key"] for p in media.get("floorPlans") or [] if p.get("key")]
    stamp = (bool(photos), str(x["collected_at"]), str(x["snapshot_id"]))
    if lid not in latest or stamp > latest[lid][0]:
        latest[lid] = (stamp, photos, plans)

cand["gallery"] = [len(latest.get(i, (0, [], []))[1]) for i in cand.listing_id]
cand["plans"] = [len(latest.get(i, (0, [], []))[2]) for i in cand.listing_id]
print(
    cand.groupby(["pool", "group"]).agg(
        ads=("cdf", "size"), photo=("gallery", lambda s: (s > 0).sum())
    )
)
cand = cand[cand.gallery > 0]
lows = cand[cand.group == "low"].sort_values("cdf")
b9 = lows[lows.pool == "b9"].drop_duplicates("building")
tables = lows[lows.pool != "b9"].drop_duplicates("listing_id")
tables = tables[~tables.listing_id.isin(b9.listing_id)]
lows = pd.concat([b9, tables], ignore_index=True)
pool = cand[(cand.group == "ctl") & ~cand.building.isin(lows.building)]
pool = pool.sample(frac=1, random_state=SEED).drop_duplicates("building")
taken, ctl = set(), []
for j, r in enumerate(lows.sample(frac=1, random_state=SEED).itertuples()):
    if j % 2:
        continue
    m = pool[
        (pool.boro == r.boro)
        & (pool.beds3 == r.beds3)
        & ((pool.year - r.year).abs() <= 1)
        & ~pool.listing_id.isin(taken)
    ]
    if len(m):
        ctl.append(m.iloc[0])
        taken.add(m.iloc[0].listing_id)
draw = pd.concat([lows, pd.DataFrame(ctl)], ignore_index=True)
assert draw.listing_id.is_unique
draw.to_parquet(OUT + "draw.parquet")
print(
    draw.groupby(["pool", "group"]).agg(
        ads=("cdf", "size"),
        plan=("plans", lambda s: (s > 0).sum()),
        years=("year", lambda s: f"{s.min()}-{s.max()}"),
    )
)

rows = []
for lid in draw.listing_id:
    _, photos, plans = latest[lid]
    n = len(photos)
    places = range(n) if n <= CAP else np.round(np.linspace(0, n - 1, CAP)).astype(int)
    rows += [(lid, "photo", j + 1, photos[i]) for j, i in enumerate(places)]
    rows += [(lid, "plan", 1, k) for k in plans[:1]]
images = pd.DataFrame(rows, columns=["listing_id", "kind", "order", "key"])
images.to_parquet(OUT + "images.parquet")

order = draw.listing_id.to_numpy()[rng.permutation(len(draw))]
n = len(order)
blind = pd.DataFrame(
    {
        "label": [f"P{i + 1:04d}" for i in range(n)],
        "listing_id": order,
        "batch": np.arange(n) // BATCH + 1,
        "repeat": False,
    }
)
again = rng.choice(order, REPEATS, replace=False)
blind = pd.concat(
    [
        blind,
        pd.DataFrame(
            {
                "label": [f"P{n + 1 + i:04d}" for i in range(REPEATS)],
                "listing_id": again,
                "batch": blind.batch.max() + 1 + np.arange(REPEATS) // BATCH,
                "repeat": True,
            }
        ),
    ],
    ignore_index=True,
)
blind.to_parquet(OUT + "blind.parquet")
facts = draw.set_index("listing_id")
os.makedirs(OUT + "batches", exist_ok=True)
for b, g in blind.groupby("batch"):
    ads = [
        {
            "label": lab,
            "bedrooms": int(facts.bedrooms[lid]),
            "full_baths": None
            if pd.isna(facts.full_baths[lid])
            else int(facts.full_baths[lid]),
            "half_baths": None
            if pd.isna(facts.half_baths[lid])
            else int(facts.half_baths[lid]),
            "borough": facts.boro[lid],
        }
        for lab, lid in zip(g.label, g.listing_id)
    ]
    with open(f"{OUT}batches/batch_{b:02d}.json", "w") as sink:
        json.dump(ads, sink, indent=1)
print(
    len(images),
    "images:",
    images.kind.value_counts().to_dict(),
    "batches",
    blind.batch.max(),
)
