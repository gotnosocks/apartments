"""Each building's year built, MapPLUTO alteration years and ground-floor retail.

For each building of the building-attributes snapshot (`building_attrs.ATTRS`) I take

1. `year_built` from that snapshot: MapPLUTO's `yearbuilt` for an NYC lot, the median parcel
   year for an NJ lot, NaN when neither gives a year from 1800 on;
2. `alter1` and `alter2`, the lot's MapPLUTO `yearalter1` and `yearalter2`, NaN when zero or
   when the building has no MapPLUTO lot;
3. `retail`, 1 where the lot's MapPLUTO `retailarea` is positive. Where `retailarea` is blank
   I fall back on `comarea`. `retail_unknown` is 1 where the building has no MapPLUTO lot or
   both areas are blank.

The lot comes from the registry's BBL, and MapPLUTO is the release `building_attrs.PLUTO`.
I write the table to EXTERNAL_ROOT/building-age/<date>-<sha>/age.parquet.

    python -m rentfrontier.building_age OUT_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import building_attrs


def building_table(
    attrs: pd.DataFrame, registry: pd.DataFrame, pluto: pd.DataFrame
) -> pd.DataFrame:
    """`year_built`, `alter1`, `alter2`, `retail` and `retail_unknown` for each building of
    `attrs`, as the module docstring sets out."""
    num = lambda s: pd.to_numeric(s, errors="coerce")
    lots = pd.DataFrame(
        {
            "bbl": pluto.bbl.astype(str),
            "alter1": num(pluto.yearalter1),
            "alter2": num(pluto.yearalter2),
            "retailarea": num(pluto.retailarea),
            "comarea": num(pluto.comarea),
        }
    ).drop_duplicates("bbl")
    reg = registry.dropna(subset=["bbl"]).drop_duplicates("building")
    reg = reg.assign(bbl=reg.bbl.astype(str), building=reg.building.astype(str))
    t = attrs[["building", "year_built"]].assign(building=attrs.building.astype(str))
    t = t.merge(reg[["building", "bbl"]], on="building", how="left")
    t = t.merge(lots, on="bbl", how="left")
    area = t.retailarea.fillna(t.comarea)
    return pd.DataFrame(
        {
            "building": t.building,
            "year_built": t.year_built.to_numpy(float),
            "alter1": t.alter1.where(t.alter1 > 0).to_numpy(float),
            "alter2": t.alter2.where(t.alter2 > 0).to_numpy(float),
            "retail": (area > 0).to_numpy(float),
            "retail_unknown": area.isna().to_numpy(float),
        }
    )


def main(argv=None) -> None:
    """Write OUT_DIR/age.parquet."""
    out = Path((argv or sys.argv[1:])[0])
    out.mkdir(parents=True, exist_ok=True)
    t = building_table(
        pd.read_parquet(building_attrs.ATTRS),
        pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"]),
        pd.read_parquet(
            building_attrs.PLUTO,
            columns=["bbl", "yearalter1", "yearalter2", "retailarea", "comarea"],
        ),
    )
    t.to_parquet(out / "age.parquet")
    print(
        f"{len(t)} buildings, year known {int(t.year_built.notna().sum())},",
        f"altered {int((np.fmax(t.alter1, t.alter2) >= 2000).sum())} since 2000,",
        f"retail {int(t.retail.sum())}, retail unknown {int(t.retail_unknown.sum())}",
    )


if __name__ == "__main__":
    main()
