"""Building zones with the unit's floor, plus each building's access to rapid transit.

The model is building zones with the unit's floor (`rentfrontier.building_zones_floor`) with
two more `bld:` columns, read from the transit snapshot (`rentfrontier.building_transit`):

    bld:log_station_km   the log of the straight-line distance to the nearest subway or PATH
                         stop, in km, floored at 0.05 km
    bld:log1p_routes     log(1 + the distinct daytime services at stops within 0.8 km)

Both are measured from the building's point, so they can take up part of the map and of the
building levels: a map value high near a busy station and lower between lines is the pattern
they would explain. A building missing from the snapshot gets the snapshot's median for both.

    python -m rentfrontier.run --model building-zones-transit --split latest --name NAME
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

NAME = "building-zones-transit"
TRANSIT_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_BUILDING_TRANSIT",
        EXTERNAL_ROOT / "building-transit" / "20261022-a4d8ac25",
    )
)
COLUMNS = ("bld:log_station_km", "bld:log1p_routes")
MIN_KM = 0.05


def columns(frame: pd.DataFrame, transit: pd.DataFrame) -> np.ndarray:
    """The new columns (COLUMNS) of `frame`'s rows."""
    t = transit.drop_duplicates("building").set_index("building")
    t = t.reindex(frame.building.astype(str))
    km = t.station_km.fillna(transit.station_km.median()).to_numpy(float)
    routes = t.routes_800m.fillna(transit.routes_800m.median()).to_numpy(float)
    return np.column_stack([np.log(np.maximum(km, MIN_KM)), np.log1p(routes)])


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    transit: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with the unit's floor's design of `frame` with the transit columns
    appended."""
    if transit is None:
        transit = pd.read_parquet(TRANSIT_SNAPSHOT / "transit.parquet")
    d = building_zones_floor.design(frame, start, **tables)
    new = columns(frame, transit)
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
    """Building zones with the unit's floor's record, with the transit snapshot."""
    return building_zones_floor.run_record(d) | {
        "building_transit": str(TRANSIT_SNAPSHOT)
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-transit`: fit on the split's training rows and
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
