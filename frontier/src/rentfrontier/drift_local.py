"""The drift model (`rentfrontier.drift`) with a short-term level for each building and
each neighbourhood.

`rentfrontier.drift_building` adds a quarterly AR(1) process for each building. This module
adds a second one for each neighbourhood, also in quarterly steps (`drift`'s local drift,
with the terms `building` and `nbhd`; the neighbourhoods' is drawn given u). The citywide walk moves every neighbourhood together, and the
surface of each zone is constant in time, so neither follows a neighbourhood that heats up
or cools against the city. In fit 4's residuals the neighbourhood-by-year means hold about
2.5% of the variance, most of it in 2025 and 2026 (docs/notes/drift-2026-11-10.md): small on
average, and largest for the ads on the market now, which are the ones I score for deals.

    python -m rentfrontier.run --model drift-local --split latest --name NAME
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

NAME = "drift-local"
# The local-drift terms, in the order the sweep draws them (`drift.groups_of`).
GROUPS = ("building", "nbhd")


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with this module's local-drift terms."""
    return drift.run(
        d, priors, settings, log, checkpoint, groups=drift.groups_of(d, GROUPS)
    )


def run_record(d: Design) -> dict:
    """The drift model's record, with the local-drift terms' settings."""
    return drift.run_record(d, GROUPS)


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-local`: fit on the split's training rows and save the
    run."""
    drift.main_run(argv, name=NAME, sample=run, spec=sys.modules[__name__])
