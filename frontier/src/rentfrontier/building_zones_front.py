"""Building zones with attributes, plus each building's street frontage.

The model is building zones with attributes (`rentfrontier.building_zones_attrs`) at its 1 km
surfaces, with six more building columns from the frontage table (`rentfrontier.frontage`):

1. The width of the widest street the building faces, curb to curb, with the parallel roadways
   of a divided boulevard added up, in bands against 40 ft or less:
   `bld:front_41_60`, `bld:front_61_80` and `bld:front_over_80`. `bld:front_unknown` marks a
   building with no outline or no street with a width, about 4% of the training rows.
2. `bld:corner`, a corner lot as MapPLUTO's lot type gives it, or the street geometry where
   the lot type is 0 or missing, against every other lot. `bld:corner_unknown` marks the
   buildings neither rule decides.

I use bands rather than log width because the widths split into side streets around 30 ft and
avenues from 56 to 84 ft, and an avenue's premium has no reason to grow smoothly from a side
street's. Like the attributes, each column is constant within a building, so it joins the
rows' fixed design and its coefficient joins the global block with the Normal(0, 0.5) prior.

    python -m rentfrontier.run --model building-zones-front --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, building_zones_attrs
from .building_zones_attrs import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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

NAME = "building-zones-front"
FRONTAGE = Path(
    os.environ.get(
        "FRONTIER_FRONTAGE",
        EXTERNAL_ROOT / "frontage" / "20261020-fbf9a82" / "frontage.parquet",
    )
)
COLUMNS = (
    "bld:front_41_60",
    "bld:front_61_80",
    "bld:front_over_80",
    "bld:front_unknown",
    "bld:corner",
    "bld:corner_unknown",
)


def columns(frame: pd.DataFrame, frontage: pd.DataFrame) -> np.ndarray:
    """The frontage columns (COLUMNS) of `frame`'s rows."""
    f = frontage.drop_duplicates("building").set_index("building")
    f = f.reindex(frame.building.astype(str))
    w = f.front_width_ft.to_numpy(float)
    known = np.isfinite(w)
    w = np.where(known, w, 0.0)
    corner = f.corner.to_numpy(float)
    return np.column_stack(
        [
            known & (w > 40) & (w <= 60),
            known & (w > 60) & (w <= 80),
            known & (w > 80),
            ~known,
            corner == 1,
            ~np.isfinite(corner),
        ]
    ).astype(float)


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
    nj_registry: pd.DataFrame | None = None,
    attrs: pd.DataFrame | None = None,
    footprints: pd.DataFrame | None = None,
    frontage: pd.DataFrame | None = None,
) -> Design:
    """Building zones with attributes' design of `frame` with the frontage columns appended.
    I leave out a column no row sets."""
    if frontage is None:
        frontage = pd.read_parquet(FRONTAGE)
    d = building_zones_attrs.design(
        frame,
        start,
        registry=registry,
        nj_registry=nj_registry,
        attrs=attrs,
        footprints=footprints,
    )
    new = columns(frame, frontage)
    count = dict(d.count)
    keep = []
    for j, n in enumerate(COLUMNS):
        count[n] = int(np.abs(new[:, j]).sum())
        if count[n] > 0:
            keep.append(j)
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, new[:, keep]]),
        names=list(d.names) + [COLUMNS[j] for j in keep],
        count=count,
    )


def run_record(d: Design) -> dict:
    """Building zones with attributes' record, with the frontage table."""
    return building_zones_attrs.run_record(d) | {"frontage": str(FRONTAGE)}


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-front`: fit on the split's training rows and
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
