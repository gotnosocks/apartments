"""L2 (`rentfrontier.drift_building_phase_unitkn_level`) with a level for ads whose text
describes a smaller unit than the coded bedroom count.

L2 takes a row's size from the coded `bedrooms`. `rentfrontier.b0bedtext` reads the size
each listing's latest description states and writes two flags used here into a copy of L2's
dataset:

- `bed_flex_at`: flex wording for the coded count ("flex 2" on a row coded with 2
  bedrooms), so a room of the coded count comes from a wall, an alcove or a conversion;
- `bed_text_fewer`: every size the text states is below the coded count (a "studio duplex"
  coded with 1 bedroom).

On L2's held-out ads of the latest split (docs/notes/bed-text-2026-11-16.md), 5,019 carry
either flag. Their asks lie 0.38 of L2's predictive spread below its median on average,
against 0.07 over all held-out ads, and 2.5% of them fall below L2's 1st percentile, against
1.1%.

This design appends the ad column `ad:bed_text_smaller`, 1 where the row carries either
flag, and its unit mean `umean:ad:bed_text_smaller` over the row itself and its unit's
training rows priced on earlier days, as `building_zones_kitchen_sink.design` gives L2's
other ad columns. Both coefficients take the flag prior of `b0.prior_arrays`, and the
sampler draws them with the design's other global columns.

A row's flag comes from its own listing's description and its own coded count, and reads no
price. An ad takes no flag from its unit's other ads except through the unit mean, which
reads only earlier training rows.

A run needs `rentfrontier.run` to list this module and a dataset with the columns
`bed_flex_at` and `bed_text_fewer`.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import building_zones_floor_asof, drift, drift_building_phase_unitkn_level
from .building_zones_floor_asof3_unitmean import unit_groups
from .building_zones_kitchen_sink import append, past_means
from .drift_building_phase_unitkn_level import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    EDGES,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    LEVELS,
    PHASES,
    PROGRESS,
    ROW_DOF,
    TRACED,
    UNIT_DOF,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    make_sampler,
    months_since_previous,
    phase_index,
    phase_levels,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn-level-bedtext"
COLUMN = "ad:bed_text_smaller"
# The columns the flag comes from, written by `rentfrontier.b0bedtext`.
SOURCE = ("bed_flex_at", "bed_text_fewer")


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """L2's design of `frame`, with the smaller-unit flag and its unit mean."""
    check(frame)
    held = building_zones_floor_asof.held_out(frame, held)
    d = drift_building_phase_unitkn_level.design(frame, start, held=held, **kw)
    return with_flag(d, frame, held)


def check(frame: pd.DataFrame) -> None:
    """Refuse a frame lacking a column of SOURCE, naming the module that writes them."""
    missing = [c for c in SOURCE if c not in frame]
    if missing:
        raise ValueError(
            f"{NAME} needs the columns {' and '.join(SOURCE)}, and the frame has no "
            f"{' or '.join(missing)} (build them with python -m rentfrontier.b0bedtext)"
        )


def flag(frame: pd.DataFrame) -> np.ndarray:
    """1.0 on the rows of `frame` with `bed_flex_at` or `bed_text_fewer`, else 0.0."""
    check(frame)
    either = frame[list(SOURCE)].fillna(False).astype(bool).any(axis=1)
    return either.to_numpy(float)


def with_flag(d: Design, frame: pd.DataFrame, held: np.ndarray) -> Design:
    """`d` with COLUMN and its unit mean over the row and its unit's training rows priced
    on earlier days."""
    assert len(d.y) == len(frame)
    x = flag(frame)[:, None]
    d = append(d, [COLUMN], x)
    um = past_means(x, unit_groups(frame), frame.price_at, ~np.asarray(held, bool))
    return append(d, ["umean:" + COLUMN], um)


def run_record(d: Design) -> dict:
    """L2's record, with the flag's column, its source and its rows."""
    return drift_building_phase_unitkn_level.run_record(d) | {
        "bed_text": {
            "source": "the row's own bed_flex_at or bed_text_fewer (rentfrontier.b0bedtext)",
            "columns": [n for n in d.names if n in (COLUMN, "umean:" + COLUMN)],
            "rows": int(d.count.get(COLUMN, 0)),
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-level-bedtext`: fit on the
    split's training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
