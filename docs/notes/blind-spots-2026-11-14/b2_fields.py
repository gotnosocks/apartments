"""S16, part 2: gather the coded fields and the latest description of each drawn ad, shuffle
the 400 together and write the readers' batches.

A reader sees, for each ad:

1. the building's address key, the unit label from the ad's URL, the neighborhood and the day
   the ask was priced;
2. the counts L1 reads: bedrooms, full and half baths;
3. the size: the ad's stated square feet, and the size L1's size column uses with its source
   (`unit_features`), when either is known;
4. the floor from L1's floor snapshot (`unit-floor`), with its top-floor, penthouse, garden and
   lower-level label flags, and the pipeline's floor fields;
5. building fields: elevator, doorman, the building's floor count, year built and altered
   (`building-age`), and residential units, floors and building class from PLUTO's latest
   release of the building's lot;
6. the ad's codes as L1 reads them (`listing-codes`): unit features, private outdoor types,
   views, fireplaces, building amenities, shared outdoor, parking and storage, the room count
   and photo, floor-plan and video counts, and the source type;
7. the pipeline's laundry, cooling, pets, exposures, months free and lease term;
8. the flags of L1's dataset: furnished, short-term, shared space, income-restricted and rent
   stabilized;
9. the description of the listing's latest record in the records file S7 used, with every
   dollar figure and every figure written as a monthly amount replaced by `[amount]`, so the
   text doesn't give away the ask, and cut at 3,500 characters.

The reader never sees the ask, L1's prediction, the residual or the group. The shuffle uses seed
20261114, and `read_id` runs 0 to 399 in shuffled order. The key from `read_id` to the draw is
in `key.parquet`, which the readers aren't pointed to."""

import json
import os
import re

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = "/data1/apartments/tmp/blind-spots-2026-11-14/"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
)
PIPE = "/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet"
UF = "/data1/apartments/external/unit-features/20261021-16cea7c/unit_features.parquet"
FLOOR = "/data1/apartments/external/unit-floor/20261021-d84914c0/floor.parquet"
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
AGE = "/data1/apartments/external/building-age/20261021-3a64aa22/age.parquet"
REG = "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
PLUTO = "/data1/apartments/external/pluto/20261017-2c61ff1-all-lots4/pluto.parquet"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"
BATCH, SEED, MAXLEN = 20, 20261114, 3500

draw = pd.read_parquet(OUT + "draw.parquet")
ids = draw.listing_id.astype(str).tolist()


def pick(path, cols):
    """The rows of `path` for the drawn listings, read a row group at a time."""
    f = pq.ParquetFile(path)
    want = pa.array(ids, type=f.schema_arrow.field("listing_id").type)
    parts = []
    for g in range(f.num_row_groups):
        t = f.read_row_group(g, columns=["listing_id", *cols])
        t = t.filter(pc.is_in(t["listing_id"], value_set=want))
        parts.append(t.to_pandas())
    d = pd.concat(parts)
    d["listing_id"] = d.listing_id.astype(str)
    return d


rows = pick(
    DATA,
    [
        "building",
        "unit_id",
        "neighbourhood",
        "price_at",
        "bedrooms",
        "full_baths",
        "half_baths",
        "furnished",
        "short_term",
        "shared_space",
        "income_restricted",
        "rent_stabilized",
        "description_known",
    ],
).drop_duplicates("listing_id")
pipe = pick(
    PIPE,
    [
        "page",
        "square_feet",
        "listed_floor",
        "physical_floor",
        "building_floor_count",
        "floors_above_ground",
        "elevator",
        "laundry_type",
        "doorman_type",
        "hvac_type",
        "pet_policy",
        "view_exposures",
        "window_exposures",
        "months_free",
        "lease_term",
    ],
).drop_duplicates("listing_id")
uf = pick(UF, ["sqft", "size_source", "laundry", "dishwasher"]).drop_duplicates(
    "listing_id"
)
fl = pick(FLOOR, ["floor", "garden", "lower", "penthouse", "top"]).drop_duplicates(
    "listing_id"
)
code_cols = [
    c
    for c in pq.read_schema(CODES).names
    if c not in ("listing_id", "collected_at", "states_amenities", "states_features")
]
codes = pick(CODES, code_cols).drop_duplicates("listing_id")
recs = pick(RECS, ["last_collected_at", "description", "display_unit"])
recs = recs.sort_values("last_collected_at").drop_duplicates("listing_id", keep="last")

age = pd.read_parquet(AGE, columns=["building", "year_built", "alter1", "alter2"])
reg = pd.read_parquet(REG, columns=["building", "bbl"]).drop_duplicates("building")
pl = pd.read_parquet(
    PLUTO, columns=["bbl", "version", "unitsres", "numfloors", "bldgclass", "landmark"]
)
pl = pl.sort_values("version").drop_duplicates("bbl", keep="last")
bld = reg.merge(pl, on="bbl", how="left").merge(age, on="building", how="outer")

d = draw[["listing_id"]].merge(rows, on="listing_id", how="left")
for t in (pipe, uf, fl, codes, recs):
    d = d.merge(t, on="listing_id", how="left")
d = d.merge(bld.drop_duplicates("building"), on="building", how="left")
assert len(d) == len(draw) == 400

MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?\b|\bUSD\s?\d[\d,]*"
    r"|\b\d{1,2},?\d{3}(?:\.\d{2})?(?=\s*(?:/|per|a)\s*(?:mo\b|month))",
)


def mask(text):
    if not isinstance(text, str):
        return ""
    return MONEY.sub("[amount]", text)[:MAXLEN]


def num(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return None
    f = float(v)
    return int(f) if f.is_integer() else round(f, 2)


def label(page):
    lab = re.search(r"/([^/?#]+)/?$", str(page or ""))
    lab = (lab.group(1) if lab else "").upper()
    return re.sub(r"[^0-9A-Z]", "", re.sub(r"^(APT|UNIT|NO)[-_.]?", "", lab))


def on(r, cols, prefix):
    return sorted(c[len(prefix) :] for c in cols if c.startswith(prefix) and r[c] == 1)


def present(r):
    """The coded fields of one ad, as the reader sees them."""
    expo = {}
    for k in ("view_exposures", "window_exposures"):
        try:
            expo[k] = sorted(
                a for a, v in json.loads(r[k] or "{}").items() if v in (True, 1)
            )
        except (TypeError, ValueError):
            expo[k] = []
    f = {
        "bedrooms": num(r.bedrooms),
        "full_baths": num(r.full_baths),
        "half_baths": num(r.half_baths),
        "stated_sqft": num(r.square_feet),
        "size_used_sqft": num(r.sqft),
        "size_source": r.size_source if isinstance(r.size_source, str) else None,
        "floor": num(r.floor),
        "top_floor": bool(r.top == 1),
        "label_penthouse": bool(r.penthouse == 1),
        "label_garden": bool(r.garden == 1),
        "label_lower_level": bool(r.lower == 1),
        "listed_floor": num(r.listed_floor),
        "building_floors": num(r.building_floor_count)
        if num(r.building_floor_count) is not None
        else num(r.numfloors),
        "elevator": None if pd.isna(r.elevator) else ("yes" if r.elevator else "no"),
        "doorman": r.doorman_type if pd.notna(r.doorman_type) else None,
        "year_built": num(r.year_built),
        "year_altered": num(r.alter1),
        "residential_units_pluto": num(r.unitsres),
        "building_class_pluto": r.bldgclass if isinstance(r.bldgclass, str) else None,
        "landmark": bool(isinstance(r.landmark, str) and r.landmark.strip() != ""),
        "unit_features": on(r, code_cols, "feat:"),
        "private_outdoor": on(r, code_cols, "private_outdoor:"),
        "views": on(r, code_cols, "views:"),
        "fireplace": on(r, code_cols, "fireplace:"),
        "building_amenities": on(r, code_cols, "amen:"),
        "shared_outdoor": on(r, code_cols, "shared_outdoor:"),
        "parking": on(r, code_cols, "parking:"),
        "storage": on(r, code_cols, "storage:"),
        "room_count": num(r.rooms),
        "photos": num(r.photos),
        "floor_plans": num(r.floorplans),
        "source_type": r.source_type if isinstance(r.source_type, str) else None,
        "laundry": r.laundry_type if pd.notna(r.laundry_type) else None,
        "dishwasher": num(r.dishwasher),
        "cooling": r.hvac_type if pd.notna(r.hvac_type) else None,
        "pets": r.pet_policy if pd.notna(r.pet_policy) else None,
        "view_exposures": expo["view_exposures"],
        "window_exposures": expo["window_exposures"],
        "months_free": num(r.months_free),
        "lease_term": r.lease_term if pd.notna(r.lease_term) else None,
        "flag_furnished": bool(r.furnished),
        "flag_short_term": bool(r.short_term),
        "flag_shared_space": bool(r.shared_space),
        "flag_income_restricted": bool(r.income_restricted),
        "flag_rent_stabilized": bool(r.rent_stabilized),
    }
    return {k: v for k, v in f.items() if not (v is None or v is False or v == [])}


rng = np.random.default_rng(SEED)
d = d.iloc[rng.permutation(len(d))].reset_index(drop=True)
d["read_id"] = np.arange(len(d))
d["desc"] = d.description.map(mask)
d[["read_id", "listing_id"]].to_parquet(OUT + "key.parquet")
rd = OUT + "read/"
os.makedirs(rd, exist_ok=True)
for b in range(0, len(d), BATCH):
    with open(rd + f"batch{b // BATCH:02d}.jsonl", "w") as fh:
        for _, r in d.iloc[b : b + BATCH].iterrows():
            fh.write(
                json.dumps(
                    {
                        "read_id": int(r.read_id),
                        "address": r.building,
                        "unit_label": label(r.page),
                        "neighborhood": r.neighbourhood,
                        "date": str(pd.Timestamp(r.price_at).date()),
                        "coded_fields": present(r),
                        "description": r.desc,
                    }
                )
                + "\n"
            )
d["has_text"] = d.desc.str.len() > 80
print(
    "ads",
    len(d),
    "with text over 80 chars",
    int(d.has_text.sum()),
    "masked figures",
    int(d.description.fillna("").map(lambda t: len(MONEY.findall(t))).sum()),
)
d[["read_id", "listing_id", "has_text"]].merge(
    draw[["listing_id", "group"]], on="listing_id"
).groupby("group").has_text.agg(["sum", "size"]).to_csv(OUT + "text_by_group.csv")
