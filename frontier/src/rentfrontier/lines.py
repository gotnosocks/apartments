"""Subway lines nearby: per registry building, the walk to the nearest station
of each line group (`LINES`), so the rent model can price each line itself
(`features.lines_v1`, nb3-lines-v1), and one row per building and line for the
site.

A station serves a line group when the MTA's static subway GTFS
(`features.GTFS_FILE`) runs one of its routes there on weekday mornings
(`transit.network`). Walks are grid (Manhattan) distances at
`transit.WALK_M_PER_MIN` from the building to the station's position; a
listing counts only stations open when its month began
(`features.stops_not_open`: 34 St-Hudson Yards on the 7 from September 2015).

The term for a line group is whether one of its stations is within `NEAR_MIN`
minutes' walk. Groups near fewer than `MIN_SHARE` of registry buildings get no
term (2026-10-06: the J/Z and the G are more than half an hour's walk from
every building, so the data can't price them). PATH is not in the MTA feed.

    python -m rentfrontier.lines      # writes WISHES/subway-lines-<date>.parquet and .csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
from pathlib import Path

import numpy as np
import pandas as pd

from . import features, transit

WISHES = Path("/data1/apartments/wishes")
FEATURE_SET = "nb3-lines-v1"
# Line groups by trunk; express variants (5X, 6X, 7X, FX) count as their line.
LINES = {
    "1": {"1"},
    "2/3": {"2", "3"},
    "4/5/6": {"4", "5", "6"},
    "7": {"7"},
    "A/C/E": {"A", "C", "E"},
    "B/D": {"B", "D"},
    "F/M": {"F", "M"},
    "G": {"G"},
    "J/Z": {"J", "Z"},
    "L": {"L"},
    "N/Q/R/W": {"N", "Q", "R", "W"},
}
NEAR_MIN = 8.0
MIN_SHARE = 0.01


def line_of(route: str) -> str | None:
    """The line group of a GTFS route id ("6X" -> "4/5/6"), None for shuttles
    and the Staten Island Railway."""
    base = route.rstrip("X") if len(route) > 1 else route
    return next((g for g, routes in LINES.items() if base in routes), None)


@functools.lru_cache(maxsize=1)
def station_lines(gtfs: str) -> pd.DataFrame:
    """Per station (GTFS parent id): name, position and the line groups whose
    trains stop there on weekday mornings."""
    edges, stations = transit.network(gtfs)
    served: dict[str, set] = {}
    for node in edges:
        if isinstance(node, tuple) and (g := line_of(node[1])):
            served.setdefault(node[0], set()).add(g)
    out = stations.copy()
    out["lines"] = [frozenset(served.get(s, ())) for s in out.index]
    return out[out.lines.map(len) > 0]


def building_lines(exclude=frozenset()) -> pd.DataFrame:
    """Per registry building and line group: walk minutes to its nearest
    station of that group and the station's name, without the stations in
    `exclude` (GTFS parent ids)."""
    return _building_lines(features.lot_registry(), features.GTFS_FILE, exclude)


@functools.lru_cache(maxsize=4)
def _building_lines(registry_file: str, gtfs: str, exclude: frozenset) -> pd.DataFrame:
    stations = station_lines(gtfs)
    stations = stations[~stations.index.isin(exclude)]
    grid = features.facing_grid()
    at = grid(stations.stop_lon.to_numpy(), stations.stop_lat.to_numpy())
    registry = pd.read_parquet(registry_file).set_index("building")
    registry = registry[registry.latitude.notna()]
    where = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    walk = np.abs(where[:, None, :] - at[None]).sum(-1) / transit.WALK_M_PER_MIN
    rows = []
    for g in LINES:
        serves = stations.lines.map(lambda s, g=g: g in s).to_numpy()
        if not serves.any():
            continue
        w = np.where(serves[None], walk, np.inf)
        i = w.argmin(1)
        rows.append(
            pd.DataFrame(
                {
                    "building": registry.index,
                    "line": g,
                    "walk_min": w[np.arange(len(w)), i],
                    "station": stations.stop_name.to_numpy()[i],
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def priced_lines(table: pd.DataFrame) -> list[str]:
    """Line groups within NEAR_MIN of at least MIN_SHARE of the buildings."""
    share = table.walk_min.le(NEAR_MIN).groupby(table.line).mean()
    return [g for g in LINES if share.get(g, 0.0) >= MIN_SHARE]


def near_lines(frame: pd.DataFrame) -> pd.DataFrame:
    """Per row and priced line group: 1.0 when one of its stations is within
    NEAR_MIN minutes' walk as of the listing's month, else 0.0: a building
    without a position (none in the registry today) counts as far from every
    line."""
    groups = priced_lines(building_lines())
    closed = frame.period.map(features.stops_not_open)
    out = pd.DataFrame(0.0, index=range(len(frame)), columns=groups)
    for exclude in closed.unique():
        rows = (closed == exclude).to_numpy()
        wide = building_lines(exclude).pivot(
            index="building", columns="line", values="walk_min"
        )
        walk = wide.reindex(index=frame.building.to_numpy()[rows], columns=groups)
        out.loc[rows, groups] = (walk.to_numpy() <= NEAR_MIN).astype(float)
    return out


def build() -> pd.DataFrame:
    """`building_lines` with FEATURE_SET's registry."""
    lots = features.lot_files(FEATURE_SET)
    token = features._LOTS.set((lots["registry"], lots["pluto"]))
    try:
        return building_lines()
    finally:
        features._LOTS.reset(token)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=WISHES)
    args = parser.parse_args(argv)
    table = build()
    table["walk_min"] = table.walk_min.round(1)
    table["near"] = table.walk_min.le(NEAR_MIN)
    table["priced"] = table.line.isin(priced_lines(table))
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.out / f"subway-lines-{dt.datetime.now(dt.UTC):%Y%m%d}"
    table.to_parquet(f"{base}.parquet")
    table.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({table.building.nunique()} buildings)")
    summary = table.groupby("line").agg(
        median_walk=("walk_min", "median"),
        near=("near", "mean"),
        priced=("priced", "first"),
    )
    print(summary.round(2).to_string())


if __name__ == "__main__":
    main()
