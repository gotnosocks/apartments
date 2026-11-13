"""L1T (`rentfrontier.drift_building_phase_unitt`), the building model with a noise scale
for each lease phase and a Student-t lasting level for each unit at 3 degrees of freedom,
sampled with each unit's mixing scale drawn with u and the lasting level integrated out.

The model is L1T's, prior and likelihood alike. Only the sweep differs. L1T draws each
kap_k from its Gamma conditional given the unit's lasting level s_k, and s_k is drawn
jointly with u just before, given the old kap_k. For a unit with one to three ads, s_k and
the unit's drift share u between them loosely, and kap_k follows s_k. Six chains of L1T on
the latest split missed the gate on nu (R-hat 1.025) and unit_sd (1.019): the chains agreed
on the values but each moved slowly, and the slow parts of nu and unit_sd moved together
(docs/notes/l1-unit-kap-collapsed-2026-11-13.md).

Sampler. The sweep is `drift.make_sampler`'s with the phases, `unit_t`,
`unit_dof_fixed=UNIT_DOF` and `unit_kap_collapsed`:

1. The scale step, the buildings' levels and the collapsed paths are drawn as in L1T.
2. Each kap_k is drawn by a slice update from its conditional given the rows' remainders,
   with u and s_k integrated out (`collapsed_kap`).
3. u and every s_k are drawn jointly given the new kap (`draw_us`).
4. ss and all kap move together along the orbit that keeps every ss^2 / kap_k, as in L1T.
   L1T's Gamma draw of the kap given s is skipped: step 2 has drawn them.

    python -m rentfrontier.run --model drift-building-phase-unitk --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building_phase_unitt
from .drift_building_phase_unitt import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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

NAME = "drift-building-phase-unitk"


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with L1T's model, the kap drawn with u and the lasting levels
    integrated out."""
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
    )


def run_record(d: Design) -> dict:
    """L1T's record, with the collapsed draw of the kap."""
    rec = drift_building_phase_unitt.run_record(d)
    return rec | {"unit_t": rec["unit_t"] | {"kap_step": "collapsed over u and s"}}


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitk`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
