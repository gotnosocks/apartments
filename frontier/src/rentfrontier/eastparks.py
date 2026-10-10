"""`riverparks` with Pier 42 dated, for the East Village parks file.

The eight neighbourhoods' parks file (`features.NB8_PARKS_FILE`) adds Pier 42
(Montgomery St, 7.5 acres), which NYC Parks acquired 2006-07-14 and which
`parks.places` refuses: a recent acquisition needs its opening day. Its
northern strip opened for interim use 2013-05-04 as a repaved lot with picnic
tables; the finished park, the 8 acres the outline maps, opened 2024-07-03.
It is dated 2024-07-03 (`OPENED`). Everything else is `riverparks`. Reads no
rents.
"""

from __future__ import annotations

import functools
import json

import numpy as np
import pandas as pd

from . import features, parks, riverparks, transit

# NYC Parks properties of MIN_ACRES or more that neither `parks.SECTIONS` nor
# `riverparks.OPENED` dates, by the day they opened as they are mapped.
OPENED = {"Pier 42": "2024-07-03"}


def places(nyc: pd.DataFrame, river: pd.DataFrame) -> pd.DataFrame:
    """`riverparks.places`, with `OPENED` parks dated by that day."""
    dated = nyc.name.isin(OPENED)
    table = riverparks.places(nyc[~dated], river)
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
    extra = pd.DataFrame(rows, columns=["kind", "name", "opened", "points"])
    return pd.concat([table, extra], ignore_index=True)


@functools.lru_cache(maxsize=2)
def building_minutes(registry_file: str, parks_file: str, river_file: str):
    """`riverparks.building_minutes` over `places`."""
    table = places(pd.read_parquet(parks_file), pd.read_parquet(river_file))
    grid = features.facing_grid()
    registry = pd.read_parquet(registry_file).dropna(subset=["latitude", "longitude"])
    registry = registry.drop_duplicates("building").set_index("building")
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
    """`riverparks.terms` over `places`: per row, over places open before the
    listing's month began, `park_min`, `high_line` and `pier`."""
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
            ("pier", pier, riverparks.PIER_MIN),
        ):
            near = np.zeros(len(rows))
            if (ok & kind).any():
                near = wide[np.ix_(rows, ok & kind)].min(1) <= limit
            out[name][rows] = np.where(located[rows], near, np.nan)
    return pd.DataFrame(out, index=frame.index)
