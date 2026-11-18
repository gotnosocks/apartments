"""Image read of the low outliers, part 1b: units of the training rows far below the model.

`insample.py` gives each training ad of the b9 fit its distance from the model's level for
the building, the date and the coded features, and each unit the mean of those distances
(`unit_resid`). Among units with 3 or more training ads and no income flag, the low units
are the lowest 1% by `unit_resid`, and candidates for controls are the middle half. The
script takes each unit's latest ad with a stored photo, keeps the lowest unit of a
building, leaves out buildings already in `draw.parquet`, caps the low units at 900
(a random draw), and matches a control to every third low unit by borough, bedroom count
(capped at 3) and year.

It then appends to `draw.parquet`, `images.parquet` and `blind.parquet`, with labels and
batches numbered after the existing ones, and writes the new batch files. 30 of the new ads
are dealt a second time.
"""

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/data1/apartments/serve/master/frontier/src")
from rentfrontier import api_records  # noqa: E402

OUT = "/data1/apartments/tmp/deals-photos-2026-11-18/"
ROWS = sys.argv[1]
BORO = {
    "new_york": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "Bronx",
    "staten_island": "Staten Island",
}
CAP, BATCH, REPEATS, LOWS, SEED = 6, 15, 30, 900, 20261119
rng = np.random.default_rng(SEED)


def boro(building):
    for k, v in BORO.items():
        if building.endswith("-" + k):
            return v
    return None


r = pd.read_parquet(
    OUT + "insample.parquet",
    columns=["listing_id", "building", "unit_id", "latest_day", "unit_resid", "unit_n"],
)
f = pd.read_parquet(
    ROWS,
    columns=["listing_id", "bedrooms", "full_baths", "half_baths", "income_restricted"],
)
f["listing_id"] = f.listing_id.astype(str)
r = r.merge(f.drop_duplicates("listing_id"), on="listing_id", validate="1:1")
r["income"] = r.income_restricted.fillna(False).astype(bool)
r = r[(r.unit_n >= 3) & ~r.groupby("unit_id").income.transform("any")]
units = r.drop_duplicates("unit_id").unit_resid
cut, q1, q3 = units.quantile([0.01, 0.25, 0.75])
print(
    "units", len(units), "low cut", round(cut, 4), "middle", round(q1, 4), round(q3, 4)
)
old = pd.read_parquet(OUT + "draw.parquet")
r = r[~r.building.isin(old.building)]
low = r[r.unit_resid <= cut].assign(group="low")
mid_units = pd.Series(r[(r.unit_resid > q1) & (r.unit_resid < q3)].unit_id.unique())
mid = r[r.unit_id.isin(mid_units.sample(6000, random_state=SEED))].assign(group="ctl")
cand = pd.concat([low, mid], ignore_index=True)
ids = set(cand.listing_id)

latest = {}
for x in api_records.captures(
    api_records.records_file(),
    ["listing_id", "collected_at", "snapshot_id", "raw_listing_json"],
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
cand = (
    cand[cand.gallery > 0]
    .sort_values("latest_day")
    .drop_duplicates("unit_id", keep="last")
)
cand["year"] = pd.to_datetime(cand.latest_day).dt.year
cand["boro"] = cand.building.map(boro)
cand["beds3"] = cand.bedrooms.clip(upper=3).astype(int)
cand["cdf"] = cand.unit_resid
cand["pool"] = "insample"
lows = cand[cand.group == "low"].sort_values("unit_resid").drop_duplicates("building")
print("low units with photos, one a building:", len(lows))
lows = lows.sample(min(LOWS, len(lows)), random_state=SEED)
pool = cand[(cand.group == "ctl") & ~cand.building.isin(lows.building)]
pool = pool.sample(frac=1, random_state=SEED).drop_duplicates("building")
taken, ctl = set(), []
for j, row in enumerate(lows.itertuples()):
    if j % 3:
        continue
    m = pool[
        (pool.boro == row.boro)
        & (pool.beds3 == row.beds3)
        & ((pool.year - row.year).abs() <= 1)
        & ~pool.listing_id.isin(taken)
    ]
    if len(m):
        ctl.append(m.iloc[0])
        taken.add(m.iloc[0].listing_id)
new = pd.concat([lows, pd.DataFrame(ctl)], ignore_index=True)[list(old.columns)]
assert not new.listing_id.isin(old.listing_id).any() and new.listing_id.is_unique
print(
    new.groupby("group").agg(
        ads=("cdf", "size"), plan=("plans", lambda s: (s > 0).sum())
    )
)
print(new[new.group == "low"].year.describe()[["min", "50%", "max"]].to_dict())

rows = []
for lid in new.listing_id:
    _, photos, plans = latest[lid]
    n = len(photos)
    places = range(n) if n <= CAP else np.round(np.linspace(0, n - 1, CAP)).astype(int)
    rows += [(lid, "photo", j + 1, photos[i]) for j, i in enumerate(places)]
    rows += [(lid, "plan", 1, k) for k in plans[:1]]
images = pd.DataFrame(rows, columns=["listing_id", "kind", "order", "key"])
blind = pd.read_parquet(OUT + "blind.parquet")
start, batch = len(blind), blind.batch.max()
order = new.listing_id.to_numpy()[rng.permutation(len(new))]
order = np.concatenate([order, rng.choice(order, REPEATS, replace=False)])
more = pd.DataFrame(
    {
        "label": [f"P{start + 1 + i:04d}" for i in range(len(order))],
        "listing_id": order,
        "batch": batch + 1 + np.arange(len(order)) // BATCH,
        "repeat": np.arange(len(order)) >= len(new),
    }
)
facts = new.set_index("listing_id")
for b, g in more.groupby("batch"):
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
pd.concat([old, new], ignore_index=True).to_parquet(OUT + "draw.parquet")
pd.concat(
    [pd.read_parquet(OUT + "images.parquet"), images], ignore_index=True
).to_parquet(OUT + "images.parquet")
pd.concat([blind, more], ignore_index=True).to_parquet(OUT + "blind.parquet")
print(len(images), "new images, batches", batch + 1, "to", more.batch.max())
