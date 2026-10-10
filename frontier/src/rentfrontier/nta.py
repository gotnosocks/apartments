"""The 2020 Neighborhood Tabulation Area of each registry building: City
Planning's 2020 NTAs (NYC Open Data 9nt8-h7nd, Manhattan), the building's
registry point tested against each area's outline (even-odd rule, so holes
count). A building in no area (a point on the water side of a pier, say) is
left out. Areas are fixed boundaries, not dated: they read no listing and no
rent.

    python -m rentfrontier.nta

writes EXTERNAL_ROOT/nta/<date>-<commit>/nta.parquet (building, nta2020,
ntaname, cdta2020), nta.geojson (the areas, for maps) and provenance.json.
Refuses a dirty tree.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from rentfrontier.listing_extras import EXTERNAL_ROOT, _git

DATASET = "9nt8-h7nd"
URL = f"https://data.cityofnewyork.us/resource/{DATASET}.geojson"
PARAMS = {"boroname": "Manhattan", "$limit": 1000}


def inside(lon: np.ndarray, lat: np.ndarray, geometry: dict) -> np.ndarray:
    """Which points lie in a GeoJSON Polygon or MultiPolygon (even-odd over
    all of its rings, so holes are outside)."""
    polygons = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    hit = np.zeros(len(lon), dtype=bool)
    for polygon in polygons:
        for ring in polygon:
            r = np.asarray(ring, dtype=float)
            x0, y0 = r[:-1, 0], r[:-1, 1]
            x1, y1 = r[1:, 0], r[1:, 1]
            # Edges that straddle each point's latitude, and where they cross it.
            straddle = (y0[None, :] > lat[:, None]) != (y1[None, :] > lat[:, None])
            with np.errstate(divide="ignore", invalid="ignore"):
                x = x0 + (lat[:, None] - y0) * (x1 - x0) / (y1 - y0)
            crossings = (straddle & (lon[:, None] < x)).sum(axis=1)
            hit ^= crossings % 2 == 1
    return hit


def assign(buildings: pd.DataFrame, areas: list[dict]) -> pd.DataFrame:
    """Per building (columns building, latitude, longitude) the area it lies
    in; `areas` are GeoJSON features with nta2020, ntaname and cdta2020."""
    b = buildings.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    lon, lat = b.longitude.to_numpy(float), b.latitude.to_numpy(float)
    found = np.full(len(b), -1)
    for i, area in enumerate(areas):
        hit = inside(lon, lat, area["geometry"]) & (found < 0)
        found[hit] = i
    keep = found >= 0
    props = [areas[i]["properties"] for i in found[keep]]
    return pd.DataFrame(
        {
            "building": b.building[keep].to_numpy(),
            "nta2020": [p["nta2020"] for p in props],
            "ntaname": [p["ntaname"] for p in props],
            "cdta2020": [p["cdta2020"] for p in props],
        }
    )


def fetch() -> tuple[dict, str]:
    url = f"{URL}?{urllib.parse.urlencode(PARAMS)}"
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.loads(response.read()), url


def main():
    from rentfrontier import features

    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    collection, url = fetch()
    areas = collection["features"]
    registry = pd.read_parquet(features.NB8_REGISTRY_FILE)
    registry = registry.drop_duplicates("building")
    table = assign(registry, areas)
    out_dir = EXTERNAL_ROOT / "nta" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "nta.parquet"
    table.to_parquet(path, index=False)
    (out_dir / "nta.geojson").write_text(json.dumps(collection))
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "source": url,
                "dataset": DATASET,
                "registry": features.NB8_REGISTRY_FILE,
                "retrieved_at": started.isoformat(),
                "commit": commit,
                "areas": len(areas),
                "buildings": len(registry),
                "assigned": len(table),
                "by_area": table.ntaname.value_counts().to_dict(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    print(f"wrote {path}: {len(table)} of {len(registry)} buildings")


if __name__ == "__main__":
    main()
