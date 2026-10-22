"""Building zones with the unit's floor, plus transit, parks, the waterfront and noise together.

The model is building zones with the unit's floor (`rentfrontier.building_zones_floor`) with
the six `bld:` location columns of the three single-feature models appended, in this order:

    bld:log_station_km    rentfrontier.building_zones_transit
    bld:log1p_routes
    bld:log_park_km       rentfrontier.building_zones_parks
    bld:log_big_park_km
    bld:log_water_km
    bld:log1p_noise       rentfrontier.building_zones_noise

Each column comes from its own model's snapshot and `columns` function, so a building gets
exactly the values it gets in that model.

    python -m rentfrontier.run --model building-zones-location --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import (
    b0,
    building_zones_floor,
    building_zones_noise,
    building_zones_parks,
    building_zones_transit,
)
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

NAME = "building-zones-location"
PARTS = (
    (building_zones_transit, "transit", "TRANSIT_SNAPSHOT", "transit.parquet"),
    (building_zones_parks, "parks", "PARKS_SNAPSHOT", "parks.parquet"),
    (building_zones_noise, "noise", "NOISE_SNAPSHOT", "noise.parquet"),
)
COLUMNS = tuple(c for module, *_ in PARTS for c in module.COLUMNS)


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    transit: pd.DataFrame | None = None,
    parks: pd.DataFrame | None = None,
    noise: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with the unit's floor's design of `frame` with the transit, parks and
    noise columns appended."""
    given = {"transit": transit, "parks": parks, "noise": noise}
    d = building_zones_floor.design(frame, start, **tables)
    blocks = []
    for module, key, snapshot, file in PARTS:
        t = given[key]
        if t is None:
            t = pd.read_parquet(getattr(module, snapshot) / file)
        blocks.append(module.columns(frame, t))
    new = np.hstack(blocks)
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
    """Building zones with the unit's floor's record, with the three location snapshots."""
    return building_zones_floor.run_record(d) | {
        "building_transit": str(building_zones_transit.TRANSIT_SNAPSHOT),
        "building_parks": str(building_zones_parks.PARKS_SNAPSHOT),
        "building_noise": str(building_zones_noise.NOISE_SNAPSHOT),
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-location`: fit on the split's training rows
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
