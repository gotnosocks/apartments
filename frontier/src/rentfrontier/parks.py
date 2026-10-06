"""Parks within reach: per registry building, the walk to the nearest park of at
least `MIN_ACRES` acres and whether an open section of the High Line is within
`HIGH_LINE_MIN` minutes, the terms `features.parks_v1` (nb3-parks-v1) adds to
the rent model, and one row per building for the site.

Parks come from NYC Parks properties (`features.PARKS_FILE`). A walk is the
grid distance (`features.facing_grid`) to the nearest point of a park's
outline, densified every `STEP_M` metres, at `transit.WALK_M_PER_MIN`. A
listing counts only parks NYC Parks had acquired before its month began (a park
without a date counts as always open), and the High Line only by the sections
open by then (`HIGH_LINE_OPENED`): its acquisition date (2006) precedes every
section. Hudson River Park is a state park and not in the source.

    python -m rentfrontier.parks      # writes WISHES/parks-<date>.parquet and .csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import features, transit

WISHES = Path("/data1/apartments/wishes")
FEATURE_SET = "nb3-parks-v1"
MIN_ACRES = 1.0
STEP_M = 20.0
HIGH_LINE_MIN = 5.0
HIGH_LINE = "The High Line"
# High Line sections, the latitude of each one's south end, and opening days.
HIGH_LINE_OPENED = (
    ("Gansevoort St to W 20th St", -90.0, "2009-06-08"),
    ("W 20th St to W 30th St", 40.7462, "2011-06-08"),
    ("W 30th St to W 34th St", 40.7522, "2014-09-21"),
)


def outline(geometry: dict, step: float = STEP_M) -> np.ndarray:
    """A (Multi)Polygon's rings as lon/lat points, adding points along each edge
    so none is more than about `step` metres from the next."""
    polygons = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    out = []
    for ring in (r for p in polygons for r in p):
        ring = np.asarray(ring, dtype=float)[:, :2]
        for a, b in itertools.pairwise(ring):
            metres = np.hypot(
                (b[0] - a[0]) * 111_320.0 * np.cos(np.radians(a[1])),
                (b[1] - a[1]) * 111_320.0,
            )
            n = max(int(np.ceil(metres / step)), 1)
            out.append(a + (b - a) * (np.arange(n) / n)[:, None])
        out.append(ring[-1:])
    return np.concatenate(out)


def places(table: pd.DataFrame) -> pd.DataFrame:
    """One row per place a listing can walk to: each park of MIN_ACRES or more
    (opened = its acquisition date) and each High Line section (opened from
    HIGH_LINE_OPENED), with its outline points (`lon`, `lat` arrays)."""
    rows = []
    for park in table.itertuples():
        if park.name != HIGH_LINE and not park.acres >= MIN_ACRES:
            continue
        points = outline(json.loads(park.geometry))
        if park.name != HIGH_LINE:
            rows.append(("park", park.name, park.acquired, points))
            continue
        north = [lo for _, lo, _ in HIGH_LINE_OPENED[1:]] + [90.0]
        for (section, lo, day), hi in zip(HIGH_LINE_OPENED, north, strict=True):
            part = points[(points[:, 1] >= lo) & (points[:, 1] < hi)]
            if len(part):
                name = f"{HIGH_LINE}, {section}"
                rows.append(("high line", name, pd.Timestamp(day), part))
    return pd.DataFrame(rows, columns=["kind", "name", "opened", "points"])


def building_minutes() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per registry building (index) and place (columns): walk minutes; and the
    places table (`places`)."""
    return _building_minutes(features.lot_registry(), features.PARKS_FILE)


@functools.lru_cache(maxsize=2)
def _building_minutes(registry_file: str, parks_file: str):
    table = places(pd.read_parquet(parks_file))
    grid = features.facing_grid()
    registry = pd.read_parquet(registry_file).set_index("building")
    registry = registry[registry.latitude.notna()]
    homes = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    walk = np.empty((len(homes), len(table)))
    for k, points in enumerate(table.points):
        at = grid(points[:, 0], points[:, 1])
        walk[:, k] = np.abs(homes[:, None, :] - at[None]).sum(-1).min(1)
    minutes = pd.DataFrame(walk / transit.WALK_M_PER_MIN, index=registry.index)
    return minutes, table


def open_places(period, opened: pd.Series) -> np.ndarray:
    """Which places had opened (or been acquired) before `period`'s month
    began; a place without a date counts as open."""
    start = pd.Timestamp(str(period)).replace(day=1)
    return (opened.isna() | (opened < start)).to_numpy()


def park_terms(frame: pd.DataFrame) -> pd.DataFrame:
    """Per row: `park_min`, the walk to the nearest open park of MIN_ACRES or
    more (the High Line's open sections included), and `high_line`, whether an
    open High Line section is within HIGH_LINE_MIN; NaN for a building without
    a position."""
    minutes, table = building_minutes()
    wide = minutes.reindex(frame.building.to_numpy()).to_numpy()
    park = np.full(len(frame), np.nan)
    high = np.full(len(frame), np.nan)
    line = (table.kind == "high line").to_numpy()
    periods = frame.period.astype(str).to_numpy()
    for period in np.unique(periods):
        rows = np.flatnonzero(periods == period)
        ok = open_places(period, table.opened)
        if ok.any():
            park[rows] = wide[np.ix_(rows, ok)].min(1)
        near = 0.0
        if (ok & line).any():
            near = wide[np.ix_(rows, ok & line)].min(1) <= HIGH_LINE_MIN
        high[rows] = np.where(np.isnan(wide[rows, 0]), np.nan, near)
    return pd.DataFrame({"park_min": park, "high_line": high}, index=frame.index)


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    """`building_minutes` with FEATURE_SET's registry."""
    lots = features.lot_files(FEATURE_SET)
    token = features._LOTS.set((lots["registry"], lots["pluto"]))
    try:
        return building_minutes()
    finally:
        features._LOTS.reset(token)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=WISHES)
    args = parser.parse_args(argv)
    minutes, table = build()
    names = table.name.to_numpy()
    line = (table.kind == "high line").to_numpy()
    out = pd.DataFrame(
        {
            "building": minutes.index,
            "nearest_park": names[minutes.to_numpy().argmin(1)],
            "park_min": minutes.min(1).round(1).to_numpy(),
            "high_line_min": minutes.loc[:, line].min(1).round(1).to_numpy(),
        }
    )
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.out / f"parks-{dt.datetime.now(dt.UTC):%Y%m%d}"
    out.to_parquet(f"{base}.parquet")
    out.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({len(out)} buildings, {len(table)} places)")
    print(out[["park_min", "high_line_min"]].describe().round(1).to_string())


if __name__ == "__main__":
    main()
