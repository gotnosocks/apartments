"""Building zones with the unit's floor, plus each building's mean of its unit columns.

The model is building zones with the unit's floor (`rentfrontier.building_zones_floor`) with
nine more `bld:` columns. Each is a building's mean, over all its rows in the frame, of a
column that changes between ads of the building:

    bld:mean_log_size_rel          unit:log_size_rel
    bld:mean_size_unknown          unit:size_unknown
    bld:mean_size_imputed          unit:size_imputed
    bld:mean_laundry_in_unit       unit:laundry_in_unit
    bld:mean_laundry_in_building   unit:laundry_in_building
    bld:mean_dishwasher            unit:dishwasher
    bld:mean_garden                unit:garden
    bld:mean_floor_unknown         either floor-unknown flag
    bld:mean_log_floor             log floor over the rows with a known floor (the floor
                                   capped as in the curves), and the mean over every row with
                                   a known floor for a building with none

The floor model gives each building a level drawn around its map value, independent of the
unit columns. On rents simulated from that model, the unit coefficients came back biased the
same way in every run (docs/notes/simulated-recovery-results-2026-10-22.md): buildings with
bigger units, in-unit laundry and dishwashers have higher levels, and a partially pooled level
leaves part of that difference to the unit columns. With the building means in the design, the
means take up the between-building part and the unit coefficients rest on differences within
a building, as in a fixed-effects fit (Mundlak 1978). The means are built from ad features, not
prices, so the latest split's held-out rows add no rent information to them.

    python -m rentfrontier.run --model building-zones-mundlak --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import b0, building_zones_floor
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

NAME = "building-zones-mundlak"
MEANS = (
    ("bld:mean_log_size_rel", ("unit:log_size_rel",)),
    ("bld:mean_size_unknown", ("unit:size_unknown",)),
    ("bld:mean_size_imputed", ("unit:size_imputed",)),
    ("bld:mean_laundry_in_unit", ("unit:laundry_in_unit",)),
    ("bld:mean_laundry_in_building", ("unit:laundry_in_building",)),
    ("bld:mean_dishwasher", ("unit:dishwasher",)),
    ("bld:mean_garden", ("unit:garden",)),
    (
        "bld:mean_floor_unknown",
        ("unit:elev_floor_unknown", "unit:walkup_floor_unknown"),
    ),
)
COLUMNS = tuple(n for n, _ in MEANS) + ("bld:mean_log_floor",)


def row_floor(x: np.ndarray, names) -> np.ndarray:
    """Each row's floor as the curve columns code it (capped), NaN where it is unknown."""
    floor = np.ones(len(x))
    for g, cap in building_zones_floor.GROUPS:
        for k in range(2, cap + 1):
            c = f"unit:{g}_f{k}"
            if c in names:
                floor[x[:, names.index(c)] == 1] = k
    for c in ("unit:elev_floor_unknown", "unit:walkup_floor_unknown"):
        if c in names:
            floor[x[:, names.index(c)] == 1] = np.nan
    return floor


def columns(x: np.ndarray, names, site: np.ndarray) -> np.ndarray:
    """The building means (COLUMNS) of the rows of design `x`, each row given its site's."""
    n = int(site.max()) + 1
    rows = np.bincount(site, minlength=n).astype(float)
    out = []
    for _, cols in MEANS:
        v = sum((x[:, names.index(c)] for c in cols if c in names), np.zeros(len(x)))
        out.append((np.bincount(site, v, minlength=n) / np.maximum(rows, 1))[site])
    lf = np.log(row_floor(x, names))
    known = ~np.isnan(lf)
    k_rows = np.bincount(site[known], minlength=n).astype(float)
    k_sum = np.bincount(site[known], lf[known], minlength=n)
    fill = lf[known].mean() if known.any() else 0.0
    site_lf = np.where(k_rows > 0, k_sum / np.maximum(k_rows, 1), fill)
    out.append(site_lf[site])
    return np.column_stack(out)


def design(frame: pd.DataFrame, start: pd.Timestamp | None = None, **tables) -> Design:
    """Building zones with the unit's floor's design of `frame` with the building means
    appended."""
    d = building_zones_floor.design(frame, start, **tables)
    new = columns(d.x, list(d.names), d.site)
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
    """Building zones with the unit's floor's record, with the building means' columns."""
    return building_zones_floor.run_record(d) | {
        "building_means": {n: list(c) for n, c in MEANS}
        | {"bld:mean_log_floor": ["log floor, known floors"]}
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-mundlak`: fit on the split's training rows and
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
