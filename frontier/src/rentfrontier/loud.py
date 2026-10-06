"""Loud streets an apartment looks onto: the terms `features.loud_v1`
(nb3-loud-v1) adds to the rent model.

A building's facades are classed by the street each one looks onto, as
`features.building_sides` classes them, but against every street centerline
(the Village's named streets too, which the base's sides leave out) and with
one split: a busy road (an avenue, or a roadway of at least
`quiet.BUSY_WIDTH_FT`: 14th and 23rd St, Hudson, Varick, Houston, Seventh Ave
South) or a quieter street.

An apartment looks onto a busy road when one of its listings shows a window on
a busy facade, or puts it at the front (F/R labels, ad text, views) of a
building whose address street is busy. Most apartments show no side at all
(2026-10-06: none of 777 Sixth Ave's or 225 W 14th St's); for those the term
is the chance a facade of theirs is a busy one: the building's share of busy
facades, or of busy street facades when its line's earlier listings put it on
a street (`features.line_orientation`), and 0 when they put it at the rear.
Reads no rents; the street map and footprints are today's.
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from . import features, quiet


def street_kind(name: str, attributes: dict) -> str | None:
    """ "busy" or "quiet" for a street centerline a facade may look onto (the
    roadway types `features.building_sides` reads), None for other ways."""
    roadway = attributes.get("rw_type")
    if roadway not in ("1", "2", "3", "9"):
        return None
    width = pd.to_numeric(attributes.get("streetwidth"), errors="coerce")
    avenue = features.street_kind(name, roadway) == "avenue"
    return "busy" if avenue or width >= quiet.BUSY_WIDTH_FT else "quiet"


def building_street_sides() -> pd.DataFrame:
    """Per registry building with a footprint, per grid direction: "busy",
    "quiet", "none" (no street) or "no facade"."""
    return _building_street_sides(features.lot_registry(), *features.area_snapshot())


@functools.lru_cache(maxsize=2)
def _building_street_sides(
    registry_file: str, basemap_file: str, footprints_file: str
) -> pd.DataFrame:
    streets = features.street_lines(basemap_file, street_kind)
    out = {
        building: features.facade_sides(ring, streets, occluders)
        for building, ring, occluders in features.building_outlines(
            registry_file, footprints_file, features.SIDE_REACH_M
        )
    }
    return pd.DataFrame.from_dict(out, orient="index")


def busy_share(sides: pd.DataFrame, street_only: bool = False) -> np.ndarray:
    """Per building row: its busy facades' share of its facades (of its street
    facades with street_only); 0 with none."""
    busy = sides.eq("busy").sum(axis=1).to_numpy()
    if street_only:
        total = sides.isin(["busy", "quiet"]).sum(axis=1).to_numpy()
    else:
        total = (sides.notna() & sides.ne("no facade")).sum(axis=1).to_numpy()
    return np.where(total > 0, busy / np.maximum(total, 1), 0.0)


def unit_terms(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Per row: "looks": its apartment looks onto a busy road (its own
    listings, pooled); "chance": for an apartment that shows no side, the chance
    one of its facades is busy (0 otherwise)."""
    b = frame.building.to_numpy()
    sides = building_street_sides().reindex(b)
    has_sides = sides.notna().all(axis=1).to_numpy()
    windows = np.zeros(len(frame), bool)
    busy_window = np.zeros(len(frame), bool)
    for d in features.GRID_DIRECTIONS:
        window = frame[f"window_{d}"].eq("yes").to_numpy() & has_sides
        windows |= window
        busy_window |= window & sides[d].eq("busy").to_numpy()
    front, rear = features.front_rear(frame)
    address_busy = quiet.building_streets().on_busy.reindex(b).eq(True).to_numpy()
    rows = pd.DataFrame(
        {"looks": busy_window | (front & address_busy), "seen": windows | front | rear}
    )
    pooled = rows.groupby(frame.unit_id.to_numpy()).transform("any")
    looks, seen = pooled.looks.to_numpy(), pooled.seen.to_numpy()
    line = features.line_orientation(frame).to_numpy()
    chance = np.where(
        np.isin(line, ["street", "both"]),
        busy_share(sides, street_only=True),
        np.where(line == "rear", 0.0, busy_share(sides)),
    )
    return {"looks": looks, "chance": np.where(seen, 0.0, chance)}
