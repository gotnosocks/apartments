"""Building zones with location, plus a flag for a building facing an elevated subway track.

The model is building zones with location (`rentfrontier.building_zones_location`) with one
more `bld:` column, read from the elevated track snapshot (`rentfrontier.building_elevated`):

    bld:elevated   1 when the building's outline lies within FRONT_M of an elevated subway
                   track, 0 otherwise

The structure runs over the middle of its street, so FRONT_M takes in the buildings on both
sides of that street and leaves out the ones around the corner. `bld:log_station_km` and
`bld:log1p_routes` measure access to the same lines and change slowly over a neighborhood. This
column changes between a building under the tracks and the one behind it. A building with no
outline gets 0.

    python -m rentfrontier.run --model building-zones-elevated --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, building_zones_location
from .building_zones_location import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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

NAME = "building-zones-elevated"
ELEVATED_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_BUILDING_ELEVATED",
        EXTERNAL_ROOT / "building-elevated" / "20261022-c9be347c",
    )
)
FRONT_M = 30.0
COLUMNS = ("bld:elevated",)


def columns(frame: pd.DataFrame, elevated: pd.DataFrame) -> np.ndarray:
    """The new column (COLUMNS) of `frame`'s rows."""
    t = elevated.drop_duplicates("building").set_index("building")
    e = t.elevated_m.reindex(frame.building.astype(str)).to_numpy(float)
    return (np.nan_to_num(e, nan=np.inf) < FRONT_M).astype(float)[:, None]


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    elevated: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with location's design of `frame` with the elevated track column
    appended."""
    if elevated is None:
        elevated = pd.read_parquet(ELEVATED_SNAPSHOT / "elevated.parquet")
    d = building_zones_location.design(frame, start, **tables)
    new = columns(frame, elevated)
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
    """Building zones with location's record, with the elevated track snapshot."""
    return building_zones_location.run_record(d) | {
        "building_elevated": str(ELEVATED_SNAPSHOT)
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-elevated`: fit on the split's training rows
    and save the run."""
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
