"""L1 with every MapPLUTO field read from the release out when the row's ad was priced.

L1 (`rentfrontier.drift_building_phase`) reads its MapPLUTO fields from release 26v2,
published 2026-08-17 (`building_attrs.PLUTO`), for every row, so an ad priced in 2015 reads
its building's class, floors, year built and lot facts as the city recorded them in 2026.
This model reads them as of the row's month, by the rule `rentfrontier.b0coop` follows:

1. the building's lot is its BBL in the registry `building_attrs.REGISTRY`, as in L1;
2. the row reads the latest release in the all-lots release file (`RELEASES`) published at
   least `features.PLUTO_RELEASE_BUFFER_DAYS` days before the first day of the month of its
   price_at. Release 22v2 carries no publication date, so no row reads it;
3. where the lot is missing from that release, or the row was priced before the first usable
   release, every field reads blank, as a building with no lot does in L1.

A release that leaves a field blank on every lot of the file never recorded that field, and
its rows read the field from 26v2, as L1 does. In this file that is `residfar` in 09v1 to 12v2.
`features.released_lots`, which the plutoasof feature sets read, keeps 26v2's values in more
cases: for a lot missing from its release, for the year built, and for a release published
before 26v2's year built. Each of those reads 26v2 for an earlier row, so this model leaves
them out.

I build L1's design, then rebuild the columns that read MapPLUTO with L1's own functions,
giving them a key of lot and release in place of the building:

- `bld:condo` from the class, as `building_attrs.attributes` sorts it;
- the elevator columns and the floor columns (`building_zones_kitchen_sink.asof_base`), which
  fall back on the class where the ads state no elevator, and read the floor count for the
  top floor;
- the build eras, `bld:built_unknown`, `bld:altered_2000_on`, `bld:retail` and
  `bld:retail_unknown` (`building_age.building_table`, `building_zones_age.columns`), from the
  year built, the alteration years and the retail and commercial areas;
- the lot columns and `bld:lot_unknown` (`building_zones_kitchen_sink.lot_table`,
  `lot_columns`), from the residential units, lot front, lot type, built and residential FAR,
  landmark, building count, class and residential area.

A row whose building has no lot in the registry keeps L1's columns. The building's position
comes from the registry and its height from the building footprints, so neither changes. The
rest of the design, the priors and the sampler are L1's, and with every row on 26v2 the
design is L1's, column for column.

    python -m rentfrontier.run --model drift-building-phase-plutoasof --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from . import (
    b0coop,
    building_age,
    building_attrs,
    building_zones_age,
    building_zones_floor_asof,
    building_zones_floor_asof3,
    building_zones_kitchen_sink,
    drift,
    drift_building_phase,
)
from .drift_building import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    make_sampler,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)
from .features import LOTS4_FILES, PLUTO_RELEASE_BUFFER_DAYS

NAME = "drift-building-phase-plutoasof"
PHASES = drift_building_phase.PHASES
RELEASES = Path(LOTS4_FILES["plutoreleases"])
# The MapPLUTO fields L1's design reads: the lot table's (`building_zones_kitchen_sink`),
# then the floor count, the year built, and the alteration years and areas of `building_age`.
FIELDS = (
    *building_zones_kitchen_sink.PLUTO_FIELDS[2:],
    "numfloors",
    "yearbuilt",
    "yearalter1",
    "yearalter2",
    "retailarea",
    "comarea",
)
# The columns `asof_base` rebuilds that read MapPLUTO. The doorman and gym columns read the ads
# alone.
BASE_COLUMNS = (
    "bld:elevator",
    "bld:elevator_unknown",
    *building_zones_kitchen_sink.FLOOR_COLUMNS,
)
AGE_COLUMNS = tuple(c for c in building_zones_age.COLUMNS if c != "bld:gym")
STATUSES = ("read", "no lot", "no release", "lot not in release")
# What the last design read, for `run_record`.
RECORD: dict = {}


def published(path: Path = RELEASES) -> pd.Series:
    """The publication day of each dated release in the file `path`, by release, earliest
    first. 22v2 carries no date and is left out."""
    t = pd.read_parquet(path, columns=["release", "published"]).drop_duplicates()
    t = t.dropna(subset=["published"]).drop_duplicates("release")
    return pd.to_datetime(t.set_index("release").published).sort_values()


def release_of(price_at: pd.Series, dates: pd.Series) -> np.ndarray:
    """The release each time in `price_at` reads, "" where none is out yet: the latest of
    `dates` (publication days by release, earliest first) at least
    PLUTO_RELEASE_BUFFER_DAYS days before the first day of the time's month."""
    usable = (dates + pd.Timedelta(days=PLUTO_RELEASE_BUFFER_DAYS)).to_numpy()
    order = np.searchsorted(usable, b0coop.months(price_at), side="right") - 1
    names = dates.index.to_numpy(dtype=object)
    return np.where(order >= 0, names[np.maximum(order, 0)], "").astype(object)


def blank(v: pd.Series) -> pd.Series:
    """`v` as strings, with whitespace stripped and empty strings missing. The older
    releases write a missing class or landmark as an empty string."""
    return v.astype("string").str.strip().replace("", pd.NA)


def stripped(v: pa.ChunkedArray) -> pa.ChunkedArray:
    """`blank` for an Arrow column of strings."""
    v = pc.utf8_trim_whitespace(v)
    return pc.if_else(pc.equal(v, ""), pa.scalar(None, v.type), v)


def lot_reads(
    frame: pd.DataFrame,
    registry: pd.DataFrame,
    path: Path = RELEASES,
    today: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """What each row of `frame` (`building`, `price_at`) reads from the release file `path`.

    I return three things:

    1. for each row, `bbl`, its building's lot in `registry` ("" for none); `release`, the
       release it reads ("" for none); `key`, the lot and release as "bbl|release"; and
       `status`, one of STATUSES;
    2. the FIELDS of each key whose lot is in its release, as strings, by key;
    3. for each release that never recorded a field, the fields its rows read from `today`
       (MapPLUTO's 26v2 lots, `building_attrs.PLUTO`, by default)."""
    dates = published(path)
    lots = registry.dropna(subset=["bbl"]).drop_duplicates("building")
    lots = pd.Series(lots.bbl.astype(str).to_numpy(), lots.building.astype(str))
    bbl = frame.building.astype(str).map(lots).fillna("").to_numpy(dtype=object)
    release = release_of(frame.price_at, dates)
    key = np.array([f"{b}|{r}" for b, r in zip(bbl, release)], dtype=object)

    # The file holds about 2.9 million lines of strings, so its columns stay in Arrow until
    # they are cut to the keys the rows read.
    t = pq.read_table(path, columns=["release", "bbl", *FIELDS])
    names = pa.array(list(dates.index), t["release"].type)
    t = t.filter(pc.is_in(t["release"], value_set=names))
    text = pa.large_string()
    t = pa.table(
        {
            "key": pc.binary_join_element_wise(
                pc.cast(t["bbl"], text),
                pc.cast(t["release"], text),
                pa.scalar("|", text),
            ),
            "release": t["release"],
            **{f: stripped(t[f]) for f in FIELDS},
        }
    )
    valid = pa.table(
        {"release": t["release"], **{f: pc.is_valid(t[f]) for f in FIELDS}}
    )
    carried = valid.group_by("release").aggregate([(f, "any") for f in FIELDS])
    carried = carried.to_pandas().set_index("release")
    carried.columns = [c.removesuffix("_any") for c in carried.columns]
    wanted = pa.array(sorted(set(key)), t["key"].type)
    t = t.filter(pc.is_in(t["key"], value_set=wanted))
    table = t.select(["key", *FIELDS]).to_pandas().drop_duplicates("key")
    table = table.set_index("key").astype(object)
    table = table.where(table.notna(), None)
    # The fields a release never recorded come from 26v2's lots.
    from_today = {
        r: [f for f in FIELDS if not carried.loc[r, f]]
        for r in sorted(carried.index)
        if not carried.loc[r].all()
    }
    if from_today:
        if today is None:
            today = pd.read_parquet(building_attrs.PLUTO, columns=["bbl", *FIELDS])
        now = today.assign(bbl=today.bbl.astype(str)).drop_duplicates("bbl")
        now = now.set_index("bbl")
        lot = table.index.str.split("|").str[0]
        rel = table.index.str.split("|").str[1]
        for r, fields in from_today.items():
            take = np.asarray(rel == r)
            for f in fields:
                v = blank(now[f]).reindex(lot[take]).astype(object)
                table.loc[take, f] = v.where(v.notna(), None).to_numpy()
    found = pd.Index(key).isin(table.index)
    status = np.select(
        [bbl == "", release == "", ~found], list(STATUSES[1:]), STATUSES[0]
    )
    rows = pd.DataFrame({"bbl": bbl, "release": release, "key": key, "status": status})
    return rows, table, from_today


def pluto_columns(
    d: Design,
    frame: pd.DataFrame,
    train: np.ndarray,
    ads: pd.DataFrame,
    amenities: pd.DataFrame,
    keys: np.ndarray,
    table: pd.DataFrame,
) -> dict[str, np.ndarray]:
    """The columns of `frame`'s rows that read MapPLUTO, each row reading the lot of its key
    in `keys` from `table` (`lot_reads`), by L1's own functions. `ads` and `amenities` are
    the tables `asof_base` reads."""
    ks = building_zones_kitchen_sink
    keyed = frame[["listing_id", "unit_id", "price_at", "bedrooms", "full_baths"]]
    keyed = keyed.assign(building=keys)
    lot = pd.Series(table.index, index=table.index)
    lot_registry = pd.DataFrame({"building": lot.to_numpy(), "bbl": lot.to_numpy()})
    cols = {}

    cls = table.bldgclass.reindex(keys).to_numpy(dtype=object)
    cols["bld:condo"] = b0coop.tenure(cls)[0]

    # `asof_base` rebuilds every column it holds, so it gets a design of those columns alone,
    # with the module's record of its changes kept as L1's design left it.
    names = [*ks.BASE_COLUMNS, *ks.FLOOR_COLUMNS]
    slim = np.empty((len(d.y), len(names)), d.x.dtype)
    for j, n in enumerate(names):
        slim[:, j] = d.x[:, d.names.index(n)]
    floors = pd.DataFrame(
        {
            "numfloors": pd.to_numeric(table.numfloors, errors="coerce"),
            "bldgclass": table.bldgclass,
        },
        index=table.index,
    )
    saved = dict(ks.CHANGED)
    try:
        e = ks.asof_base(
            dataclasses.replace(d, x=slim, names=names, count={}),
            keyed,
            train,
            ads,
            amenities,
            floors,
        )
    finally:
        ks.CHANGED.clear()
        ks.CHANGED.update(saved)
    for j, n in enumerate(names):
        if n in BASE_COLUMNS:
            cols[n] = e.x[:, j]

    year = pd.to_numeric(table.yearbuilt, errors="coerce")
    attrs = pd.DataFrame(
        {"building": lot.to_numpy(), "year_built": year.where(year >= 1800).to_numpy()}
    )
    ages = building_age.building_table(
        attrs, lot_registry, table.rename_axis("bbl").reset_index()
    )
    gyms = pd.DataFrame({"building": pd.Series([], dtype=object), "gym": []})
    new = building_zones_age.columns(keyed, gyms, ages)
    for j, n in enumerate(building_zones_age.COLUMNS):
        if n in AGE_COLUMNS:
            cols[n] = new[:, j]

    release = lot.str.split("|").str[1]
    facts = ks.lot_table(
        lot_registry,
        table.rename_axis("bbl").reset_index().assign(version=release.to_numpy()),
    )
    n3, x3 = ks.lot_columns(keyed, facts)
    cols |= dict(zip(n3, x3.T))
    return cols


def put(
    d: Design, cols: dict, keep: np.ndarray, train: np.ndarray
) -> tuple[Design, dict]:
    """`d` with each of `cols` that its design holds written in, except on the rows under
    `keep`, and the rows each one changed in training and held out. The columns go into
    `d.x` in place, since a copy of a full design takes about 4 GB."""
    x, count, changed = d.x, dict(d.count), {}
    for name, v in cols.items():
        if name not in d.names:
            continue
        j = d.names.index(name)
        v = np.where(keep, x[:, j], np.asarray(v, x.dtype))
        moved = x[:, j] != v
        changed[name] = {
            "train": int(moved[train].sum()),
            "held": int(moved[~train].sum()),
        }
        x[:, j] = v
        count[name] = int((v != 0).sum())
    return dataclasses.replace(d, x=x, count=count), changed


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    held=None,
    ads: pd.DataFrame | None = None,
    amenities: pd.DataFrame | None = None,
    registry: pd.DataFrame | None = None,
    releases: Path = RELEASES,
    today: pd.DataFrame | None = None,
    **kw,
) -> Design:
    """L1's design of `frame`, with its MapPLUTO columns read from each row's release in the
    file `releases`, as the module docstring sets out. `ads` and `amenities` are the tables of
    `building_zones_floor_asof.design`, `registry` the buildings' lots and `today` the lots
    of 26v2, all read when not given."""
    held = building_zones_floor_asof.held_out(frame, held)
    train = ~held
    if ads is None:
        ads = building_zones_floor_asof3.read_ads()
    if amenities is None:
        amenities = pd.read_parquet(
            building_zones_floor_asof.AMENITIES / "amenities.parquet"
        )
    if registry is None:
        registry = pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"])
    d = drift_building_phase.design(
        frame, start, held=held, ads=ads, amenities=amenities, **kw
    )
    rows, table, from_today = lot_reads(frame, registry, releases, today)
    cols = pluto_columns(
        d, frame, train, ads, amenities, rows.key.to_numpy(dtype=object), table
    )
    d, changed = put(d, cols, rows.bbl.to_numpy() == "", train)
    RECORD.clear()
    RECORD.update(
        releases=str(releases),
        buffer_days=PLUTO_RELEASE_BUFFER_DAYS,
        rule=(
            "the latest dated release published at least buffer_days days before the "
            "first day of the row's price month; blank where the lot is missing from it"
        ),
        rows_by_release=rows.release.replace("", "none").value_counts().to_dict(),
        rows_by_status=rows.status.value_counts().to_dict(),
        fields_from_26v2=from_today,
        changed_rows=changed,
    )
    return d


def run_record(d: Design) -> dict:
    """L1's record, with the releases the rows read and the rows each column changed."""
    return drift_building_phase.run_record(d) | {"pluto_asof": dict(RECORD)}


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-plutoasof`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
