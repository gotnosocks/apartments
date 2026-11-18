"""The base model (`rentfrontier.drift_building`) with a level for ads whose text describes
a smaller unit than the coded bedroom count.

`drift-building-phase-unitkn-level-bedtext` gave this flag to L2, and its pool led L2 by 224
held-out elpd on the latest split (docs/notes/bed-text-2026-11-16.md). L2 does not price the
Deals page: its market pool missed the convergence gate, and its backtest tied the base
model's (docs/notes/l2-market-2026-11-15.md). This module gives the same two columns to the
base model, so the flag can be tested on the fits Deals publishes from.

The design is `drift.design` of the frame, followed by
`drift_building_phase_unitkn_level_bedtext.with_flag`, which appends:

- `ad:bed_text_smaller`: 1 where the row carries `bed_flex_at` or `bed_text_fewer`, the
  columns `rentfrontier.b0bedtext` writes from each listing's latest description;
- `umean:ad:bed_text_smaller`: the mean of that column over the row itself and its unit's
  training rows priced on earlier days.

Both coefficients take the flag prior of `b0.prior_arrays`, and the sampler draws them with
the design's other global columns.

A row's flag comes from its own listing's description and its own coded count, and reads no
price. The unit mean reads only the row and earlier training rows. In a backtest the
description is the listing's latest one, as it is for the base model's other text columns,
so an ad's text may have been edited after the scoring day.

A run needs `rentfrontier.run` to list this module and a dataset with the columns
`bed_flex_at` and `bed_text_fewer`.

    python -m rentfrontier.run --model drift-building-bedtext --split market --name NAME
"""

from __future__ import annotations

import sys

import pandas as pd

from . import building_zones_floor_asof, drift, drift_building
from .drift_building import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    make_sampler,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)
from .drift_building_phase_unitkn_level_bedtext import COLUMN, check, with_flag

NAME = "drift-building-bedtext"


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The base model's design of `frame`, with the smaller-unit flag and its unit mean."""
    check(frame)
    held = building_zones_floor_asof.held_out(frame, held)
    return with_flag(drift.design(frame, start, held=held, **kw), frame, held)


def run_record(d: Design) -> dict:
    """The base model's record, with the flag's column, its source and its rows."""
    return drift_building.run_record(d) | {
        "bed_text": {
            "source": "the row's own bed_flex_at or bed_text_fewer (rentfrontier.b0bedtext)",
            "columns": [n for n in d.names if n in (COLUMN, "umean:" + COLUMN)],
            "rows": int(d.count.get(COLUMN, 0)),
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-bedtext`: fit on the split's training rows
    and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
