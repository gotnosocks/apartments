"""L1TKN (`rentfrontier.drift_building_phase_unitkn`) with L2's level in the mean for each
lease phase (`rentfrontier.drift_building_phase_level`).

L1TKN gives each unit's lasting level a Student-t prior at 3 degrees of freedom and holds
the rows' nu at 2. L2 adds a 0/1 column for each lease phase other than 10-13 months to
L1's design, so a phase moves a row's expected ask as well as its noise scale. This module
puts the two together: the design is L2's, built by `drift_building_phase_level.design`,
and the sweep is L1TKN's, run by `drift_building_phase_unitkn.run`. The six coefficients
take the Normal(0, 0.5) prior of a flag and are drawn with the design's other global
columns, as in L2.

A relist within two months tends to follow an ad that did not let at its first ask. Under
L1TKN's heavy-tailed unit level, a unit whose few ads are all relists can keep the relists'
discount as its own lasting level, so the phase coefficients and the units' levels share
those ads. The rehearsal in docs/notes/unitkn-rehearsals-2026-11-14.md checks that the
sweep still mixes on the six coefficients.

    python -m rentfrontier.run --model drift-building-phase-unitkn-level --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building_phase_level, drift_building_phase_unitkn
from .drift_building_phase_level import LEVELS, design, phase_levels  # noqa: F401
from .drift_building_phase_unitkn import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    EDGES,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
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
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn-level"


def run_record(d: Design) -> dict:
    """L1TKN's record, with the phase levels' columns and their prior from L2's."""
    return drift_building_phase_unitkn.run_record(d) | {
        "phase": drift_building_phase_level.run_record(d)["phase"]
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-level`: fit on the split's
    training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
