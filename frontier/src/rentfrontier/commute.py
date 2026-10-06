"""Commute times for the apartment ranking, not the rent model: per registry
building and destination in `DESTINATIONS`, the weekday door-to-door minutes by
subway leaving 08:00-09:00, and the transfers on that trip.

The rent model keeps `transit.midtown_minutes` (nb3-transit-v1), the generic time
to the midtown hubs that the market prices. This table answers one person's
question, "how long to my office?", so it never enters a fit; the ranking reads it
as a pro or con. Destinations live in `config/commute-destinations.json` (name,
address, latitude, longitude); add one there and rerun.

Same routing as `transit`: the MTA's static GTFS (`features.GTFS_FILE`), each line's
median time between stations, boarding waits of half the headway (at most
`transit.MAX_WAIT_MIN`), the feed's transfers, and grid walks at
`transit.WALK_M_PER_MIN` to stations within `transit.WALK_REACH_M` at both ends,
or the whole way on foot.

    python -m rentfrontier.commute      # writes WISHES/commute-<date>.parquet and .csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import heapq
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, features, transit

WISHES = Path("/data1/apartments/wishes")
DESTINATIONS = data.REPO / "config" / "commute-destinations.json"
FEATURE_SET = "nb3-transit-v1"
DEPARTING = (8 * 3600, 9 * 3600)
_DEST = "destination"


def destinations(path: Path = DESTINATIONS) -> pd.DataFrame:
    return pd.DataFrame(json.loads(Path(path).read_text())).set_index("name")


@functools.lru_cache(maxsize=1)
def _network(gtfs: str):
    return transit.network(gtfs, hours=DEPARTING, by_stop=True)


def station_trips(edges: dict, egress: dict) -> dict:
    """Per station: (minutes, boardings) of the quickest trip to the
    destination, leaving the network at a station s after egress[s] minutes
    on foot."""
    back: dict = {}
    for a, out in edges.items():
        for b, w in out:
            back.setdefault(b, []).append((a, w))
    for s, w in egress.items():
        back.setdefault(_DEST, []).append((s, w))
    best = {_DEST: (0.0, 0)}
    heap = [(0.0, 0, 0, _DEST)]
    count = 1
    while heap:
        d, boards, _, node = heapq.heappop(heap)
        if d > best[node][0]:
            continue
        for prev, w in back.get(node, ()):
            # prev -> node boards a train when prev is a station and node a car
            b = boards + (isinstance(prev, str) and isinstance(node, tuple))
            if d + w < best.get(prev, (np.inf, 0))[0]:
                best[prev] = (d + w, b)
                count += 1
                heapq.heappush(heap, (d + w, b, count, prev))
    return {k: v for k, v in best.items() if isinstance(k, str) and k != _DEST}


def compute(places: pd.DataFrame) -> pd.DataFrame:
    edges, stations = _network(features.GTFS_FILE)
    grid = features.facing_grid()
    at = grid(stations.stop_lon.to_numpy(), stations.stop_lat.to_numpy())
    registry = pd.read_parquet(features.lot_registry()).set_index("building")
    here = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    out = []
    for name, p in places.iterrows():
        there = grid(p.longitude, p.latitude)
        off = np.abs(at - there).sum(axis=1)
        egress = {
            s: m / transit.WALK_M_PER_MIN
            for s, m in zip(stations.index, off, strict=True)
            if m <= transit.WALK_REACH_M
        }
        trips = station_trips(edges, egress)
        ride = np.array([trips.get(s, (np.inf, 0))[0] for s in stations.index])
        boards = np.array([trips.get(s, (np.inf, 0))[1] for s in stations.index])
        for building, h in zip(registry.index, here, strict=True):
            if np.isnan(h).any():
                continue
            walk_m = np.abs(at - h).sum(axis=1)
            total = np.where(
                walk_m <= transit.WALK_REACH_M,
                walk_m / transit.WALK_M_PER_MIN + ride,
                np.inf,
            )
            i = int(total.argmin())
            on_foot = np.abs(there - h).sum() / transit.WALK_M_PER_MIN
            if on_foot <= total[i]:
                row = (on_foot, 0, on_foot, None)
            else:
                row = (
                    total[i],
                    max(int(boards[i]) - 1, 0),
                    walk_m[i] / transit.WALK_M_PER_MIN,
                    stations.stop_name.iloc[i],
                )
            out.append((building, name, p.address, *row))
    table = pd.DataFrame(
        out,
        columns=[
            "building",
            "destination",
            "address",
            "minutes",
            "transfers",
            "walk_to_station_min",
            "station",
        ],
    )
    table["minutes"] = table.minutes.round(1)
    table["walk_to_station_min"] = table.walk_to_station_min.round(1)
    return table


def build(places: pd.DataFrame | None = None) -> pd.DataFrame:
    """`compute` with FEATURE_SET's registry."""
    lots = features.lot_files(FEATURE_SET)
    token = features._LOTS.set((lots["registry"], lots["pluto"]))
    try:
        return compute(destinations() if places is None else places)
    finally:
        features._LOTS.reset(token)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=WISHES)
    args = parser.parse_args(argv)
    table = build()
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.out / f"commute-{dt.datetime.now(dt.UTC):%Y%m%d}"
    table.to_parquet(f"{base}.parquet")
    table.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({len(table)} building-destination rows)")
    print(
        table.groupby("destination")[["minutes", "transfers"]]
        .describe()
        .round(1)
        .T.to_string()
    )


if __name__ == "__main__":
    main()
