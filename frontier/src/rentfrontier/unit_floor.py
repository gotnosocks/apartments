"""The floor of each listing's unit.

I write `floor.parquet` into a snapshot directory, EXTERNAL_ROOT/unit-floor/<date>-<sha>/,
with one row per listing of the pipeline rows (`unit_features.ROWS`):

1. `floor`: the pipeline's `listed_floor`. The pipeline reads it from the unit label of the
   ad's URL, or from a floor the source states, and leaves it blank where the listing's
   captures disagree on the label or the floor is above the building's floor count. Where it
   is blank and the label is a garden, ground, basement or lower-level label, I set floor 1.
2. `penthouse`: 1 where the label starts with PH or contains PENT.

    python -m rentfrontier.unit_floor OUT_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .unit_features import ROWS, unit_label

GROUND = r"GARDEN|GDN|^GF?$|^GRD|GROUND|BSMT|BASEMENT|CELLAR|LOWER|^LL\d*$"
PENTHOUSE = r"^PH|PENT"


def floor_table(rows: pd.DataFrame) -> pd.DataFrame:
    """`floor` and `penthouse` for each of `rows`' listings, as the module docstring sets
    out. `rows` needs listing_id, page and listed_floor."""
    r = rows.drop_duplicates("listing_id").reset_index(drop=True)
    lab = unit_label(r.page.fillna(""))
    floor = r.listed_floor.astype(float)
    ground = lab.str.contains(GROUND)
    return pd.DataFrame(
        {
            "listing_id": r.listing_id.astype(str),
            "floor": floor.where(floor.notna() | ~ground, 1.0).to_numpy(float),
            "penthouse": lab.str.contains(PENTHOUSE).to_numpy(float),
        }
    )


def main(argv=None) -> None:
    """Write OUT_DIR/floor.parquet."""
    out = Path((argv or sys.argv[1:])[0])
    out.mkdir(parents=True, exist_ok=True)
    t = floor_table(
        pd.read_parquet(ROWS, columns=["listing_id", "page", "listed_floor"])
    )
    t.to_parquet(out / "floor.parquet")
    print(
        f"{len(t)} listings, floor known {int(t.floor.notna().sum())},",
        f"penthouse {int(t.penthouse.sum())},",
        f"median floor {float(np.nanmedian(t.floor)):.0f}",
    )


if __name__ == "__main__":
    main()
