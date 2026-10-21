"""The floor of each listing's unit, and whether it is on the top floor or below grade.

I write `floor.parquet` into a snapshot directory, EXTERNAL_ROOT/unit-floor/<date>-<sha>/,
with one row per listing of the pipeline rows (`unit_features.ROWS`):

1. `floor`: the pipeline's `listed_floor`. The pipeline reads it from the unit label of the
   ad's URL, or from a floor the source states, and leaves it blank where the listing's
   captures disagree on the label or the floor is above the building's floor count. Where it
   is blank I fill it in two cases:
   - a garden, ground, basement or lower-level label gets floor 1;
   - a penthouse label (starting with PH, or containing PENT) gets the building's floor
     count, when the pipeline has one.
2. `garden`: 1 for a garden, ground, basement or lower-level label.
3. `top`: 1 for a penthouse label, or where `floor` reaches the building's floor count in a
   building of 2 floors or more.

    python -m rentfrontier.unit_floor OUT_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .unit_features import ROWS, unit_label

GARDEN = r"GARDEN|GDN|^GF?$|^GRD|GROUND|BSMT|BASEMENT|CELLAR|LOWER|^LL\d*$"
PENTHOUSE = r"^PH|PENT"


def floor_table(rows: pd.DataFrame) -> pd.DataFrame:
    """`floor`, `garden` and `top` for each of `rows`' listings, as the module docstring sets
    out. `rows` needs listing_id, page, listed_floor and building_floor_count."""
    r = rows.drop_duplicates("listing_id").reset_index(drop=True)
    lab = unit_label(r.page.fillna(""))
    garden = lab.str.contains(GARDEN) & ~lab.str.contains(PENTHOUSE)
    ph = lab.str.contains(PENTHOUSE)
    count = r.building_floor_count.astype(float)
    floor = r.listed_floor.astype(float)
    floor = floor.where(floor.notna() | ~garden, 1.0)
    floor = floor.where(floor.notna() | ~ph, count)
    top = ph | ((count >= 2) & (floor >= count))
    return pd.DataFrame(
        {
            "listing_id": r.listing_id.astype(str),
            "floor": floor.to_numpy(float),
            "garden": garden.to_numpy(float),
            "top": top.to_numpy(float),
        }
    )


def main(argv=None) -> None:
    """Write OUT_DIR/floor.parquet."""
    out = Path((argv or sys.argv[1:])[0])
    out.mkdir(parents=True, exist_ok=True)
    t = floor_table(
        pd.read_parquet(
            ROWS,
            columns=["listing_id", "page", "listed_floor", "building_floor_count"],
        )
    )
    t.to_parquet(out / "floor.parquet")
    print(
        f"{len(t)} listings, floor known {int(t.floor.notna().sum())},",
        f"garden {int(t.garden.sum())}, top {int(t.top.sum())},",
        f"median floor {float(np.nanmedian(t.floor)):.0f}",
    )


if __name__ == "__main__":
    main()
