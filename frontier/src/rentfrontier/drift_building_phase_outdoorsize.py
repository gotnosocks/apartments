"""L1, the building model with a noise scale for each lease phase
(`rentfrontier.drift_building_phase`), with the stated size of the unit's private outdoor
space in the means.

L1 reads the private outdoor types and the private-outdoor feature from the listing codes,
so a 40 sq ft balcony and a 1,500 sq ft terrace take the same premium. `rentfrontier.b0outdoorsize`
reads the stated area of the unit's private outdoor space from each listing's latest
description and writes it into a copy of L1's dataset as `outdoor_sqft`, NaN where the ad
states none. On 1,474 held-out ads with an area (docs/notes/outdoor-size-2026-11-14.md), the
ask exceeds L1's median by 1.0% more for each doubling of the area, and by 2.8 points more on
ads whose listing codes give the unit no private outdoor space. Rescored on L1's draws, the
best such shift gains only +6.6 ± 4.2 elpd, since the excess falls mostly on ads with wide
intervals, so the note recommends a noise factor for these rows ahead of this design.

This design appends three ad columns built from `outdoor_sqft`:

- `ad:outdoor_sqft_stated`, 1 where the ad states an area;
- `ad:outdoor_log2_sqft`, log2 of the area over CENTER sq ft where the ad states one, else 0,
  so `ad:outdoor_sqft_stated` carries the premium at CENTER sq ft;
- `ad:outdoor_sqft_uncoded`, 1 where the ad states an area and none of L1's private outdoor
  columns (`ad:feat_private_outdoor_space`, `ad:private_outdoor_*`) is set on the row.

Each column also gets its unit mean, `umean:` and the column's name, over the row itself and
its unit's training rows priced on earlier days, as `building_zones_kitchen_sink.design` gives
L1's other ad columns. The new coefficients take the flag prior of `b0.prior_arrays`, and
the sampler draws them with the design's other global columns.

Each row's columns come from its own listing's description and its own codes, and read no
price. An ad of a unit takes no area from the unit's other ads except through the unit mean,
which reads only earlier training rows.

A run needs `rentfrontier.run` to list this module, as it lists `drift_building_phase_income`,
and a dataset with the column `outdoor_sqft`.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import building_zones_floor_asof, drift, drift_building_phase
from .building_zones_floor_asof3_unitmean import unit_groups
from .building_zones_kitchen_sink import append, past_means
from .drift_building_phase import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
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

NAME = "drift-building-phase-outdoorsize"
# The area, in sq ft, at which `ad:outdoor_log2_sqft` is 0: the median of the dataset copy's
# stated areas.
CENTER = 500.0
COLUMNS = ("ad:outdoor_sqft_stated", "ad:outdoor_log2_sqft", "ad:outdoor_sqft_uncoded")
# The column the areas come from, with the module that writes it.
SOURCE = {"outdoor_sqft": "rentfrontier.b0outdoorsize"}
CODED = ("ad:feat_private_outdoor_space", "ad:private_outdoor_")


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """L1's design of `frame`, with the outdoor area's columns and their unit means."""
    check(frame)
    held = building_zones_floor_asof.held_out(frame, held)
    d = drift_building_phase.design(frame, start, held=held, **kw)
    return with_outdoor(d, frame, held)


def check(frame: pd.DataFrame) -> None:
    """Refuse a frame with no `outdoor_sqft`, naming the module that writes it."""
    missing = [c for c in SOURCE if c not in frame]
    if missing:
        build = ", then ".join(f"python -m {m}" for m in SOURCE.values())
        raise ValueError(
            f"{NAME} needs the column outdoor_sqft, and the frame has no "
            f"{' or '.join(missing)} (build it with {build})"
        )


def outdoor_columns(
    frame: pd.DataFrame, names: list[str], x: np.ndarray
) -> tuple[list[str], np.ndarray]:
    """The (rows, 3) columns of `COLUMNS` from `frame.outdoor_sqft` and the private outdoor
    columns among the design's `names` and `x`."""
    check(frame)
    sqft = pd.to_numeric(frame.outdoor_sqft, errors="coerce").to_numpy(float)
    stated = np.isfinite(sqft) & (sqft > 0)
    coded = [j for j, n in enumerate(names) if n.startswith(CODED)]
    po = (x[:, coded] > 0).any(axis=1) if coded else np.zeros(len(frame), bool)
    log2 = np.zeros(len(frame))
    log2[stated] = np.log2(sqft[stated] / CENTER)
    cols = np.column_stack([stated, log2, stated & ~po]).astype(float)
    return list(COLUMNS), cols


def with_outdoor(d: Design, frame: pd.DataFrame, held: np.ndarray) -> Design:
    """`d` with the outdoor area's columns and, for each, its unit mean over the row and its
    unit's training rows priced on earlier days."""
    assert len(d.y) == len(frame)
    names, x = outdoor_columns(frame, list(d.names), d.x)
    d = append(d, names, x)
    um = past_means(x, unit_groups(frame), frame.price_at, ~np.asarray(held, bool))
    return append(d, ["umean:" + n for n in names], um)


def run_record(d: Design) -> dict:
    """L1's record, with the outdoor columns, their source and their rows."""
    names = list(d.names)
    return drift_building_phase.run_record(d) | {
        "outdoor_size": {
            "source": "the row's own outdoor_sqft (rentfrontier.b0outdoorsize)",
            "center_sqft": CENTER,
            "coded_columns": [n for n in names if n.startswith(CODED)],
            "columns": [n for n in names if n in COLUMNS],
            "unit_means": [n for n in names if n in {"umean:" + c for c in COLUMNS}],
            "rows": {n: int(d.count.get(n, 0)) for n in COLUMNS},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-outdoorsize`: fit on the split's
    training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
