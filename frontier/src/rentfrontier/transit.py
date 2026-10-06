"""Subway time to midtown: per registry building, the weekday morning door to
platform-exit time to the nearest of Times Sq-42 St, Grand Central-42 St and
34 St-Herald Sq (`MIDTOWN`), and the walk to its nearest station; the terms
`features.transit_v1` (nb3-transit-v1) adds to the rent model.

From the MTA's static subway GTFS (`features.GTFS_FILE`, today's schedule),
weekday trips leaving 07:00-10:00. The Chelsea and Village lines are older
than the listings; a listing walks only to stations open when its month began
(`features.stops_not_open`: 34 St-Hudson Yards from September 2015):

- riding: each line's median time between consecutive stations;
- boarding: half that line's median headway at the station, in its direction
  (at most `MAX_WAIT_MIN`), so a frequent line beats a rare one;
- transfers: within a station free beyond the next boarding wait, between
  stations the feed's `min_transfer_time`;
- walking: grid (Manhattan) distance at `WALK_M_PER_MIN` from the building to a
  station entrance point (the station's position) within `WALK_REACH_M`, or
  straight to a midtown station.

No timetable or walking network beyond that; a measure for comparing
buildings, not a trip planner. Reads no rents.

    python -m rentfrontier.transit      # prints the table for the registry
"""

from __future__ import annotations

import functools
import heapq
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import features

MIDTOWN = {
    "127": "Times Sq-42 St",
    "631": "Grand Central-42 St",
    "D17": "34 St-Herald Sq",
}
WALK_M_PER_MIN = 80.0
WALK_REACH_M = 1500.0
MAX_WAIT_MIN = 10.0
HOURS = (7 * 3600, 10 * 3600)


def _seconds(clock: pd.Series) -> np.ndarray:
    hms = clock.str.split(":", expand=True).astype(int)
    return (hms[0] * 3600 + hms[1] * 60 + hms[2]).to_numpy()


def _reader(gtfs: str):
    """read(name, **kw) -> DataFrame of a GTFS table, from a zip or a folder."""
    if str(gtfs).endswith(".zip"):
        with zipfile.ZipFile(gtfs) as z:
            files = {n: z.read(n) for n in z.namelist()}
        return lambda name, **kw: pd.read_csv(io.BytesIO(files[name]), dtype=str, **kw)
    return lambda name, **kw: pd.read_csv(Path(gtfs) / name, dtype=str, **kw)


def network(gtfs: str) -> tuple[dict, pd.DataFrame]:
    """(edges, stations): edges[node] -> [(next node, minutes)] where a node is
    a station (parent stop id) or (station, route, direction) on board;
    stations has each parent stop's name and position."""
    read = _reader(gtfs)
    stops = read("stops.txt")
    parent = dict(zip(stops.stop_id, stops.parent_station.fillna(stops.stop_id)))
    stations = stops[stops.location_type.eq("1")].set_index("stop_id")
    stations = stations[["stop_name", "stop_lat", "stop_lon"]].astype(
        {"stop_lat": float, "stop_lon": float}
    )
    calendar = read("calendar.txt")
    weekday = set(calendar.service_id[calendar.wednesday.eq("1")])
    trips = read("trips.txt")
    trips = trips[trips.service_id.isin(weekday)].set_index("trip_id")
    times = read(
        "stop_times.txt",
        usecols=["trip_id", "stop_id", "departure_time", "stop_sequence"],
    )
    times = times[times.trip_id.isin(trips.index)].copy()
    times["t"] = _seconds(times.departure_time)
    times["seq"] = times.stop_sequence.astype(int)
    times["station"] = times.stop_id.map(parent)
    times["route"] = times.trip_id.map(trips.route_id)
    times["dir"] = times.trip_id.map(trips.direction_id)
    times = times.sort_values(["trip_id", "seq"])
    start = times.groupby("trip_id").t.transform("min")
    times = times[(start >= HOURS[0]) & (start < HOURS[1])]

    nxt = times.groupby("trip_id").shift(-1)
    hops = pd.DataFrame(
        {
            "a": times.station,
            "b": nxt.station,
            "route": times.route,
            "dir": times.dir,
            "min": (nxt.t - times.t) / 60,
        }
    ).dropna()
    hops = hops.groupby(["a", "b", "route", "dir"], as_index=False)["min"].median()

    waits = (
        times.sort_values("t")
        .groupby(["station", "route", "dir"])
        .t.agg(
            lambda t: np.median(np.diff(t.to_numpy())) / 60 if len(t) > 1 else np.inf
        )
    )
    edges: dict = {}
    for (station, route, d), headway in waits.items():
        car = (station, route, d)
        wait = min(headway / 2, MAX_WAIT_MIN)
        edges.setdefault(station, []).append((car, wait))
        edges.setdefault(car, []).append((station, 0.0))
    for h in hops.itertuples():
        edges.setdefault((h.a, h.route, h.dir), []).append(
            ((h.b, h.route, h.dir), h.min)
        )
    transfers = read("transfers.txt")
    for t in transfers.itertuples():
        a, b = parent.get(t.from_stop_id), parent.get(t.to_stop_id)
        if a and b and a != b:
            edges.setdefault(a, []).append((b, float(t.min_transfer_time or 0) / 60))
    return edges, stations


def station_minutes(edges: dict, targets) -> dict:
    """Minutes from each station to the nearest of targets (stations)."""
    back: dict = {}
    for a, out in edges.items():
        for b, w in out:
            back.setdefault(b, []).append((a, w))
    best = {t: 0.0 for t in targets}
    heap = [(0.0, i, t) for i, t in enumerate(targets)]
    count = len(heap)
    while heap:
        d, _, node = heapq.heappop(heap)
        if d > best.get(node, np.inf):
            continue
        for prev, w in back.get(node, ()):
            if d + w < best.get(prev, np.inf):
                best[prev] = d + w
                count += 1
                heapq.heappush(heap, (d + w, count, prev))
    return {k: v for k, v in best.items() if isinstance(k, str)}


def building_transit(exclude=frozenset()) -> pd.DataFrame:
    """Per registry building: minutes to midtown, walk minutes to its nearest
    station, and that station's name, walking only to stations not in
    `exclude` (GTFS parent ids)."""
    return _building_transit(features.lot_registry(), features.GTFS_FILE, exclude)


@functools.lru_cache(maxsize=1)
def _network(gtfs: str):
    edges, stations = network(gtfs)
    return station_minutes(edges, list(MIDTOWN)), stations


@functools.lru_cache(maxsize=4)
def _building_transit(
    registry_file: str, gtfs: str, exclude: frozenset
) -> pd.DataFrame:
    ride, stations = _network(gtfs)
    stations = stations[~stations.index.isin(exclude)]
    at = features.facing_grid()(
        stations.stop_lon.to_numpy(), stations.stop_lat.to_numpy()
    )
    ride_min = stations.index.map(lambda s: ride.get(s, np.inf)).to_numpy(float)
    target = stations.index.isin(list(MIDTOWN))
    registry = pd.read_parquet(registry_file).set_index("building")
    grid = features.facing_grid()
    rows = []
    for building, r in registry.iterrows():
        if pd.isna(r.latitude):
            rows.append((building, np.nan, np.nan, None))
            continue
        walk = np.abs(at - grid(r.longitude, r.latitude)).sum(axis=1) / WALK_M_PER_MIN
        total = np.where(walk * WALK_M_PER_MIN <= WALK_REACH_M, walk + ride_min, np.inf)
        total = np.where(target, walk, total)  # walking all the way counts too
        i = int(walk.argmin())
        rows.append(
            (building, float(total.min()), float(walk[i]), stations.stop_name.iloc[i])
        )
    return pd.DataFrame(
        rows, columns=["building", "midtown_min", "station_walk_min", "station"]
    ).set_index("building")


def midtown_minutes(frame: pd.DataFrame) -> np.ndarray:
    """Per row: minutes to midtown as of the listing's month."""
    closed = frame.period.map(features.stops_not_open)
    out = np.full(len(frame), np.nan)
    for exclude in closed.unique():
        rows = (closed == exclude).to_numpy()
        table = building_transit(exclude)
        out[rows] = table.midtown_min.reindex(
            frame.building.to_numpy()[rows]
        ).to_numpy()
    return out


def main(argv=None):
    table = building_transit()
    print(table.describe().round(1).to_string())
    print(table.sort_values("midtown_min").to_string(max_rows=40))


if __name__ == "__main__":
    main()
