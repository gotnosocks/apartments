"""The drift model (`rentfrontier.drift`) with a short-term level for each building.

Each building gets one more term in its rows' means, a stationary AR(1) process in quarterly
steps (`drift`'s local drift, with the term `building`, drawn by its collapsed step):

    a_b(m) = rho a_b(m - 1) + Normal(0, s^2 (1 - rho^2))

The drift model lets each unit's level move, one unit at a time. The residuals of fit 4, which
has a constant level for each unit, still move together across the units of one building: two
ads of different units within three months correlate at 0.26, and the correlation is gone a
few years apart (docs/notes/drift-2026-11-10.md). A landlord reprices a whole building at
once, and a renovation, a new management company or a concession campaign moves every unit's
asking rent for a few months. With this term an ad of one unit this month informs the
prediction for its neighbours down the hall.

    python -m rentfrontier.run --model drift-building --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift
from .drift import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    HYP,
    KEPT,
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

NAME = "drift-building"
# The buildings' levels take a Student-t prior with this many degrees of freedom unless
# `--level-dof` says otherwise (0 for the normal prior). Under the normal prior about ten
# buildings far from their neighbourhoods held the outer boroughs' spread and every pooled
# fit missed the convergence gate; with 4 all three fits of 2026-11-10 pass
# (docs/notes/drift-2026-11-10.md, rounds seven to nine).
LEVEL_DOF = 4.0
# The local-drift terms, in the order the sweep draws them (`drift.groups_of`).
GROUPS = ("building",)


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with this module's local-drift terms."""
    return drift.run(
        d, priors, settings, log, checkpoint, groups=drift.groups_of(d, GROUPS)
    )


def run_record(d: Design) -> dict:
    """The drift model's record, with the local-drift terms' settings."""
    return drift.run_record(d, GROUPS)


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building`: fit on the split's training rows and save the
    run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
