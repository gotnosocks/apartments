"""The building model (`rentfrontier.drift_building`) with a noise scale for each lease phase.

The building model gives every row of a bedroom group the same noise scale sigma. An ad's
distance from its unit's previous ad changes how far it strays from the unit's level,
though: a relist within two months repeats the last ask, and an ad a year after the last
one is the usual lease-renewal turnover. So this design sorts each row into a phase by the
months from the price_at of the same unit's previous ad in the dataset, training or held
out, to the row's own price_at:

    none    the unit's first ad in the dataset, or a row with no unit_id
    0-2     under 3 months
    3-9     3 to under 10 months
    10-13   10 to under 14 months, the reference phase
    14-21   14 to under 22 months
    22-25   22 to under 26 months
    26+     26 months or more

A row's noise scale is then

    s_i = sigma[group_i] * f[phase_i]

with f = 1 for the reference phase, and each other phase's log f takes a Normal(0,
`drift.PHASE_PRIOR`) prior. The sampler draws the six free log factors in its scale step,
jointly with the unit scales, sigma and nu (`drift.make_sampler`).

    python -m rentfrontier.run --model drift-building-phase --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

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

NAME = "drift-building-phase"
# The phases, the reference first. `EDGES` holds the months at which each binned phase
# starts, in the order of `PHASES[2:]`, so 0-2 runs from 0 to 3 months.
PHASES = ("10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+")
BINNED = ("0-2", "3-9", "10-13", "14-21", "22-25", "26+")
EDGES = (3, 10, 14, 22, 26)
MONTH_DAYS = 365.25 / 12


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The building model's design of `frame`, with each row's lease phase."""
    d = drift_building.design(frame, start, held=held, **kw)
    assert len(d.y) == len(frame)
    return dataclasses.replace(d, phase=phase_index(frame), phases=PHASES)


def months_since_previous(frame: pd.DataFrame) -> np.ndarray:
    """Each row's months from the price_at of its unit's previous ad in `frame` to its own,
    NaN for a unit's first ad and for a row with no unit_id. A unit is a (building, unit_id)
    pair, as in `drift.unit_index`, and ads of a unit are ordered by price_at, then
    audit_id."""
    at = pd.to_datetime(frame.price_at, utc=True).dt.tz_convert(None).to_numpy()
    none = frame.unit_id.isna().to_numpy()
    unit_id = frame.unit_id.astype(object).to_numpy()
    key = (
        frame.building.astype(str).to_numpy(object) + "|" + np.where(none, "", unit_id)
    )
    order = pd.DataFrame(
        {
            "key": key.astype(str),
            "at": at,
            "audit": frame.audit_id.astype(str).to_numpy(),
        }
    ).sort_values(["key", "at", "audit"], kind="stable")
    prev = order.groupby("key", sort=False)["at"].shift(1)
    months = ((order["at"] - prev).dt.total_seconds() / 86400 / MONTH_DAYS).to_numpy()
    out = np.full(len(frame), np.nan)
    out[order.index.to_numpy()] = months
    out[none] = np.nan
    return out


def phase_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's lease phase, as its place in `PHASES`."""
    months = months_since_previous(frame)
    have = ~np.isnan(months)
    names = np.full(len(frame), "none", dtype=object)
    names[have] = np.asarray(BINNED, dtype=object)[
        np.searchsorted(EDGES, months[have], side="right")
    ]
    return pd.Index(PHASES).get_indexer(names).astype(np.int64)


def run_record(d: Design) -> dict:
    """The building model's record, with the phases, their prior and their rows."""
    count = np.bincount(d.phase, minlength=len(d.phases))
    return drift_building.run_record(d) | {
        "phase": {
            "phases": list(d.phases),
            "reference": d.phases[0],
            "months_from": "the price_at of the same unit's previous ad in the dataset",
            "log_factor_prior": f"Normal(0, {drift.PHASE_PRIOR})",
            "rows": {p: int(c) for p, c in zip(d.phases, count)},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase`: fit on the split's training rows and
    save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
