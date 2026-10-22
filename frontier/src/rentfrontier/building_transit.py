"""Each building's distance to rapid transit and the services in walking range, as a snapshot.

I read the MTA's subway stations (`external/subway`, 496 stops with their daytime routes) and
the PATH stations (`external/path`, 13 stops), and every building of the NYC and NJ registries
with a point. For each building I measure the straight-line distance to every stop and keep:

    station_km    the distance to the nearest subway or PATH stop
    routes_800m   the number of distinct daytime services among the stops within 0.8 km; each
                  subway route letter or number counts once, and PATH counts as one service

Straight lines are shorter than walks, more so where a park, a rail yard or a river lies
between the building and the stop. I accept that for this snapshot.

    python -m rentfrontier.building_transit OUT_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .registry import EXTERNAL_ROOT

SUBWAY = EXTERNAL_ROOT / "subway" / "20260929-8e7c364" / "subway.parquet"
PATH_STOPS = EXTERNAL_ROOT / "path" / "20261002-0adddaf" / "path.parquet"
REGISTRY = EXTERNAL_ROOT / "registry" / "20261019-bcfbb52-extend" / "registry.parquet"
NJ_REGISTRY = EXTERNAL_ROOT / "registry-nj" / "20261019-2d485c6" / "registry.parquet"
RANGE_KM = 0.8
EARTH_KM = 6371.0


def stops(subway: pd.DataFrame, path: pd.DataFrame) -> pd.DataFrame:
    """Every stop's latitude, longitude and set of daytime services."""
    a = pd.DataFrame(
        {
            "lat": subway.gtfs_latitude.astype(float),
            "lon": subway.gtfs_longitude.astype(float),
            "routes": subway.daytime_routes.fillna("").str.split().map(frozenset),
        }
    )
    b = pd.DataFrame(
        {
            "lat": path.stop_lat.astype(float),
            "lon": path.stop_lon.astype(float),
            "routes": [frozenset({"PATH"})] * len(path),
        }
    )
    return pd.concat([a, b], ignore_index=True)


def distances_km(lat, lon, slat, slon) -> np.ndarray:
    """(buildings, stops) great-circle distances."""
    p1, p2 = np.radians(lat)[:, None], np.radians(slat)[None, :]
    dl = np.radians(slon)[None, :] - np.radians(lon)[:, None]
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def table(buildings: pd.DataFrame, st: pd.DataFrame, block: int = 4000) -> pd.DataFrame:
    """station_km and routes_800m for each building with a point."""
    b = buildings.dropna(subset=["latitude", "longitude"]).drop_duplicates("building")
    lat, lon = b.latitude.to_numpy(float), b.longitude.to_numpy(float)
    routes = st.routes.tolist()
    near, count = [], []
    for i in range(0, len(b), block):
        d = distances_km(
            lat[i : i + block], lon[i : i + block], st.lat.to_numpy(), st.lon.to_numpy()
        )
        near.append(d.min(axis=1))
        for row in d <= RANGE_KM:
            count.append(
                len(frozenset().union(*(routes[j] for j in np.flatnonzero(row))))
            )
    return pd.DataFrame(
        {
            "building": b.building.astype(str).to_numpy(),
            "station_km": np.concatenate(near) if near else [],
            "routes_800m": np.asarray(count, dtype=int),
        }
    )


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    st = stops(pd.read_parquet(SUBWAY), pd.read_parquet(PATH_STOPS))
    cols = ["building", "latitude", "longitude"]
    b = pd.concat(
        [
            pd.read_parquet(REGISTRY, columns=cols),
            pd.read_parquet(NJ_REGISTRY, columns=cols),
        ]
    )
    t = table(b, st)
    a.out.mkdir(parents=True, exist_ok=False)
    t.to_parquet(a.out / "transit.parquet")
    (a.out / "provenance.json").write_text(
        json.dumps(
            {
                "subway": str(SUBWAY),
                "subway_sha256": _sha(SUBWAY),
                "path": str(PATH_STOPS),
                "path_sha256": _sha(PATH_STOPS),
                "registry": str(REGISTRY),
                "nj_registry": str(NJ_REGISTRY),
                "range_km": RANGE_KM,
                "buildings": len(t),
                "stops": len(st),
            },
            indent=2,
        )
    )
    print(
        f"{len(t)} buildings; station_km median {t.station_km.median():.3f}, "
        f"routes_800m median {t.routes_800m.median():.0f}; wrote {a.out}"
    )


if __name__ == "__main__":
    main()
