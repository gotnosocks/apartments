"""The site's diagnostics folder: a drift fit's held-out misses beside the facts around them.

    python -m rentfrontier.drift_diagnostics publish LATEST_RUN --market MARKET_RUN \
        --ads ADS.parquet --registry REGISTRY.parquet --features EXTERNAL_DIR --out DIR

`publish` starts from the ads of `rentfrontier.drift_estimates`: the ads a fit on the latest
split held out, then the ads a fit on the market split held out, an ad in both taking the
market fit's row. For each of them it works out how far the ask sits from the model (`gap`,
`miss`, `pit`, `z`), how much the fit knew about the ad's unit and building (`unit_ads`,
`building_ads`, `basis`), the apartment's previous ad (`prev_*`), and a list of detector codes
(`flags`). It then joins the attributes listed in `FEATURES` from the pipeline's ads file and
from the snapshot folders under `--features`, so that a page can tabulate the misses against
each attribute.

`publish` writes these tables to the folder `--out`, and `meta.json` after them:

- `ads.parquet`: one row per held-out ad.
- `buildings.parquet`: one row per building of the latest fit, with the posterior mean and
  standard deviation of the building's level (see `levels`), the building's training and
  held-out ads, and the building-level attributes.
- `history.parquet`: every ad of the latest fit's dataset and the ads the market fit's
  dataset adds, sorted by building, unit and day.
- `meta.json`: the runs, their gates, the feature list, the files each attribute came from,
  the counts, and the sha256 of the three tables. A reader checks the hashes before showing
  the tables together.

Reading the attributes. Each entry of `meta.json["features"]` says whether the fit has a term
for the attribute (`in_model`) and whether the attribute is known only once the ad has run
for a while (`after`). A trend of the misses along an attribute with `in_model` false points
at a missing term. Along an attribute with `in_model` true it points at the form of the
existing term. An attribute with `after` true (days listed, price cuts) describes how the
market answered the ask, and a fit can't use it to price a new ad.

Both runs must be fits of one model that passed the convergence gate, as
`drift_estimates` requires. docs/model/diagnostics.md describes the columns.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.special import ndtri

from . import drift_deals, drift_estimates
from . import run as run_module
from .b0data import sha256

# The widest normal score an ad gets: a `pit` of 0 or 1 would otherwise be infinite.
Z_CAP = 6.0
# |miss| above this puts `extreme` on an ad.
EXTREME = 4.0
# The width of a normal distribution's central 80%, in standard deviations.
WIDTH80 = 2.5631
# An ask over this many times the apartment's previous ask, or under one over it, is a jump.
ASK_JUMP = 2.0
# `basis` reads `building` from this many training ads of the building.
BUILDING_BASIS = 5
# `building_side`: the fewest held-out ads of a building, the share of them on one side of
# the 80% range, and the `pit` bounds of that range.
SIDE_ADS, SIDE_SHARE, SIDE_PIT = 5, 0.8, (0.1, 0.9)
# The plausible range of the ask per square foot, in dollars a year (12 asks over the area),
# by bedrooms (3 stands for 3 or more). The bounds sit near the 0.5% and 99.5% points of the
# held-out ads with an area on 2026-11-10: studios 32 to 143, one bedroom 27 to 137, two 23
# to 152, three or more 20 to 167. About 1% of the ads with an area fall outside.
PPSF = {0: (30.0, 150.0), 1: (25.0, 140.0), 2: (22.0, 155.0), 3: (20.0, 170.0)}
# An attribute known for a smaller share of the ads than this, or a flag true for a smaller
# share, is left out of the tables and recorded under `meta.json["skipped"]`.
MIN_SHARE = 0.01
FLAGS = ("beds_conflict", "beds_jump", "ask_jump", "ppsf", "extreme", "building_side")
# The columns read from the pipeline's ads file. `floor` is worked out from two of them.
AD_COLUMNS = (
    "listing_id",
    "page",
    "square_feet",
    "label_floor",
    "advertised_floor",
    "months_free",
    "first_ask",
    "days_on_market",
    "lease_term",
    "hvac_type",
    "pet_policy",
)
CORE = (
    "listing_id",
    "source",
    "building",
    "address",
    "unit_id",
    "unit",
    "neighbourhood",
    "day",
    "status",
    "bedrooms",
    "full_baths",
    "half_baths",
    "ask",
    "model_median",
    *(f"model_{b}" for b in drift_estimates.BOUNDS),
    "gap",
    "miss",
    "pit",
    "z",
    "unit_ads",
    "building_ads",
    "basis",
    "prev_ask",
    "prev_day",
    "prev_bedrooms",
    "square_feet",
    "floor",
    "months_free",
    "first_ask",
    "days_on_market",
    "latitude",
    "longitude",
)
HISTORY = (
    "listing_id",
    "building",
    "unit_id",
    "unit",
    "day",
    "ask",
    "bedrooms",
    "full_baths",
    "heldout",
    "market",
)


@dataclass(frozen=True)
class Source:
    """A family of snapshot folders under the features root: the table inside a snapshot
    and the column its rows are keyed by (`listing_id`, `building` or `bbl`)."""

    family: str
    file: str
    key: str


# The pipeline's ads file is read once for the core columns and serves as a source too.
ADS = "ads"
SOURCES = {
    "codes": Source("listing-codes", "listing-codes.parquet", "listing_id"),
    "unit": Source("unit-features", "unit_features.parquet", "listing_id"),
    "unit-floor": Source("unit-floor", "floor.parquet", "listing_id"),
    "extras": Source("listing-extras", "listing-extras.parquet", "listing_id"),
    "lister": Source("lister", "lister.parquet", "listing_id"),
    "outcomes": Source("listing-outcomes", "listing-outcomes.parquet", "listing_id"),
    "attrs": Source("building-attrs", "attrs.parquet", "building"),
    "age": Source("building-age", "age.parquet", "building"),
    "gym": Source("building-gym", "gym.parquet", "building"),
    "transit": Source("building-transit", "transit.parquet", "building"),
    "parks": Source("building-parks", "parks.parquet", "building"),
    "park-front": Source("building-park-front", "park_front.parquet", "building"),
    "noise": Source("building-noise", "noise.parquet", "building"),
    "elevated": Source("building-elevated", "elevated.parquet", "building"),
    "frontage": Source("frontage", "frontage.parquet", "building"),
    "truck": Source("unit-features", "truck.parquet", "building"),
    "pluto": Source("pluto", "pluto.parquet", "bbl"),
}


@dataclass(frozen=True)
class Feature:
    """An attribute joined to the tables: the column `column` of the source `source`,
    written as `name` with the plain label `label`.

    `kind` is `number`, `category` or `flag`. `level` is `ad`, `unit` or `building`, and
    the building-level attributes also go to `buildings.parquet`, so their sources are
    keyed by building or by lot. `in_model` says the fit has a term for the attribute.
    `after` says the attribute is known only after the ad has run. With `present`, a flag
    is true where the source's column holds any value (a landmark's name) and false where
    the source has the row with the column empty."""

    name: str
    label: str
    kind: str
    level: str
    source: str
    column: str
    in_model: bool = False
    after: bool = False
    present: bool = False


def _f(name, label, kind, level, source, column=None, **kw) -> Feature:
    return Feature(name, label, kind, level, source, column or name, **kw)


# Adding an attribute is one line here. The first four are core columns of `ads.parquet`.
FEATURES = (
    _f("square_feet", "Square feet in the ad", "number", "unit", ADS, in_model=True),
    _f("floor", "Floor", "number", "unit", ADS, in_model=True),
    _f("months_free", "Months free", "number", "ad", ADS, in_model=True),
    _f("days_on_market", "Days on the market", "number", "ad", ADS, after=True),
    _f("lease_term", "Lease term in months", "number", "ad", ADS, in_model=True),
    _f("hvac_type", "Heating and cooling", "category", "unit", ADS),
    _f("pet_policy", "Pet policy", "category", "ad", ADS, in_model=True),
    _f("photos", "Photos in the ad", "number", "ad", "codes", in_model=True),
    _f("floorplans", "Floor plans in the ad", "number", "ad", "codes", in_model=True),
    _f("source_type", "Ad entered by", "category", "ad", "codes", in_model=True),
    _f("central_ac", "Central air", "flag", "unit", "codes", "feat:CENTRAL_AC", in_model=True),
    _f("dishwasher", "Dishwasher", "flag", "unit", "codes", "feat:DISHWASHER", in_model=True),
    _f("fireplace", "Fireplace", "flag", "unit", "codes", "feat:FIREPLACE", in_model=True),
    _f("hardwood", "Hardwood floors", "flag", "unit", "codes", "feat:HARDWOOD_FLOORS", in_model=True),
    _f("private_outdoor", "Private outdoor space", "flag", "unit", "codes", "feat:PRIVATE_OUTDOOR_SPACE", in_model=True),
    _f("view", "A view", "flag", "unit", "codes", "feat:VIEW", in_model=True),
    _f("washer_dryer", "Washer and dryer in the unit", "flag", "unit", "codes", "feat:WASHER_DRYER", in_model=True),
    _f("loft", "Loft", "flag", "unit", "codes", "feat:LOFT", in_model=True),
    _f("furnished", "Furnished", "flag", "ad", "codes", "feat:FURNISHED"),
    _f("view_city", "City view", "flag", "unit", "codes", "views:CITY", in_model=True),
    _f("view_park", "Park view", "flag", "unit", "codes", "views:PARK", in_model=True),
    _f("view_skyline", "Skyline view", "flag", "unit", "codes", "views:SKYLINE", in_model=True),
    _f("view_water", "Water view", "flag", "unit", "codes", "views:WATER", in_model=True),
    _f("balcony", "Balcony", "flag", "unit", "codes", "private_outdoor:BALCONY", in_model=True),
    _f("ad_pool", "Ad states a pool", "flag", "ad", "codes", "amen:POOL", in_model=True),
    _f("ad_parking", "Ad states parking", "flag", "ad", "codes", "amen:PARKING", in_model=True),
    _f("ad_roof_deck", "Ad states a shared roof deck", "flag", "ad", "codes", "shared_outdoor:ROOF_DECK", in_model=True),
    _f("ad_concierge", "Ad states a concierge", "flag", "ad", "codes", "amen:CONCIERGE", in_model=True),
    _f("model_sqft", "Square feet the model reads", "number", "unit", "unit", "sqft", in_model=True),
    _f("size_source", "Where the model's size comes from", "category", "unit", "unit", in_model=True),
    _f("laundry", "Laundry", "category", "unit", "unit", in_model=True),
    _f("top_floor", "Top floor", "flag", "unit", "unit-floor", "top", in_model=True),
    _f("penthouse", "Penthouse", "flag", "unit", "unit-floor", in_model=True),
    _f("broker_group", "Brokerage", "category", "ad", "extras"),
    _f("lister_kind", "Kind of lister", "category", "ad", "lister", "kind"),
    _f("n_cuts", "Price cuts", "number", "ad", "outcomes", after=True),
    _f("n_raises", "Price raises", "number", "ad", "outcomes", after=True),
    _f("days_listed", "Days listed, from the ad's price history", "number", "ad", "outcomes", after=True),
    _f("building_floors", "Floors in the building", "number", "building", "attrs", "floors", in_model=True),
    _f("building_elevator", "Elevator", "category", "building", "attrs", "elevator", in_model=True),
    _f("building_doorman", "Doorman", "category", "building", "attrs", "doorman", in_model=True),
    _f("tenure", "Rental, condo or co-op", "category", "building", "attrs", in_model=True),
    _f("year_built", "Year built", "number", "building", "attrs", in_model=True),
    _f("year_altered", "Year of the first recorded alteration", "number", "building", "age", "alter1", in_model=True),
    _f("retail", "Retail in the building", "flag", "building", "age", in_model=True),
    _f("gym", "Gym", "flag", "building", "gym", in_model=True),
    _f("station_km", "Kilometres to the nearest subway station", "number", "building", "transit"),
    _f("routes_800m", "Subway routes within 800 m", "number", "building", "transit"),
    _f("park_km", "Kilometres to the nearest park", "number", "building", "parks"),
    _f("big_park_km", "Kilometres to the nearest large park", "number", "building", "parks"),
    _f("water_km", "Kilometres to the water", "number", "building", "parks"),
    _f("park_edge_m", "Metres to a park's edge", "number", "building", "park-front"),
    _f("noise_per_year", "Noise complaints nearby per year", "number", "building", "noise"),
    _f("elevated_m", "Metres to an elevated train line", "number", "building", "elevated"),
    _f("front_width_ft", "Width of the street in front, in feet", "number", "building", "frontage"),
    _f("corner", "Corner building", "flag", "building", "frontage", in_model=True),
    _f("truck_route", "On a through truck route", "flag", "building", "truck", "truck_through", in_model=True),
    _f("lot_units", "Homes on the lot", "number", "building", "pluto", "unitsres", in_model=True),
    _f("lot_building_area", "Building area on the lot, in square feet", "number", "building", "pluto", "bldgarea", in_model=True),
    _f("built_far", "Built floor area ratio", "number", "building", "pluto", "builtfar", in_model=True),
    _f("building_class", "City building class", "category", "building", "pluto", "bldgclass", in_model=True),
    _f("landmark", "Landmark", "flag", "building", "pluto", in_model=True, present=True),
    _f("historic_district", "In a historic district", "flag", "building", "pluto", "histdist", present=True),
)  # fmt: skip


def newest(root: Path, family: str) -> Path | None:
    """The newest snapshot folder of `family` under `root`: the latest by the date its
    name starts with, and among those of one date the one written last."""
    folder = root / family
    if not folder.is_dir():
        return None
    found = [p for p in folder.iterdir() if p.is_dir()]
    return max(found, key=lambda p: (p.name[:8], p.stat().st_mtime), default=None)


def source_files(root: Path | None, given: dict | None = None) -> dict:
    """Each source's table: the path `given` names for it, or the table in the newest
    snapshot folder of its family under `root`. None where there is no such file."""
    out = {}
    for name, s in SOURCES.items():
        path = (given or {}).get(name)
        if path is None and root is not None:
            folder = newest(root, s.family)
            path = None if folder is None else folder / s.file
        out[name] = Path(path) if path is not None and Path(path).exists() else None
    return out


def _typed(values: pd.Series, found: np.ndarray, f: Feature) -> pd.Series:
    """`values` (the source's column at each row, missing where the source lacks the row)
    as the feature's kind. `found` marks the rows the source has."""
    if f.kind == "number":
        return pd.to_numeric(values, errors="coerce").astype(float)
    if f.kind == "category":
        text = values.astype(object).where(values.notna(), None)
        return text.map(lambda v: (str(v).strip() or None) if v is not None else None)
    if f.present:
        stated = values.notna() & (values.astype(str).str.strip() != "")
        return pd.Series(pd.array(stated, dtype="boolean")).where(found, pd.NA)
    known = values.notna().to_numpy()
    on = pd.to_numeric(values, errors="coerce").fillna(0).to_numpy() > 0
    return pd.Series(pd.array(on, dtype="boolean")).where(known, pd.NA)


def attach(
    features, keys: pd.DataFrame, files: dict, tables: dict | None = None
) -> tuple[pd.DataFrame, list[dict]]:
    """The columns of `features` for the rows of `keys`, a frame holding the key columns
    (`listing_id`, `building`, `bbl`) the sources are joined by. `files` is
    `source_files`' mapping, and `tables` holds sources already in memory, indexed by
    their key. A source with no file, or without one of its columns, is passed over: the
    second value lists each attribute left out and why."""
    tables = tables or {}
    out, skipped = {}, []
    for name in dict.fromkeys(f.source for f in features):
        wanted = [f for f in features if f.source == name]
        key = "listing_id" if name == ADS else SOURCES[name].key
        if name in tables:
            table = tables[name]
        elif files.get(name) is None:
            skipped += [{"name": f.name, "why": f"no {name} table"} for f in wanted]
            continue
        else:
            have = set(pq.read_schema(files[name]).names)
            lost = [f for f in wanted if f.column not in have or key not in have]
            skipped += [
                {"name": f.name, "why": f"{files[name].name} has no column {f.column}"}
                for f in lost
            ]
            wanted = [f for f in wanted if f not in lost]
            if not wanted:
                continue
            asked = sorted(set(keys[key].dropna().astype(str)))
            if pa.types.is_integer(pq.read_schema(files[name]).field(key).type):
                asked = [int(v) for v in asked if v.lstrip("-").isdigit()]
            table = pd.read_parquet(
                files[name],
                columns=[key, *dict.fromkeys(f.column for f in wanted)],
                filters=[(key, "in", asked)],
            )
            table = table.assign(**{key: table[key].astype(str)})
            table = table.drop_duplicates(key).set_index(key)
        at = keys[key].astype(str).astype(object).where(keys[key].notna(), None)
        found = at.isin(table.index).to_numpy()
        joined = table.reindex(at.to_numpy())
        for f in wanted:
            column = joined[f.column].reset_index(drop=True)
            out[f.name] = _typed(column, found, f).array
    return pd.DataFrame(out, index=keys.index), skipped


def _fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }


def _rows(run_dir: Path) -> tuple[pd.DataFrame, np.ndarray]:
    """The columns of the run's dataset rows read here, and the run's held-out mask."""
    path = drift_deals._dataset(run_dir) / "rows.parquet"
    have = pq.read_schema(path).names
    want = (
        "listing_id",
        "building",
        "unit_id",
        "neighbourhood",
        "bedrooms",
        "full_baths",
        "latest_ask",
        "latest_day",
        "price_at",
    )
    frame = pd.read_parquet(path, columns=[c for c in want if c in have])
    return frame, np.load(run_dir / "posterior.npz")["heldout"]


def apartment(frame: pd.DataFrame) -> pd.Series:
    """Each row's apartment: its building and unit_id, with the pieces "~1", "~2" the
    dataset cuts a unit into where its bedroom count changes put back together
    (`drift_deals.PIECE`). Missing for a row with no unit_id."""
    unit = frame.unit_id.astype(str).str.replace(drift_deals.PIECE, "", regex=True)
    return (frame.building.astype(str) + "|" + unit).where(frame.unit_id.notna())


def previous(frame: pd.DataFrame, key: pd.Series) -> pd.DataFrame:
    """For each row, the ask, day and bedrooms of the ad before it in its apartment's
    history, ordered by day. Missing for an apartment's first ad."""
    order = ["latest_day"] + (["price_at"] if "price_at" in frame else [])
    known = frame[key.notna().to_numpy()].assign(_key=key)
    known = known.sort_values(["_key", *order], kind="stable")
    before = known.groupby("_key", sort=False)[
        ["latest_ask", "latest_day", "bedrooms"]
    ].shift(1)
    return before.reindex(frame.index)


def run_ads(
    run_dir: Path, source: str, registry: pd.DataFrame | None
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """`drift_estimates.table` for the run, with the columns worked out from the run's
    scores and its dataset rows. Also the rows and the held-out mask."""
    out, res = drift_estimates.table(run_dir, source, registry)
    frame, held = _rows(run_dir)
    if (frame.listing_id[held].astype(str).to_numpy() != out.listing_id).any():
        raise SystemExit(
            f"{run_dir.name}'s rows are not the ones its table was built on"
        )
    pit = np.asarray(res["cdf"], float)
    out["pit"] = pit
    with np.errstate(divide="ignore"):
        out["z"] = np.clip(ndtri(pit), -Z_CAP, Z_CAP)
    out["gap"] = np.log(out.ask.to_numpy(float)) - np.asarray(res["pred"], float)
    q = np.asarray(res["q"], float)
    lo, hi = (q[:, drift_estimates.BOUNDS[b]] for b in ("lo80", "hi80"))
    out["miss"] = out.gap.to_numpy() / ((hi - lo) / WIDTH80)
    trained = frame.building[~held].astype(str).value_counts()
    out["building_ads"] = out.building.map(trained).fillna(0).astype(int).to_numpy()
    out["basis"] = np.where(
        out.unit_ads > 0,
        "unit",
        np.where(out.building_ads >= BUILDING_BASIS, "building", "area"),
    )
    key = apartment(frame)
    before = previous(frame, key)[held]
    out["prev_ask"] = before.latest_ask.to_numpy(float)
    day = pd.to_datetime(before.latest_day).dt.strftime("%Y-%m-%d")
    out["prev_day"] = day.where(day.notna(), None).to_numpy(object)
    out["prev_bedrooms"] = before.bedrooms.to_numpy(float)
    counts = frame.bedrooms.groupby(key).nunique()
    out["_beds_conflict"] = (key[held].map(counts).fillna(0) > 1).to_numpy()
    return out, frame, held


def _ads_file(ads: Path) -> pd.DataFrame:
    """The ads file's columns `AD_COLUMNS` indexed by listing, with `floor`: the floor
    read from the unit's label, or else the floor the ad states."""
    have = set(pq.read_schema(ads).names)
    a = pd.read_parquet(ads, columns=[c for c in AD_COLUMNS if c in have])
    a = a.assign(listing_id=a.listing_id.astype(str)).drop_duplicates("listing_id")
    a = a.set_index("listing_id")
    for c in AD_COLUMNS[1:]:
        if c not in a:
            a[c] = None if c in ("page", "hvac_type", "pet_policy") else np.nan
    a["floor"] = a.label_floor.astype(float).fillna(a.advertised_floor.astype(float))
    return a


def ppsf_outside(ask, square_feet, bedrooms) -> np.ndarray:
    """True where the ask per square foot a year is outside `PPSF` for the bedrooms.
    False without an area."""
    ask, area = np.asarray(ask, float), np.asarray(square_feet, float)
    band = np.clip(np.nan_to_num(np.asarray(bedrooms, float)), 0, 3).astype(int)
    lo = np.array([PPSF[b][0] for b in range(4)])[band]
    hi = np.array([PPSF[b][1] for b in range(4)])[band]
    with np.errstate(divide="ignore", invalid="ignore"):
        rate = 12 * ask / area
    return np.isfinite(rate) & ((rate < lo) | (rate > hi))


def detect(t: pd.DataFrame) -> list[list[str]]:
    """Each ad's detector codes, in the order of `FLAGS`:

    - `beds_conflict`: the ads of the apartment carry more than one bedroom count;
    - `beds_jump`: the bedroom count differs from the apartment's previous ad;
    - `ask_jump`: the ask is over `ASK_JUMP` times the previous ask, or under one over it;
    - `ppsf`: the ask per square foot is outside `PPSF`;
    - `extreme`: |miss| is above `EXTREME`;
    - `building_side`: the building has `SIDE_ADS` held-out ads or more, `SIDE_SHARE` of
      them or more sit under the model's 80% range, or that share sit over it, and this ad
      is one of those."""
    ratio = t.ask.to_numpy(float) / t.prev_ask.to_numpy(float)
    under, over = t.pit < SIDE_PIT[0], t.pit > SIDE_PIT[1]
    by = t.building
    many = by.map(by.value_counts()).to_numpy() >= SIDE_ADS
    side = np.zeros(len(t), bool)
    for out in (under, over):
        share = out.groupby(by).transform("mean").to_numpy()
        side |= many & (share >= SIDE_SHARE) & out.to_numpy()
    marks = {
        "beds_conflict": t["_beds_conflict"].to_numpy(bool),
        "beds_jump": (
            t.prev_bedrooms.notna() & (t.prev_bedrooms != t.bedrooms)
        ).to_numpy(),
        "ask_jump": np.isfinite(ratio) & ((ratio > ASK_JUMP) | (ratio < 1 / ASK_JUMP)),
        "ppsf": ppsf_outside(t.ask, t.square_feet, t.bedrooms),
        "extreme": (t.miss.abs() > EXTREME).to_numpy(),
        "building_side": side,
    }
    stacked = np.column_stack([marks[c] for c in FLAGS])
    return [[c for c, on in zip(FLAGS, row) if on] for row in stacked]


def levels(run_dir: Path, record: dict, buildings) -> tuple[pd.DataFrame | None, str]:
    """Each building's zone and the posterior mean and standard deviation of its level,
    from the run's kept draws `bld`. The second value says why there are none, when the
    order of the fit's buildings can't be rebuilt.

    The fit gives a building a level `lev`, constant over time, and its zone a smooth
    surface F over the map. It keeps `bld = lev - F` at the building's point: how far the
    building's log rents sit from the surface of its zone at that point, after the terms
    for the building's attributes, the units' own levels and the building's quarterly
    path. The prior of `bld` is a Student-t with the zone's spread `bld_sd`. A level of
    0.10 reads as asks about 10% over what the location and the attributes give.

    The draws carry no building names. `whitened_zones.design` numbers the buildings zone
    by zone, and inside a zone in the order they first appear in the dataset's rows, among
    the buildings its two registries place. The numbering is rebuilt here from `buildings`
    (the rows' buildings, in the rows' order) and the registries the run's record names,
    and it is used only if it gives each zone the count of buildings the record has."""
    z = np.load(run_dir / "posterior.npz")
    paths = [record.get("registry"), record.get("nj_registry")]
    if "kept/bld" not in z or not all(p and Path(p).exists() for p in paths):
        return None, "the run keeps no building levels, or its registries are not here"
    from . import whitened_zones

    registry = pd.read_parquet(
        paths[0], columns=["building", "bbl", "latitude", "longitude"]
    )
    nj = pd.read_parquet(paths[1], columns=["building", "latitude", "longitude"])
    frame = pd.DataFrame({"building": np.asarray(buildings)})
    sites = whitened_zones.sites_of(frame, registry, nj)
    parts, surfaces = [], []
    for k, name in enumerate(whitened_zones.ZONES):
        on = sites.index[(sites.zone == k).to_numpy()]
        if len(on):
            surfaces.append({"name": name, "sites": len(on)})
            parts.append(pd.DataFrame({"building": on, "zone": name}))
    recorded = [
        {"name": s["name"], "sites": s["sites"]} for s in record.get("surfaces", [])
    ]
    draws = z["kept/bld"]
    if surfaces != recorded or sum(s["sites"] for s in surfaces) != draws.shape[-1]:
        return None, "the rebuilt order of the buildings does not match the run's zones"
    out = pd.concat(parts, ignore_index=True)
    draws = draws.reshape(-1, draws.shape[-1]).astype(float)
    out["level"], out["level_sd"] = draws.mean(axis=0), draws.std(axis=0)
    return out.set_index("building"), ""


def _label(pages: pd.Series) -> list[str]:
    return [drift_deals.unit_label(p) for p in pages]


def history(
    frame: pd.DataFrame,
    held: np.ndarray,
    ads: pd.DataFrame | None,
    later: tuple[pd.DataFrame, np.ndarray] | None = None,
) -> pd.DataFrame:
    """One row per ad, sorted by building, unit and day: the latest run's dataset rows
    `frame` with its held-out mask `held`, then the rows of `later` (the market run's rows
    and mask) for the ads the market fit held out and for the ads `frame` lacks. An ad
    the market fit held out takes the market dataset's row, the row its estimate was made
    for. `heldout` says the fit behind the row held the ad out, and `market` says the ad
    was on the market on the scoring day."""
    parts = [frame.assign(heldout=np.asarray(held, bool), market=False)]
    if later is not None:
        rows, on = later
        rows = rows.assign(heldout=np.asarray(on, bool), market=np.asarray(on, bool))
        open_ids = set(rows.listing_id[rows.market].astype(str))
        known = set(frame.listing_id.astype(str))
        new = rows.market | ~rows.listing_id.astype(str).isin(known)
        parts = [parts[0][~frame.listing_id.astype(str).isin(open_ids)], rows[new]]
    frame = pd.concat(parts, ignore_index=True)
    ids = frame.listing_id.astype(str)
    out = pd.DataFrame(
        {
            "listing_id": ids.to_numpy(),
            "building": frame.building.astype(str).to_numpy(),
            "unit_id": frame.unit_id.where(frame.unit_id.notna(), "").astype(str),
            "unit": "" if ads is None else _label(ads.page.reindex(ids)),
            "day": pd.to_datetime(frame.latest_day).dt.strftime("%Y-%m-%d"),
            "ask": frame.latest_ask.to_numpy(float),
            "bedrooms": frame.bedrooms.to_numpy(float),
            "full_baths": frame.full_baths.to_numpy(float),
            "heldout": frame.heldout.to_numpy(bool),
            "market": frame.market.to_numpy(bool),
        }
    )
    out = out.sort_values(["building", "unit_id", "day", "listing_id"], kind="stable")
    return out[list(HISTORY)].reset_index(drop=True)


# Plain words for the fit's coefficient names, tried in order: the first pattern found in
# a name gives its term.
TERMS = (
    (r"^umean:", "Each unit's average of the ad-level attributes, beside the ad's own value"),
    (r"^alpha$", ""),
    (r"^bed>=", "Bedrooms"),
    (r"^bed=\d+:full", "Full baths, by bedrooms"),
    (r"^half", "Half baths"),
    (r"^(sin|cos)\d", "Season of the year"),
    (r"shared_space", "A room in a shared apartment"),
    (r"income_restricted", "Income-restricted units"),
    (r"rent_stabilized", "Rent stabilization"),
    (r"bld:(log_height|height_)", "Building height"),
    (r"bld:elevator", "Elevator"),
    (r"bld:condo", "Condo building"),
    (r"bld:doorman", "Doorman (full-time, part-time, virtual)"),
    (r"size", "Size relative to homes with the same bedrooms"),
    (r"laundry", "Laundry in the unit or in the building"),
    (r"dishwasher", "Dishwasher"),
    (r"truck", "On a through truck route"),
    (r"bld:gym", "Gym"),
    (r"bld:built_", "Year built, in bands"),
    (r"altered", "Altered since 2000"),
    (r"retail", "Retail in the building"),
    (r"unit:(elev|walkup)_(f\d+|floor_unknown)", "Floor, apart for elevator and walk-up buildings"),
    (r"_top$", "Top floor"),
    (r"penthouse", "Penthouse"),
    (r"unit:(garden|lower)", "Garden and lower-level units"),
    (r"central_ac", "Central air"),
    (r"fireplace", "Fireplace, by type"),
    (r"hardwood", "Hardwood floors"),
    (r"loft", "Loft"),
    (r"private_outdoor", "Private outdoor space, by type"),
    (r"view", "Views, by type"),
    (r"(features|amenities)_unstated", "Ads stating no features or amenities"),
    (r"rooms", "Rooms beyond the bedrooms"),
    (r"photos", "Photos in the ad"),
    (r"floorplan|video|tour3d", "Floor plan, video and 3D tour in the ad"),
    (r"ad:source_", "Ad entered by a feed or by the owner"),
    (r"months_free", "Months free"),
    (r"lease_", "Long and short leases"),
    (r"exposure", "Exposures"),
    (r"pets", "Pet policy"),
    (r"bld:(amen|parking|shared_outdoor|storage)_", "Building amenities stated in ads"),
    (r"units", "Homes in the building"),
    (r"lot_", "Lot frontage"),
    (r"corner", "Corner building"),
    (r"far_used", "Built floor area ratio"),
    (r"landmark", "Landmark"),
    (r"multi_building", "More than one building on the lot"),
    (r"bld:class_", "City building class"),
    (r"area_per_unit", "Building area per home"),
)  # fmt: skip
# Plain words for the parts of the fit outside the coefficients, by the kept draws
# marking each part.
PARTS = (
    ("kept/L", "The city's rent level over time"),
    ("kept/gp_w", "A smooth surface over the map in each zone"),
    ("kept/bld", "A level for each building"),
    ("kept/building_ar_sd", "A quarterly path for each building"),
    ("kept/unit_sd", "A level for each unit"),
    ("kept/drift_sd", "A drift over time for each unit"),
)


def model_terms(run_dir: Path) -> list[str]:
    """The fit's terms in plain words: its coefficient names (`names` in the run's
    `posterior.npz`) read through `TERMS`, then the parts in `PARTS` the run kept draws
    of. A name `TERMS` has no pattern for is listed as it is."""
    z = np.load(run_dir / "posterior.npz")
    names = [str(n) for n in z["names"]] if "names" in z else []
    out = []
    for name in names:
        out.append(next((t for p, t in TERMS if re.search(p, name)), name))
    out += [text for key, text in PARTS if key in z]
    return [t for t in dict.fromkeys(out) if t]


def building_table(
    frame: pd.DataFrame,
    held: np.ndarray,
    ads: pd.DataFrame,
    level: pd.DataFrame | None,
    registry: pd.DataFrame | None,
) -> pd.DataFrame:
    """One row per building of the latest fit's rows `frame`: where it is, its level,
    its training ads, and its held-out ads in the table `ads` with their mean gap, miss and z."""
    name = frame.building.astype(str)
    out = pd.DataFrame({"building": name.unique()})
    hood = frame.neighbourhood.where(frame.neighbourhood.notna(), "").astype(str)
    pairs = pd.DataFrame({"building": name.to_numpy(), "hood": hood.to_numpy()})
    pairs = pairs.value_counts().reset_index().drop_duplicates("building")
    common = pairs.set_index("building").hood
    out["neighbourhood"] = out.building.map(common).to_numpy()
    if registry is None:
        out["address"], out["latitude"], out["longitude"] = "", np.nan, np.nan
    else:
        reg = registry.reindex(out.building)
        out["address"] = [drift_deals.title_address(v) for v in reg.label]
        out["latitude"] = reg.latitude.to_numpy(float).round(5)
        out["longitude"] = reg.longitude.to_numpy(float).round(5)
    if level is not None:
        at = level.reindex(out.building)
        out["zone"] = at.zone.to_numpy(object)
        out["level"], out["level_sd"] = at.level.to_numpy(), at.level_sd.to_numpy()
    trained = name[~held].value_counts()
    out["train_ads"] = out.building.map(trained).fillna(0).astype(int).to_numpy()
    by = ads.groupby("building")
    out["heldout_ads"] = out.building.map(by.size()).fillna(0).astype(int).to_numpy()
    out["heldout_gap"] = out.building.map(by.gap.mean()).to_numpy(float)
    out["heldout_miss"] = out.building.map(by.miss.mean()).to_numpy(float)
    out["heldout_z"] = out.building.map(by.z.mean()).to_numpy(float)
    first = ["building", "address", "latitude", "longitude", "neighbourhood"]
    return out[first + [c for c in out if c not in first]]


def coverage(pit) -> dict:
    """The share of `pit` inside the central 50%, 80% and 95% of the predictive
    distribution."""
    pit = np.asarray(pit, float)
    return {
        str(c): float((np.abs(pit - 0.5) <= c / 200).mean()) if len(pit) else None
        for c in (50, 80, 95)
    }


def diagnostics(
    latest: Path,
    market: Path | None = None,
    ads: Path | None = None,
    registry: Path | None = None,
    features: Path | None = None,
    sources: dict | None = None,
) -> tuple[dict, dict]:
    """The tables of `publish` by name, and its meta, written nowhere.

    `ads` is the pipeline's ads file. Without it the market run's dataset names one, and
    with no market run the build of the latest run's dataset does. `features` is the root
    of the snapshot folders, and `sources` maps a name of `SOURCES` to a table to read
    instead of the newest snapshot's."""
    record = drift_estimates._result(latest, "latest")
    model = record["model"]["name"]
    reg = drift_estimates._registry(registry)
    meta = {
        "model": model,
        "runs": {"latest": latest.name},
        "datasets": {"latest": drift_estimates._provenance(record)},
        "gate": {"latest": drift_deals._gate(record)},
    }
    manifest = json.loads((drift_deals._dataset(latest) / "manifest.json").read_text())
    named = ((manifest.get("build") or {}).get("ads") or {}).get("path")
    if market is not None:
        other, about = drift_deals._checked(market, backtest=False, model=model)
        drift_estimates._result(market, "market")
        meta["runs"]["market"] = market.name
        meta["datasets"]["market"] = drift_estimates._provenance(other)
        meta["gate"]["market"] = drift_deals._gate(other)
        meta["scoring_day"] = about.get("scoring_day")
        named = about["ads"]
    ads = ads or (Path(named) if named and Path(named).exists() else None)

    past, frame, held = run_ads(latest, "latest", reg)
    parts, later = [past], None
    if market is not None:
        now, rows, on = run_ads(market, "market", reg)
        new = on | ~rows.listing_id.astype(str).isin(set(frame.listing_id.astype(str)))
        later = rows[new].reset_index(drop=True), on[new.to_numpy()]
        del rows
        parts = [past[~past.listing_id.isin(now.listing_id)], now]
    t = pd.concat(parts, ignore_index=True)
    t = t.sort_values(["day", "listing_id"], kind="stable").reset_index(drop=True)

    file = None if ads is None else _ads_file(ads)
    at = (
        pd.DataFrame(index=t.listing_id) if file is None else file.reindex(t.listing_id)
    )
    t["unit"] = _label(at.page) if "page" in at else ""
    for c in ("square_feet", "floor", "months_free", "first_ask", "days_on_market"):
        t[c] = at[c].to_numpy(float) if c in at else np.nan
    t["flags"] = detect(t)

    files = source_files(features, sources)
    keys = t[["listing_id", "building"]].copy()
    lots = None
    if registry is not None and "bbl" in pq.read_schema(registry).names:
        lots = pd.read_parquet(registry, columns=["building", "bbl"])
        lots = lots.drop_duplicates("building").set_index("building").bbl
    keys["bbl"] = None if lots is None else keys.building.map(lots).to_numpy(object)
    extra = [f for f in FEATURES if f.name not in CORE]
    tables = {} if file is None else {ADS: file}
    if file is None:
        files = files | {ADS: None}
    joined, skipped = attach(extra, keys, files, tables)
    listed = []
    for f in FEATURES:
        column = t[f.name] if f.name in CORE else joined.get(f.name)
        if column is None:
            continue
        known = float(column.notna().mean()) if len(column) else 0.0
        true = float(column.fillna(False).mean()) if f.kind == "flag" else None
        thin = known < MIN_SHARE or (true is not None and true < MIN_SHARE)
        if thin and f.name not in CORE:
            why = (
                f"known for {known:.2%} of the ads"
                if known < MIN_SHARE
                else f"true for {true:.2%} of the ads"
            )
            skipped.append({"name": f.name, "why": why})
            continue
        listed.append(
            {
                "name": f.name,
                "label": f.label,
                "kind": f.kind,
                "level": f.level,
                "in_model": f.in_model,
                "after": f.after,
                "source": f.source,
                "known_share": round(known, 4),
            }
        )
    names = [f["name"] for f in listed if f["name"] not in CORE]
    t = pd.concat([t, joined[names]], axis=1)
    t = t[[*CORE, *names, "flags"]]

    level, why = levels(latest, record, frame.building.astype(str).to_numpy())
    b = building_table(frame, held, t, level, reg)
    of_building = [f for f in FEATURES if f.level == "building" and f.name in names]
    bkeys = b[["building"]].copy()
    bkeys["bbl"] = None if lots is None else bkeys.building.map(lots).to_numpy(object)
    b = pd.concat([b, attach(of_building, bkeys, files, tables)[0]], axis=1)

    past_ads = history(frame, held, file, later)
    codes = t["flags"].explode().dropna()
    meta |= {
        "features": listed,
        "skipped": skipped,
        "sources": {
            ADS: None if ads is None else _fingerprint(ads),
            **{
                name: _fingerprint(files[name])
                for name in dict.fromkeys(f["source"] for f in listed)
                if name != ADS and files.get(name) is not None
            },
        },
        "level": (
            "posterior mean of the building's level less its zone's surface at the "
            "building's point, on the log scale"
            if level is not None
            else None
        ),
        "level_missing": why or None,
        "model_terms": model_terms(latest),
        "ppsf": {
            "unit": "dollars per square foot a year",
            "bounds": {str(k): list(v) for k, v in PPSF.items()},
        },
        "coverage": coverage(t.pit[t.source == "latest"]),
        "counts": {
            "ads": {
                "all": int(len(t)),
                **{s: int((t.source == s).sum()) for s in ("latest", "market")},
            },
            "buildings": int(len(b)),
            "history": int(len(past_ads)),
            "basis": {k: int(v) for k, v in t.basis.value_counts().items()},
            "flags": {c: int((codes == c).sum()) for c in FLAGS},
        },
    }
    return {"ads": t, "buildings": b, "history": past_ads}, meta


def _write(frame: pd.DataFrame, path: Path) -> str:
    """Write `frame` to `path` under a temporary name, then rename it. Returns the
    file's sha256."""
    table = pa.Table.from_pandas(frame.drop(columns="flags", errors="ignore"))
    if "flags" in frame:
        table = table.append_column(
            "flags", pa.array(frame["flags"].tolist(), type=pa.list_(pa.string()))
        )
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    pq.write_table(table.replace_schema_metadata(None), tmp, compression="zstd")
    os.replace(tmp, path)
    return sha256(path)


def publish(
    latest: Path,
    out: Path,
    market: Path | None = None,
    ads: Path | None = None,
    registry: Path | None = None,
    features: Path | None = None,
    sources: dict | None = None,
) -> dict:
    """Write `ads.parquet`, `buildings.parquet` and `history.parquet` to the folder `out`,
    then `meta.json` with their hashes. Everything is computed before anything is
    written."""
    tables, meta = diagnostics(latest, market, ads, registry, features, sources)
    out.mkdir(parents=True, exist_ok=True)
    meta["sha256"] = {
        name: _write(frame, out / f"{name}.parquet") for name, frame in tables.items()
    }
    meta["published"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    drift_deals._replace(out / "meta.json", json.dumps(meta, indent=2))
    return meta


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("command", choices=("publish",))
    p.add_argument("run", help="the run on the latest split")
    p.add_argument("--market", help="the run on the market split")
    p.add_argument("--ads", type=Path, help="the pipeline's ads file")
    p.add_argument("--registry", type=Path)
    p.add_argument("--features", type=Path, help="the root of the snapshot folders")
    p.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="read this table for a source instead of its newest snapshot",
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--runs", default=str(run_module.RUNS))
    args = p.parse_args(argv)
    given = dict(s.split("=", 1) for s in args.source)
    if set(given) - set(SOURCES):
        p.error(f"--source names must be among {', '.join(SOURCES)}")
    runs = Path(args.runs)
    meta = publish(
        runs / args.run,
        args.out,
        runs / args.market if args.market else None,
        args.ads,
        args.registry,
        args.features,
        given,
    )
    print(json.dumps(meta | {"features": len(meta["features"])}, indent=2))


if __name__ == "__main__":
    main()
