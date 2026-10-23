"""Building zones with the unit's floor on as-of features read from the build after #1242, with
a random effect for each unit and each unit's means of the columns that change between its ads.

The model is `rentfrontier.building_zones_floor_asof3_unit` with one more column for each name
in COLUMNS, `umean:` followed by that name. A row's value in the new column is the mean of the
named column over the training rows of the row's unit, a unit being a pair of the frame's
building and `unit_id` as in the unit effects. A row with no `unit_id`, or a held-out ad of a
unit with no training row, forms a unit of its own and takes its own value. The means come from
ad features, not prices, so the held-out rows add no rent information to them.

With the unit's mean beside it, the coefficient on a column measures how rent moves when the
column changes between ads of the same unit, and the column's sum with its mean's coefficient
measures how rent differs between units with different means (Mundlak 1978). The unit effect
alone leaves both inside one coefficient: it assumes a unit's effect is independent of its
features, so a feature that never changes within a unit still gets its coefficient from
differences between units. The run record counts, for each column, the rows of units with an
effect whose value differs from their unit's mean, since a column with few such rows has a weakly
identified within coefficient.

COLUMNS holds the unit columns that ads of one unit can label differently: the size terms, the
laundry, dishwasher and garden labels, and the stabilized flag. Bedrooms, baths, the floor
curves and the building columns stay out, since they rarely change between a unit's ads.

    python -m rentfrontier.run --model building-zones-floor-asof3-unitmean --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import b0, building_zones_floor_asof
from . import building_zones_floor_asof3_unit as unit3
from .building_zones_floor_asof3_unit import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    KEPT,
    MIN_UNIT_ROWS,
    PROGRESS,
    TRACED,
    UNIT_SD_PRIOR,
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
    unit_index,
    unit_offset,
    wave_matrix,
)

NAME = "building-zones-floor-asof3-unitmean"
COLUMNS = (
    "unit:log_size_rel",
    "unit:size_unknown",
    "unit:size_imputed",
    "unit:laundry_in_unit",
    "unit:laundry_in_building",
    "unit:dishwasher",
    "unit:garden",
    "flag:rent_stabilized",
)
PREFIX = "umean:"


def unit_groups(frame: pd.DataFrame) -> np.ndarray:
    """Each row's group for the means: its (building, unit_id) pair numbered from 0, and a
    group of its own for a row with no `unit_id`."""
    key = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    g = pd.factorize(key.fillna(""))[0].astype(np.int64)
    alone = frame.unit_id.isna().to_numpy()
    g[alone] = g.max() + 1 + np.arange(alone.sum())
    return g


def unit_means(x: np.ndarray, group: np.ndarray, train: np.ndarray) -> np.ndarray:
    """The mean of each column of `x` over the training rows of each row's group, and the
    row's own value where its group has no training row."""
    train = np.asarray(train, bool)
    n = int(group.max()) + 1
    w = train.astype(float)
    rows = np.bincount(group, w, minlength=n)[group]
    out = np.empty_like(x, dtype=float)
    for j in range(x.shape[1]):
        s = np.bincount(group, x[:, j] * w, minlength=n)[group]
        out[:, j] = np.where(rows > 0, s / np.maximum(rows, 1), x[:, j])
    return out


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The asof3 design with unit effects (`building_zones_floor_asof3_unit`), with the
    training rows' unit means of COLUMNS appended."""
    held = building_zones_floor_asof.held_out(frame, held)
    d = unit3.design(frame, start, held=held, **kw)
    names = list(d.names)
    cols = [c for c in COLUMNS if c in names]
    x = d.x[:, [names.index(c) for c in cols]]
    new = unit_means(x, unit_groups(frame), ~held)
    count = dict(d.count) | {
        PREFIX + c: int((new[:, j] != 0).sum()) for j, c in enumerate(cols)
    }
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, new]),
        names=names + [PREFIX + c for c in cols],
        count=count,
    )


def run_record(d: Design) -> dict:
    """The asof3 unit-effect record, with the unit means' columns and, for each column, the
    rows of units with an effect whose value differs from their unit's mean."""
    names = list(d.names)
    pairs = [c for c in COLUMNS if PREFIX + c in names]
    keyed = d.unit >= 0
    return unit3.run_record(d) | {
        "unit_means": {
            "columns": {PREFIX + c: c for c in pairs},
            "rows": "training rows of the unit, own value with none",
            "within": "the column's coefficient",
            "between": "the column's coefficient plus its unit mean's",
            "rows_off_unit_mean": {
                c: int(
                    (
                        np.abs(
                            d.x[keyed, names.index(c)]
                            - d.x[keyed, names.index(PREFIX + c)]
                        )
                        > 1e-9
                    ).sum()
                )
                for c in pairs
            },
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof3-unitmean`: fit on the split's
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
