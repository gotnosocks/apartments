"""Each building's distance from its own outline to the edge of a park of FRONT_ACRES or more,
as a snapshot.

`building_parks.park_km` measures from the building's point, usually the middle of its lot, so
a building across the avenue from Central Park and one 40 m back on a side street can read
nearly the same. Here I measure from the footprint instead:

1. For each registry building with a real BIN I take its footprint outline from the NYC
   building footprints, with points every 3 m (`frontage.outline`).
2. I trace every NYC Parks property of FRONT_ACRES or more (`building_parks.PARKS`) with
   points every STEP_M along its edges, in the same metres as the outline. I leave out the
   types in NOT_PARKS: the Broadway and Eastern Parkway medians, Grand Army Plaza's traffic
   circle, the Brooklyn Museum's grounds, and the institutional grounds around the Natural
   History Museum and the Botanic Garden are Parks properties but not a park to look onto. I
   keep the High Line and the Battery Park City esplanade: both are open green space a window
   can look onto, and a building beside the High Line can stand under 1 m from it.
3. `park_edge_m` is the distance from the nearest outline point to the nearest park point.

A building facing a park across a street lands at about the street's width plus its sidewalks,
15 to 45 m on most streets. `park_edge_m` stays NaN for a building with no outline, about 4%
of the training ads.

    python -m rentfrontier.building_park_front OUT_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from . import building_parks, frontage

FRONT_ACRES = 5.0
NOT_PARKS = (
    "Mall",
    "Parkway",
    "Triangle/Plaza",
    "Managed Sites",
    "Buildings/Institutions",
)
STEP_M = 5.0


def park_points(parks: pd.DataFrame, acres: float = FRONT_ACRES) -> np.ndarray:
    """Points every STEP_M or less along the edges of each park of `acres` or more."""
    pts = []
    keep = (parks.acres >= acres) & ~parks.typecategory.isin(NOT_PARKS)
    for g in parks[keep].geometry:
        for ring in building_parks.rings(json.loads(g)):
            p, _ = frontage.densify(frontage.metres(ring[:, 0], ring[:, 1]), STEP_M)
            pts.append(p)
    return np.vstack(pts)


def table(
    registry: pd.DataFrame, footprints: pd.DataFrame, parks: pd.DataFrame
) -> pd.DataFrame:
    """One row per registry building: park_edge_m."""
    reg = registry.drop_duplicates("building").set_index("building")
    bins = reg.bin.astype("string").str.replace(r"\.0$", "", regex=True)
    placeholder = bins.str.fullmatch(r"[1-5]000000").fillna(True).astype(bool)
    fp = footprints.assign(
        bin=footprints.bin.astype("string").str.replace(r"\.0$", "", regex=True)
    )
    fp = fp[fp.geometry.notna()].drop_duplicates("bin").set_index("bin").geometry
    tree = cKDTree(park_points(parks))
    dist = {}
    for b, bin_, ph in zip(reg.index, bins, placeholder):
        if ph or bin_ not in fp.index:
            continue
        dist[b] = float(tree.query(frontage.outline(fp.at[bin_]))[0].min())
    return pd.DataFrame(
        {"building": reg.index, "park_edge_m": reg.index.map(dist).to_numpy(float)}
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="rentfrontier.building_park_front")
    parser.add_argument("out", type=Path)
    a = parser.parse_args(argv)
    registry = pd.read_parquet(frontage.REGISTRY, columns=["building", "bin"])
    footprints = pd.read_parquet(frontage.FOOTPRINTS, columns=["bin", "geometry"])
    parks = pd.read_parquet(building_parks.PARKS)
    t = table(registry, footprints, parks)
    a.out.mkdir(parents=True, exist_ok=True)
    t.to_parquet(a.out / "park_front.parquet", index=False)
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    (a.out / "provenance.json").write_text(
        json.dumps(
            {
                "commit": commit,
                "inputs": {
                    str(p): _sha(p)
                    for p in (
                        frontage.REGISTRY,
                        frontage.FOOTPRINTS,
                        building_parks.PARKS,
                    )
                },
                "front_acres": FRONT_ACRES,
                "not_parks": list(NOT_PARKS),
                "rows": len(t),
                "known": int(t.park_edge_m.notna().sum()),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
