"""What is nearby: per registry building, the walk (grid metres, along the
avenues and streets) to the nearest place of each kind in the places snapshot
(`features.PLACES_FILE`, `external.fetch_places`), and the terms
`features.nearby_v1` (nb3-nearby-v1) adds to the rent model.

Kinds (`KINDS`): a dog run or off-leash area (Ben's benchmark: about 400 m
from 401 E 88th St to Carl Schurz Park's), a hospital, an ambulance or EMS
station (sirens), a homeless drop-in center (DHS publishes no shelter
addresses; its shelter counts are by community district only, and Chelsea and
the Village are one district each), a NYCHA tax lot, and Madison Square Garden.
The places are today's (the Facilities Database and the drop-in list carry no
opening dates); the NYCHA developments and the Garden are older than the
listings. Reads no rents.

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


def building_places() -> pd.DataFrame:
    """Per registry building: grid metres to the nearest place of each kind
    (columns named by kind)."""
    return _building_places(features.lot_registry(), features.PLACES_FILE)


@functools.lru_cache(maxsize=2)
def _building_places(registry_file: str, places_file: str) -> pd.DataFrame:
    grid = features.facing_grid()
    places = pd.read_parquet(places_file).dropna(subset=["latitude", "longitude"])
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
    """Per row and kind: log of the walk to the nearest place, at least
    `FLOOR_M` (a building's centre is that far from its own door), NaN where
    the building has no position."""
    table = building_places().reindex(frame.building.to_numpy())
    return {k: np.log(np.maximum(table[k].to_numpy(), FLOOR_M)) for k in KINDS}


def main(argv=None):
    table = building_places()
    print(table.describe().round(0).to_string())


if __name__ == "__main__":
    main()
