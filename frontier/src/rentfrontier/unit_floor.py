"""The floor of each listing's unit, and whether it is a top-floor, penthouse, garden or
lower-level unit.

I write `floor.parquet` into a snapshot directory, EXTERNAL_ROOT/unit-floor/<date>-<sha>/,
with one row per listing of the pipeline rows (`unit_features.ROWS`):

1. `floor`: the pipeline's `listed_floor`. The pipeline reads it from the unit label of the
   ad's URL, or from a floor the source states, and leaves it blank where the listing's
   captures disagree on the label or the floor is above the building's floor count. Where it
   is blank I fill it in two cases:
   - a garden, ground, basement or lower-level label gets floor 1;
   - a penthouse label (starting with PH, or containing PENT) gets the building's top floor.
2. `garden`: 1 for a garden or ground label.
3. `lower`: 1 for a basement, cellar or lower-level label.
4. `penthouse`: 1 for a penthouse label.
5. `top`: 1 where `floor` reaches the building's top floor, in a building of 2 floors or more.
   I take the top floor from MapPLUTO's `numfloors` for the building's lot, rounded down. For
   a building with no lot or no `numfloors`, I take the highest `listed_floor` among the
   building's listings. `top_source` says which: `pluto`, `ads` or `none`.

    python -m rentfrontier.unit_floor OUT_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .unit_features import ROWS, unit_label

GARDEN = r"GARDEN|GDN|^GF?$|^GRD|GROUND"
LOWER = r"BSMT|BASEMENT|CELLAR|LOWER|^LL\d*$"
PENTHOUSE = r"^PH|PENT"


def top_floors(
    rows: pd.DataFrame, registry: pd.DataFrame, pluto: pd.DataFrame
) -> pd.DataFrame:
    """Each building's top floor and its source, as the module docstring sets out. `rows`
    needs building and listed_floor."""
    lots = pd.DataFrame(
        {
            "bbl": pluto.bbl.astype(str),
            "numfloors": np.floor(pd.to_numeric(pluto.numfloors, errors="coerce")),
        }
    ).drop_duplicates("bbl")
    reg = registry.dropna(subset=["bbl"]).drop_duplicates("building")
    reg = reg.assign(bbl=reg.bbl.astype(str), building=reg.building.astype(str))
    pl = reg.merge(lots, on="bbl").set_index("building").numfloors
    pl = pl[pl >= 1]
    seen = rows.assign(building=rows.building.astype(str)).groupby("building")
    seen = seen.listed_floor.max()
    top = pl.reindex(seen.index.union(pl.index))
    source = pd.Series(np.where(top.notna(), "pluto", "none"), index=top.index)
    fill = top.isna() & seen.reindex(top.index).notna()
    top[fill] = seen.reindex(top.index)[fill]
    source[fill] = "ads"
    return pd.DataFrame({"top_floor": top, "top_source": source})


def floor_table(rows: pd.DataFrame, tops: pd.DataFrame) -> pd.DataFrame:
    """`floor`, `garden`, `lower`, `penthouse`, `top` and `top_source` for each of `rows`'
    listings, as the module docstring sets out. `rows` needs listing_id, building, page and
    listed_floor, and `tops` is `top_floors`' table."""
    r = rows.drop_duplicates("listing_id").reset_index(drop=True)
    lab = unit_label(r.page.fillna(""))
    ph = lab.str.contains(PENTHOUSE)
    garden = lab.str.contains(GARDEN) & ~ph
    lower = lab.str.contains(LOWER) & ~ph & ~garden
    t = tops.reindex(r.building.astype(str))
    count = pd.Series(t.top_floor.to_numpy(float), index=r.index)
    floor = r.listed_floor.astype(float)
    floor = floor.where(floor.notna() | ~(garden | lower), 1.0)
    floor = floor.where(floor.notna() | ~ph, count)
    top = (count >= 2) & (floor >= count)
    return pd.DataFrame(
        {
            "listing_id": r.listing_id.astype(str),
            "floor": floor.to_numpy(float),
            "garden": garden.to_numpy(float),
            "lower": lower.to_numpy(float),
            "penthouse": ph.to_numpy(float),
            "top": top.to_numpy(float),
            "top_source": t.top_source.fillna("none").to_numpy(),
        }
    )


def main(argv=None) -> None:
    """Write OUT_DIR/floor.parquet."""
    out = Path((argv or sys.argv[1:])[0])
    out.mkdir(parents=True, exist_ok=True)
    from . import building_attrs

    rows = pd.read_parquet(
        ROWS, columns=["listing_id", "building", "page", "listed_floor"]
    )
    tops = top_floors(
        rows,
        pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"]),
        pd.read_parquet(building_attrs.PLUTO, columns=["bbl", "numfloors"]),
    )
    t = floor_table(rows, tops)
    t.to_parquet(out / "floor.parquet")
    print(
        f"{len(t)} listings, floor known {int(t.floor.notna().sum())},",
        f"garden {int(t.garden.sum())}, lower {int(t.lower.sum())},",
        f"penthouse {int(t.penthouse.sum())}, top {int(t.top.sum())}",
        f"({t[t.top == 1].top_source.value_counts().to_dict()}),",
        f"median floor {float(np.nanmedian(t.floor)):.0f}",
    )


if __name__ == "__main__":
    main()
