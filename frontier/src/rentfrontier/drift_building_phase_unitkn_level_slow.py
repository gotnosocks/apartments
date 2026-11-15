"""L2 on the unitkn base (`rentfrontier.drift_building_phase_unitkn_level`) with each unit's
lasting level reverting slowly to 0.

In L2 a unit's level at an ad is u_k(t) = s_k + d_k(t): a lasting level s_k ~ Normal(0,
ss^2 / kap_k), constant over the unit's life, and an OU drift d_k with sd and a time
constant of about 2.6 years. Two ads of the unit far apart in time still share all of
s_k. This model lets s_k move as an OU process of its own, with a time constant unit_tau
of many years, so the covariance of u_k between two ads becomes

    (ss^2 / kap_k) exp(-|t_a - t_b| / unit_tau) + sd^2 exp(-|t_a - t_b| / tau).

At unit_tau = infinity the model is L2. A new ad then takes a share of the unit's record
that falls with the years since the record's ads, slowly at first and then on the drift's
scale. The prior on log unit_tau is Normal(log 40, 1). The two time constants are told
apart by the lags they act on, 2.6 years against decades, and the Student-t mixing scale
stays on the slow part alone, as it did on s_k. The gap screen behind the change and its
predictions are in docs/notes/l2-unit-record-2026-11-15.md.

Sampler. The sweep is L2's with `drift.make_sampler`'s `unit_slow`:

1. The scale step samples log unit_tau with the other unit scales, u and the buildings'
   levels integrated out, the Kalman filter on each unit's state (s, d) taking the slow
   level's OU step between ads.
2. The collapsed kap step reads each unit's density in its kap from a factorization of
   the unit's covariance made once a sweep (`drift.make_sampler`'s `kap_logp`).
3. u is drawn as before by Matheron's rule, with the lasting level's prior draw an OU path
   in place of a constant.

    python -m rentfrontier.run --model drift-building-phase-unitkn-level-slow --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building_phase_unitkn_level
from .drift import UNIT_TAU_LOG_PRIOR
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

NAME = "drift-building-phase-unitkn-level-slow"


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with L2's model and sweep on the unitkn base, and the slow lasting level."""
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
        unit_slow=True,
    )


def run_record(d: Design) -> dict:
    """L2's record on the unitkn base, with the slow level's prior."""
    mu, sd = UNIT_TAU_LOG_PRIOR
    return drift_building_phase_unitkn_level.run_record(d) | {
        "unit_slow": {"unit_tau_log_prior": f"Normal({mu:.4f}, {sd})"}
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-level-slow`: fit on the split's
    training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
