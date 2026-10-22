"""Building zones with location, plus a flag for a building facing a park.

The model is building zones with location (`rentfrontier.building_zones_location`) with one
more `bld:` column, read from the park frontage snapshot (`rentfrontier.building_park_front`):

    bld:park_front   1 when the building's outline lies within FRONT_M of the edge of a park of
                     5 acres or more, 0 otherwise

FRONT_M takes in a building across a street or an avenue from the park, and one on the park's
own edge. `bld:log_park_km` and `bld:log_big_park_km` measure from the building's point and
change slowly across a neighborhood. This column changes between a building on the park and the
one behind it. A building with no outline gets 0.

    python -m rentfrontier.run --model building-zones-parkfront --split latest --name NAME
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

NAME = "building-zones-parkfront"
PARK_FRONT_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_BUILDING_PARK_FRONT",
        EXTERNAL_ROOT / "building-park-front" / "20261022-5ddc0e5d",
    )
)
FRONT_M = 40.0
COLUMNS = ("bld:park_front",)


def columns(frame: pd.DataFrame, front: pd.DataFrame) -> np.ndarray:
    """The new column (COLUMNS) of `frame`'s rows."""
    t = front.drop_duplicates("building").set_index("building")
    e = t.park_edge_m.reindex(frame.building.astype(str)).to_numpy(float)
    return (np.nan_to_num(e, nan=np.inf) < FRONT_M).astype(float)[:, None]


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    park_front: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with location's design of `frame` with the park frontage column
    appended."""
    if park_front is None:
        park_front = pd.read_parquet(PARK_FRONT_SNAPSHOT / "park_front.parquet")
    d = building_zones_location.design(frame, start, **tables)
    new = columns(frame, park_front)
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
    """Building zones with location's record, with the park frontage snapshot."""
    return building_zones_location.run_record(d) | {
        "building_park_front": str(PARK_FRONT_SNAPSHOT)
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-parkfront`: fit on the split's training rows
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
