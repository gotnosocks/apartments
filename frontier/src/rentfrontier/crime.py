"""Felonies reported near each building, from NYPD's complaint data on NYC
Open Data (historic: qgea-i56i, 2006 on; current year: 5uac-w243), in the
precincts around the neighbourhoods (`PRECINCTS`):

    python -m rentfrontier.crime

writes EXTERNAL_ROOT/crime/<date>-<commit>/felonies.csv (complaint number,
report date, offense key, latitude, longitude) and provenance.json. Refuses a
dirty tree.

A listing counts the felonies reported in the `WINDOW` before its day, never
on or after it. NYPD publishes each quarter some weeks after it ends, so a
renter could not have read the latest weeks yet; the count is still of crimes
reported before the listing, which is the rule for this term.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from rentfrontier.listing_extras import EXTERNAL_ROOT, _git

DATASETS = ("qgea-i56i", "5uac-w243")
# Manhattan precincts covering Chelsea, the Villages, Flatiron, Gramercy, East
# Village, Stuy Town and NoMad, and those bordering them within `RADIUS_M`.
PRECINCTS = ("1", "5", "6", "7", "9", "10", "13", "14", "17")
RADIUS_M = 250.0
WINDOW = dt.timedelta(days=365)
URL = "https://data.cityofnewyork.us/resource/{}.csv"
PAGE = 50_000


def query(dataset: str, offset: int) -> str:
    return (
        URL.format(dataset)
        + "?"
        + urllib.parse.urlencode(
            {
                "$select": "cmplnt_num,rpt_dt,ky_cd,latitude,longitude",
                "$where": f"law_cat_cd = 'FELONY' and addr_pct_cd in"
                f" ({','.join(repr(p) for p in PRECINCTS)})",
                "$order": "cmplnt_num",
                "$limit": str(PAGE),
                "$offset": str(offset),
            }
        )
    )


def _metres(lat, lon) -> np.ndarray:
    """Local east and north metres, flat about 40.74° N."""
    lat0 = np.radians(40.74)
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    return np.column_stack(
        [np.radians(lon) * 6_371_000.0 * np.cos(lat0), np.radians(lat) * 6_371_000.0]
    )


def felonies_near(
    latitude, longitude, at: pd.Series, felonies: pd.DataFrame
) -> np.ndarray:
    """Per point and listing day `at` (naive), the felonies within `RADIUS_M`
    metres reported in [day - `WINDOW`, day); NaN for a point without
    coordinates or a window the table does not cover."""
    days = pd.to_datetime(at).dt.normalize().to_numpy()
    span = np.timedelta64(WINDOW.days, "D")
    reported = pd.to_datetime(felonies.rpt_dt).dt.normalize().to_numpy()
    found = _metres(felonies.latitude, felonies.longitude)
    placed = np.isfinite(found).all(axis=1)
    first, last = reported.min(), reported.max()
    reported, tree = reported[placed], cKDTree(found[placed])
    where = _metres(latitude, longitude)
    covered = (
        np.isfinite(where).all(axis=1)
        & (days - span >= first)
        & (days <= last + np.timedelta64(1, "D"))
    )
    out = np.full(len(days), np.nan)
    # One neighbourhood query per distinct point; dates by binary search.
    rows = np.flatnonzero(covered)
    points, inverse = np.unique(where[rows], axis=0, return_inverse=True)
    inverse = inverse.ravel()
    order = np.argsort(inverse, kind="stable")
    bounds = np.searchsorted(inverse[order], np.arange(len(points) + 1))
    for k, near in enumerate(tree.query_ball_point(points, RADIUS_M)):
        dates = np.sort(reported[near])
        mine = rows[order[bounds[k] : bounds[k + 1]]]
        out[mine] = np.searchsorted(dates, days[mine]) - np.searchsorted(
            dates, days[mine] - span
        )
    return out


def fetch(dataset: str) -> tuple[pd.DataFrame, list[str]]:
    parts, hashes, offset = [], [], 0
    while True:
        url = query(dataset, offset)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=300) as r:
                    raw = r.read()
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(30 * (attempt + 1))
        page = pd.read_csv(io.BytesIO(raw), dtype={"cmplnt_num": str, "ky_cd": str})
        parts.append(page)
        hashes.append(hashlib.sha256(raw).hexdigest())
        offset += len(page)
        if len(page) < PAGE:
            return pd.concat(parts, ignore_index=True), hashes
        time.sleep(3)


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    parts, sources = [], []
    for dataset in DATASETS:
        got, hashes = fetch(dataset)
        parts.append(got)
        sources.append(
            {
                "dataset": dataset,
                "query": query(dataset, 0),
                "rows": len(got),
                "page_sha256": hashes,
            }
        )
    # The current-year table may repeat a complaint the historic one has.
    table = pd.concat(parts, ignore_index=True).drop_duplicates("cmplnt_num")
    table["rpt_dt"] = pd.to_datetime(table.rpt_dt).dt.date
    table = table.sort_values(["rpt_dt", "cmplnt_num"])
    out_dir = EXTERNAL_ROOT / "crime" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "felonies.csv"
    table.to_csv(path, index=False)
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "built_at": started.isoformat(),
                "commit": commit,
                "precincts": PRECINCTS,
                "sources": sources,
                "reported": [str(table.rpt_dt.min()), str(table.rpt_dt.max())],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {path}: {len(table)} felonies")
    print(table.rpt_dt.map(lambda d: d.year).value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
