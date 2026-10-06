"""Jobs within reach: per registry building, how many jobs (Census LEHD LODES
workplace counts, `features.LODES_FILE`) stand within `MINUTES` minutes by
walking and the subway, the term `features.access_v1` (nb3-access-v1) adds to
the rent model, and one row per building for the site.

A block is within reach when the walk to it (grid distance at
`transit.WALK_M_PER_MIN`), or a walk to a station within `transit.WALK_REACH_M`,
the wait and ride to another (`transit.network`, weekday mornings, today's
timetable) and the walk from there, takes at most `MINUTES`. Blocks stand at
their LODES internal points. A listing counts only stations open when its
month began (`features.stops_not_open`) and the jobs of the year LODES had
published by then: the listing's year less `LAG_YEARS` (LODES comes out about
two years after the year it counts), within the years published (2002-2023).

    python -m rentfrontier.access      # writes WISHES/jobs-access-<date>.parquet and .csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import heapq
from pathlib import Path

import numpy as np
import pandas as pd

from . import features, transit

WISHES = Path("/data1/apartments/wishes")
FEATURE_SET = "nb3-access-v1"
MINUTES = 30.0
LAG_YEARS = 2


def ride_minutes(edges: dict, stations) -> np.ndarray:
    """[i, j]: minutes from boarding at station i to leaving the train at
    station j (0 on the diagonal; inf when unreachable)."""
    index = {s: k for k, s in enumerate(stations)}
    out = np.full((len(stations), len(stations)), np.inf)
    for i, source in enumerate(stations):
        best = {source: 0.0}
        heap = [(0.0, 0, source)]
        count = 1
        while heap:
            d, _, node = heapq.heappop(heap)
            if d > best.get(node, np.inf):
                continue
            if isinstance(node, str) and node in index:
                out[i, index[node]] = min(out[i, index[node]], d)
            for nxt, w in edges.get(node, ()):
                if d + w < best.get(nxt, np.inf):
                    best[nxt] = d + w
                    count += 1
                    heapq.heappush(heap, (d + w, count, nxt))
    return out


def reach(
    homes: np.ndarray,
    at: np.ndarray,
    ride: np.ndarray,
    blocks: np.ndarray,
    minutes: float = MINUTES,
) -> np.ndarray:
    """[home, block]: whether the block is within `minutes` of the home (grid
    metres), walking or by a station at `at` and the rides between them."""
    speed, far = transit.WALK_M_PER_MIN, transit.WALK_REACH_M
    egress = np.abs(at[:, None, :] - blocks[None]).sum(-1, dtype=np.float32) / speed
    egress[egress * speed > far] = np.inf
    out = np.zeros((len(homes), len(blocks)), dtype=bool)
    for h, home in enumerate(homes):
        walk = np.abs(at - home).sum(1) / speed
        walk[walk * speed > far] = np.inf
        arrive = (walk[:, None] + ride).min(0).astype(np.float32)
        near = arrive <= minutes
        by_train = (arrive[near, None] + egress[near]).min(0) if near.any() else np.inf
        direct = np.abs(blocks - home).sum(1) / speed
        out[h] = np.minimum(by_train, direct) <= minutes
    return out


def building_jobs(exclude=frozenset()) -> pd.DataFrame:
    """Per registry building (index) and LODES year (columns): jobs within
    MINUTES, without the stations in `exclude` (GTFS parent ids)."""
    return _building_jobs(
        features.lot_registry(), features.GTFS_FILE, features.LODES_FILE, exclude
    )


@functools.lru_cache(maxsize=1)
def _rides(gtfs: str):
    edges, stations = transit.network(gtfs)
    return ride_minutes(edges, list(stations.index)), stations


@functools.lru_cache(maxsize=4)
def _building_jobs(
    registry_file: str, gtfs: str, lodes_file: str, exclude: frozenset
) -> pd.DataFrame:
    ride, stations = _rides(gtfs)
    keep = ~stations.index.isin(exclude)
    ride, stations = ride[np.ix_(keep, keep)], stations[keep]
    grid = features.facing_grid()
    at = grid(stations.stop_lon.to_numpy(), stations.stop_lat.to_numpy())
    lodes = pd.read_parquet(lodes_file)
    blocks = grid(lodes.longitude.to_numpy(), lodes.latitude.to_numpy())
    jobs = lodes.filter(like="jobs_")
    registry = pd.read_parquet(registry_file).set_index("building")
    registry = registry[registry.latitude.notna()]
    homes = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    within = reach(homes, at, ride, blocks)
    table = within.astype(np.float64) @ jobs.to_numpy(dtype=np.float64)
    years = [int(c.removeprefix("jobs_")) for c in jobs.columns]
    return pd.DataFrame(table, index=registry.index, columns=years)


def jobs_year(period: str, years) -> int:
    """The LODES year a listing of `period` (YYYY-MM) reads."""
    return int(min(max(int(str(period)[:4]) - LAG_YEARS, min(years)), max(years)))


def jobs_within(frame: pd.DataFrame) -> np.ndarray:
    """Per row: jobs within MINUTES as of the listing's month (NaN for a
    building without a position)."""
    closed = frame.period.map(features.stops_not_open)
    out = np.full(len(frame), np.nan)
    for exclude in closed.unique():
        rows = np.flatnonzero((closed == exclude).to_numpy())
        table = building_jobs(exclude)
        part = frame.iloc[rows]
        year = part.period.map(lambda p, y=table.columns: jobs_year(p, y))
        wide = table.reindex(part.building.to_numpy())
        out[rows] = wide.to_numpy()[
            np.arange(len(rows)), table.columns.get_indexer(year.to_numpy())
        ]
    return out


def build() -> pd.DataFrame:
    """`building_jobs` with FEATURE_SET's registry."""
    lots = features.lot_files(FEATURE_SET)
    token = features._LOTS.set((lots["registry"], lots["pluto"]))
    try:
        return building_jobs()
    finally:
        features._LOTS.reset(token)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=WISHES)
    args = parser.parse_args(argv)
    table = build()
    latest = max(table.columns)
    out = pd.DataFrame(
        {
            "building": table.index,
            "jobs_30min": table[latest].round().astype(int).to_numpy(),
            "lodes_year": latest,
        }
    )
    out["jobs_rank"] = out.jobs_30min.rank(pct=True).round(3)
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.out / f"jobs-access-{dt.datetime.now(dt.UTC):%Y%m%d}"
    out.to_parquet(f"{base}.parquet")
    out.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({len(out)} buildings, LODES {latest})")
    print(out.jobs_30min.describe().round(0).to_string())


if __name__ == "__main__":
    main()
