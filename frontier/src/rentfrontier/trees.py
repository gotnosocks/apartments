"""Street trees near each building, from NYC Parks' street tree censuses on NYC
Open Data (2005: 29bw-z7pj; 2015: uvpi-gqnh), each read only from the day it
was published (`CENSUSES`, plus `BUFFER`), so a listing counts the trees of
the latest census out by then:

    python -m rentfrontier.trees

writes EXTERNAL_ROOT/trees/<date>-<commit>/trees.csv (census, alive,
latitude, longitude; the trees in `BOX`) and provenance.json. Refuses a dirty
tree.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from rentfrontier.listing_extras import EXTERNAL_ROOT, _git

# Census year: (dataset, the statuses of a live tree, the day it was published).
# The 2005 census was reported in 2006-07, before the first listing (2010);
# the 2015 census went up on NYC Open Data on 2016-06-03.
CENSUSES = {
    2005: ("29bw-z7pj", ("Excellent", "Good", "Poor"), "2007-01-01"),
    2015: ("uvpi-gqnh", ("Alive",), "2016-06-03"),
}
BUFFER = dt.timedelta(days=7)
# South, north, west, east: lower Manhattan from Canal St to 59th St, with a margin.
BOX = (40.70, 40.77, -74.03, -73.96)
RADIUS_M = 100.0
URL = "https://data.cityofnewyork.us/resource/{}.csv"


def query(dataset: str) -> str:
    south, north, west, east = BOX
    return (
        URL.format(dataset)
        + "?"
        + urllib.parse.urlencode(
            {
                "$select": "status,latitude,longitude",
                "$where": f"latitude between {south} and {north}"
                f" and longitude between {west} and {east}",
                "$limit": "500000",
            }
        )
    )


def _metres(lat, lon) -> np.ndarray:
    """Local east and north metres, flat about the box's centre."""
    lat0 = np.radians((BOX[0] + BOX[1]) / 2)
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    return np.column_stack(
        [np.radians(lon) * 6_371_000.0 * np.cos(lat0), np.radians(lat) * 6_371_000.0]
    )


def live_trees_near(
    latitude, longitude, at: pd.Series, trees: pd.DataFrame
) -> np.ndarray:
    """Per point and listing day `at` (naive), the live street trees within
    `RADIUS_M` metres in the latest census published (plus `BUFFER`) by that
    day; NaN for a point without coordinates or a day before every census."""
    days = pd.to_datetime(at).dt.normalize().to_numpy()
    where = _metres(latitude, longitude)
    known = np.isfinite(where).all(axis=1)
    out = np.full(len(days), np.nan)
    for year, (_, _, published) in sorted(CENSUSES.items()):
        live = trees[trees.census.eq(year) & trees.alive]
        tree = cKDTree(_metres(live.latitude, live.longitude))
        rows = known & (days >= np.datetime64(pd.Timestamp(published) + BUFFER))
        out[rows] = tree.query_ball_point(where[rows], RADIUS_M, return_length=True)
    return out


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    parts, sources = [], []
    for year, (dataset, alive, published) in sorted(CENSUSES.items()):
        url = query(dataset)
        with urllib.request.urlopen(url, timeout=300) as r:
            raw = r.read()
        got = pd.read_csv(io.BytesIO(raw)).dropna(subset=["latitude", "longitude"])
        parts.append(
            pd.DataFrame(
                {
                    "census": year,
                    "alive": got.status.isin(alive),
                    "latitude": got.latitude,
                    "longitude": got.longitude,
                }
            )
        )
        sources.append(
            {
                "census": year,
                "dataset": dataset,
                "url": url,
                "published": published,
                "rows": len(got),
                "statuses": got.status.value_counts(dropna=False).to_dict(),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    table = pd.concat(parts, ignore_index=True)
    out_dir = EXTERNAL_ROOT / "trees" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "trees.csv"
    table.to_csv(path, index=False)
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "built_at": started.isoformat(),
                "commit": commit,
                "box": BOX,
                "sources": sources,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    print(f"wrote {path}")
    print(table.groupby(["census", "alive"]).size().to_string())


if __name__ == "__main__":
    main()
