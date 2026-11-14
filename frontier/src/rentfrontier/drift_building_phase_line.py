"""The building model with noise phases (`rentfrontier.drift_building_phase`) and a level
for each line of a building, between the building's level and the unit's.

A line is the units of one building with the same bedrooms and full baths, and each unit's
lasting level centers on its line's,

    s_k ~ Normal(l_line(k), ss^2),    l_m ~ Normal(0, line_sd^2).

The screen of 2026-11-12 (docs/notes/line-level-screen-2026-11-12.md) moved the phase
model's held-out predictions by the shrunk mean residual of the earlier held-out ads of other
units in the same line, and gained 750 elpd (SE 83). Its design, its priors and its rows'
means are otherwise the phase model's. `rentfrontier.drift_line` holds the sampler, which
integrates the lines out with the units and the buildings' levels and paths, and the rules
that give each unit its line.

    python -m rentfrontier.run --model drift-building-phase-line --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import pandas as pd

from . import (
    building_zones_floor_asof,
    drift,
    drift_building_phase,
    drift_line,
)
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
    Priors,
    gp_spec,
    site_rows,
    site_zone,
    split_index,
    wave_matrix,
    years,
)
from .drift_line import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    Design,
    Settings,
    diagnostics,
    make_sampler,
    subset,
    summarize,
)

NAME = "drift-building-phase-line"
PHASES = drift_building_phase.PHASES


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The phase model's design of `frame`, with each row's line (`drift_line.line_index`).
    A line with no training row under the split's held-out rows `held` (the split's own by
    default) carries -1."""
    d = drift_building_phase.design(frame, start, held=held, **kw)
    line, lines = drift_line.line_index(
        frame, building_zones_floor_asof.held_out(frame, held)
    )
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        line=line,
        lines=lines,
    )


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift_line.run` with the building model's local-drift terms."""
    return drift_line.run(
        d, priors, settings, log, checkpoint, groups=drift.groups_of(d, GROUPS)
    )


def run_record(d: Design) -> dict:
    """The phase model's record, with the lines'."""
    return drift_building_phase.run_record(d) | drift_line.run_record(d)


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-line`: fit on the split's training rows
    and save the run."""
    drift_line.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
