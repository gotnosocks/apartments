"""The building model with noise phases (`rentfrontier.drift_building_phase`), with the
phase of a unit's first ad split in two.

Under the phase model (L1) the factor of the phase "none" came out at 1.64, and the rows
behind it are of two kinds (docs/notes/first-ads-and-quick-returns-2026-11-12.md). A unit
with a single ad in the dataset holds 57% of those rows and 2.6 times the later phases'
share of rows beyond 6 scales from their cell, while the first ads of units with later ads
hold 1.6 times. This design gives each kind a factor of its own:

    first   the unit's first ad, with at least one more ad of the unit in the dataset
    only    the unit's only ad in the dataset, or a row with no unit_id

The other phases are the phase model's, and a row's noise scale is

    s_i = sigma[group_i] * f[phase_i]

with f = 1 for the phase 10-13 and each other log f under the Normal(0,
`drift.PHASE_PRIOR`) prior. A row counts its unit's ads over the whole frame, training and
held out, as the phase model reads the previous ad over the whole frame. The latest split
holds out a last ad of a unit with at least two ads, so a held-out row always has a
previous ad and never lands in either phase. The split moves only the training rows'
noise, and through it sigma and the other factors.

    python -m rentfrontier.run --model drift-building-phase-first --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import drift, drift_building, drift_building_phase
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
    diagnostics,
    gp_spec,
    make_sampler,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-first"
# The phases, the reference first, with the phase model's "none" split into "first" and
# "only".
PHASES = ("10-13", "first", "only", "0-2", "3-9", "14-21", "22-25", "26+")


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The building model's design of `frame`, with each row's lease phase."""
    d = drift_building.design(frame, start, held=held, **kw)
    assert len(d.y) == len(frame)
    return dataclasses.replace(d, phase=phase_index(frame), phases=PHASES)


def ads_of_unit(frame: pd.DataFrame) -> np.ndarray:
    """Each row's count of its unit's ads in `frame`, 1 for a row with no unit_id. A unit is
    a (building, unit_id) pair, as in `drift_building_phase.months_since_previous`."""
    none = frame.unit_id.isna().to_numpy()
    key = pd.Series(
        frame.building.astype(str).to_numpy(object)
        + "|"
        + np.where(none, "", frame.unit_id.astype(object).to_numpy())
    )
    count = key.map(key.value_counts()).to_numpy(np.int64, copy=True)
    count[none] = 1
    return count


def phase_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's lease phase, as its place in `PHASES`: the phase model's, with its
    "none" taken as "only" for a unit with a single ad (or no unit_id) and as "first"
    otherwise."""
    names = np.asarray(drift_building_phase.PHASES, dtype=object)[
        drift_building_phase.phase_index(frame)
    ]
    first = names == "none"
    names[first] = np.where(ads_of_unit(frame)[first] > 1, "first", "only")
    return pd.Index(PHASES).get_indexer(names).astype(np.int64)


def run_record(d: Design) -> dict:
    """The building model's record, with the phases, their prior and their rows."""
    count = np.bincount(d.phase, minlength=len(d.phases))
    return drift_building.run_record(d) | {
        "phase": {
            "phases": list(d.phases),
            "reference": d.phases[0],
            "months_from": "the price_at of the same unit's previous ad in the dataset",
            "first_or_only": "the count of the unit's ads in the dataset, held out included",
            "log_factor_prior": f"Normal(0, {drift.PHASE_PRIOR})",
            "rows": {p: int(c) for p, c in zip(d.phases, count)},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-first`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
