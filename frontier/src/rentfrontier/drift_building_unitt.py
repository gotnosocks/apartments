"""The building model (`rentfrontier.drift_building`) with a Student-t lasting level for each
unit.

The building model draws each unit's lasting level s_k from Normal(0, ss^2). A few units sit
far from their building and their columns, though: a penthouse coded as a plain 2 bedroom,
or a rent-stabilized unit in a market building. Under a normal prior such a unit pulls ss up
for every unit, and its own level is shrunk too hard toward 0. Here each unit gets a mixing
scale kap_k of its own:

    s_k | kap_k ~ Normal(0, ss^2 / kap_k),   kap_k ~ Gamma(nu_u / 2, rate nu_u / 2),

so s_k is Student-t with nu_u degrees of freedom and scale ss. The walk part of u is the
building model's, and so is everything else.

The prior on nu_u is Gamma(2, rate 0.1) (`drift.UNIT_DOF_PRIOR`), the one the rows' noise nu
already takes (`b0.Priors.nu`). Its mean is 20, and 95% of its mass lies between about 2.4
and 56, so it leaves room for heavy tails and for a level that is close to normal, and the
data decide between them. I chose it over a log-uniform prior on 2 to 50 because it has no
hard edges for the slice update to meet, and over the buildings' fixed 4 because the units
are many (a few hundred thousand), and they can pin nu_u.

Sampler. The sweep is `drift.make_sampler`'s with `unit_t`:

1. The global block, the scales and the buildings' levels and paths are drawn as before,
   with u integrated out given the kap. Each unit's lasting variance in the kernel K is
   ss^2 / kap_k in place of ss^2, so W, the Kalman filter and the scale step's density read
   the kap. The scale step also moves nu_u, carrying the kap along as it carries the rows'
   lam with their nu: it holds each eta_k = (log kap_k - m(nu_u)) / s(nu_u) fixed, where m
   and s are the mean and sd of log kap under Gamma(nu_u / 2, nu_u / 2), and its density
   has the map's Jacobian. Step 3 alone moves nu_u only as far as the kap drawn at its old
   value allow, and ss and nu_u trade against each other, so this move lets them travel
   together.
2. u and every unit's s_k are drawn jointly given the rows' remainders by Matheron's rule
   (`drift.make_sampler`'s `draw_us`): a draw of (s, walk, noise) from the prior, then
   s_k corrected by ss^2 / kap_k times the sum of W r over the unit's rows, and u by K W r.
   This is the building model's u step with the lasting part kept apart.
3. Given s (`update_unit_t`): nu_u by a slice update on the Student-t density of s with the
   kap integrated out, then each kap_k from its Gamma conditional, then ss and all kap
   together along the orbit (ss, kap) -> (g ss, g^2 kap), which keeps every ss^2 / kap_k,
   so the rows' density does not change. On the orbit g^2 has a Gamma conditional, which
   is drawn exactly.

Steps 1 and 2 are those of the building model at fixed kap, which leave the conditional
posterior given the kap unchanged. The scale step's move of nu_u is a slice update on the
joint density of the scales and eta, which is the posterior in those coordinates. Each part of step 3 draws from a conditional of the full
posterior: (nu_u, kap) given s and ss is drawn as nu_u with kap integrated out and then kap
given nu_u, and the orbit draw is exact. So the sweep leaves the posterior unchanged.

The run traces and keeps `unit_dof` (nu_u), and the gate checks it with the other scalars.
A prediction for a row of a unit with training rows uses its unit's kap_k. A row of a unit
with none uses a kap drawn from Gamma(nu_u / 2, nu_u / 2) at each sweep, so over the kept
draws its unit level is Student-t.

    python -m rentfrontier.run --model drift-building-unitt --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building
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

NAME = "drift-building-unitt"


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with the building model's local-drift terms and a Student-t lasting
    level for each unit."""
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        groups=drift.groups_of(d, GROUPS),
        unit_t=True,
    )


def run_record(d: Design) -> dict:
    """The building model's record, with the units' Student-t prior."""
    a, b = drift.UNIT_DOF_PRIOR
    return drift_building.run_record(d) | {
        "unit_t": {
            "lasting_level": "Normal(0, unit_sd^2 / kap), kap ~ Gamma(nu / 2, rate nu / 2)",
            "unit_dof_prior": f"Gamma({a}, rate {b})",
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-unitt`: fit on the split's training rows and
    save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
