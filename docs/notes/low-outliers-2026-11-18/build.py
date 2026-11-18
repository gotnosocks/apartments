"""Draw the ads for the far-below read and write the readers' groups.

Sets: `below` and `control` from b9's held-out ads since 2024-07 in the read half of the
buildings, `deal` and `dealctl` from the live Deals file (no cautions).
Each ad's packet carries its text with rents, its coded fields, and the unit's other ads.
"""

import json, re, sys
import numpy as np, pandas as pd, pyarrow.parquet as pq

SEED = 20261118
OUT = "/data1/apartments/tmp/low-outliers-2026-11-18/"
ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
REC = "/data1/apartments/pipeline/datasets/records-0d20eb92b9f08c7d.parquet"
rng = np.random.default_rng(SEED)


def draw(df, n):
    df = df.sample(frac=1, random_state=int(rng.integers(1 << 31)))
    return df.drop_duplicates("unit_id").groupby("building").head(2).head(n)


h = pd.read_parquet(OUT + "held_b9.parquet")
h["day"] = pd.to_datetime(h.price_at)
pool = h[(h.half == "read") & (h.day >= "2024-07-01") & ~h.income_restricted]
S = [
    draw(pool[pool.cdf < 0.01], 110).assign(set="below"),
    draw(pool[(pool.cdf > 0.25) & (pool.cdf < 0.75)], 55).assign(set="control"),
]
print("below eligible", (pool.cdf < 0.01).sum())
S = [
    s[["listing_id", "unit_id", "building", "cdf", "set"]].assign(
        as_of=s.day.dt.strftime("%Y-%m-%d")
    )
    for s in S
]

deals = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
deals = deals[deals.cautions.map(len) == 0].rename(columns={"below_share": "cdf"})
ads_ids = (
    pq.read_table(ADS, columns=["listing_id", "unit_id"])
    .to_pandas()
    .drop_duplicates("listing_id")
)
deals = deals.merge(ads_ids, on="listing_id", how="left")
top = (
    deals.sort_values("cdf")
    .drop_duplicates("unit_id")
    .groupby("building")
    .head(2)
    .head(60)
    .assign(set="deal")
)
ctl = draw(deals[(deals.cdf > 0.25) & (deals.cdf < 0.75)], 30).assign(set="dealctl")
print("deal cdf max", top.cdf.max())
S += [
    s[["listing_id", "unit_id", "building", "cdf", "set"]].assign(as_of="2026-11-10")
    for s in (top, ctl)
]
A = pd.concat(S).reset_index(drop=True)
A = A.drop_duplicates("listing_id")
ids = A.sample(frac=1, random_state=3).listing_id.values
ngroups = int(np.ceil(len(ids) / 20))
A["group"] = A.listing_id.map({l: i % ngroups for i, l in enumerate(ids)})
A["pos"] = A.groupby("group").cumcount()
print(A.groupby(["group", "set"]).size().unstack().fillna(0).astype(int).to_string())

cols = [
    "listing_id",
    "unit_id",
    "building",
    "neighbourhood",
    "status",
    "page_price",
    "months_free",
    "lease_term",
    "first_day",
    "off_day",
    "days_on_market",
    "first_ask",
    "latest_ask",
    "bedrooms",
    "full_baths",
    "half_baths",
    "square_feet",
    "advertised_floor",
    "physical_floor",
    "floors_above_ground",
    "elevator",
    "laundry_type",
    "doorman_type",
    "pet_policy",
    "furnished",
    "short_term",
    "concession",
    "exclusion_reasons",
    "building_check",
]
T = (
    pq.read_table(
        ADS,
        columns=cols,
        filters=[("unit_id", "in", list(A.unit_id.dropna().unique()))],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
T["first_day"] = pd.to_datetime(T.first_day)
need = set(A.listing_id)
prev = {}
for _, a in A.iterrows():
    u = T[
        (T.unit_id == a.unit_id)
        & (T.listing_id != a.listing_id)
        & (T.first_day < pd.Timestamp(a.as_of))
    ].sort_values("first_day")
    prev[a.listing_id] = u
    if len(u):
        need.add(u.listing_id.iloc[-1])
R = pq.read_table(
    REC,
    columns=["listing_id", "collected_at", "raw_listing_json"],
    filters=[("listing_id", "in", [int(x) for x in need])],
).to_pandas()
R["listing_id"] = R.listing_id.astype(str)
R = R.sort_values("collected_at").groupby("listing_id").tail(1).set_index("listing_id")
print("records found", len(R), "of", len(need))


def clean(v):
    if isinstance(v, (np.ndarray, list)):
        return [clean(x) for x in v]
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, np.floating):
        return None if np.isnan(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return v


def text(l):
    if l not in R.index:
        return None, {}
    j = json.loads(R.loc[l].raw_listing_json)
    return re.sub(r"<br\s*/?>", "\n", j.get("description") or ""), j


Ti = T.set_index("listing_id")
packets = {}
for _, a in A.iterrows():
    l = a.listing_id
    desc, j = text(l)
    pdx = j.get("propertyDetails") or {}
    media = j.get("media") or {}
    f = clean(Ti.loc[l].to_dict()) if l in Ti.index else {}
    bc = f.pop("building_check", None) or {}
    f.pop("unit_id", None)
    hist = []
    for _, u in prev[l].iterrows():
        hist.append(
            {
                "listed": clean(u.first_day),
                "status": u.status,
                "first_ask": clean(u.first_ask),
                "last_ask": clean(u.latest_ask),
                "months_free": clean(u.months_free),
                "bedrooms": clean(u.bedrooms),
                "full_baths": clean(u.full_baths),
                "square_feet": clean(u.square_feet),
                "furnished": clean(u.furnished),
                "short_term": clean(u.short_term),
                "days_on_market": clean(u.days_on_market),
                "left_out_of_model_for": clean(u.exclusion_reasons) or None,
            }
        )
    pdesc = text(prev[l].listing_id.iloc[-1])[0] if len(prev[l]) else None
    p = {
        "ad": f"G{a.group:02d}-{a.pos:02d}",
        "listing_id": l,
        "address": (pdx.get("address") or {}).get("street"),
        "unit": (pdx.get("address") or {}).get("displayUnit"),
        "source": (j.get("listingSource") or {}).get("sourceType"),
        "agency": (j.get("legacy") or {}).get("sourceGroupLabel"),
        "photo_count": len(media.get("photos") or []),
        "floor_plan_count": len(media.get("floorPlans") or []),
        "rooms": pdx.get("roomCount"),
        "amenities": pdx.get("amenities") or {},
        "features": pdx.get("features") or {},
        "coded_fields": {k: v for k, v in f.items() if v is not None and v != []},
        "building_numfloors": bc.get("numfloors"),
        "building_units": bc.get("unitsres"),
        "description": desc,
        "unit_earlier_ads": hist,
        "previous_ad_description": (pdesc[:1800] if pdesc else None),
    }
    packets.setdefault(int(a.group), []).append(p)
import os

os.makedirs(OUT + "groups", exist_ok=True)
os.makedirs(OUT + "answers", exist_ok=True)
for g, ps in packets.items():
    json.dump(
        sorted(ps, key=lambda p: p["ad"]),
        open(OUT + f"groups/g{g:02d}.json", "w"),
        indent=1,
        default=str,
    )
A.to_csv(OUT + "key.csv", index=False)
print(
    len(A),
    "ads",
    ngroups,
    "groups; no text",
    sum(not (p["description"] or "").strip() for ps in packets.values() for p in ps),
    "with history",
    sum(bool(p["unit_earlier_ads"]) for ps in packets.values() for p in ps),
)
