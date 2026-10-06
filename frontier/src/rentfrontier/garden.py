"""Garden view, one row per apartment, for the site and as a wish to price: does
the apartment look out over the open middle of its block (the rear yards and
gardens) rather than a light well, an air shaft or the next building's wall?

The table is a current snapshot, pooled over every listing like `exposure`, to
show. The model input is `features.garden_v1` (per row, its line read as of
earlier listings; footprints are today's, as for the building sides). Evidence, per apartment:

- stated: a listing ticks "garden view" or its ad says so (`GARDEN_TEXT`);
- open: how far its rear windows can see before another building's wall
  (`block_openness`: rays from each rear facade, footprints of every building);
  windows from its own listings, else the side its exposure label (own or line)
  puts it on;
- yard: the lot's own rear yard in feet (MapPLUTO lot depth less building depth,
  inside lots only), for reference.

Labels describe the evidence, not a probability: "stated"; "open rear" when
the rear windows see at least `SHUT_OPEN_M` of open block; "walled rear" when
they see less (a shaft or the next wall); "" with no rear windows known. Ad text
does not confirm the measure: ads mention a garden from 6-11% of measured
apartments whatever the distance (2026-10-06), and the floor matters more
(listings tick garden view for 18% of measured apartments on floors 1-5, 11%
above), so the table carries the floor. Whether the rent model can use it is
for PSIS-LOO to judge (`features.garden_v1`, nb3-garden-v1, which reads no rents).

    python -m rentfrontier.garden            # writes WISHES/garden-<date>.parquet and .csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import itertools
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, descriptions, exposure, features

WISHES = Path("/data1/apartments/wishes")
FEATURE_SET = "nb3-lineface-v1"
OPEN_REACH_M = 60.0
CONTACT_M = 1.0  # a wall that touches the next building has no windows
SHUT_OPEN_M = 8.0
# Not Madison Square Garden or a roof garden.
_GARDEN = r"(?<!square )(?<!roof )(?<!rooftop )\b(?:gardens?|back ?yards?|rear yards?)"
GARDEN_TEXT = (
    rf"{_GARDEN}[- ]views?|\b(?:overlook\w*|views? (?:of|over|onto)|fac\w*|look\w* "
    rf"(?:out )?(?:on|over)\w*)[^.]{{0,30}}{_GARDEN}"
)
# A far-off direction, so a parity count never runs along a grid-aligned edge.
_FAR = np.array([1000.0, 731.0])


def clear_distances(ring, occluders, reach: float = OPEN_REACH_M) -> dict:
    """For one counter-clockwise outline (grid metres): per grid direction the
    distances rays from its facades travel before a wall (capped at reach), one
    per `features.SIDE_SPACING_M` of facade; 0 where the ray starts inside
    another building (a party wall shared edge to edge)."""
    e0 = np.concatenate([occluders[0], ring[:-1]])
    e1 = np.concatenate([occluders[1], ring[1:]])
    out = {d: [] for d in features.GRID_DIRECTIONS}
    for p, q in itertools.pairwise(ring):
        edge = q - p
        length = float(np.hypot(*edge))
        if length < features.SIDE_MIN_EDGE_M:
            continue
        normal = np.array([edge[1], -edge[0]]) / length
        side = max(
            features.GRID_DIRECTIONS,
            key=lambda d: normal @ np.array(features.GRID_DIRECTIONS[d]),
        )
        spots = np.arange(features.SIDE_SPACING_M / 2, length, features.SIDE_SPACING_M)
        for s in spots if len(spots) else [length / 2]:
            start = p + edge * (s / length) + 0.3 * normal
            inside = np.isfinite(features._hits(start, start + _FAR, *occluders))
            if inside.sum() % 2:
                out[side].append(0.0)
                continue
            hit = features._hits(start, start + reach * normal, e0, e1)
            out[side].append(
                0.3 + reach * min(float(hit.min()) if len(hit) else 1.0, 1.0)
            )
    return out


def openness(distances: list) -> float:
    """A facade's open distance: the median over its spots that don't touch
    the next building (NaN when every spot does)."""
    d = np.asarray(distances)
    d = d[d > CONTACT_M]
    return float(np.median(d)) if len(d) else np.nan


def block_openness() -> pd.DataFrame:
    """Per registry building with a footprint, per grid direction: the open
    distance its facades on that side look across (metres, NaN with none)."""
    return _block_openness(features.lot_registry(), *features.area_snapshot())


@functools.lru_cache(maxsize=2)
def _block_openness(registry_file: str, basemap_file: str, footprints_file: str):
    # The outline choice and the grid are `features._building_sides`'s.
    registry = pd.read_parquet(registry_file).set_index("building")
    lat0, lon0 = features._grid_origin()
    phi, metres = math.radians(features.FRONTAGE_BEARING_DEG), 111_320.0
    cos0 = math.cos(math.radians(lat0))

    def grid(lon, lat):
        east = (np.asarray(lon, float) - lon0) * metres * cos0
        north = (np.asarray(lat, float) - lat0) * metres
        return np.stack(
            [
                east * math.cos(phi) - north * math.sin(phi),
                east * math.sin(phi) + north * math.cos(phi),
            ],
            -1,
        )

    def rings_of(geometry):
        geometry = json.loads(geometry)
        polygons = geometry["coordinates"]
        polygons = polygons if geometry["type"] == "MultiPolygon" else [polygons]
        return [grid([q[0] for q in pg[0]], [q[1] for q in pg[0]]) for pg in polygons]

    footprints = pd.read_parquet(footprints_file)
    e0, e1, owner = [], [], []
    for r in footprints.itertuples():
        for ring in rings_of(r.geometry):
            e0.append(ring[:-1])
            e1.append(ring[1:])
            owner += [str(r.bin)] * (len(ring) - 1)
    e0, e1 = np.concatenate(e0), np.concatenate(e1)
    owner = np.array(owner)
    by_bin = footprints.groupby(footprints.bin.astype(str))
    by_lot = footprints.groupby(footprints.base_bbl.astype(str))
    out = {}
    for building, r in registry.iterrows():
        key_bin, key_lot = str(r.bin), str(r.bbl)
        if not re.fullmatch(r"[1-5]000000", key_bin) and key_bin in by_bin.groups:
            rows = by_bin.get_group(key_bin)
        elif key_lot in by_lot.groups:
            rows = by_lot.get_group(key_lot)
        else:
            continue
        rings = [
            (str(b), ring)
            for b, g in zip(rows.bin, rows.geometry)
            for ring in rings_of(g)
        ]
        here = grid(r.longitude, r.latitude)
        ring_bin, ring = min(
            rings, key=lambda q: float(np.hypot(*(q[1].mean(0) - here)))
        )
        if 0.5 * np.sum(ring[:-1, 0] * ring[1:, 1] - ring[1:, 0] * ring[:-1, 1]) < 0:
            ring = ring[::-1]
        own = (owner == ring_bin) & (not re.fullmatch(r"[1-5]000000", ring_bin))
        centre = ring.mean(0)
        radius = float(np.hypot(*(ring - centre).T).max()) + OPEN_REACH_M + 10.0
        reach = np.minimum(np.hypot(*(e0 - centre).T), np.hypot(*(e1 - centre).T))
        near = (reach - np.hypot(*(e1 - e0).T) < radius) & ~own
        dist = clear_distances(ring, (e0[near], e1[near]))
        out[building] = {d: openness(v) for d, v in dist.items()}
    return pd.DataFrame.from_dict(out, orient="index")


def rear_open(frame: pd.DataFrame) -> np.ndarray:
    """Per row: how far its apartment's rear windows see across the block
    (metres; NaN with no rear window known). From its own window directions,
    pooled over its listings as `features.unit_sides` pools them; otherwise,
    when its own listings or its line's earlier listings
    (`features.line_orientation`) put it at the rear, its building's most open
    rear side."""
    b = frame.building.to_numpy()
    sides = features.building_sides().reindex(b)
    rear = block_openness().reindex(b).where(sides.eq("none").to_numpy())
    windows = pd.DataFrame(
        {d: frame[f"window_{d}"].eq("yes").to_numpy() for d in features.GRID_DIRECTIONS}
    )
    windows = windows.groupby(frame.unit_id.to_numpy()).transform("any")
    windows = windows[rear.columns].to_numpy()
    own = rear.where(windows).max(axis=1).to_numpy()
    has_windows = windows.any(axis=1) & sides.notna().all(axis=1).to_numpy()
    at_rear = features.unit_sides(frame)["none"].to_numpy() | np.isin(
        features.line_orientation(frame).to_numpy(), ["rear", "both"]
    )
    building = rear.max(axis=1).to_numpy()
    return np.where(has_windows, own, np.where(at_rear, building, np.nan))


def rear_yard_ft(lots: pd.DataFrame) -> pd.Series:
    """MapPLUTO lot depth less building depth, on inside lots (type 5) with a
    building no deeper than the lot; NaN elsewhere (corner and through lots
    have no rear yard)."""
    depth = pd.to_numeric(lots.lotdepth, errors="coerce")
    bldg = pd.to_numeric(lots.bldgdepth, errors="coerce")
    ok = lots.lottype.astype(str).eq("5") & (bldg > 0) & (depth >= bldg)
    return (depth - bldg).where(ok)


def label(stated: bool, open_m: float) -> str:
    if stated:
        return "stated"
    if np.isnan(open_m):
        return ""
    return "open rear" if open_m >= SHUT_OPEN_M else "walled rear"


def compute(frame: pd.DataFrame) -> pd.DataFrame:
    sides = features.building_sides()
    opens = block_openness()
    # Only rear sides (no street within reach) look over the block.
    rear = opens.where(sides.reindex(opens.index).eq("none"))
    labels = exposure.compute(frame).set_index("unit_id")
    text = descriptions.attach(frame).fillna("").str.lower()
    phrase = text.str.extract(f"({GARDEN_TEXT})", flags=re.IGNORECASE)[0]
    lots = features.building_lots(frame)
    rows = pd.DataFrame(
        {
            "unit_id": frame.unit_id.to_numpy(),
            "flag": frame.view_garden.eq("yes").to_numpy(),
            "phrase": phrase.to_numpy(),
            "floor": pd.to_numeric(frame.listed_floor, errors="coerce").to_numpy(),
            "yard_ft": rear_yard_ft(lots).to_numpy(),
            **{
                d: frame[f"window_{d}"].eq("yes").to_numpy()
                for d in features.GRID_DIRECTIONS
            },
        }
    )
    units = rows.groupby("unit_id").agg(
        flag=("flag", "any"),
        phrase=("phrase", "first"),
        floor=("floor", "median"),
        yard_ft=("yard_ft", "median"),
        **{d: (d, "any") for d in features.GRID_DIRECTIONS},
    )
    units = units.join(labels[["building", "url", "exposure", "source"]])
    out = []
    for u in units.itertuples():
        by_dir = rear.loc[u.building] if u.building in rear.index else None
        windows = [d for d in features.GRID_DIRECTIONS if getattr(u, d)]
        open_m, how = np.nan, ""
        if by_dir is not None and windows:
            seen = by_dir[windows].dropna()
            if len(seen):
                open_m, how = float(seen.max()), "windows " + "/".join(seen.index)
        elif by_dir is not None and u.exposure in ("rear", "both"):
            if by_dir.notna().any():
                open_m = float(by_dir.max())
                how = f"exposure {u.exposure} ({u.source})"
        stated = bool(u.flag) or isinstance(u.phrase, str)
        why = []
        if u.flag:
            why.append("listing ticks garden view")
        if isinstance(u.phrase, str):
            why.append(f'ad says "{u.phrase}"')
        if how:
            why.append(f"{how}: rear sees {open_m:.0f} m of open block")
        if not np.isnan(u.yard_ft):
            why.append(f"lot rear yard {u.yard_ft:.0f} ft")
        out.append(
            {
                "unit_id": u.Index,
                "building": u.building,
                "url": u.url,
                "garden_view": label(stated, open_m),
                "open_m": round(open_m, 1) if not np.isnan(open_m) else np.nan,
                "measured_by": how,
                "stated": stated,
                "exposure": u.exposure,
                "floor": u.floor,
                "yard_ft": u.yard_ft,
                "evidence": "; ".join(why),
            }
        )
    return pd.DataFrame(out)


def build(frame: pd.DataFrame) -> pd.DataFrame:
    """`compute` with FEATURE_SET's lot, area and description files."""
    lots = features.lot_files(FEATURE_SET)
    area = features.area_files(FEATURE_SET)
    tokens = (
        (features._LOTS, features._LOTS.set((lots["registry"], lots["pluto"]))),
        (features._AREA, features._AREA.set((area["basemap"], area["footprints"]))),
        (
            descriptions.SOURCES,
            descriptions.SOURCES.set(
                tuple(Path(p) for p in features.description_files(FEATURE_SET).values())
            ),
        ),
    )
    try:
        return compute(frame)
    finally:
        for var, token in tokens:
            var.reset(token)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--rules", nargs="*", default=["unit-labels-v5"])
    parser.add_argument("--out", type=Path, default=WISHES)
    args = parser.parse_args(argv)
    frame = data.load()
    frame, _ = data.apply_rules(frame, np.zeros(len(frame), dtype=bool), args.rules)
    table = build(frame)
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.out / f"garden-{dt.datetime.now(dt.UTC):%Y%m%d}"
    table.to_parquet(f"{base}.parquet")
    table.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({len(table)} apartments)")
    print(table.garden_view.value_counts().to_string())


if __name__ == "__main__":
    main()
