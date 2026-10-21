"""Building zones with unit features, a building gym, year built and ground-floor retail.

The model is building zones with unit features (`rentfrontier.building_zones_unit`), truck
route column included, with these columns appended:

    bld:gym                1 where at least half of the building's listings stating amenities
                           list a gym (`rentfrontier.building_gym`, as in building zones gym)
    bld:built_pre1900      year built before 1900
    bld:built_1940_1979    year built 1940 to 1979
    bld:built_1980_1999    year built 1980 to 1999
    bld:built_2000_2009    year built 2000 to 2009
    bld:built_2010_on      year built 2010 or later
    bld:built_unknown      no year built
    bld:altered_2000_on    a MapPLUTO alteration year from 2000 up to the ad's year
    bld:retail             the lot has MapPLUTO retail area (commercial area where retail is
                           blank)
    bld:retail_unknown     the lot has neither area, or the building has no MapPLUTO lot

The age and retail columns come from the building age snapshot (`rentfrontier.building_age`).
The reference building was built 1900 to 1939, has no alteration since 2000 and no retail.
On the latest split's 1,706,837 training ads, 7,368 have no year built and 10,859 have no
retail area. A building missing from the snapshot gets both unknown flags.

I compare each alteration year with the year of the ad's price, so an alteration after the ad
leaves the flag at 0. That makes `bld:altered_2000_on` vary between ads of one building. Like
the unit columns, it enters the rows' fixed design, as do the other columns, which stay
constant within a building. Every coefficient joins the global block with the Normal(0, 0.5)
prior.

    python -m rentfrontier.run --model building-zones-age --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, building_zones_unit
from .building_zones_gym import GYM_SNAPSHOT
from .building_zones_unit import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)
from .registry import EXTERNAL_ROOT

NAME = "building-zones-age"
AGE_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_BUILDING_AGE",
        EXTERNAL_ROOT / "building-age" / "20261021-3a64aa22",
    )
)
ERAS = (  # (column, first year, last year)
    ("bld:built_pre1900", 0, 1899),
    ("bld:built_1940_1979", 1940, 1979),
    ("bld:built_1980_1999", 1980, 1999),
    ("bld:built_2000_2009", 2000, 2009),
    ("bld:built_2010_on", 2010, 9999),
)
COLUMNS = (
    "bld:gym",
    *(e[0] for e in ERAS),
    "bld:built_unknown",
    "bld:altered_2000_on",
    "bld:retail",
    "bld:retail_unknown",
)


def columns(frame: pd.DataFrame, gyms: pd.DataFrame, ages: pd.DataFrame) -> np.ndarray:
    """The new columns (COLUMNS) of `frame`'s rows. A building missing from `gyms` has no
    gym."""
    b = frame.building.astype(str)
    gym = b.map(gyms.drop_duplicates("building").set_index("building").gym)
    a = ages.drop_duplicates("building").set_index("building").reindex(b)
    year = a.year_built.to_numpy(float)
    ad_year = pd.to_datetime(frame.price_at).dt.year.to_numpy(float)
    altered = np.zeros(len(frame), bool)
    for c in ("alter1", "alter2"):
        y = a[c].to_numpy(float)
        altered |= (y >= 2000) & (y <= ad_year)
    eras = [(year >= lo) & (year <= hi) for _, lo, hi in ERAS]
    unknown = a.retail_unknown.fillna(1.0).to_numpy(float) == 1
    return np.column_stack(
        [
            gym.fillna(0.0).to_numpy(float) == 1,
            *eras,
            np.isnan(year),
            altered,
            a.retail.fillna(0.0).to_numpy(float) == 1,
            unknown,
        ]
    ).astype(float)


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
    nj_registry: pd.DataFrame | None = None,
    attrs: pd.DataFrame | None = None,
    footprints: pd.DataFrame | None = None,
    units: pd.DataFrame | None = None,
    trucks: pd.DataFrame | None = None,
    gyms: pd.DataFrame | None = None,
    ages: pd.DataFrame | None = None,
) -> Design:
    """Building zones with unit features' design of `frame` with the new columns appended. I
    leave out a column no row sets."""
    if gyms is None:
        gyms = pd.read_parquet(GYM_SNAPSHOT / "gym.parquet")
    if ages is None:
        ages = pd.read_parquet(AGE_SNAPSHOT / "age.parquet")
    d = building_zones_unit.design(
        frame,
        start,
        registry=registry,
        nj_registry=nj_registry,
        attrs=attrs,
        footprints=footprints,
        units=units,
        trucks=trucks,
    )
    new = columns(frame, gyms, ages)
    count = dict(d.count)
    keep = []
    for j, n in enumerate(COLUMNS):
        count[n] = int((new[:, j] != 0).sum())
        if count[n] > 0:
            keep.append(j)
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, new[:, keep]]),
        names=list(d.names) + [COLUMNS[j] for j in keep],
        count=count,
    )


def run_record(d: Design) -> dict:
    """Building zones with unit features' record, with the gym and age snapshots."""
    return building_zones_unit.run_record(d) | {
        "building_gym": str(GYM_SNAPSHOT),
        "building_age": str(AGE_SNAPSHOT),
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-age`: fit on the split's training rows and
    save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
