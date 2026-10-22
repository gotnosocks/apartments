"""Building zones with the unit's floor, plus a flag for a building facing a park.

The model is building zones with the unit's floor (`rentfrontier.building_zones_floor`) with
the park frontage column of `rentfrontier.building_zones_parkfront` appended:

    bld:park_front   1 when the building's outline lies within FRONT_M of the edge of a park of
                     5 acres or more, 0 otherwise

`building_zones_parkfront` adds the flag to the location model, whose six distance and noise
columns moved when the flag came in. Here the flag goes on the floor model alone, so its
estimate and its held-out gain don't mix with shifts in those columns.

    python -m rentfrontier.run --model building-zones-floor-parkfront --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import b0, building_zones_floor, building_zones_parkfront
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
from .building_zones_parkfront import COLUMNS

NAME = "building-zones-floor-parkfront"


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    park_front: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with the unit's floor's design of `frame` with the park frontage column
    appended."""
    if park_front is None:
        park_front = pd.read_parquet(
            building_zones_parkfront.PARK_FRONT_SNAPSHOT / "park_front.parquet"
        )
    d = building_zones_floor.design(frame, start, **tables)
    new = building_zones_parkfront.columns(frame, park_front)
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
    """Building zones with the unit's floor's record, with the park frontage snapshot."""
    return building_zones_floor.run_record(d) | {
        "building_park_front": str(building_zones_parkfront.PARK_FRONT_SNAPSHOT)
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-parkfront`: fit on the split's training
    rows and save the run."""
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
