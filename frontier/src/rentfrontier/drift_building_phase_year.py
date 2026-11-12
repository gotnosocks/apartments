"""The building model with noise phases (`rentfrontier.drift_building_phase`) and a noise
factor for each calendar year.

The phase model's held-out asks of 2020 to 2022 are covered 0.736 by the 80% interval
against 0.81 to 0.82 in the other years, and the outlier sprint found the same spread on
training rows of those years (docs/notes/outlier-sprint-2026-11-11.md). This design
multiplies each row's noise scale by a factor for the calendar year of its price_at:

    s_i = sigma[group_i] * f[phase_i] * g[year_i]

f is the phase model's, with f = 1 for the phase 10-13. `YEARS` lists the years. The rows
of 2011 to 2013 are few (3,156 training rows in the dataset of 2026-11-12), so they join
2014, and a row after the last year takes the last year's factor. g = 1 for
`REFERENCE_YEAR`, and each other year's log g takes the Normal(0, `drift.PHASE_PRIOR`)
prior the phases' log factors take.

The sampler sees the crossed cells of phase and year as its phases, with
`Design.phase_map` marking the two free factors each cell multiplies, so the scale step
draws the six phase and twelve year log factors with the unit scales, sigma and nu
(`drift.make_sampler`). The run keeps each cell's factor as `phase_scale` and each
predicted row's cell as `pred_phase`, which `drift_score` and `drift_pool` read as they
do the phase model's.

    python -m rentfrontier.run --model drift-building-phase-year --split latest --name NAME
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

NAME = "drift-building-phase-year"
PHASES = drift_building_phase.PHASES
# The years, the reference first. 2024 has 122,144 training rows and 26,316 held-out ads
# in the dataset of 2026-11-12 and lies in the steady years after 2022.
REFERENCE_YEAR = 2024
FIRST_YEAR, LAST_YEAR = 2014, 2026
YEARS = (REFERENCE_YEAR,) + tuple(
    y for y in range(FIRST_YEAR, LAST_YEAR + 1) if y != REFERENCE_YEAR
)


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The building model's design of `frame`, with each row's cell of lease phase and
    year."""
    d = drift_building.design(frame, start, held=held, **kw)
    assert len(d.y) == len(frame)
    cell = drift_building_phase.phase_index(frame) * len(YEARS) + year_index(frame)
    return dataclasses.replace(d, phase=cell, phases=cells(), phase_map=cell_map())


def year_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's year, as its place in `YEARS`: the year of its price_at in UTC, with
    the years before `FIRST_YEAR` taken as it and those after `LAST_YEAR` as it."""
    at = pd.to_datetime(frame.price_at, utc=True).dt.year.to_numpy()
    at = np.clip(at, FIRST_YEAR, LAST_YEAR)
    return pd.Index(YEARS).get_indexer(at).astype(np.int64)


def cells() -> tuple:
    """The cells' names, "phase|year", phase-major, the reference (10-13, 2024) first."""
    return tuple(f"{p}|{y}" for p in PHASES for y in YEARS)


def cell_map() -> np.ndarray:
    """The (cells, 6 + 12) map from cells to the free factors: the phases but the
    reference, then the years but the reference."""
    P, Y = len(PHASES), len(YEARS)
    out = np.zeros((P * Y, P - 1 + Y - 1))
    for p in range(P):
        for y in range(Y):
            if p:
                out[p * Y + y, p - 1] = 1
            if y:
                out[p * Y + y, P - 1 + y - 1] = 1
    return out


def factors(phase_scale: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each phase's factor and each year's factor from the cells' factors
    (..., cells): the column of the reference year and the row of the reference phase."""
    f = np.asarray(phase_scale).reshape(*np.shape(phase_scale)[:-1], len(PHASES), -1)
    return f[..., :, 0], f[..., 0, :]


def run_record(d: Design) -> dict:
    """The building model's record, with the phases, the years, their prior and their
    rows."""
    count = np.bincount(d.phase, minlength=len(d.phases)).reshape(len(PHASES), -1)
    return drift_building.run_record(d) | {
        "phase": {
            "phases": list(PHASES),
            "reference": PHASES[0],
            "months_from": "the price_at of the same unit's previous ad in the dataset",
            "years": list(YEARS),
            "reference_year": REFERENCE_YEAR,
            "year_of": f"the price_at in UTC, clipped to {FIRST_YEAR} to {LAST_YEAR}",
            "cells": "phase|year, phase-major; a cell's factor is its phase's times its year's",
            "log_factor_prior": f"Normal(0, {drift.PHASE_PRIOR})",
            "rows": {p: int(c) for p, c in zip(PHASES, count.sum(axis=1))},
            "year_rows": {str(y): int(c) for y, c in zip(YEARS, count.sum(axis=0))},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-year`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
