"""Building zones with unit features, without truck routes and with a building gym.

The model is building zones with unit features (`rentfrontier.building_zones_unit`) with the
`bld:truck_through` column dropped and one column added from the building gym snapshot
(`rentfrontier.building_gym`):

    bld:gym   1 where at least half of the building's listings stating amenities list a gym

A building with no listing stating amenities counts as having no gym. On the latest split
those buildings carry 0.5% of training ads, so I leave out a flag of their own. Like the other
`bld:` columns, the gym column is constant within a building, and its coefficient joins the
global block with the Normal(0, 0.5) prior.

    python -m rentfrontier.run --model building-zones-gym --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, building_zones_unit
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

NAME = "building-zones-gym"
GYM_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_BUILDING_GYM",
        EXTERNAL_ROOT / "building-gym" / "20261021-752c7d3d",
    )
)
DROPPED = ("bld:truck_through",)
COLUMNS = ("bld:gym",)


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
) -> Design:
    """Building zones with unit features' design of `frame`, less DROPPED and with `bld:gym`
    appended. A building missing from `gyms` has no gym."""
    if gyms is None:
        gyms = pd.read_parquet(GYM_SNAPSHOT / "gym.parquet")
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
    keep = [j for j, n in enumerate(d.names) if n not in DROPPED]
    g = gyms.drop_duplicates("building").set_index("building").gym
    gym = frame.building.astype(str).map(g).fillna(0.0).to_numpy(float) == 1
    count = {n: v for n, v in d.count.items() if n not in DROPPED}
    count["bld:gym"] = int(gym.sum())
    return dataclasses.replace(
        d,
        x=np.hstack([d.x[:, keep], gym[:, None].astype(float)]),
        names=[d.names[j] for j in keep] + list(COLUMNS),
        count=count,
    )


def run_record(d: Design) -> dict:
    """Building zones with unit features' record, with the building gym snapshot."""
    return building_zones_unit.run_record(d) | {"building_gym": str(GYM_SNAPSHOT)}


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-gym`: fit on the split's training rows and
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
