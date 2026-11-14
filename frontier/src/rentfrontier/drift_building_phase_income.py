"""The building model with noise phases (`rentfrontier.drift_building_phase`) and a factor
on the noise of the rows whose own listing's text describes an income-restricted unit.

`rentfrontier.b0textflags` writes the column `income_restricted_v2` into a copy of L1's
dataset: `b0income.INCOME` with the phrases the readers of 2026-11-13 found, and since
2026-11-14 a guard against a negation ("no income restrictions") just before the match
(docs/notes/text-flags-2026-11-13.md). S15 (docs/notes/income-flag-2026-11-14.md) emulated
L1 reading that column as a level and gained nothing, but L1's 80% interval covers only 0.56
of the held-out ads it marks, against 0.75 for other ads. On those ads a multiplier on L1's
noise scale and unit sd, picked on half of the buildings, gained about 64 elpd on the other
half. S15b found that the AMI tier stated in the ad explains little of that scatter, and
that a multiplier on the noise scale alone gains about as much.

So this design gives a marked row the phase model's noise times a factor k,

    s_i = sigma[group_i] * f[phase_i] * k^m_i,    m_i = 1 for a marked row, else 0.

The unit's process, the building's level and the rows' means are the phase model's, and the
phase model's coefficient for the old `income_restricted` flag stays in the means. In each
draw a held-out row's location and the sd of its unit's part come out the same whatever its
own mark, and the mark widens only the row's noise. So the predictive median, a median over
the draws, moves with the row's own mark only through the width of that noise. A marked
training row weighs less in its unit's and its building's estimates. log k takes the
Normal(0, `drift.PHASE_PRIOR`) prior of the phases' log factors.

Each row's mark comes from its own listing's description, so an ad of a unit takes no mark
from the unit's other ads, and a later ad's text marks no earlier row.

The sampler takes the crossed cells of phase and mark as its phases, with `Design.phase_map`
marking the free factors each cell multiplies, so the scale step draws the six phase factors
and k with the unit scales, sigma and nu (`drift.make_sampler`), as it does for
`drift_building_phase_duplex`. The run keeps each cell's factor as `phase_scale` and each
predicted row's cell as `pred_phase`, which `drift_score` and `drift_pool` read as they do
the phase model's.

    python -m rentfrontier.run --model drift-building-phase-income --split latest --name NAME

The run needs a dataset with the column `income_restricted_v2`.
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import drift, drift_building, drift_building_phase
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

NAME = "drift-building-phase-income"
PHASES = drift_building_phase.PHASES
# The marks, the reference first.
MARKS = ("other", "income-restricted")
# The column a row's mark comes from, with the module that writes it.
MARK_COLUMNS = {"income_restricted_v2": "rentfrontier.b0textflags"}
# The column of k among the free factors, after the six phase factors.
INCOME = len(PHASES) - 1


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The building model's design of `frame`, with each row's cell of lease phase and
    mark."""
    mark = mark_index(frame)
    d = drift_building.design(frame, start, held=held, **kw)
    assert len(d.y) == len(frame)
    cell = drift_building_phase.phase_index(frame) * len(MARKS) + mark
    return dataclasses.replace(d, phase=cell, phases=cells(), phase_map=cell_map())


def mark_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's mark, as its place in `MARKS`: 1 for a row with `income_restricted_v2`
    true, 0 for one with it false or missing."""
    missing = [c for c in MARK_COLUMNS if c not in frame]
    if missing:
        build = ", then ".join(f"python -m {m}" for m in MARK_COLUMNS.values())
        raise ValueError(
            f"drift-building-phase-income needs the column income_restricted_v2, and the "
            f"frame has no {' or '.join(missing)} (build it with {build})"
        )
    marked = np.zeros(len(frame), bool)
    for c in MARK_COLUMNS:
        marked |= frame[c].eq(True).fillna(False).to_numpy(bool)
    return marked.astype(np.int64)


def cells() -> tuple:
    """The cells' names, "phase|mark", phase-major, the reference (10-13, other) first."""
    return tuple(f"{p}|{m}" for p in PHASES for m in MARKS)


def cell_map() -> np.ndarray:
    """The (cells, 6 + 1) map from cells to the free factors: the phases but the
    reference, then k."""
    P, M = len(PHASES), len(MARKS)
    out = np.zeros((P * M, P))
    for p in range(P):
        for m in range(M):
            if p:
                out[p * M + m, p - 1] = 1
            if m:
                out[p * M + m, INCOME] = 1
    return out


def factors(phase_scale: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each phase's factor and k from the cells' factors (..., cells): the column of the
    unmarked rows, and the marked rows' factor in the reference phase."""
    f = np.asarray(phase_scale).reshape(*np.shape(phase_scale)[:-1], len(PHASES), -1)
    return f[..., :, 0], f[..., 0, 1]


def run_record(d: Design) -> dict:
    """The building model's record, with the phases, the marks, their prior and their
    rows."""
    count = np.bincount(d.phase, minlength=len(d.phases)).reshape(len(PHASES), -1)
    return drift_building.run_record(d) | {
        "phase": {
            "phases": list(PHASES),
            "reference": PHASES[0],
            "months_from": "the price_at of the same unit's previous ad in the dataset",
            "marks": list(MARKS),
            "mark_of": "the row's own income_restricted_v2 column "
            "(rentfrontier.b0textflags), marked when it is true",
            "cells": "phase|mark, phase-major; a marked cell's factor is its phase's "
            "times k",
            "log_factor_prior": f"Normal(0, {drift.PHASE_PRIOR})",
            "rows": {p: int(c) for p, c in zip(PHASES, count.sum(axis=1))},
            "mark_rows": {m: int(c) for m, c in zip(MARKS, count.sum(axis=0))},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-income`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
