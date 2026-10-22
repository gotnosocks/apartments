"""Building zones with building means, with the means and the features under them taken from
the split's training rows.

The model is building zones with building means (`rentfrontier.building_zones_mundlak`) on the
as-of floor design (`rentfrontier.building_zones_floor_asof`). The building means model averages
each unit column over every row of the building in the frame, held-out rows included. Here I
average over the building's training rows only and give the mean to all of its rows. A building
with no training row takes the mean over all training rows, and its `bld:mean_log_floor` the
mean log floor over training rows with a known floor. On the latest split every held-out row's
unit has a training row, so no building of that split needs the fallback.

    python -m rentfrontier.run --model building-zones-mundlak-asof --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import b0, building_zones_floor_asof
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
from .building_zones_mundlak import COLUMNS, MEANS, row_floor

NAME = "building-zones-mundlak-asof"


def columns(x: np.ndarray, names, site: np.ndarray, train: np.ndarray) -> np.ndarray:
    """The building means (COLUMNS) of design `x` over the rows in `train`, each row given its
    site's."""
    train = np.asarray(train, bool)
    n = int(site.max()) + 1
    w = train.astype(float)
    rows = np.bincount(site, w, minlength=n)
    out = []
    for _, cols in MEANS:
        v = sum((x[:, names.index(c)] for c in cols if c in names), np.zeros(len(x)))
        fill = v[train].mean() if train.any() else 0.0
        s = np.bincount(site, v * w, minlength=n)
        out.append(np.where(rows > 0, s / np.maximum(rows, 1), fill)[site])
    lf = np.log(row_floor(x, names))
    known = ~np.isnan(lf) & train
    k_rows = np.bincount(site[known], minlength=n).astype(float)
    k_sum = np.bincount(site[known], lf[known], minlength=n)
    fill = lf[known].mean() if known.any() else 0.0
    out.append(np.where(k_rows > 0, k_sum / np.maximum(k_rows, 1), fill)[site])
    return np.column_stack(out)


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **tables
) -> Design:
    """The as-of floor design of `frame` with the training rows' building means appended."""
    held = building_zones_floor_asof.held_out(frame, held)
    d = building_zones_floor_asof.design(frame, start, held=held, **tables)
    new = columns(d.x, list(d.names), d.site, ~held)
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
    """The as-of floor model's record, with the building means' columns."""
    return building_zones_floor_asof.run_record(d) | {
        "building_means": {n: list(c) for n, c in MEANS}
        | {"bld:mean_log_floor": ["log floor, known floors"]},
        "building_means_rows": "training",
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-mundlak-asof`: fit on the split's training rows
    and save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    building_zones_floor_asof.SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
