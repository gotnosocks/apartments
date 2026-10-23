"""Building zones with the unit's floor on as-of features, with some amenity premiums allowed to
change across the pandemic.

The model, priors and sampler are those of `rentfrontier.building_zones_floor_asof3`. I take
its design and split each column in SPLIT_COLUMNS into three, one per period of the ad's
latest-ask day (`latest_day`, the day `b0.design` places on the time walk's weekly grid):

    pre2020-03       before 2020-03-01
    2020-03to2021    2020-03-01 to 2021-12-31
    2022on           2022-01-01 on

A split column holds the original column's value on rows in its period and 0 elsewhere, so the
three of them add up to the original, which I then drop. I name each one after its original
with the period appended, as in `unit:dishwasher@2022on`, so it keeps the original's
Normal(0, 0.5) prior from `b0.prior_arrays`. As the other designs do with flags, I leave out a
split column no row sets.

The columns I split:
- `unit:laundry_in_unit` and `unit:dishwasher`, from the row's own ad;
- `unit:garden`, the garden or ground label on floor 1;
- `bld:doorman_full`, `bld:doorman_part` and `bld:doorman_virtual`, the building's doorman
  type from its training ads.

The question is whether renters paid these premiums differently during the pandemic and after
it (follow-up fit 5 in docs/notes/conference-followups-2026-10-22.md).

    python -m rentfrontier.run --model building-zones-floor-asof3-periods --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import b0, building_zones_floor_asof, building_zones_floor_asof3
from .building_zones_floor_asof3 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    ROWS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)

NAME = "building-zones-floor-asof3-periods"
SPLIT_COLUMNS = (
    "unit:laundry_in_unit",
    "unit:dishwasher",
    "unit:garden",
    "bld:doorman_full",
    "bld:doorman_part",
    "bld:doorman_virtual",
)
# Each period's suffix and its first and last-plus-one latest-ask day (None leaves it open).
PERIODS = (
    ("pre2020-03", None, "2020-03-01"),
    ("2020-03to2021", "2020-03-01", "2022-01-01"),
    ("2022on", "2022-01-01", None),
)


def period_name(column: str, period: str) -> str:
    """The name of `column`'s split column for `period`."""
    return f"{column}@{period}"


def period_masks(frame: pd.DataFrame) -> np.ndarray:
    """A (rows, periods) boolean array: each row of `frame` in the period of its latest-ask day."""
    day = pd.to_datetime(frame.latest_day)
    cols = []
    for _, lo, hi in PERIODS:
        m = np.ones(len(frame), bool)
        if lo is not None:
            m &= (day >= pd.Timestamp(lo)).to_numpy()
        if hi is not None:
            m &= (day < pd.Timestamp(hi)).to_numpy()
        cols.append(m)
    return np.column_stack(cols)


def split_periods(d: Design, frame: pd.DataFrame) -> Design:
    """`d` with each of its columns in SPLIT_COLUMNS replaced, in place, by its period columns.
    I leave out a period column no row sets."""
    masks = period_masks(frame)
    count = dict(d.count)
    cols, names = [], []
    for j, n in enumerate(d.names):
        if n not in SPLIT_COLUMNS:
            cols.append(d.x[:, j])
            names.append(n)
            continue
        count.pop(n, None)
        for k, (p, _, _) in enumerate(PERIODS):
            v = d.x[:, j] * masks[:, k]
            name = period_name(n, p)
            count[name] = int((v != 0).sum())
            if count[name] > 0:
                cols.append(v)
                names.append(name)
    return dataclasses.replace(d, x=np.column_stack(cols), names=names, count=count)


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, ads=None, **kw
) -> Design:
    """The asof3 design of `frame` with its SPLIT_COLUMNS split by period."""
    d = building_zones_floor_asof3.design(frame, start, held=held, ads=ads, **kw)
    return split_periods(d, frame)


def run_record(d: Design) -> dict:
    """The asof3 record, with the split columns and the periods."""
    rec = building_zones_floor_asof3.run_record(d)
    rec["periods"] = {
        "day": "latest_day",
        "columns": list(SPLIT_COLUMNS),
        "periods": [{"suffix": p, "from": lo, "before": hi} for p, lo, hi in PERIODS],
    }
    return rec


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof3-periods`: fit on the split's
    training rows and save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    building_zones_floor_asof.SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
