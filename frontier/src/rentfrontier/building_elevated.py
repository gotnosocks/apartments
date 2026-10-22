"""Each building's distance from its own outline to an elevated subway track, as a snapshot.

An elevated line runs over the middle of its street, so the buildings on either side face the
structure from across a sidewalk and half a roadway. I find the track and measure to it:

1. The MTA's station list (`SUBWAY`) gives each station's structure. I take a track segment
   as elevated when the stations at both of its ends are ELEVATED structures (Elevated or
   Viaduct). Embankments, open cuts and at-grade track don't pass over a street.
2. For each GTFS shape in the MTA subway feed (`GTFS`), I take a trip on that shape, place
   its stops on the shape, and keep the stretch of shape between consecutive elevated stops,
   with points every STEP_M. A stretch between an elevated stop and an underground one is
   left out, so the last block or two before a portal reads as not elevated.
3. For each registry building with a real BIN I take its footprint outline (`frontage.outline`)
   and measure `elevated_m`, the distance from the nearest outline point to the nearest track
   point.

A building facing the structure across its street lands at about half the street's width plus
the sidewalk, 10 to 25 m on most of these streets. `elevated_m` stays NaN for a building with
no outline.

    python -m rentfrontier.building_elevated OUT_DIR
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

from . import frontage
from .registry import EXTERNAL_ROOT

GTFS = EXTERNAL_ROOT / "mta-gtfs" / "20261006"
SUBWAY = EXTERNAL_ROOT / "subway" / "20260929-8e7c364" / "subway.parquet"
ELEVATED = ("Elevated", "Viaduct")
STEP_M = 5.0


def track_points(
    stations: pd.DataFrame,
    trips: pd.DataFrame,
    stop_times: pd.DataFrame,
    stops: pd.DataFrame,
    shapes: pd.DataFrame,
) -> np.ndarray:
    """Points every STEP_M or less along each shape's stretches between consecutive elevated
    stops, in `frontage.metres`."""
    elevated = set(stations.gtfs_stop_id[stations.structure.isin(ELEVATED)].astype(str))
    pos = stops.set_index("stop_id")[["stop_lon", "stop_lat"]]
    first = trips.drop_duplicates("shape_id").set_index("trip_id").shape_id
    st = stop_times[stop_times.trip_id.isin(first.index)]
    pts = []
    for trip, s in st.groupby("trip_id"):
        s = s.sort_values("stop_sequence")
        ids = s.stop_id.astype(str)
        parent = ids.where(~ids.str[-1].isin(["N", "S"]), ids.str[:-1]).to_numpy()
        flags = np.isin(parent, list(elevated))
        if not (flags[:-1] & flags[1:]).any():
            continue
        p = shapes[shapes.shape_id == first[trip]].sort_values("shape_pt_sequence")
        line = frontage.metres(p.shape_pt_lon.to_numpy(), p.shape_pt_lat.to_numpy())
        at = cKDTree(line).query(
            frontage.metres(pos.loc[ids, "stop_lon"], pos.loc[ids, "stop_lat"])
        )[1]
        for k in np.flatnonzero(flags[:-1] & flags[1:]):
            i, j = sorted((at[k], at[k + 1]))
            if j > i:
                pts.append(frontage.densify(line[i : j + 1], STEP_M)[0])
    return np.vstack(pts)


def table(
    registry: pd.DataFrame, footprints: pd.DataFrame, track: np.ndarray
) -> pd.DataFrame:
    """One row per registry building: elevated_m."""
    reg = registry.drop_duplicates("building").set_index("building")
    bins = reg.bin.astype("string").str.replace(r"\.0$", "", regex=True)
    placeholder = bins.str.fullmatch(r"[1-5]000000").fillna(True).astype(bool)
    fp = footprints.assign(
        bin=footprints.bin.astype("string").str.replace(r"\.0$", "", regex=True)
    )
    fp = fp[fp.geometry.notna()].drop_duplicates("bin").set_index("bin").geometry
    tree = cKDTree(track)
    dist = {}
    for b, bin_, ph in zip(reg.index, bins, placeholder):
        if ph or bin_ not in fp.index:
            continue
        dist[b] = float(tree.query(frontage.outline(fp.at[bin_]))[0].min())
    return pd.DataFrame(
        {"building": reg.index, "elevated_m": reg.index.map(dist).to_numpy(float)}
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="rentfrontier.building_elevated")
    parser.add_argument("out", type=Path)
    a = parser.parse_args(argv)
    feed = {n: GTFS / f"{n}.txt" for n in ("trips", "stop_times", "stops", "shapes")}
    track = track_points(
        pd.read_parquet(SUBWAY),
        pd.read_csv(feed["trips"]),
        pd.read_csv(
            feed["stop_times"], usecols=["trip_id", "stop_id", "stop_sequence"]
        ),
        pd.read_csv(feed["stops"]),
        pd.read_csv(feed["shapes"]),
    )
    registry = pd.read_parquet(frontage.REGISTRY, columns=["building", "bin"])
    footprints = pd.read_parquet(frontage.FOOTPRINTS, columns=["bin", "geometry"])
    t = table(registry, footprints, track)
    a.out.mkdir(parents=True, exist_ok=True)
    t.to_parquet(a.out / "elevated.parquet", index=False)
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
                        SUBWAY,
                        *feed.values(),
                        frontage.REGISTRY,
                        frontage.FOOTPRINTS,
                    )
                },
                "elevated": list(ELEVATED),
                "track_points": len(track),
                "rows": len(t),
                "known": int(t.elevated_m.notna().sum()),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
