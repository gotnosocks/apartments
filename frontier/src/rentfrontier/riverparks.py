"""Hudson River Park and its new piers, dated, beside the NYC Parks properties.

NYC Parks properties (`parks`) leave out Hudson River Park, a state park, so no
feature has carried the river parks that opened during the listings. This
module adds them as places a listing walks to, each counted from the day it
opened (`PLACES`):

- the park's esplanade and greenway (NYC Open Data jr73-mxkz, "Publicly Owned
  Waterfront", agency HRPT). Its sections beside the six neighbourhoods were
  open before the listings start in 2010: Chelsea Waterside 2000, Greenwich
  Village (Piers 45, 46, 51) 2003-05-30, Chelsea Cove 2009-10. It is dated
  2003-05-30. A walk reaches its east edge along West St, so the piers inside
  its outline (Pier 26, 2020, among them) don't shorten it.
- Little Island (Pier 55), opened 2021-05-21, OpenStreetMap way 833335529.
- Pier 57's rooftop park, opened 2022-04-18, OpenStreetMap relation 20786211
  (the pier).
- Gansevoort Peninsula, opened 2023-10-02 (jr73-mxkz).

The six neighbourhoods' parks file (`features.NB6_PARKS_FILE`) also reaches
Andrew Haswell Green Park (E 60th St), which `parks.SECTIONS` has no date for:
its acre-plus second phase opened 2023-12-19 (`OPENED`). Reads no rents.

    python -m rentfrontier.riverparks

writes EXTERNAL_ROOT/riverparks/<date>-<commit>/riverparks.parquet (name,
opened, source, geometry) and provenance.json. Refuses a dirty tree.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from . import features, parks, transit
from .listing_extras import EXTERNAL_ROOT, _git

WATERFRONT_URL = "https://data.cityofnewyork.us/resource/jr73-mxkz.geojson"
OSM_URL = "https://nominatim.openstreetmap.org/lookup"
USER_AGENT = "rentfrontier-research/1.0 (one-off lookup)"
# name, opened, source and the source's key: the waterfront dataset's name, or
# an OpenStreetMap id for Nominatim's lookup.
PLACES = (
    (
        "Hudson River Park esplanade",
        "2003-05-30",
        "jr73-mxkz",
        "Hudson River Park and Greenway",
    ),
    ("Little Island", "2021-05-21", "osm", "W833335529"),
    ("Pier 57 rooftop park", "2022-04-18", "osm", "R20786211"),
    ("Gansevoort Peninsula", "2023-10-02", "jr73-mxkz", "Gansevoort Peninsula (HRPT)"),
)
# The new piers (all but the esplanade): `pier` is whether one open by the
# listing's month is within PIER_MIN minutes.
PIERS = ("Little Island", "Pier 57 rooftop park", "Gansevoort Peninsula")
PIER_MIN = 10.0
# NYC Parks properties of MIN_ACRES or more that `parks.SECTIONS` doesn't
# date, by the day they opened as they are mapped.
OPENED = {"Andrew Haswell Green Park": "2023-12-19"}


def places(nyc: pd.DataFrame, river: pd.DataFrame) -> pd.DataFrame:
    """`parks.places` over the NYC Parks table, with `OPENED` parks dated by
    that day, plus the river places (kind "river pier" for PIERS, else
    "park")."""
    dated = nyc.name.isin(OPENED)
    table = parks.places(nyc[~dated])
    rows = [
        (
            "park",
            p.name,
            pd.Timestamp(OPENED[p.name]),
            parks.outline(json.loads(p.geometry)),
        )
        for p in nyc[dated].itertuples()
        if p.acres >= parks.MIN_ACRES
    ]
    rows += [
        (
            "river pier" if p.name in PIERS else "park",
            p.name,
            pd.Timestamp(p.opened),
            parks.outline(json.loads(p.geometry)),
        )
        for p in river.itertuples()
    ]
    extra = pd.DataFrame(rows, columns=["kind", "name", "opened", "points"])
    return pd.concat([table, extra], ignore_index=True)


@functools.lru_cache(maxsize=2)
def building_minutes(registry_file: str, parks_file: str, river_file: str):
    """Per registry building (index) and place (columns): walk minutes over
    the facing grid; and the places table."""
    table = places(pd.read_parquet(parks_file), pd.read_parquet(river_file))
    grid = features.facing_grid()
    registry = pd.read_parquet(registry_file).drop_duplicates("building")
    registry = registry.set_index("building")
    registry = registry[registry.latitude.notna()]
    homes = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    walk = np.empty((len(homes), len(table)))
    for k, points in enumerate(table.points):
        at = grid(points[:, 0], points[:, 1])
        walk[:, k] = np.concatenate(
            [
                np.abs(homes[i : i + 256, None, :] - at[None]).sum(-1).min(1)
                for i in range(0, len(homes), 256)
            ]
        )
    minutes = pd.DataFrame(walk / transit.WALK_M_PER_MIN, index=registry.index)
    return minutes, table


def terms(frame: pd.DataFrame, parks_file: str, river_file: str) -> pd.DataFrame:
    """Per row, over places open before the listing's month began
    (`parks.open_places`): `park_min`, the walk to the nearest park of
    MIN_ACRES or more, river places and High Line sections included;
    `high_line`, an open High Line section within HIGH_LINE_MIN; and `pier`,
    an open new river pier within PIER_MIN. NaN for a building without a
    position."""
    minutes, table = building_minutes(features.lot_registry(), parks_file, river_file)
    wide = minutes.reindex(frame.building.to_numpy()).to_numpy()
    located = ~np.isnan(wide[:, 0])
    out = {k: np.full(len(frame), np.nan) for k in ("park_min", "high_line", "pier")}
    line = (table.kind == "high line").to_numpy()
    pier = (table.kind == "river pier").to_numpy()
    periods = frame.period.astype(str).to_numpy()
    for period in np.unique(periods):
        rows = np.flatnonzero(periods == period)
        ok = parks.open_places(period, table.opened)
        out["park_min"][rows] = wide[np.ix_(rows, ok)].min(1)
        for name, kind, limit in (
            ("high_line", line, parks.HIGH_LINE_MIN),
            ("pier", pier, PIER_MIN),
        ):
            near = np.zeros(len(rows))
            if (ok & kind).any():
                near = wide[np.ix_(rows, ok & kind)].min(1) <= limit
            out[name][rows] = np.where(located[rows], near, np.nan)
    return pd.DataFrame(out, index=frame.index)


def _get(url: str, params: dict) -> dict:
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def fetch() -> tuple[pd.DataFrame, list[str]]:
    """PLACES with their outlines, and the URLs read."""
    urls, geometry = [], {}
    names = [key for _, _, source, key in PLACES if source == "jr73-mxkz"]
    where = "name in(" + ",".join(f"'{n}'" for n in names) + ")"
    params = {"$where": where, "$limit": 100}
    urls.append(f"{WATERFRONT_URL}?{urllib.parse.urlencode(params)}")
    for f in _get(WATERFRONT_URL, params)["features"]:
        geometry[f["properties"]["name"]] = f["geometry"]
    ids = [key for _, _, source, key in PLACES if source == "osm"]
    params = {"osm_ids": ",".join(ids), "format": "geojson", "polygon_geojson": 1}
    urls.append(f"{OSM_URL}?{urllib.parse.urlencode(params)}")
    for f in _get(OSM_URL, params)["features"]:
        p = f["properties"]
        geometry[f"{p['osm_type'][0].upper()}{p['osm_id']}"] = f["geometry"]
    rows = []
    for name, opened, source, key in PLACES:
        g = geometry[key]
        if g["type"] not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"{name}: {g['type']}, not an area")
        rows.append((name, pd.Timestamp(opened), source, key, json.dumps(g)))
    table = pd.DataFrame(rows, columns=["name", "opened", "source", "key", "geometry"])
    return table, urls


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    table, urls = fetch()
    out_dir = EXTERNAL_ROOT / "riverparks" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "riverparks.parquet"
    table.to_parquet(path, index=False)
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "sources": urls,
                "osm_licence": "OpenStreetMap contributors, ODbL",
                "retrieved_at": started.isoformat(),
                "commit": commit,
                "places": table[["name", "opened", "source", "key"]]
                .astype(str)
                .to_dict("records"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    print(f"wrote {path}: {len(table)} places")


if __name__ == "__main__":
    main()
