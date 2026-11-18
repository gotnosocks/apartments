"""`rentfrontier.drift_building_bedtext_layout` with levels for an ad whose coded bedroom or
bath count is above the lowest, or below the highest, count among the apartment's earlier ads.

The layout model marks the first ad after a count changes. Its backtest of 2026-11-18
(`docs/notes/low-outliers-2026-11-18.md`) gained 39 elpd on the 864 marked open ads and lost
14 on 691 unmarked open ads of apartments with marked training rows: the count had changed
in an earlier ad and stayed, so those ads carried no mark while the apartment's level had
been fitted with one. On the base model's latest-split pool, ads coding more bedrooms than
the apartment's lowest earlier count and carrying no previous-ad mark ask 0.9% under the
prediction, and 1.6% under for baths.

The design is `drift_building_bedtext_layout.design` of the frame, followed by `with_range`,
which appends COLUMNS:

- `ad:beds_above_low`: the row's `bedrooms` is above the lowest count of the apartment's
  earlier training ads;
- `ad:beds_below_high`: it is below the highest of them;
- `ad:baths_above_low` and `ad:baths_below_high`: the same for `full_baths` plus half of
  `half_baths`.

The earlier ads of a row are the training rows of the same apartment priced on an earlier
day (`earlier_range`), with the apartment as `drift_building_bedtext_layout.previous` keys
it. An ad marked against its previous ad is marked here too, and every later ad of the
apartment at the changed count keeps the range mark. A row with no `unit_id`, with no
earlier training row of its apartment, or with a missing count gets 0.

Each column reads the row's own coded counts and those of earlier training rows, and no
price. The coefficients take the flag prior of `b0.prior_arrays`.

    python -m rentfrontier.run --model drift-building-bedtext-layout-range --split market --name NAME
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import building_zones_floor_asof, drift, drift_building_bedtext_layout
from .building_zones_kitchen_sink import append
from .drift_building_bedtext_layout import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    PIECE,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    counts,
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

NAME = "drift-building-bedtext-layout-range"
COLUMNS = (
    "ad:beds_above_low",
    "ad:beds_below_high",
    "ad:baths_above_low",
    "ad:baths_below_high",
)
_RANGE = ["low_beds", "high_beds", "low_baths", "high_baths"]


def earlier_range(frame: pd.DataFrame, train: np.ndarray) -> pd.DataFrame:
    """For each row of `frame`, the lowest and highest `counts` among the training rows of
    its apartment priced on an earlier day, NaN where there is none. A training row with a
    missing count is passed over for that count."""
    c = counts(frame)
    whole = frame.unit_id.astype(str).str.replace(PIECE, "", regex=True)
    c["key"] = (frame.building.astype(str) + "|" + whole).to_numpy()
    c["day"] = pd.to_datetime(frame.price_at, utc=True).dt.normalize().to_numpy()
    c["row"] = np.arange(len(c))
    known = frame.unit_id.notna().to_numpy()
    days = (
        c[np.asarray(train, bool) & known]
        .groupby(["key", "day"], sort=False)
        .agg(
            low_beds=("beds", "min"),
            high_beds=("beds", "max"),
            low_baths=("baths", "min"),
            high_baths=("baths", "max"),
        )
        .reset_index()
        .sort_values("day", kind="stable")
    )
    for name in _RANGE:
        # A day with no count of its own carries the range of the days before it.
        if name.startswith("low"):
            days[name] = (
                days[name].fillna(np.inf).groupby(days.key, sort=False).cummin()
            )
        else:
            days[name] = (
                days[name].fillna(-np.inf).groupby(days.key, sort=False).cummax()
            )
    days[_RANGE] = days[_RANGE].replace([np.inf, -np.inf], np.nan)
    got = pd.merge_asof(
        c[known].sort_values("day", kind="stable"),
        days[["key", "day", *_RANGE]],
        on="day",
        by="key",
        allow_exact_matches=False,
    ).set_index("row")
    return got[_RANGE].reindex(c.row).reset_index(drop=True)


def marks(frame: pd.DataFrame, train: np.ndarray) -> np.ndarray:
    """COLUMNS for the rows of `frame`: 1.0 where the row's count is above the lowest (or
    below the highest) of its `earlier_range`, else 0.0."""
    c, r = counts(frame), earlier_range(frame, train)
    beds, baths = c.beds.to_numpy(), c.baths.to_numpy()
    with np.errstate(invalid="ignore"):
        x = np.column_stack(
            [
                beds > r.low_beds.to_numpy(),
                beds < r.high_beds.to_numpy(),
                baths > r.low_baths.to_numpy(),
                baths < r.high_baths.to_numpy(),
            ]
        )
    return x.astype(float)


def with_range(d: Design, frame: pd.DataFrame, held: np.ndarray) -> Design:
    """`d` with COLUMNS appended."""
    assert len(d.y) == len(frame)
    return append(d, list(COLUMNS), marks(frame, ~np.asarray(held, bool)))


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The layout model's design of `frame`, with the four range columns."""
    held = building_zones_floor_asof.held_out(frame, held)
    d = drift_building_bedtext_layout.design(frame, start, held=held, **kw)
    return with_range(d, frame, held)


def run_record(d: Design) -> dict:
    """The layout model's record, with the range columns and the rows each one marks."""
    return drift_building_bedtext_layout.run_record(d) | {
        "layout_range": {
            "source": "the row's bedrooms and baths against the lowest and highest counts of its apartment's earlier training ads",
            "columns": [n for n in d.names if n in COLUMNS],
            "rows": {n: int(d.count.get(n, 0)) for n in COLUMNS},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-bedtext-layout-range`: fit on the split's
    training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
