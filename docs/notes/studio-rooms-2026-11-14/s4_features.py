"""S17, part 4: fields for candidate rules over all 905 rows of the pool, written before the
reads were scored.

For each pool row I gather, from the ads file of the build behind L1's dataset and the
listing codes:

1. the unit's other ads (the same `unit_id`, kept or not): how many open within 730 days of
   the row's ad, how many of those code 1 bedroom or more, the modal count among them, and
   whether one of them also codes a room count within 1 of the row's;
2. whether the unit has any other ad typed as a studio (coded 0 with at most 3 rooms);
3. units of the same line on other floors of the building, coded 1 or more with a room count
   within 1 of the row's;
4. the stated size (`square_feet`, else the record's living area) and the lister;
5. whether the latest description says "studio", and whether it names a bedroom count.

I also give each held-out row L1's step for its bedrooms, `delta_k`: the posterior mean of
the bedroom ladder (`bed>=1` to `bed>=k`) for the unit's modal count k, with the full-bath
terms of count k in place of those of a studio. L1 also reads `ad:extra_rooms`, whose
coefficient is near zero per ad and 0.015 a room in the unit mean, and I leave it out.
I write `features.parquet`."""

import re

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = "/data1/apartments/tmp/studio-rooms-2026-11-14/"
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
NEAR = 730
STUDIO = r"(?i)\bstudio\b"
BEDS = (
    r"(?i)\b(?:[1-6]|one|two|three|four|five|six)[\s-]*(?:bed(?:room)?s?|br|bdrm?s?)\b"
)

pool = pd.read_parquet(OUT + "pool.parquet")
ads = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "unit_id",
        "building",
        "page",
        "on_day",
        "bedrooms",
        "full_baths",
        "square_feet",
        "in_rows",
    ],
)
ads = ads[ads.building.isin(set(pool.building))]
ads["label"] = ads.page.str.rsplit("/", n=1).str[-1].str.lower()
codes = pd.read_parquet(CODES, columns=["listing_id", "rooms"])
ads = ads.merge(codes, on="listing_id", how="left")


def line_of(label):
    """The floor and line of a unit label, as in part 2."""
    if not isinstance(label, str):
        return None, None
    lab = re.sub(r"^(?:apt|unit|#)[-_ ]*", "", label)
    if m := re.fullmatch(r"(?:ph)?(\d{1,3})-?([a-z]{1,2})", lab):
        return m[1], "letter:" + m[2]
    if m := re.fullmatch(r"(\d{1,2})(\d{2})", lab):
        return m[1], "number:" + m[2]
    if m := re.fullmatch(r"(\d{1,2})(?:fl|floor)?", lab):
        return m[1], "floor-through"
    if m := re.fullmatch(r"([a-z])-?(\d{1,2})", lab):
        return m[2], "letter:" + m[1]
    return None, None


fl = ads.label.map(line_of)
ads["floor"], ads["line"] = fl.str[0], fl.str[1]
ads["day"] = pd.to_datetime(ads.on_day)

f = pq.ParquetFile(RECS)
ids = pc.cast(list(set(ads.listing_id)), "string")
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(
        g,
        columns=[
            "listing_id",
            "last_collected_at",
            "lister",
            "living_area",
            "description",
        ],
    )
    t = t.filter(pc.is_in(t["listing_id"], value_set=ids))
    desc = pc.fill_null(t["description"], "")
    parts.append(
        pd.DataFrame(
            {
                "listing_id": t["listing_id"].to_numpy(zero_copy_only=False),
                "t": t["last_collected_at"].to_numpy(zero_copy_only=False),
                "lister": t["lister"].to_numpy(zero_copy_only=False),
                "living_area": t["living_area"].to_numpy(zero_copy_only=False),
                "says_studio": pc.match_substring_regex(desc, STUDIO).to_numpy(
                    zero_copy_only=False
                ),
                "names_beds": pc.match_substring_regex(desc, BEDS).to_numpy(
                    zero_copy_only=False
                ),
                "desc_len": pc.utf8_length(desc).to_numpy(zero_copy_only=False),
            }
        )
    )
recs = pd.concat(parts).sort_values("t").drop_duplicates("listing_id", keep="last")
ads = ads.merge(recs.drop(columns="t"), on="listing_id", how="left")
ads["size"] = ads.square_feet.fillna(pd.to_numeric(ads.living_area, errors="coerce"))

post = np.load(RUN + "posterior.npz", allow_pickle=True)
names = [str(n) for n in post["names"]]
beta = post["kept/beta"].reshape(-1, len(names)).mean(axis=0)
b = dict(zip(names, beta))


def bath_terms(k, full):
    return sum(b.get(f"bed={k}:full>={j}", 0.0) for j in (2, 3, 4) if full >= j)


def delta(k, full):
    if not k or np.isnan(k):
        return np.nan
    k = int(min(k, 5))
    full = 1 if np.isnan(full) else full
    ladder = sum(b[f"bed>={j}"] for j in range(1, k + 1))
    return ladder + bath_terms(k, full) - bath_terms(0, full)


rows = []
for _, r in pool.iterrows():
    me = ads[ads.listing_id == r.listing_id].iloc[0]
    u = ads[(ads.unit_id == me.unit_id) & (ads.listing_id != me.listing_id)]
    if pd.isna(me.unit_id):
        u = u.iloc[:0]
    near = u[(u.day - me.day).abs().dt.days <= NEAR]
    nc = near[near.bedrooms >= 1]
    ln = ads[
        (ads.building == me.building)
        & (ads.line == me.line)
        & (ads.label != me.label)
        & (ads.unit_id != me.unit_id)
        & (ads.bedrooms >= 1)
        & ((ads.rooms - me.rooms).abs() <= 1)
    ]
    if me.line is None:
        ln = ln.iloc[:0]
    k = nc.bedrooms.mode().min() if len(nc) else np.nan
    rows.append(
        {
            "listing_id": r.listing_id,
            "unit_other": len(u),
            "unit_near": len(near),
            "unit_near_1plus": len(nc),
            "unit_near_all_1plus": len(near) > 0 and len(nc) == len(near),
            "unit_near_1plus_rooms": bool(((nc.rooms - me.rooms).abs() <= 1).any()),
            "unit_any_1plus": bool((u.bedrooms >= 1).any()),
            "unit_typed_studio": bool(((u.bedrooms == 0) & (u.rooms <= 3)).any()),
            "k_unit": k,
            "line_1plus_rooms": len(ln),
            "line_k": ln.bedrooms.mode().min() if len(ln) else np.nan,
            "size": me["size"],
            "lister": me.lister,
            "says_studio": bool(me.says_studio) if pd.notna(me.says_studio) else False,
            "names_beds": bool(me.names_beds) if pd.notna(me.names_beds) else False,
            "desc_len": me.desc_len,
            "delta_k": delta(k, me.full_baths),
        }
    )
feat = pool.merge(pd.DataFrame(rows), on="listing_id")
feat["bld_units_in_pool"] = feat.groupby("building").listing_id.transform("size")
feat.to_parquet(OUT + "features.parquet")
print(len(feat))
print(
    feat[
        [
            "unit_near_1plus",
            "unit_near_all_1plus",
            "unit_near_1plus_rooms",
            "unit_typed_studio",
            "line_1plus_rooms",
            "says_studio",
            "names_beds",
        ]
    ]
    .astype(float)
    .gt(0)
    .mean()
)
print({k: round(v, 4) for k, v in b.items() if k.startswith("bed")})
