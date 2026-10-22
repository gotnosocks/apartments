"""Building zones with location, plus a flag for a building on the waterfront.

The model is building zones with location (`rentfrontier.building_zones_location`) with one
more `bld:` column, read from the parks snapshot (`rentfrontier.building_parks`) that already
gives the location model its `bld:log_water_km`:

    bld:waterfront   1 when the building's point lies within FRONT_KM of the shoreline,
                     0 otherwise

`bld:log_water_km` changes smoothly with distance, so it spreads a waterfront premium over the
blocks behind the shore. This column steps between the first row of buildings and the rest.
FRONT_KM takes in a building with a highway or an esplanade between it and the water, and a lot
of 30 to 60 m depth. A building with no point gets 0.

    python -m rentfrontier.run --model building-zones-waterfront --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import b0, building_zones_location, building_zones_parks
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
    run_record,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)

NAME = "building-zones-waterfront"
FRONT_KM = 0.15
COLUMNS = ("bld:waterfront",)


def columns(frame: pd.DataFrame, parks: pd.DataFrame) -> np.ndarray:
    """The new column (COLUMNS) of `frame`'s rows."""
    t = parks.drop_duplicates("building").set_index("building")
    w = t.water_km.reindex(frame.building.astype(str)).to_numpy(float)
    return (np.nan_to_num(w, nan=np.inf) < FRONT_KM).astype(float)[:, None]


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    parks: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with location's design of `frame` with the waterfront column appended."""
    if parks is None:
        parks = pd.read_parquet(building_zones_parks.PARKS_SNAPSHOT / "parks.parquet")
    d = building_zones_location.design(frame, start, parks=parks, **tables)
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


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-waterfront`: fit on the split's training rows
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
