"""L1, the building model with a noise scale for each lease phase
(`rentfrontier.drift_building_phase`), with a level in the mean for each lease phase as well.

L1 lets a phase change how far an ad strays from its unit's level, and leaves the ad's
expected ask where it is. The phases also differ in their expected ask. A relist within two
months follows an ad that did not let at its first ask, so it tends to ask less than the
unit's usual level. An ad two years or more after the last one comes after a renewal, and
renewals raise rents more slowly than the market. So this design adds a 0/1 column for each
phase other than the reference:

    phase:none, phase:0-2, phase:3-9, phase:14-21, phase:22-25, phase:26+

and a row's mean gains the coefficient of its phase's column, or nothing in the reference
phase, 10-13 months. Each coefficient takes the Normal(0, 0.5) prior that `b0.prior_arrays`
gives a flag, and the sampler draws them with the design's other columns. A row's phase
comes from the price_at dates of its unit's ads alone (`drift_building_phase.phase_index`),
so building a held-out row's columns uses no rent.

The noise scales are L1's: s_i = sigma[group_i] * f[phase_i].

    python -m rentfrontier.run --model drift-building-phase-level --split latest --name NAME
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import building_zones_kitchen_sink, drift, drift_building_phase
from .drift_building_phase import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    EDGES,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    PHASES,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    make_sampler,
    months_since_previous,
    phase_index,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-level"
# The columns of the phase levels, one for each phase after the reference, `PHASES[0]`.
LEVELS = tuple(f"phase:{p}" for p in PHASES[1:])


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """L1's design of `frame`, with a level column for each lease phase but the reference."""
    return phase_levels(drift_building_phase.design(frame, start, held=held, **kw))


def phase_levels(d: Design) -> Design:
    """`d` with a 0/1 column for each phase after the reference, set on the rows in it."""
    assert tuple(d.phases) == PHASES, "the levels follow L1's phases"
    x = (d.phase[:, None] == np.arange(1, len(d.phases))[None, :]).astype(float)
    return building_zones_kitchen_sink.append(d, list(LEVELS), x)


def run_record(d: Design) -> dict:
    """L1's record, with the phase levels' columns and their prior."""
    record = drift_building_phase.run_record(d)
    record["phase"] |= {
        "levels": [n for n in LEVELS if n in d.names],
        "level_prior": "Normal(0, 0.5), a flag's prior in b0.prior_arrays",
    }
    return record


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-level`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
