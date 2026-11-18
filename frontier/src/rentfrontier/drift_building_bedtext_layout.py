"""The served model (`rentfrontier.drift_building_bedtext`) with levels for an ad whose coded
bedroom or bath count differs from the count in the apartment's previous ad.

On 2026-11-18 brokers' readings of the ads the base model prices far too high
(`docs/notes/low-outliers-2026-11-18.md`) kept meeting an apartment whose earlier ads coded
fewer rooms: a studio relisted as a one-bedroom, a dining room counted as a fourth bedroom, a
second bath in the fields where the text gives one. The model adds the whole step for the
extra room, and the ask moves by less. On the half of the buildings nobody read, the base
model's held-out gap is -0.029 where the bedroom count rose, +0.018 where it fell, -0.034
where the bath count rose and +0.029 where it fell.

The design is `drift_building_bedtext.design` of the frame, followed by `with_layout`, which
appends COLUMNS:

- `ad:beds_up_prev` and `ad:beds_down_prev`: the row's `bedrooms` is above or below the
  count of the apartment's previous ad;
- `ad:baths_up_prev` and `ad:baths_down_prev`: the same for `full_baths` plus half of
  `half_baths`.

The previous ad of a row is the latest training row of the same apartment priced on an
earlier day (`previous`). The apartment is the building and the `unit_id` without the "~1",
"~2" ending `data.split_unit_histories` gives a later piece, so a row whose bedroom count
jumped by two or more still finds the ad before the jump. A row with no `unit_id`, with no
earlier training row of its apartment, or with a count missing on either side gets 0 in
every column.

Each column reads the row's own coded counts and those of an earlier training row, and no
price. The four coefficients take the flag prior of `b0.prior_arrays`, and the sampler
draws them with the design's other global columns.

A run needs `rentfrontier.run` to list this module and a dataset with the columns of
`rentfrontier.b0bedtext`.

    python -m rentfrontier.run --model drift-building-bedtext-layout --split market --name NAME
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import building_zones_floor_asof, drift, drift_building_bedtext
from .building_zones_kitchen_sink import append
from .drift_building_bedtext import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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

NAME = "drift-building-bedtext-layout"
COLUMNS = (
    "ad:beds_up_prev",
    "ad:beds_down_prev",
    "ad:baths_up_prev",
    "ad:baths_down_prev",
)
# The end of a unit id that `data.split_unit_histories` gave a later piece of the unit.
PIECE = r"~\d+$"


def counts(frame: pd.DataFrame) -> pd.DataFrame:
    """Each row's coded bedrooms, and its baths with a half bath as 0.5 (NaN where the row
    has no full-bath count)."""
    half = frame.half_baths.astype(float).fillna(0.0)
    return pd.DataFrame(
        {
            "beds": frame.bedrooms.to_numpy(float),
            "baths": (frame.full_baths.astype(float) + 0.5 * half).to_numpy(float),
        }
    )


def previous(frame: pd.DataFrame, train: np.ndarray) -> pd.DataFrame:
    """For each row of `frame`, the `counts` of the latest training row of its apartment
    priced on an earlier day, NaN where there is none. Of several training rows on that
    day the last in `frame`'s order stands."""
    c = counts(frame)
    whole = frame.unit_id.astype(str).str.replace(PIECE, "", regex=True)
    c["key"] = (frame.building.astype(str) + "|" + whole).to_numpy()
    c["day"] = pd.to_datetime(frame.price_at, utc=True).dt.normalize().to_numpy()
    c["row"] = np.arange(len(c))
    known = frame.unit_id.notna().to_numpy()
    src = c[np.asarray(train, bool) & known].drop_duplicates(
        ["key", "day"], keep="last"
    )
    src = src.rename(columns={"beds": "prev_beds", "baths": "prev_baths"})
    got = pd.merge_asof(
        c[known].sort_values("day", kind="stable"),
        src[["key", "day", "prev_beds", "prev_baths"]].sort_values(
            "day", kind="stable"
        ),
        on="day",
        by="key",
        allow_exact_matches=False,
    ).set_index("row")
    return got[["prev_beds", "prev_baths"]].reindex(c.row).reset_index(drop=True)


def changes(frame: pd.DataFrame, train: np.ndarray) -> np.ndarray:
    """COLUMNS for the rows of `frame`: 1.0 where the row's count is above (or below) its
    `previous` count, else 0.0."""
    c, p = counts(frame), previous(frame, train)
    beds, pb = c.beds.to_numpy(), p.prev_beds.to_numpy()
    baths, pt = c.baths.to_numpy(), p.prev_baths.to_numpy()
    with np.errstate(invalid="ignore"):
        x = np.column_stack([beds > pb, beds < pb, baths > pt, baths < pt])
    return x.astype(float)


def with_layout(d: Design, frame: pd.DataFrame, held: np.ndarray) -> Design:
    """`d` with COLUMNS appended."""
    assert len(d.y) == len(frame)
    return append(d, list(COLUMNS), changes(frame, ~np.asarray(held, bool)))


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The served model's design of `frame`, with the four layout-change columns."""
    held = building_zones_floor_asof.held_out(frame, held)
    d = drift_building_bedtext.design(frame, start, held=held, **kw)
    return with_layout(d, frame, held)


def run_record(d: Design) -> dict:
    """The served model's record, with the layout columns and the rows each one marks."""
    return drift_building_bedtext.run_record(d) | {
        "layout": {
            "source": "the row's bedrooms and baths against the previous training ad of its apartment",
            "columns": [n for n in d.names if n in COLUMNS],
            "rows": {n: int(d.count.get(n, 0)) for n in COLUMNS},
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-bedtext-layout`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
