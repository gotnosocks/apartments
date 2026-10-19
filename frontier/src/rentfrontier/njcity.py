"""Rail stops, ferry landings and parks on the New Jersey side, for Hoboken and Jersey City.

The NYC features read MTA subway stations (`external subway`), NYC Parks properties (`parks`) and
Hudson River Park (`riverparks`), none of which cover New Jersey. PATH stations already have a
snapshot (`external/path`). This module snapshots the rest of what an NJ building walks to:

- NJ Transit rail stops (GTFS, Mobility Database mirror mdb-509): the Hudson-Bergen Light Rail
  stations and Hoboken Terminal's commuter rail, each with the routes stopping there.
- NY Waterway landings (GTFS, mdb-3192), each with its routes.
- Parks: OpenStreetMap `leisure=park` ways and relations, with outlines and acres.

All three cover BOX, which holds the four StreetEasy areas and the Manhattan shore across the
river. Reads no rents.

    python -m rentfrontier.njcity

writes EXTERNAL_ROOT/njcity/<date>-<commit>/transit.parquet (source, stop_id, name, mode,
routes, latitude, longitude), parks.parquet (osm_id, name, acres, geometry) and
provenance.json. Refuses a dirty tree.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import numpy as np
import pandas as pd

from .listing_extras import EXTERNAL_ROOT, _git

# south, west, north, east
BOX = (40.69, -74.10, 40.77, -74.01)
FEEDS = {
    "njt-rail": "https://files.mobilitydatabase.org/mdb-509/latest.zip",
    "ny-waterway": "https://files.mobilitydatabase.org/mdb-3192/latest.zip",
}
# GTFS route_type to mode, in the order a stop served by several modes takes its mode from.
MODES = {"2": "rail", "0": "light rail", "4": "ferry"}
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "rentfrontier-research/1.0 (one-off lookup)"
M_PER_DEG_LAT = 111_320.0
SQ_M_PER_ACRE = 4046.8564224


def _read(url: str, data: bytes | None = None, tries: int = 6) -> bytes:
    """The body at the URL. The public Overpass server often answers 502 or 504 when busy, so after
    a 5xx answer or a network error I send the request again after 5, 10, 20, 40 and 80 seconds.
    A 4xx answer fails at once."""
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except OSError as error:
            client = isinstance(error, urllib.error.HTTPError) and error.code < 500
            if client or attempt == tries - 1:
                raise
            time.sleep(5 * 2**attempt)
    raise AssertionError


def _table(z: zipfile.ZipFile, name: str) -> list[dict]:
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8-sig")))


def in_box(lat: float, lon: float) -> bool:
    south, west, north, east = BOX
    return south <= lat <= north and west <= lon <= east


def stops(source: str, blob: bytes) -> pd.DataFrame:
    """The feed's stops inside BOX that some trip stops at, with the short names (or long
    names) of the routes stopping there. A stop served by several modes takes the first of
    them in MODES order."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    routes = {r["route_id"]: r for r in _table(z, "routes.txt")}
    trip_route = {t["trip_id"]: t["route_id"] for t in _table(z, "trips.txt")}
    kept = {
        s["stop_id"]: s
        for s in _table(z, "stops.txt")
        if s.get("stop_lat") and in_box(float(s["stop_lat"]), float(s["stop_lon"]))
    }
    served: dict[str, set[str]] = {}
    for st in _table(z, "stop_times.txt"):
        if st["stop_id"] in kept:
            served.setdefault(st["stop_id"], set()).add(trip_route[st["trip_id"]])
    rows = []
    for stop_id, route_ids in served.items():
        s = kept[stop_id]
        named = sorted(
            {
                routes[r].get("route_short_name") or routes[r]["route_long_name"]
                for r in route_ids
            }
        )
        types = {routes[r]["route_type"] for r in route_ids}
        mode = next((m for t, m in MODES.items() if t in types), "other")
        rows.append(
            (
                source,
                stop_id,
                s["stop_name"],
                mode,
                ",".join(named),
                float(s["stop_lat"]),
                float(s["stop_lon"]),
            )
        )
    columns = ["source", "stop_id", "name", "mode", "routes", "latitude", "longitude"]
    return pd.DataFrame(rows, columns=columns).sort_values(["source", "name"])


def acres(geometry: dict) -> float:
    """Area of a GeoJSON Polygon or MultiPolygon in acres, on a local flat projection, with
    holes taken out."""
    polygons = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    total = 0.0
    for polygon in polygons:
        for i, ring in enumerate(polygon):
            r = np.asarray(ring, dtype=float)
            x = r[:, 0] * M_PER_DEG_LAT * np.cos(np.radians(r[:, 1].mean()))
            y = r[:, 1] * M_PER_DEG_LAT
            a = abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2
            total += -a if i else a
    return total / SQ_M_PER_ACRE


def stitch(lines: list[list[list[float]]]) -> list[list[list[float]]]:
    """Closed rings from member ways, joining open ways end to end. Ways left open drop out."""
    rings, open_ = [], [list(line) for line in lines if len(line) >= 2]
    while open_:
        ring = open_.pop(0)
        grown = True
        while ring[0] != ring[-1] and grown:
            grown = False
            for i, line in enumerate(open_):
                if line[0] == ring[-1]:
                    ring += line[1:]
                elif line[-1] == ring[-1]:
                    ring += line[::-1][1:]
                elif line[-1] == ring[0]:
                    ring = line[:-1] + ring
                elif line[0] == ring[0]:
                    ring = line[::-1][:-1] + ring
                else:
                    continue
                open_.pop(i)
                grown = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def outline(element: dict) -> dict | None:
    """A GeoJSON outline of an Overpass way or multipolygon relation (`out geom`): a closed way
    gives a Polygon, and a relation's outer and inner member ways, joined into rings, give a
    MultiPolygon."""

    def coords(points):
        return [[p["lon"], p["lat"]] for p in points]

    if element["type"] == "way":
        rings = stitch([coords(element.get("geometry", []))])
        return {"type": "Polygon", "coordinates": rings} if rings else None
    members = [m for m in element.get("members", []) if m.get("type") == "way"]
    outers = stitch(
        [coords(m.get("geometry", [])) for m in members if m.get("role") != "inner"]
    )
    inners = stitch(
        [coords(m.get("geometry", [])) for m in members if m.get("role") == "inner"]
    )
    if not outers:
        return None
    # Each inner ring goes with the first outer ring around its first point.
    polygons = [[o] for o in outers]
    for inner in inners:
        x, y = inner[0]
        for p in polygons:
            o = np.asarray(p[0])
            cross = (o[:-1, 1] > y) != (o[1:, 1] > y)
            with np.errstate(divide="ignore", invalid="ignore"):
                at = o[:-1, 0] + (y - o[:-1, 1]) * (o[1:, 0] - o[:-1, 0]) / (
                    o[1:, 1] - o[:-1, 1]
                )
            if np.count_nonzero(cross & (x < at)) % 2:
                p.append(inner)
                break
    return {"type": "MultiPolygon", "coordinates": polygons}


def parks() -> tuple[pd.DataFrame, str]:
    """OpenStreetMap parks inside BOX with their outlines, and the query sent. A park way that is
    also a member of a park relation counts once, as part of the relation. A reply carrying an
    Overpass runtime remark is incomplete, so I refuse it."""
    south, west, north, east = BOX
    box = f"({south},{west},{north},{east})"
    query = (
        f'[out:json][timeout:120];(way["leisure"="park"]{box};'
        f'relation["leisure"="park"]{box};);out body geom;'
    )
    reply = json.loads(
        _read(OVERPASS_URL, urllib.parse.urlencode({"data": query}).encode())
    )
    if "remark" in reply:
        raise RuntimeError(f"Overpass remark: {reply['remark']}")
    in_relation = {
        m["ref"]
        for e in reply["elements"]
        if e["type"] == "relation"
        for m in e.get("members", [])
        if m.get("type") == "way"
    }
    rows = []
    for e in reply["elements"]:
        if e["type"] == "way" and e["id"] in in_relation:
            continue
        g = outline(e)
        if g is None:
            continue
        rows.append(
            (
                f"{e['type'][0].upper()}{e['id']}",
                e.get("tags", {}).get("name"),
                acres(g),
                json.dumps(g),
            )
        )
    table = pd.DataFrame(rows, columns=["osm_id", "name", "acres", "geometry"])
    return table.sort_values("acres", ascending=False), query


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    blobs = {source: _read(url) for source, url in FEEDS.items()}
    transit = pd.concat([stops(s, b) for s, b in blobs.items()], ignore_index=True)
    park_table, query = parks()
    out_dir = EXTERNAL_ROOT / "njcity" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    files = {"transit.parquet": transit, "parks.parquet": park_table}
    for name, table in files.items():
        table.to_parquet(out_dir / name, index=False)
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "feeds": FEEDS,
                "feed_sha256": {
                    s: hashlib.sha256(b).hexdigest() for s, b in blobs.items()
                },
                "overpass": OVERPASS_URL,
                "overpass_query": query,
                "osm_licence": "OpenStreetMap contributors, ODbL",
                "box": BOX,
                "retrieved_at": started.isoformat(),
                "commit": commit,
                "stops": transit.groupby("mode").size().to_dict(),
                "parks": len(park_table),
                "sha256": {
                    name: hashlib.sha256((out_dir / name).read_bytes()).hexdigest()
                    for name in files
                },
            },
            indent=2,
        )
    )
    print(
        f"wrote {out_dir}: {transit.groupby('mode').size().to_dict()}, {len(park_table)} parks"
    )


if __name__ == "__main__":
    main()
