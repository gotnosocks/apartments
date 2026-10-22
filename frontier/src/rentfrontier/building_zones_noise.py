"""Building zones with building means, plus the outdoor noise complaints around each building.

The model is building zones with building means (`rentfrontier.building_zones_mundlak`) with
one more `bld:` column, read from the noise snapshot (`rentfrontier.building_noise`):

    bld:log1p_noise   log(1 + outdoor 311 noise complaints a year within 150 m, 2020 to 2025)

A building missing from the snapshot gets the snapshot's median.

    python -m rentfrontier.run --model building-zones-noise --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, building_zones_mundlak
from .building_zones_mundlak import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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

NAME = "building-zones-noise"
NOISE_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_BUILDING_NOISE",
        EXTERNAL_ROOT / "building-noise" / "20261022-208c44b3",
    )
)
COLUMNS = ("bld:log1p_noise",)


def columns(frame: pd.DataFrame, noise: pd.DataFrame) -> np.ndarray:
    """The new column (COLUMNS) of `frame`'s rows."""
    t = noise.drop_duplicates("building").set_index("building")
    t = t.reindex(frame.building.astype(str))
    v = t.noise_per_year.fillna(noise.noise_per_year.median()).to_numpy(float)
    return np.log1p(v)[:, None]


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    noise: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """Building zones with building means' design of `frame` with the noise column
    appended."""
    if noise is None:
        noise = pd.read_parquet(NOISE_SNAPSHOT / "noise.parquet")
    d = building_zones_mundlak.design(frame, start, **tables)
    new = columns(frame, noise)
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
    """Building zones with building means' record, with the noise snapshot."""
    return building_zones_mundlak.run_record(d) | {
        "building_noise": str(NOISE_SNAPSHOT)
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-noise`: fit on the split's training rows and
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
