"""What is nearby: per registry building, the walk (grid metres, along the
avenues and streets) to the nearest place of each kind in the places snapshot
(`features.places_file()`, `external.fetch_places`), and the terms
`features.nearby_v1` (nb3-nearby-v1) adds to the rent model.

Kinds (`KINDS`): a dog run or off-leash area (Ben's benchmark: about 400 m
from 401 E 88th St to Carl Schurz Park's), a hospital, an ambulance or EMS
station (sirens), a homeless drop-in center (DHS publishes no shelter
addresses; its shelter counts are by community district only, and Chelsea and
the Village are one district each), a NYCHA tax lot, and Madison Square Garden.
The places are today's. A listing counts a place in `OPENED` only from the
month it opened (no future information); the NYCHA developments and the Garden
are older than the listings, the other places are taken as older too (the
Facilities Database and the drop-in list carry no opening dates). Reads no
rents.

    python -m rentfrontier.nearby      # prints the table for the registry
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from . import features

KINDS = {
    "dog run": "dog run",
    "hospital": "hospital",
    "ambulance station": "ambulance station",
    "drop-in center": "homeless drop-in center",
    "nycha": "NYCHA housing",
    "arena": "Madison Square Garden",
}
FLOOR_M = 50.0
# Places near the registry that opened after the data begin (2010), by name.
OPENED = {
    "NORTHWELL GREENWICH VILLAGE HOSPITAL": "2014-07-01",  # Lenox Health ER
    "Gansevoort Peninsula Dog Park": "2023-10-01",
}


def not_open(month) -> frozenset:
    """Names of the places in OPENED that had not opened when `month` began."""
    start = pd.Timestamp(month).replace(day=1)
    return frozenset(n for n, day in OPENED.items() if pd.Timestamp(day) > start)


def building_places(exclude=frozenset()) -> pd.DataFrame:
    """Per registry building: grid metres to the nearest place of each kind
    (columns named by kind), without the places named in `exclude`."""
    return _building_places(features.lot_registry(), features.places_file(), exclude)


@functools.lru_cache(maxsize=4)
def _building_places(registry_file: str, places_file: str, exclude: frozenset):
    grid = features.facing_grid()
    places = pd.read_parquet(places_file).dropna(subset=["latitude", "longitude"])
    places = places[~places.name.isin(exclude)]
    registry = pd.read_parquet(registry_file).set_index("building")
    here = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    out = pd.DataFrame(index=registry.index)
    for kind in KINDS:
        p = places[places.kind.eq(kind)]
        at = grid(p.longitude.to_numpy(), p.latitude.to_numpy())
        d = np.abs(here[:, None, :] - at[None]).sum(-1)
        out[kind] = d.min(axis=1) if len(p) else np.nan
    return out


def terms(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Per row and kind: log of the walk to the nearest place open in the
    listing's month, at least `FLOOR_M` (a building's centre is that far from
    its own door), NaN where the building has no position."""
    closed = frame.period.map(not_open)
    metres = {k: np.full(len(frame), np.nan) for k in KINDS}
    for exclude in closed.unique():
        rows = (closed == exclude).to_numpy()
        table = building_places(exclude).reindex(frame.building.to_numpy()[rows])
        for k in KINDS:
            metres[k][rows] = table[k].to_numpy()
    return {k: np.log(np.maximum(m, FLOOR_M)) for k, m in metres.items()}


def main(argv=None):
    table = building_places()
    print(table.describe().round(0).to_string())


if __name__ == "__main__":
    main()
