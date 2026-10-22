"""Building zones with location, plus a flag for a building standing mid-block on an avenue.

The model is building zones with location (`rentfrontier.building_zones_location`) with one
more `bld:` column, read from the frontage table (`rentfrontier.frontage`):

    bld:avenue_midblock   1 when the widest street the building faces is over 60 ft curb to
                          curb and its lot is not a corner lot, 0 otherwise

Streets over 60 ft are mostly avenues, crosstown streets such as 14th and 23rd, and boulevards.
A corner building on such a street also faces a side street, and its corner units often look
onto both. A mid-block building faces only the wide street, so its street-side units get the
traffic with no quieter side. A building with no known width or no known corner gets 0.

    python -m rentfrontier.run --model building-zones-avenue --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import b0, building_zones_front, building_zones_location
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

NAME = "building-zones-avenue"
WIDE_FT = 60.0
COLUMNS = ("bld:avenue_midblock",)


def columns(frame: pd.DataFrame, frontage: pd.DataFrame) -> np.ndarray:
    """The new column (COLUMNS) of `frame`'s rows."""
    f = frontage.drop_duplicates("building").set_index("building")
    f = f.reindex(frame.building.astype(str))
    w = f.front_width_ft.to_numpy(float)
    corner = f.corner.to_numpy(float)
    wide = np.isfinite(w) & (np.where(np.isfinite(w), w, 0.0) > WIDE_FT)
    return (wide & (corner == 0)).astype(float)[:, None]


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    frontage: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with location's design of `frame` with the avenue column appended."""
    if frontage is None:
        frontage = pd.read_parquet(building_zones_front.FRONTAGE)
    d = building_zones_location.design(frame, start, **tables)
    new = columns(frame, frontage)
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
    """Building zones with location's record, with the frontage table."""
    return building_zones_location.run_record(d) | {
        "frontage": str(building_zones_front.FRONTAGE)
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-avenue`: fit on the split's training rows
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
