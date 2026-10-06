"""Quiet streets: one row per apartment for the site, and the street terms
`features.quiet_v1` (nb3-quiet-v1) adds to the rent model.

Every building is placed on its address street's LION centerline (`centerline_name`;
the Village's named streets too, which `features.frontage_street` leaves out), and
measured three ways from today's basemap:

- on a busy road: an avenue (`features.street_kind`) or a roadway at least
  `BUSY_WIDTH_FT` wide (Hudson St, Seventh Ave South, Varick, 23rd St);
- the roadway width of its address street, where narrow is at most `NARROW_FT`;
- how far it stands from the nearest busy road (mid-block at `MID_BLOCK_M`).

The address street is found for 98% of buildings. Ads call the street or block
quiet or tree-lined (`QUIET_TEXT`) in 11% of a typical building's ads off busy
roads, against 2% on them (2026-10-06, 2,941 buildings, unit-labels-v5). Off busy
roads the share is 6.6% within 30 m of one and 11-12% past 30 m, and 5% on 35-45 ft
roadways against 10-13% at 35 ft or less. The ad text is weak evidence, so
PSIS-LOO judges the terms. Labels: "stated" (an ad says
so), "busy road", "quiet street" (narrow and mid-block), "side street" (off busy
roads otherwise), "" where the address street isn't found.

    python -m rentfrontier.quiet      # writes WISHES/quiet-street-<date>.parquet and .csv
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

from . import data, descriptions, features

WISHES = Path("/data1/apartments/wishes")
FEATURE_SET = "nb3-lineface-v1"
BUSY_WIDTH_FT = 50.0
NARROW_FT = 30.0
MID_BLOCK_M = 60.0
QUIET_TEXT = (
    r"\bquiet(?:,? (?:and )?(?:tree[- ]lined|residential|charming|leafy))?"
    r" (?:side )?(?:street|block)\b(?![- ]facing)"
    r"|\b(?:street|block) is (?:very |so )?quiet\b"
    r"|\btree[- ]lined (?:side )?(?:street|block)\b"
)
_SUFFIX = {
    "STREET": "ST",
    "PLACE": "PL",
    "AVENUE": "AVE",
    "ROAD": "RD",
    "SQUARE": "SQ",
    "LANE": "LN",
    "COURT": "CT",
    "TERRACE": "TER",
    "SOUTH": "S",
}
_ALIASES = {
    "B'WAY": "BROADWAY",
    "6 AVE": "AVE OF THE AMERICAS",
    "AVENUE OF THE AMERICAS": "AVE OF THE AMERICAS",
    "AVENUE OF AMERICAS": "AVE OF THE AMERICAS",
    "AMERICAS AVE": "AVE OF THE AMERICAS",
    "W ST": "WEST ST",
}


def centerline_name(label: str) -> list[str]:
    """LION centerline names an address label's street may go by, most likely
    first ("10 PERRY STREET" -> ["PERRY ST"], "WEST 4 STREET" -> ["W  4 ST"],
    "WEST HOUSTON STREET" -> ["W  HOUSTON ST", "HOUSTON ST"])."""
    address = str(label).upper().split(",")[0]
    m = re.match(r"^\d+[A-Z]?(?:-\d+[A-Z]?)?\s+(.+)$", address)
    if not m:
        return []
    words = [str(features.ORDINAL_AVENUES.get(w, w)) for w in m.group(1).split()]
    words = [_SUFFIX.get(w, w) if i else w for i, w in enumerate(words)]
    name = " ".join(words)
    if name in _ALIASES:
        return [_ALIASES[name]]
    for long, short in (("WEST", "W"), ("EAST", "E")):
        if words[0] == long and len(words) > 2:
            rest = " ".join(words[1:])
            return [f"{short}  {rest}", rest]
    return [name]


def _grid():
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

    return grid


def _distance(p, a, b) -> np.ndarray:
    """Distance from point p to each segment a[i]-b[i]."""
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    return np.hypot(*(p - (a + t[:, None] * ab)).T)


def street_segments(basemap_file: str) -> pd.DataFrame:
    """Street centerline segments (grid metres) with name, roadway width (ft)
    and whether the road is busy."""
    grid = _grid()
    streets = pd.read_parquet(basemap_file).query("layer == 'street'")
    rows = []
    for r in streets.itertuples():
        attrs = json.loads(r.attributes)
        geometry = json.loads(r.geometry)
        lines = geometry["coordinates"]
        lines = lines if geometry["type"] == "MultiLineString" else [lines]
        width = pd.to_numeric(attrs.get("streetwidth"), errors="coerce")
        kind = features.street_kind(r.name, attrs.get("rw_type"))
        for line in lines:
            p = grid([q[0] for q in line], [q[1] for q in line])
            for a, b in itertools.pairwise(p):
                rows.append((r.name, width, kind, *a, *b))
    out = pd.DataFrame(rows, columns=["name", "width", "kind", "x0", "y0", "x1", "y1"])
    out["busy"] = out.kind.eq("avenue") | (out.width >= BUSY_WIDTH_FT)
    return out


def building_streets() -> pd.DataFrame:
    """Per registry building: its address street, that street's roadway width
    (ft) and busyness where the building stands, and the distance (m) to the
    nearest busy road."""
    return _building_streets(features.lot_registry(), features.area_snapshot()[0])


@functools.lru_cache(maxsize=2)
def _building_streets(registry_file: str, basemap_file: str) -> pd.DataFrame:
    registry = pd.read_parquet(registry_file).set_index("building")
    segments = street_segments(basemap_file)
    ends = {
        name: (g[["x0", "y0"]].to_numpy(), g[["x1", "y1"]].to_numpy(), g)
        for name, g in segments.groupby("name")
    }
    busy = segments[segments.busy]
    b0, b1 = busy[["x0", "y0"]].to_numpy(), busy[["x1", "y1"]].to_numpy()
    grid = _grid()
    out = []
    for building, r in registry.iterrows():
        if pd.isna(r.latitude):
            out.append((building, None, np.nan, None, np.nan))
            continue
        p = grid(r.longitude, r.latitude)
        to_busy = float(_distance(p, b0, b1).min()) if len(busy) else np.nan
        name = next((n for n in centerline_name(r.label) if n in ends), None)
        if name is None:
            out.append((building, None, np.nan, None, to_busy))
            continue
        a, b, g = ends[name]
        i = int(_distance(p, a, b).argmin())
        out.append((building, name, g.width.iloc[i], bool(g.busy.iloc[i]), to_busy))
    return pd.DataFrame(
        out, columns=["building", "street", "width_ft", "on_busy", "to_busy_m"]
    ).set_index("building")


def street_terms(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Per row: on a busy road; off one, on a narrow street; off one, mid-block."""
    s = building_streets().reindex(frame.building.to_numpy())
    on_busy = s.on_busy.eq(True).to_numpy()
    off = s.on_busy.eq(False).to_numpy()
    return {
        "busy": on_busy,
        "narrow": off & (s.width_ft.to_numpy() <= NARROW_FT),
        "mid_block": off & (s.to_busy_m.to_numpy() >= MID_BLOCK_M),
    }


def label(stated: bool, on_busy, narrow: bool, mid_block: bool) -> str:
    if stated:
        return "stated"
    if on_busy is None or pd.isna(on_busy):
        return ""
    if on_busy:
        return "busy road"
    return "quiet street" if narrow and mid_block else "side street"


def compute(frame: pd.DataFrame) -> pd.DataFrame:
    text = descriptions.attach(frame).fillna("").str.lower()
    rows = pd.DataFrame(
        {
            "unit_id": frame.unit_id.to_numpy(),
            "building": frame.building.to_numpy(),
            "url": frame.canonical_unit_url.to_numpy(),
            "phrase": text.str.extract(f"({QUIET_TEXT})")[0].to_numpy(),
        }
    )
    units = rows.groupby("unit_id").agg(
        building=("building", "first"), url=("url", "first"), phrase=("phrase", "first")
    )
    s = building_streets().reindex(units.building.to_numpy())
    out = []
    for u, st in zip(units.itertuples(), s.itertuples(), strict=True):
        stated = isinstance(u.phrase, str)
        on_busy = st.on_busy
        narrow = bool(st.width_ft <= NARROW_FT)
        mid = bool(st.to_busy_m >= MID_BLOCK_M)
        why = []
        if stated:
            why.append(f'ad says "{u.phrase}"')
        if isinstance(st.street, str):
            why.append(f"{st.street}, roadway {st.width_ft:.0f} ft")
        if not np.isnan(st.to_busy_m):
            why.append(f"{st.to_busy_m:.0f} m from a busy road")
        out.append(
            {
                "unit_id": u.Index,
                "building": u.building,
                "url": u.url,
                "quiet_street": label(stated, on_busy, narrow, mid),
                "street": st.street,
                "width_ft": st.width_ft,
                "on_busy_road": on_busy,
                "to_busy_m": round(st.to_busy_m, 1),
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
    base = args.out / f"quiet-street-{dt.datetime.now(dt.UTC):%Y%m%d}"
    table.to_parquet(f"{base}.parquet")
    table.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({len(table)} apartments)")
    print(table.quiet_street.value_counts().to_string())
    print("street found:", round(table.street.notna().mean(), 3))


if __name__ == "__main__":
    main()
