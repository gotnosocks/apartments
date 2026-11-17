"""L2 with the smaller-unit flag on the ad and a column for units ever advertised that way.

`drift-building-phase-unitkn-level-bedtext` gave the flag of `rentfrontier.b0bedtext` to L2
as an ad column and its unit mean over the row and the unit's earlier training rows. Its
pool led L2 by 224 held-out elpd, and `docs/notes/bed-text-2026-11-16.md` splits that lead:
the 5,288 unflagged held-out ads in units with a flagged earlier ad lost 107 (SE 15). A
unit's mean over earlier rows changes from one ad of the unit to the next, so the model
moved those ads by a coefficient of -0.059 times a share, while L2's unit level had already
priced the unit.

This design keeps the ad column `ad:bed_text_smaller` and replaces the unit mean with
`uever:ad:bed_text_smaller`: 1 where the row itself or any training row of its unit carries
the flag. The column holds a single value over a unit's training rows, so it shifts the
unit as a whole, and the ad column is left with the difference between a unit's flagged and
unflagged ads. Both coefficients take the flag prior of `b0.prior_arrays`.

A row's flag comes from its own listing's description and its own coded count, and reads no
price. The unit column reads the flags of the unit's training rows on any day, which are
text and coded counts, and reads no held-out row but the row itself.

A run needs `rentfrontier.run` to list this module and a dataset with the columns
`bed_flex_at` and `bed_text_fewer`.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import building_zones_floor_asof, drift, drift_building_phase_unitkn_level
from .building_zones_floor_asof3_unitmean import unit_groups
from .building_zones_floor_asof3_unitmean import unit_means
from .building_zones_kitchen_sink import append
from .drift_building_phase_unitkn_level_bedtext import COLUMN, SOURCE, check, flag
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

NAME = "drift-building-phase-unitkn-level-bedunit"
EVER = "uever:" + COLUMN


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """L2's design of `frame`, with the smaller-unit flag and the unit's ever-flagged
    column."""
    check(frame)
    held = building_zones_floor_asof.held_out(frame, held)
    d = drift_building_phase_unitkn_level.design(frame, start, held=held, **kw)
    return with_flag(d, frame, held)


def ever(x: np.ndarray, group: np.ndarray, train: np.ndarray) -> np.ndarray:
    """1.0 on the rows with `x` above 0 themselves or on a training row of their group."""
    share = unit_means(x[:, None], group, train)[:, 0]
    return ((x > 0) | (share > 0)).astype(float)


def with_flag(d: Design, frame: pd.DataFrame, held: np.ndarray) -> Design:
    """`d` with COLUMN and EVER, the flag over the row and its unit's training rows."""
    assert len(d.y) == len(frame)
    x = flag(frame)
    d = append(d, [COLUMN], x[:, None])
    e = ever(x, unit_groups(frame), ~np.asarray(held, bool))
    return append(d, [EVER], e[:, None])


def run_record(d: Design) -> dict:
    """L2's record, with the two columns, their source and their rows."""
    return drift_building_phase_unitkn_level.run_record(d) | {
        "bed_text": {
            "source": "the row's own bed_flex_at or bed_text_fewer (rentfrontier.b0bedtext)",
            "columns": [n for n in d.names if n in (COLUMN, EVER)],
            "rows": int(d.count.get(COLUMN, 0)),
            "rows_in_units_ever_flagged": int(d.count.get(EVER, 0)),
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-level-bedunit`: fit on the
    split's training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
