"""L1, the building model with a noise scale for each lease phase
(`rentfrontier.drift_building_phase`), with a Student-t lasting level for each unit whose
degrees of freedom are fixed at 3.

The design is L1's: each row's noise scale is sigma[group] times its lease phase's factor.
Each unit's lasting level s_k takes U2's prior (`rentfrontier.drift_building_unitt`):

    s_k | kap_k ~ Normal(0, ss^2 / kap_k),   kap_k ~ Gamma(nu_u / 2, rate nu_u / 2),

but nu_u is held at `UNIT_DOF` = 3 instead of sampled. In u2a, two chains of U2 on the rows
split, nu_u sat near 2.2, mixed slowly (bulk ESS 65) and moved with ss (correlation 0.78),
so six chains would likely have missed the gate on it alone. The value 3 is a round prior
choice with a heavy tail and a finite variance. It is not read off u2a, whose training rows
include some of the latest split's held-out ads (docs/notes/unit-level-reads-2026-11-12.md).

Sampler. The sweep is `drift.make_sampler`'s with the phases, `unit_t` and
`unit_dof_fixed=UNIT_DOF`:

1. The scale step draws L1's scales and phase factors with u integrated out given the kap,
   as U2's does, without nu_u among its coordinates.
2. u and every unit's s_k are drawn jointly as in U2 (`draw_us`).
3. Given s (`update_unit_t`), each kap_k is drawn from its Gamma conditional at nu_u = 3,
   then ss and all kap together along the orbit that keeps every ss^2 / kap_k. U2's slice
   update of nu_u is skipped.

The run traces and keeps L1's quantities, and the gate checks them. `unit_dof` is a
constant here, so the run leaves it out of both.

    python -m rentfrontier.run --model drift-building-phase-unitt --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building_phase
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

NAME = "drift-building-phase-unitt"
# The units' degrees of freedom, fixed as a prior choice.
UNIT_DOF = 3.0


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with the building model's local-drift terms and a Student-t lasting
    level for each unit at `UNIT_DOF` degrees of freedom. A design from `design` carries
    the lease phases."""
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        groups=drift.groups_of(d, GROUPS),
        unit_t=True,
        unit_dof_fixed=UNIT_DOF,
    )


def run_record(d: Design) -> dict:
    """L1's record, with the units' Student-t prior at its fixed degrees of freedom."""
    return drift_building_phase.run_record(d) | {
        "unit_t": {
            "lasting_level": "Normal(0, unit_sd^2 / kap), kap ~ Gamma(nu / 2, rate nu / 2)",
            "unit_dof_fixed": UNIT_DOF,
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitt`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
