"""The fit 8 model with every unit, building and ad-label feature on hand: the kitchen sink.

The model and sampler are `rentfrontier.building_zones_floor_asof3_cap64` (fit 8): the
neighborhood surface at 1 km in each zone, each building's level around it, the walk, the
bedroom and bath steps, the elevator and walk-up floor curves and the building columns of
the as-of design. Fit 8 reads a building's elevator, doorman and gym from all of its
training ads at any date, and its top floor from MapPLUTO, else the highest floor its
training ads list. For each row I rebuild these from the row's own ad and the building's
training ads priced on earlier days (`asof_base`), with the same MapPLUTO fallbacks, and move
the row's floor columns to the elevator or walk-up curve that its rebuilt elevator picks.
The served model reads the same values as fit 8, so `run_record` counts the rows whose
values change.

Then I append every other column I can code for a unit or a building, leaving out map and
distance columns (transit, parks, water, noise, schools), since the surface stands in for
those. The columns come in groups:

1. `ad:` columns from each ad's own record (`rentfrontier.listing_codes`, and the pipeline
   rows of `building_zones_floor_asof3.ROWS`):
   - each unit feature code (`feat:`), private outdoor type, view and fireplace type set on
     at least MIN_ROWS training rows, apart from the codes the design already carries
     (DUPLICATES), with `ad:features_unstated` for an empty feature list;
   - rooms beyond the bedrooms, the logged photo count, a floor plan, a video and a 3D tour;
   - the listing's source (feed or owner against a partner broker), the months free, a lease
     longer or shorter than 12 months, each window exposure, and the pet policy;
   - the square of `unit:log_size_rel`, an engineered term.
2. `bld:` building amenity codes. For each row I take the listings of its building that state
   amenities, among the row itself and the training rows priced on earlier days, and give
   the row a code when at least half of them list it, as `building_gym` does for the gym
   over all of a building's listings. I keep a code held on the rows of at least
   MIN_BUILDINGS buildings. `bld:amenities_unstated` marks a row with no such listing.
3. `bld:` lot columns from the latest MapPLUTO release of the building's lot (26v2, the
   release the base design's height, age and retail columns read): the logged residential
   units and lot frontage, a corner lot, the share of the allowed floor area built, landmark
   status, several buildings on the lot, the C, D and S building classes and the logged
   residential floor area per unit. `bld:lot_unknown` marks a building with no lot.
4. `umean:` unit means, for fit 4's columns (but `unit:garden`, which no unit's ads change)
   and every `ad:` unit column. Fit 4 averaged over
   all of a unit's training rows. Here I average over the row itself and the unit's training
   rows priced on earlier days, so no row reads an ad that came after it.

With the unit mean beside a unit column, the column's own coefficient measures the change
from the unit's earlier ads, and the unit mean's adds the difference between units (Mundlak
1978). The model has no unit effects, since fit 4's unit effects mixed poorly. Every new
column comes from ad fields and records, never from prices.

I leave out building means of unit columns (Fit B's `building_zones_mundlak_asof` columns)
and the building's bedroom mix, since both average over a building's later ads. I also leave
out the rent stabilization registrations and HPD violations, which the external snapshots
hold for Manhattan lots only.

    python -m rentfrontier.run --model building-zones-kitchen-sink --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    b0,
    building_attrs,
    building_gym,
    building_zones_floor,
    building_zones_floor_asof,
    building_zones_floor_asof3,
    building_zones_floor_asof3_cap64,
)
from .building_zones_floor_asof3_cap64 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    ELEV_CAP,
    GROUPS,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)
from .building_zones_floor_asof3_unitmean import unit_groups
from .unit_floor import GARDEN, LOWER, PENTHOUSE, unit_label
from .registry import EXTERNAL_ROOT

NAME = "building-zones-kitchen-sink"
CODES = Path(
    os.environ.get(
        "FRONTIER_LISTING_CODES",
        EXTERNAL_ROOT / "listing-codes" / "20261023-ks" / "listing-codes.parquet",
    )
)
EXTRA_FIELDS = (
    "months_free",
    "lease_term",
    "window_exposures",
    "pet_policy",
)
PLUTO_FIELDS = (
    "bbl",
    "version",
    "unitsres",
    "lotfront",
    "lottype",
    "builtfar",
    "residfar",
    "landmark",
    "numbldgs",
    "bldgclass",
    "resarea",
)
MIN_ROWS = 2000
MIN_BUILDINGS = 100
# Columns a block in past_sums.
BLOCK = 16
UNIT_LISTS = ("feat", "private_outdoor", "views", "fireplace")
BUILDING_LISTS = ("amen", "parking", "shared_outdoor", "storage")
# Codes the design already carries: dishwasher, laundry and furnished (`unit:`, `flag:`), and the doorman,
# elevator, gym and laundry room (`bld:`).
DUPLICATES = {
    "feat:DISHWASHER",
    "feat:FURNISHED",
    "feat:WASHER_DRYER",
    "amen:DOORMAN",
    "amen:ELEVATOR",
    "amen:GYM",
    "amen:LAUNDRY",
}
EXPOSURES = ("north", "south", "east", "west")
# MapPLUTO classes against all others. The design's `bld:condo` already marks class R.
CLASSES = ("C", "D", "S")
# The base columns `asof_base` rebuilds, besides the floor columns (FLOOR_COLUMNS).
BASE_COLUMNS = (
    "bld:elevator",
    "bld:elevator_unknown",
    "bld:doorman_full",
    "bld:doorman_part",
    "bld:doorman_virtual",
    "bld:gym",
)
FLOOR_COLUMNS = [
    f"unit:{g}_f{j}" for g, cap in GROUPS for j in range(2, cap + 1)
] + list(building_zones_floor.COLUMNS[-7:])
# The rows `asof_base` changed in the last design, by column, for `run_record`.
CHANGED: dict = {}
FIT4 = (
    "unit:log_size_rel",
    "unit:size_unknown",
    "unit:size_imputed",
    "unit:laundry_in_unit",
    "unit:laundry_in_building",
    "unit:dishwasher",
    "flag:rent_stabilized",
)


def code_columns(t: pd.DataFrame, lists) -> list[str]:
    """The code columns of the listing-codes table `t` in `lists`."""
    return [c for c in t.columns if c.split(":")[0] in lists and c not in DUPLICATES]


def exposure_flags(raw: pd.Series) -> np.ndarray:
    """Each row's window exposures, one 0/1 column per EXPOSURES, from the pipeline's JSON."""
    out = np.zeros((len(raw), len(EXPOSURES)))
    for i, s in enumerate(raw.to_numpy(object)):
        if not isinstance(s, str):
            continue
        try:
            j = json.loads(s)
        except ValueError:
            continue
        for k, e in enumerate(EXPOSURES):
            out[i, k] = float(bool(j.get(e)))
    return out


def ad_columns(
    frame: pd.DataFrame,
    codes: pd.DataFrame,
    extras: pd.DataFrame,
    train: np.ndarray,
    log_size_rel: np.ndarray,
) -> tuple[list[str], np.ndarray]:
    """Group 1's names and columns for the rows of `frame`."""
    lid = frame.listing_id.astype(str).to_numpy()
    c = codes.set_index("listing_id").reindex(lid)
    names, cols = [], []

    def add(name, v):
        names.append(name)
        cols.append(np.nan_to_num(np.asarray(v, float)))

    for code in code_columns(codes, UNIT_LISTS):
        v = c[code].fillna(0).to_numpy(float)
        if v[train].sum() >= MIN_ROWS:
            add("ad:" + code.replace(":", "_").lower(), v)
    stated = c.states_features.fillna(0).to_numpy(float)
    add("ad:features_unstated", 1 - stated)
    rooms = pd.to_numeric(c.rooms, errors="coerce").to_numpy(float)
    beds = frame.bedrooms.to_numpy(float)
    known = np.isfinite(rooms) & (rooms > 0)
    add("ad:extra_rooms", np.where(known, np.clip(rooms - beds - 1, 0, 6), 0))
    add("ad:rooms_unknown", ~known)
    add("ad:log1p_photos", np.log1p(c.photos.fillna(0).to_numpy(float)))
    add("ad:floorplan", c.floorplans.fillna(0).to_numpy(float) > 0)
    add("ad:video", c.videos.fillna(0).to_numpy(float) > 0)
    add("ad:tour3d", c.tour3d.fillna(0).to_numpy(float) > 0)
    src = c.source_type.astype(object).to_numpy()
    add("ad:source_feed", src == "FEED")
    add("ad:source_owner", src == "OWNER")
    add("ad:codes_unknown", c.photos.isna().to_numpy())

    e = extras.drop_duplicates("listing_id").set_index("listing_id").reindex(lid)
    add("ad:months_free", pd.to_numeric(e.months_free, errors="coerce").fillna(0))
    term = pd.to_numeric(e.lease_term, errors="coerce").to_numpy(float)
    add("ad:lease_long", np.isfinite(term) & (term > 12))
    add("ad:lease_short", np.isfinite(term) & (term < 12))
    exp = exposure_flags(e.window_exposures)
    for k, name in enumerate(EXPOSURES):
        add(f"ad:exposure_{name}", exp[:, k])
    pets = e.pet_policy.astype(object).to_numpy()
    add("ad:pets_not_allowed", pets == "not_allowed")
    add("ad:pets_approval", pets == "approval_required")
    add("ad:log_size_rel_sq", log_size_rel**2)
    return names, np.column_stack(cols)


def days(at: pd.Series) -> np.ndarray:
    """The UTC day number of each time in `at`."""
    t = pd.DatetimeIndex(pd.to_datetime(at, utc=True)).tz_convert(None)
    return t.to_numpy().astype("datetime64[D]").astype(np.int64)


def past_sums(
    x: np.ndarray, w: np.ndarray, group: np.ndarray, at: pd.Series
) -> tuple[np.ndarray, np.ndarray]:
    """For each row, the sums of `x * w` and of `w` over the rows of its group priced on
    earlier days than it."""
    day = days(at)
    key = group.astype(np.int64) * (1 << 20) + (day - day.min())
    o = np.argsort(key, kind="stable")
    k = key[o]
    ws = np.concatenate([[0.0], np.cumsum(w[o])])
    hi = np.searchsorted(k, key, side="left")
    lo = np.searchsorted(k, group.astype(np.int64) * (1 << 20), side="left")
    # A block of columns at a time, so the cumulative sums of 1.9M rows stay small.
    out = np.empty(x.shape)
    for j in range(0, x.shape[1], BLOCK):
        xs = np.cumsum(x[o, j : j + BLOCK] * w[o, None], axis=0)
        xs = np.vstack([np.zeros((1, xs.shape[1])), xs])
        out[:, j : j + BLOCK] = xs[hi] - xs[lo]
    return out, ws[hi] - ws[lo]


def past_means(
    x: np.ndarray, group: np.ndarray, at: pd.Series, train: np.ndarray
) -> np.ndarray:
    """The mean of each column of `x` over the row itself and the training rows of its
    group priced on earlier days."""
    s, n = past_sums(x, np.asarray(train, float), group, at)
    return (s + x) / (n + 1)[:, None]


def past_max(
    v: np.ndarray, group: np.ndarray, at: pd.Series, w: np.ndarray
) -> np.ndarray:
    """For each row, the largest `v` over the rows of its group with `w` priced on earlier
    days than it, NaN where there are none."""
    day = days(at)
    key = group.astype(np.int64) * (1 << 20) + (day - day.min())
    o = np.argsort(key, kind="stable")
    vs = pd.Series(np.where(w[o] & np.isfinite(v[o]), v[o], np.nan))
    g = pd.Series(group[o])
    run = vs.groupby(g).cummax().groupby(g).ffill().to_numpy()
    hi = np.searchsorted(key[o], key, side="left")
    lo = np.searchsorted(key[o], group.astype(np.int64) * (1 << 20), side="left")
    return np.where(hi > lo, run[np.maximum(hi - 1, 0)], np.nan)


def asof_base(
    d: Design,
    frame: pd.DataFrame,
    train: np.ndarray,
    ads: pd.DataFrame,
    amenities: pd.DataFrame,
    lots: pd.DataFrame,
) -> Design:
    """`d` with BASE_COLUMNS and FLOOR_COLUMNS rebuilt for each row from its own ad and its
    building's training ads priced on earlier days, as the module docstring sets out. `ads`
    are the pipeline rows, `amenities` the listing amenities table and `lots` the MapPLUTO
    and NJ floors and classes (`building_zones_floor_asof.load_lots`)."""
    rows = building_zones_floor_asof.ad_rows(frame, ads)
    site, at = d.site, frame.price_at
    train = np.asarray(train, bool)
    tw = train.astype(float)

    def share(x):
        s, n = past_sums(x, tw, site, at)
        return (s + x) / (n + 1)[:, None]

    x = np.column_stack(
        [
            rows.elevator.eq(True),
            rows.elevator.eq(False),
            rows.doorman_type.eq("full_time"),
            rows.doorman_type.isin(["part_time", "unspecified"]),
            rows.doorman_type.eq("virtual"),
        ]
    ).astype(float)
    m = share(x)
    lot = lots.reindex(frame.building.astype(str).to_numpy())
    cls = lot.bldgclass.fillna("").astype(str).to_numpy()
    cls = pd.Series(cls)
    lot_yes = (
        cls.str.startswith("D") | cls.isin(building_attrs.ELEVATOR_CLASSES)
    ).to_numpy()
    lot_no = (
        cls.str[:1].isin(["A", "B", "C", "S"]) | cls.isin(building_attrs.WALKUP_CLASSES)
    ).to_numpy()
    stated = m[:, 0] + m[:, 1] > 0
    elevator = np.select(
        [stated & (m[:, 0] >= m[:, 1]), stated, lot_yes, lot_no],
        ["yes", "no", "yes", "no"],
        "unknown",
    )
    k = building_attrs.SHARE
    doorman = np.select(
        [m[:, 2] > k, m[:, 3] > k, m[:, 4] > k], ["full", "part", "virtual"], "none"
    )

    a = amenities.assign(listing_id=amenities.listing_id.astype(str))
    a = a.drop_duplicates("listing_id").set_index("listing_id")
    lid = rows.listing_id.to_numpy()
    states = a.states.reindex(lid).fillna(False).astype(bool).to_numpy()
    gym = (a.gym.reindex(lid).fillna(False).astype(bool).to_numpy() & states).astype(
        float
    )
    first = ~pd.Series(lid).duplicated().to_numpy()
    s, n = past_sums(gym[:, None], (train & states & first).astype(float), site, at)
    s, n = s[:, 0] + gym, n + states
    gym_col = (n > 0) & (s >= building_gym.MAJORITY * n)

    base = {
        "bld:elevator": elevator == "yes",
        "bld:elevator_unknown": elevator == "unknown",
        "bld:doorman_full": doorman == "full",
        "bld:doorman_part": doorman == "part",
        "bld:doorman_virtual": doorman == "virtual",
        "bld:gym": gym_col,
    }

    pl = np.floor(pd.to_numeric(lot.numfloors, errors="coerce").to_numpy(float))
    listed = rows.listed_floor.astype(float).to_numpy()
    seen = np.fmax(past_max(listed, site, at, train), listed)
    count = np.where(pl >= 1, pl, seen)
    lab = unit_label(rows.page.fillna(""))
    ph = lab.str.contains(PENTHOUSE).to_numpy()
    garden = lab.str.contains(GARDEN).to_numpy() & ~ph
    lower = lab.str.contains(LOWER).to_numpy() & ~ph & ~garden
    floor = np.where(np.isnan(listed) & (garden | lower), 1.0, listed)
    floor = np.where(np.isnan(floor) & ph, count, floor)
    top = (count >= 2) & (floor >= count)
    group = {"elev": base["bld:elevator"], "walkup": ~base["bld:elevator"]}
    cols = {}
    for g, cap in GROUPS:
        f = np.minimum(floor, cap)
        for j in range(2, cap + 1):
            cols[f"unit:{g}_f{j}"] = group[g] & (f == j)
    cols |= {
        "unit:elev_top": top & group["elev"],
        "unit:walkup_top": top & group["walkup"],
        "unit:penthouse": ph,
        "unit:garden": garden,
        "unit:lower": lower,
        "unit:elev_floor_unknown": np.isnan(floor) & group["elev"],
        "unit:walkup_floor_unknown": np.isnan(floor) & group["walkup"],
    }
    base |= cols

    names = list(d.names)
    x = d.x.copy()
    count_ = dict(d.count)
    CHANGED.clear()
    for name, v in base.items():
        j = names.index(name)
        v = v.astype(x.dtype)
        CHANGED[name] = {
            "train": int((x[train, j] != v[train]).sum()),
            "held": int((x[~train, j] != v[~train]).sum()),
        }
        x[:, j] = v
        count_[name] = int(v.sum())
    return dataclasses.replace(d, x=x, count=count_)


def building_codes(
    frame: pd.DataFrame, site: np.ndarray, codes: pd.DataFrame, train: np.ndarray
) -> tuple[list[str], np.ndarray]:
    """Group 2's names and columns: for each row, the majority over its building's listings
    that state amenities among the row itself and the training rows priced on earlier days."""
    keep = code_columns(codes, BUILDING_LISTS)
    lid = frame.listing_id.astype(str).to_numpy()
    c = codes.set_index("listing_id")[["states_amenities", *keep]].reindex(lid)
    stating = c.states_amenities.fillna(0).to_numpy(float) > 0
    x = c[keep].fillna(0).to_numpy(float) * stating[:, None]
    s, n = past_sums(
        x, (np.asarray(train, bool) & stating).astype(float), site, frame.price_at
    )
    s, n = s + x, n + stating
    names = ["bld:amenities_unstated"]
    cols = [(n == 0).astype(float)]
    has = (s >= 0.5 * n[:, None]) & (n[:, None] > 0)
    for j, code in enumerate(keep):
        if len(np.unique(site[has[:, j]])) >= MIN_BUILDINGS:
            names.append("bld:" + code.replace(":", "_").lower())
            cols.append(has[:, j].astype(float))
    return names, np.column_stack(cols)


def lot_table(registry: pd.DataFrame, pluto: pd.DataFrame) -> pd.DataFrame:
    """Group 3's columns for each building of `registry` with a lot, by building."""
    p = pluto.sort_values("version").drop_duplicates("bbl", keep="last").copy()
    num = ["unitsres", "lotfront", "lottype", "builtfar", "residfar", "numbldgs"]
    for k in [*num, "resarea"]:
        p[k] = pd.to_numeric(p[k], errors="coerce")
    units = p.unitsres.where(p.unitsres > 0)
    cls = p.bldgclass.fillna("").astype(str).str[:1]
    t = pd.DataFrame(
        {
            "bbl": p.bbl,
            "bld:log_units": np.log(units).fillna(0),
            "bld:units_unknown": units.isna().astype(float),
            "bld:log_lot_front": np.log(p.lotfront.where(p.lotfront > 0)).fillna(
                np.log(25.0)
            ),
            "bld:corner": (p.lottype == 3).astype(float),
            "bld:far_used": (p.builtfar / p.residfar.where(p.residfar > 0))
            .clip(0, 3)
            .fillna(1.0),
            "bld:landmark": p.landmark.notna().astype(float),
            "bld:multi_building": (p.numbldgs > 1).astype(float),
            **{f"bld:class_{k}": (cls == k).astype(float) for k in CLASSES},
            "bld:log_area_per_unit": np.log(
                (p.resarea / units).where(p.resarea > 0)
            ).fillna(0),
        }
    )
    out = registry.dropna(subset=["bbl"]).merge(t, on="bbl", how="inner")
    return out.drop_duplicates("building").set_index("building").drop(columns="bbl")


def lot_columns(
    frame: pd.DataFrame, lots: pd.DataFrame
) -> tuple[list[str], np.ndarray]:
    """Group 3's names and columns for the rows of `frame`, with `bld:lot_unknown` and the
    reference values for a building with no lot."""
    t = lots.reindex(frame.building.astype(str).to_numpy())
    unknown = t.isna().all(axis=1).to_numpy(float)
    fill = {"bld:log_lot_front": np.log(25.0), "bld:far_used": 1.0}
    t = t.fillna(fill).fillna(0)
    return [*t.columns, "bld:lot_unknown"], np.column_stack(
        [t.to_numpy(float), unknown]
    )


def read_tables() -> dict:
    """The tables `design` reads when not given."""
    registry = pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"])
    return {
        "codes": pd.read_parquet(CODES).drop(columns=["collected_at"]),
        "extras": pd.read_parquet(
            building_zones_floor_asof3.ROWS, columns=["listing_id", *EXTRA_FIELDS]
        ).assign(listing_id=lambda t: t.listing_id.astype(str)),
        "lots": lot_table(
            registry,
            pd.read_parquet(building_attrs.PLUTO, columns=list(PLUTO_FIELDS)),
        ),
    }


def append(d: Design, names: list[str], x: np.ndarray) -> Design:
    """`d` with the columns `x` named `names` appended, leaving out any column no row sets
    or that repeats one already in the design."""
    have = set(d.names)
    keep = [
        j for j, n in enumerate(names) if n not in have and np.abs(x[:, j]).sum() > 0
    ]
    count = dict(d.count) | {
        names[j]: int((x[:, j] != 0).sum()) for j in range(len(names))
    }
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, x[:, keep]]),
        names=list(d.names) + [names[j] for j in keep],
        count=count,
    )


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    held=None,
    codes: pd.DataFrame | None = None,
    extras: pd.DataFrame | None = None,
    lot_facts: pd.DataFrame | None = None,
    ads: pd.DataFrame | None = None,
    amenities: pd.DataFrame | None = None,
    lots: pd.DataFrame | None = None,
    **kw,
) -> Design:
    """Fit 8's design of `frame` with its building attributes and floor columns rebuilt
    (`asof_base`) and groups 1 to 4 appended. `lot_facts` is `read_tables`' lot table, and
    `ads`, `amenities` and `lots` are the tables of `building_zones_floor_asof.design`."""
    held = building_zones_floor_asof.held_out(frame, held)
    train = ~held
    if codes is None or extras is None or lot_facts is None:
        t = read_tables()
        codes = t["codes"] if codes is None else codes
        extras = t["extras"] if extras is None else extras
        lot_facts = t["lots"] if lot_facts is None else lot_facts
    if ads is None:
        ads = building_zones_floor_asof3.read_ads()
    if amenities is None:
        amenities = pd.read_parquet(
            building_zones_floor_asof.AMENITIES / "amenities.parquet"
        )
    if lots is None:
        lots = building_zones_floor_asof.load_lots()
    d = building_zones_floor_asof3_cap64.design(
        frame, start, held=held, ads=ads, amenities=amenities, lots=lots, **kw
    )
    d = asof_base(d, frame, train, ads, amenities, lots)
    names = list(d.names)
    size = d.x[:, names.index("unit:log_size_rel")]
    n1, x1 = ad_columns(frame, codes, extras, train, size)
    d = append(d, n1, x1)
    n2, x2 = building_codes(frame, d.site, codes, train)
    d = append(d, n2, x2)
    n3, x3 = lot_columns(frame, lot_facts)
    d = append(d, n3, x3)

    names = list(d.names)
    within = [n for n in FIT4 if n in names] + [n for n in names if n.startswith("ad:")]
    wx = d.x[:, [names.index(n) for n in within]]
    um = past_means(wx, unit_groups(frame), frame.price_at, train)
    return append(d, ["umean:" + n for n in within], um)


def run_record(d: Design) -> dict:
    """Fit 8's record with the kitchen sink's sources and column groups."""
    names = list(d.names)
    groups = {
        "ad": [n for n in names if n.startswith("ad:")],
        "unit_means": [n for n in names if n.startswith("umean:")],
    }
    return building_zones_floor_asof3_cap64.run_record(d) | {
        "kitchen_sink": {
            "asof_base_changed_rows": dict(CHANGED),
            "listing_codes": str(CODES),
            "pipeline_rows": str(building_zones_floor_asof3.ROWS),
            "pluto": str(building_attrs.PLUTO),
            "min_rows": MIN_ROWS,
            "min_buildings": MIN_BUILDINGS,
            "groups": groups,
            "means_rows": "the row and training rows priced on earlier days",
        }
    }


def main_run(argv, name: str = NAME, spec=None) -> None:
    """`rentfrontier.run --model building-zones-kitchen-sink`: fit on the split's training
    rows and save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {name}"
    parser.set_defaults(model=name)
    parser.add_argument("--site-block", type=int)
    parser.add_argument("--joint-amp", action="store_true", default=None)
    building_zones_floor_asof.SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=name,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=spec or sys.modules[__name__],
    )
