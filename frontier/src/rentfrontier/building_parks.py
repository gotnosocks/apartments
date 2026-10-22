"""Each building's distance to parks and to the waterfront, as a snapshot.

I read the NYC Parks properties fetched over the extended registry's area
(`external/parks/20261022-ec93668`, 1,041 properties) and the city's borough boundaries,
clipped to the shoreline (NYC Open Data gthc-hcne), which I fetch here. For every NYC registry
building with a point I keep:

    park_km       the straight-line distance to the nearest edge of a park of PARK_ACRES or more
    big_park_km   the same for a park of BIG_ACRES or more (Central Park, Prospect Park, Riverside
                  Park, Flushing Meadows and the like)
    water_km      the distance to the nearest point of shoreline

I trace each outline with points no more than STEP_M apart and measure to the nearest point. A
borough's boundary is shoreline except where it meets another borough: I drop the boundary
points within LAND_M of another borough's boundary, which removes the Brooklyn and Queens line
and the short land borders in the Harlem River's Marble Hill. The city's outer land borders
(the Bronx with Westchester, Queens with Nassau) stay in and count as shore. Hudson River Park
is a state park and is not among the properties, but its esplanade is on the shoreline, so
`water_km` stands in for it.

Parks get no opening dates here: a park counts for every listing. Most parks of PARK_ACRES or
more opened long before 2010.

    python -m rentfrontier.building_parks OUT_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from . import external
from .registry import EXTERNAL_ROOT

PARKS = EXTERNAL_ROOT / "parks" / "20261022-ec93668" / "parks.parquet"
REGISTRY = EXTERNAL_ROOT / "registry" / "20261019-bcfbb52-extend" / "registry.parquet"
PARK_ACRES = 1.0
BIG_ACRES = 30.0
STEP_M = 20.0
LAND_M = 60.0
LAT0 = 40.7
M_PER_LAT = 111_320.0
M_PER_LON = M_PER_LAT * math.cos(math.radians(LAT0))


def metres(lon, lat) -> np.ndarray:
    """(n, 2) east and north metres from (0, LAT0)."""
    return np.column_stack(
        [
            np.asarray(lon, float) * M_PER_LON,
            (np.asarray(lat, float) - LAT0) * M_PER_LAT,
        ]
    )


def rings(geometry: dict):
    """A (Multi)Polygon's rings as (n, 2) lon/lat arrays."""
    polygons = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    for p in polygons:
        for r in p:
            yield np.asarray(r, dtype=float)[:, :2]


def trace(geometry: dict, step: float = STEP_M) -> np.ndarray:
    """Points in metres along every edge of the geometry, no more than `step` apart."""
    out = []
    for ring in rings(geometry):
        m = metres(ring[:, 0], ring[:, 1])
        for a, b in zip(m[:-1], m[1:]):
            n = max(int(np.ceil(np.hypot(*(b - a)) / step)), 1)
            out.append(a + (b - a) * (np.arange(n) / n)[:, None])
        out.append(m[-1:])
    return np.concatenate(out) if out else np.empty((0, 2))


def shore(boroughs: list[dict], land: float = LAND_M) -> np.ndarray:
    """The boundary points of every borough, less those within `land` of another
    borough's boundary."""
    traced = [trace(g) for g in boroughs]
    keep = []
    for i, pts in enumerate(traced):
        others = [t for j, t in enumerate(traced) if j != i]
        if not others:
            keep.append(pts)
            continue
        d, _ = cKDTree(np.concatenate(others)).query(pts)
        keep.append(pts[d > land])
    return np.concatenate(keep)


def nearest_km(homes: np.ndarray, points: np.ndarray) -> np.ndarray:
    return cKDTree(points).query(homes)[0] / 1000.0


def table(
    buildings: pd.DataFrame, parks: pd.DataFrame, boroughs: list[dict]
) -> pd.DataFrame:
    """park_km, big_park_km and water_km for each building with a point."""
    b = buildings.dropna(subset=["latitude", "longitude"]).drop_duplicates("building")
    homes = metres(b.longitude, b.latitude)
    out = {"building": b.building.astype(str).to_numpy()}
    for col, acres in (("park_km", PARK_ACRES), ("big_park_km", BIG_ACRES)):
        big = parks[parks.acres >= acres]
        pts = np.concatenate([trace(json.loads(g)) for g in big.geometry])
        out[col] = nearest_km(homes, pts)
    out["water_km"] = nearest_km(homes, shore(boroughs))
    return pd.DataFrame(out)


def fetch_boroughs() -> tuple[list[dict], str, dict]:
    rows, q = external._rows(
        external.BOROUGHS_ID, {"$select": "boroname, the_geom", "$order": "boroname"}
    )
    return [r["the_geom"] for r in rows], q, external._version(external.BOROUGHS_ID)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    boroughs, query, version = fetch_boroughs()
    parks = pd.read_parquet(PARKS)
    b = pd.read_parquet(REGISTRY, columns=["building", "latitude", "longitude"])
    t = table(b, parks, boroughs)
    a.out.mkdir(parents=True, exist_ok=False)
    t.to_parquet(a.out / "parks.parquet")
    (a.out / "boroughs.json").write_text(json.dumps(boroughs))
    (a.out / "provenance.json").write_text(
        json.dumps(
            {
                "parks": str(PARKS),
                "parks_sha256": _sha(PARKS),
                "registry": str(REGISTRY),
                "boroughs_source": f"{external.SOCRATA}/{external.BOROUGHS_ID}",
                "boroughs_query": query,
                "boroughs_version": version,
                "park_acres": PARK_ACRES,
                "big_acres": BIG_ACRES,
                "step_m": STEP_M,
                "land_m": LAND_M,
                "buildings": len(t),
            },
            indent=2,
            default=str,
        )
    )
    print(
        f"{len(t)} buildings; medians park_km {t.park_km.median():.3f}, "
        f"big_park_km {t.big_park_km.median():.3f}, water_km {t.water_km.median():.3f}; "
        f"wrote {a.out}"
    )


if __name__ == "__main__":
    main()
