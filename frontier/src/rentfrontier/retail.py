"""Street retail: per registry building, the storefronts and the restaurants,
cafes and bars ("food services") within `RADIUS_M` (grid walk), from the
Storefront Registry's first reporting year (`FIRST_YEAR`, filed for 2019 and
2020; `features.STOREFRONTS_FILE`), and the terms `features.retail_v1`
(nb3-retail-v1) adds to the rent model.

The registry starts in 2019, so earlier listings see their block's storefronts
as filed then: a measure of how much street retail a block was built with,
which seldom changes (the count of filings in the box moved by under 4% a year
from 2019 to 2024), not of which shops were open in a listing's month. Vacancy
is left out for that reason. Reads no rents.

    python -m rentfrontier.retail      # prints the table for the registry
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from . import features

FIRST_YEAR = "2019 and 2020"
RADIUS_M = 150.0
FOOD = "FOOD SERVICES"


def building_retail() -> pd.DataFrame:
    """Per registry building: storefronts and food-service storefronts within
    RADIUS_M."""
    return _building_retail(features.lot_registry(), features.STOREFRONTS_FILE)


@functools.lru_cache(maxsize=2)
def _building_retail(registry_file: str, storefronts_file: str) -> pd.DataFrame:
    from scipy.spatial import cKDTree

    grid = features.facing_grid()
    shops = pd.read_parquet(storefronts_file)
    shops = shops[shops.reporting_year.eq(FIRST_YEAR)].dropna(
        subset=["latitude", "longitude"]
    )
    registry = pd.read_parquet(registry_file).set_index("building")
    here = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    at = grid(shops.longitude.to_numpy(), shops.latitude.to_numpy())
    food = shops.primary_business_activity.eq(FOOD).to_numpy()
    tree = cKDTree(at)
    ok = ~np.isnan(here).any(axis=1)
    near = [
        tree.query_ball_point(p, RADIUS_M, p=1) if k else [] for p, k in zip(here, ok)
    ]
    return pd.DataFrame(
        {
            "storefronts": np.where(ok, [len(i) for i in near], np.nan),
            "food": np.where(ok, [int(food[i].sum()) for i in near], np.nan),
        },
        index=registry.index,
    )


def terms(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Per row: log1p of the storefronts and of the food services nearby."""
    table = building_retail().reindex(frame.building.to_numpy())
    return {k: np.log1p(table[k].to_numpy()) for k in ("storefronts", "food")}


def main(argv=None):
    print(building_retail().describe().round(1).to_string())


if __name__ == "__main__":
    main()
