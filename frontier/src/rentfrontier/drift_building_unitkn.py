"""The building model with a Student-t lasting level for each unit at 3 degrees of freedom
and the rows' degrees of freedom held at 2, without lease phases.

This is L1TKN (`rentfrontier.drift_building_phase_unitkn`) with the phases taken out: each
row's noise scale is its group's sigma, with no factor for the months since the unit's
previous ad, and the mean has no level for a phase. The design is the building model's
(`rentfrontier.drift_building`), so no column of it reads the dates of a unit's other ads.

A fit of this model next to L2 (`rentfrontier.drift_building_phase_unitkn_level`) on the
same rows measures the phases' whole contribution, the noise factors and the levels
together (docs/notes/no-phase-2026-11-16.md).

Sampler. The sweep is `drift.make_sampler`'s with `unit_t`, the units' degrees of freedom
fixed at `UNIT_DOF`, each unit's mixing scale drawn with u and the lasting level integrated
out (`unit_kap_collapsed`), and the rows' nu fixed at `ROW_DOF`. These are L1TKN's
settings, and the scale step draws sigma and unit_sd without phase factors.

    python -m rentfrontier.run --model drift-building-unitkn --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building, drift_building_phase_unitkn
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
    design,
    diagnostics,
    gp_spec,
    make_sampler,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-unitkn"

# The units' and the rows' degrees of freedom, L1TKN's values.
UNIT_DOF = drift_building_phase_unitkn.UNIT_DOF
ROW_DOF = drift_building_phase_unitkn.ROW_DOF


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with the building model's design and L1TKN's sweep settings."""
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
    """The building model's record, with the units' Student-t prior and both fixed
    degrees of freedom."""
    return drift_building.run_record(d) | {
        "unit_t": {
            "lasting_level": "Normal(0, unit_sd^2 / kap), kap ~ Gamma(nu / 2, rate nu / 2)",
            "unit_dof": UNIT_DOF,
            "kap_step": "collapsed",
        },
        "row_dof_fixed": ROW_DOF,
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-unitkn`: fit on the split's training rows
    and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
