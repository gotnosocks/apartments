"""Building zones with the unit's floor, plus each building's distance to parks and the water.

The model is building zones with the unit's floor (`rentfrontier.building_zones_floor`) with
three more `bld:` columns, read from the parks snapshot (`rentfrontier.building_parks`):

    bld:log_park_km       log of the distance to the nearest park of 1 acre or more, in km
    bld:log_big_park_km   log of the distance to the nearest park of 30 acres or more
    bld:log_water_km      log of the distance to the nearest shoreline

Each distance is floored at 0.05 km before the log. A building missing from the snapshot gets
the snapshot's medians.

    python -m rentfrontier.run --model building-zones-parks --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, building_zones_floor
from .building_zones_floor import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
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
from .registry import EXTERNAL_ROOT

NAME = "building-zones-parks"
PARKS_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_BUILDING_PARKS",
        EXTERNAL_ROOT / "building-parks" / "20261022-ec936683",
    )
)
SOURCES = (
    ("bld:log_park_km", "park_km"),
    ("bld:log_big_park_km", "big_park_km"),
    ("bld:log_water_km", "water_km"),
)
COLUMNS = tuple(n for n, _ in SOURCES)
MIN_KM = 0.05


def columns(frame: pd.DataFrame, parks: pd.DataFrame) -> np.ndarray:
    """The new columns (COLUMNS) of `frame`'s rows."""
    t = parks.drop_duplicates("building").set_index("building")
    t = t.reindex(frame.building.astype(str))
    return np.column_stack(
        [
            np.log(np.maximum(t[c].fillna(parks[c].median()).to_numpy(float), MIN_KM))
            for _, c in SOURCES
        ]
    )


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    parks: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with the unit's floor's design of `frame` with the parks columns
    appended."""
    if parks is None:
        parks = pd.read_parquet(PARKS_SNAPSHOT / "parks.parquet")
    d = building_zones_floor.design(frame, start, **tables)
    new = columns(frame, parks)
    count = dict(d.count) | {
        n: int((new[:, j] != 0).sum()) for j, n in enumerate(COLUMNS)
    }
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, new]),
        names=list(d.names) + list(COLUMNS),
        count=count,
    )


def run_record(d: Design) -> dict:
    """Building zones with the unit's floor's record, with the parks snapshot."""
    return building_zones_floor.run_record(d) | {"building_parks": str(PARKS_SNAPSHOT)}


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-parks`: fit on the split's training rows and
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
