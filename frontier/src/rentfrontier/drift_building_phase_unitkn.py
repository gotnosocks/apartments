"""L1TK (`rentfrontier.drift_building_phase_unitk`) with the rows' degrees of freedom nu
held at 2, as the units' are held at 3.

Against L1 this model makes two changes: L1T's Student-t lasting level for each unit, and
the rows' fixed nu. L1TK's six-chain check on the 1-in-90 building sample left unit_sd
moving slowly, along a direction where unit_sd, nu, sigma and the rows' mixing scales
trade the size of a unit's lasting departure against the ad's
(docs/notes/l1-row-dof-fixed-2026-11-13.md). With nu fixed the scale step and the noise
step no longer move along nu, and the direction loses a coordinate.

The value 2 is a round prior value. The rows' Student-t at 2 degrees of freedom has a
finite mean and an infinite variance: a heavy tail of the kind the ads' typos and
mislabeled units give. L1T's training posterior put nu at 1.99 (1.975 to 2.009), so the
model moves little from L1T's.

Sampler. The sweep is L1TK's with `drift.make_sampler`'s `row_dof_fixed=ROW_DOF`: the
noise step skips nu's slice update and still draws sigma and lam, and the scale step
leaves log nu out of its coordinates.

    python -m rentfrontier.run --model drift-building-phase-unitkn --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building_phase_unitk
from .drift_building_phase_unitk import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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
    UNIT_DOF,
    ZONES,
    Design,
    Priors,
    Settings,
    design,
    diagnostics,
    gp_spec,
    make_sampler,
    months_since_previous,
    phase_index,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn"

# The rows' degrees of freedom.
ROW_DOF = 2.0


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with L1TK's model and sweep, and the rows' nu at `ROW_DOF`."""
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        groups=drift.groups_of(d, GROUPS),
        unit_t=True,
        unit_dof_fixed=UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=ROW_DOF,
    )


def run_record(d: Design) -> dict:
    """L1TK's record, with the rows' fixed nu."""
    return drift_building_phase_unitk.run_record(d) | {"row_dof_fixed": ROW_DOF}


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
