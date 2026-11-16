"""L2 on the unitkn base (`rentfrontier.drift_building_phase_unitkn_level`) with the noise
phases' factors drawn a second time each sweep, with the rows' mixing scales integrated out.

The model is L2's. A row's noise is Student-t with nu = 2 and scale sigma[group] times its
phase's factor, held in the sampler as a Normal with variance (sigma f)^2 / lam_i.

In L2's sweep the factors move in the scale step alone. That step integrates out u, the
buildings' levels and the paths, and it holds every lam_i at the state's value while it
slices. The noise step then draws sigma given the rows' remainders with lam integrated out,
and draws lam at the factors the scale step left. On the market of 2026-11-09 the factor of
the `none` phase, a unit's first ad, was the quantity that missed the gate
(docs/notes/l2-market-2026-11-15.md), and the sums log sigma[g] + log factor[none] had the
lowest bulk ESS after `unit_sd`.

Sampler. The sweep is L2's with `drift.make_sampler`'s `phase_collapsed`: after the noise
step has drawn sigma, it draws each free factor from its own rows' Student-t density at
that sigma, with lam integrated out, and then draws lam at the new factors. The check and
its predictions are in docs/notes/phase-collapsed-2026-11-16.md.

    python -m rentfrontier.run --model drift-building-phase-unitkn-level-phase --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building_phase_unitkn_level
from .drift_building_phase_unitkn_level import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    EDGES,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    LEVELS,
    PHASES,
    PROGRESS,
    ROW_DOF,
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
    phase_levels,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn-level-phase"


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with L2's model and sweep on the unitkn base, and the factors' second
    draw in the noise step."""
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
        phase_collapsed=True,
    )


def run_record(d: Design) -> dict:
    """L2's record on the unitkn base, with the sampler's option."""
    return drift_building_phase_unitkn_level.run_record(d) | {"phase_collapsed": True}


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-level-phase`: fit on the
    split's training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
