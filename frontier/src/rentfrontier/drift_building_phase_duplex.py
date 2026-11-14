"""The building model with noise phases (`rentfrontier.drift_building_phase`) and a factor
on the noise of the rows of duplex apartments and of apartments called penthouses in their
text.

S7 of the causal screens (docs/notes/causal-screens-2026-11-13.md) read each listing's
description for an apartment on two or three levels, and `rentfrontier.b0duplex` writes
its pattern into a dataset as the column `duplex`. The phase model prices the duplex ads
right on average, but their squared gap from its median is 0.0114 against 0.0059 for the
other ads, and its 80% interval covers 0.719 of them. A duplex whose previous ad was the
same duplex with the same bedrooms has a squared gap of 0.0110, so the excess shows from one
ad of the unit to the next.

S14 (docs/notes/unusual-units-2026-11-13.md) found that the asks of ads calling the unit a
penthouse in their text scatter about as much wider than the phase model expects as the
duplexes' asks do, and `rentfrontier.b0penthouse` writes its text pattern into a dataset as
the column `penthouse`. Resampling buildings put a multiplier
on the phase model's noise scale and unit sd at 1.2 to 1.5 for those penthouses without
duplexes and at 1.3 to 1.4 for duplexes without penthouses. The two ranges overlap, so the
two kinds share a mark: a row is marked when its `duplex` or its `penthouse` is true.

So this design gives a marked row the phase model's noise times a factor k,

    s_i = sigma[group_i] * f[phase_i] * k^m_i,    m_i = 1 for a marked row, else 0.

The unit's process, the building's level and the rows' means are the phase model's. In
each draw a held-out row's location and the sd of its unit's part come out the same whatever
its own mark, and the mark widens only the row's noise. So the predictive median, a median
over the draws, moves with the row's own mark only through the width of that noise. A marked
training row weighs less in its unit's and its building's estimates. log k takes the
Normal(0, `drift.PHASE_PRIOR`) prior of the phases' log factors.

Each row's mark comes from its own listing's description (`rentfrontier.b0duplex`,
`rentfrontier.b0penthouse`). An ad of a unit takes no mark from the unit's other ads, so a
later ad's text marks no earlier row.

The sampler takes the crossed cells of phase and mark as its phases, with `Design.phase_map`
marking the free factors each cell multiplies, so the scale step draws the six phase factors
and k with the unit scales, sigma and nu (`drift.make_sampler`). The run keeps each cell's
factor as `phase_scale` and each predicted row's cell as `pred_phase`, which `drift_score`
and `drift_pool` read as they do the phase model's.

    python -m rentfrontier.run --model drift-building-phase-duplex --split latest --name NAME

The run needs a dataset with the columns `duplex` and `penthouse`.
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

NAME = "drift-building-phase-duplex"
PHASES = drift_building_phase.PHASES
# The marks, the reference first.
MARKS = ("other", "duplex or penthouse")
# The columns a row's mark comes from, each with the module that writes it.
MARK_COLUMNS = {
    "duplex": "rentfrontier.b0duplex",
    "penthouse": "rentfrontier.b0penthouse",
}
# The column of k among the free factors, after the six phase factors.
DUPLEX = len(PHASES) - 1


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
    """Each row's mark, as its place in `MARKS`: 1 for a row with `duplex` or `penthouse`
    true, 0 for one with each of them false or missing."""
    missing = [c for c in MARK_COLUMNS if c not in frame]
    if missing:
        build = ", then ".join(f"python -m {m}" for m in MARK_COLUMNS.values())
        raise ValueError(
            f"drift-building-phase-duplex needs the columns duplex and penthouse, and the "
            f"frame has no {' or '.join(missing)} (build them with {build})"
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
                out[p * M + m, DUPLEX] = 1
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
            "mark_of": "the row's own duplex column (rentfrontier.b0duplex) or its own "
            "penthouse column (rentfrontier.b0penthouse), marked when either is true",
            "cells": "phase|mark, phase-major; a marked cell's factor is its phase's "
            "times k",
            "log_factor_prior": f"Normal(0, {drift.PHASE_PRIOR})",
            "rows": {p: int(c) for p, c in zip(PHASES, count.sum(axis=1))},
            "mark_rows": {m: int(c) for m, c in zip(MARKS, count.sum(axis=0))},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-duplex`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
