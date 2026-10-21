"""Building frontage: the width of the widest street each building faces, and whether it
stands on a corner lot.

Width. For each registry building with a real BIN I take its footprint outline from the NYC
building footprints and lay points along it every 3 m. I lay points every 5 m along the street
centerlines of the basemap (city streets, highways and service roads: LION `rw_type` 1, 2 and
12), each carrying its roadway's curb-to-curb width (`streetwidth`, in feet), name and
direction. A building faces a street when a centerline point lies within half its roadway's
width plus REACH_M (20 m) of the outline. REACH_M only finds the street: it covers the
sidewalk, a front yard or a plaza, and I never add it to a width.

A divided boulevard such as Park Ave, Eastern Pkwy or Queens Blvd comes in the centerlines as
several parallel roadways with the same name, each with its own width. For each street a
building faces I start from the matched point nearest the outline. I collect the points of the
same name lying within ALONG_M (30 m) along that point's direction and PARALLEL_M (60 m)
across it, on roadways running within about 25 degrees of it. I group them by their offset
across the street, starting a new roadway at each gap of GAP_M (4 m) or more, and add up the
median width of each roadway. The building's `front_width_ft` is the largest such sum over the
streets it faces. A roadway with no width counts as unknown, and the width stays NaN when the
building has no outline or faces no street with a width.

Corner. `corner` comes from the MapPLUTO lot type of the building's BBL: 3 (corner) is a
corner, and every other known type (1, 2 and 4 to 9) is not. For lot type 0 or a BBL MapPLUTO
lacks, I fall back to the street geometry: the building is on a corner when it faces two
differently named streets crossing at more than 45 degrees. `corner_source` records which
rule decided, and `corner` stays NaN when neither does.

    python -m rentfrontier.frontage snapshot
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .registry import EXTERNAL_ROOT

REGISTRY = EXTERNAL_ROOT / "registry" / "20261019-bcfbb52-extend" / "registry.parquet"
FOOTPRINTS = (
    EXTERNAL_ROOT / "footprints" / "20261016-5f07157-all" / "footprints.parquet"
)
BASEMAP = EXTERNAL_ROOT / "basemap" / "20261016-5f07157-all" / "basemap.parquet"
PLUTO = EXTERNAL_ROOT / "pluto" / "20261017-2c61ff1-all-lots4" / "pluto.parquet"
ROAD_TYPES = ("1", "2", "12")  # LION rw_type: street, highway, service road
REACH_M = 20.0
ALONG_M = 30.0
PARALLEL_M = 60.0
GAP_M = 4.0
PARALLEL_COS = 0.9
CORNER_COS = 0.7
STREET_STEP_M = 5.0
OUTLINE_STEP_M = 3.0
FT = 0.3048
LAT0, LON0 = 40.7, -73.95
M_PER_LAT = 111_320.0
M_PER_LON = M_PER_LAT * np.cos(np.radians(LAT0))


def metres(lon, lat) -> np.ndarray:
    """Lon/lat to metres east and north of LAT0, LON0."""
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return np.stack([(lon - LON0) * M_PER_LON, (lat - LAT0) * M_PER_LAT], -1)


def densify(line: np.ndarray, step: float):
    """Points every `step` metres or less along a polyline in metres, at the middle of each
    piece, with each piece's unit direction."""
    pts, dirs = [], []
    for a, b in zip(line[:-1], line[1:]):
        d = b - a
        n = float(np.hypot(*d))
        if n == 0:
            continue
        k = max(1, int(np.ceil(n / step)))
        t = (np.arange(k) + 0.5) / k
        pts.append(a + t[:, None] * d)
        dirs.append(np.repeat((d / n)[None], k, 0))
    if not pts:
        return np.zeros((0, 2)), np.zeros((0, 2))
    return np.vstack(pts), np.vstack(dirs)


def street_points(basemap: pd.DataFrame) -> pd.DataFrame:
    """The basemap's roadways as points every STREET_STEP_M: x, y, ux, uy (direction), width
    in feet (NaN unknown), name and the roadway's row."""
    s = basemap[basemap.layer == "street"].reset_index(drop=True)
    out = []
    for i, (attrs, geometry) in enumerate(zip(s.attributes, s.geometry)):
        a = json.loads(attrs)
        if str(a.get("rw_type", "")).strip() not in ROAD_TYPES:
            continue
        w = pd.to_numeric(a.get("streetwidth"), errors="coerce")
        w = float(w) if w is not None and w > 0 else np.nan
        g = json.loads(geometry)
        lines = (
            g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        )
        for line in lines:
            line = np.asarray(line, float)
            p, u = densify(metres(line[:, 0], line[:, 1]), STREET_STEP_M)
            if len(p):
                out.append(
                    pd.DataFrame(
                        {"x": p[:, 0], "y": p[:, 1], "ux": u[:, 0], "uy": u[:, 1]}
                    ).assign(width=w, name=str(a.get("stname_label", "")), road=i)
                )
    return pd.concat(out, ignore_index=True)


def outline(geometry: str) -> np.ndarray:
    """Points every OUTLINE_STEP_M along the outer rings of a footprint's polygons."""
    g = json.loads(geometry)
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    pts = []
    for poly in polys:
        ring = np.asarray(poly[0], float)
        p, _ = densify(metres(ring[:, 0], ring[:, 1]), OUTLINE_STEP_M)
        pts.append(p)
    return np.vstack(pts)


def arrays(streets: pd.DataFrame) -> dict:
    """The street points as arrays, with a KD-tree on their positions."""
    xy = streets[["x", "y"]].to_numpy()
    return {
        "xy": xy,
        "u": streets[["ux", "uy"]].to_numpy(),
        "name": streets.name.to_numpy(),
        "width": streets.width.to_numpy(float),
        "tree": cKDTree(xy),
        "reach": np.nanmax(streets.width.to_numpy(float), initial=0) * FT / 2 + REACH_M,
    }


def roadway_width(s: dict, j: int) -> float:
    """The summed width in feet of the roadways named like point j that run beside it: one
    median width per group of parallel points, grouped by their offset across the street."""
    xy, u = s["xy"], s["u"]
    near = np.array(s["tree"].query_ball_point(xy[j], np.hypot(ALONG_M, PARALLEL_M)))
    near = near[s["name"][near] == s["name"][j]]
    near = near[np.abs(u[near] @ u[j]) >= PARALLEL_COS]
    d = xy[near] - xy[j]
    along = d @ u[j]
    across = d[:, 0] * u[j, 1] - d[:, 1] * u[j, 0]
    keep = (np.abs(along) <= ALONG_M) & (np.abs(across) <= PARALLEL_M)
    near, across = near[keep], across[keep]
    order = np.argsort(across)
    near, across = near[order], across[order]
    starts = np.r_[0, np.flatnonzero(np.diff(across) >= GAP_M) + 1, len(near)]
    w = s["width"][near]
    total = 0.0
    for a, b in zip(starts[:-1], starts[1:]):
        m = np.median(w[a:b])
        if not np.isfinite(m):
            return np.nan
        total += float(m)
    return total


def faced(s: dict, pts: np.ndarray) -> dict:
    """The streets an outline faces, as {name: index of the matched point nearest it}."""
    cand = sorted({j for js in s["tree"].query_ball_point(pts, s["reach"]) for j in js})
    if not cand:
        return {}
    cand = np.array(cand)
    dist = cKDTree(pts).query(s["xy"][cand])[0]
    ok = dist <= np.nan_to_num(s["width"][cand]) * FT / 2 + REACH_M
    out = {}
    for j in cand[ok][np.argsort(dist[ok], kind="stable")]:
        out.setdefault(s["name"][j], int(j))
    return out


def frontage(
    registry: pd.DataFrame,
    footprints: pd.DataFrame,
    streets: pd.DataFrame,
    pluto: pd.DataFrame,
) -> pd.DataFrame:
    """One row per registry building: front_width_ft, front_street, corner, corner_source."""
    reg = registry.drop_duplicates("building").set_index("building")
    bins = reg.bin.astype("string").str.replace(r"\.0$", "", regex=True)
    placeholder = bins.str.fullmatch(r"[1-5]000000").fillna(True).astype(bool)
    fp = footprints.assign(
        bin=footprints.bin.astype("string").str.replace(r"\.0$", "", regex=True)
    )
    fp = fp[fp.geometry.notna()].drop_duplicates("bin").set_index("bin").geometry
    s = arrays(streets)
    u = s["u"]
    width, street, geo_corner = {}, {}, {}
    for b, bin_, ph in zip(reg.index, bins, placeholder):
        if ph or bin_ not in fp.index:
            continue
        hits = faced(s, outline(fp.at[bin_]))
        sums = {n: roadway_width(s, j) for n, j in hits.items()}
        sums = {n: v for n, v in sums.items() if np.isfinite(v)}
        if sums:
            street[b] = max(sums, key=sums.get)
            width[b] = sums[street[b]]
        js = list(hits.values())
        geo_corner[b] = any(
            abs(u[a] @ u[c]) < CORNER_COS for k, a in enumerate(js) for c in js[k + 1 :]
        )
    lots = pluto.assign(
        bbl=pluto.bbl.astype("string").str.replace(r"\.0$", "", regex=True)
    ).drop_duplicates("bbl")
    lot_type = pd.to_numeric(lots.set_index("bbl").lottype, errors="coerce")
    lt = (
        reg.bbl.astype("string")
        .str.replace(r"\.0$", "", regex=True)
        .map(lot_type)
        .to_numpy(float)
    )
    geo = reg.index.map(geo_corner).to_numpy(object)
    from_pluto = np.isfinite(lt) & (lt != 0)
    from_geo = ~from_pluto & pd.notna(geo)
    corner = np.full(len(reg), np.nan)
    corner[from_pluto] = lt[from_pluto] == 3
    corner[from_geo] = geo[from_geo].astype(bool)
    return pd.DataFrame(
        {
            "building": reg.index,
            "front_width_ft": reg.index.map(width).to_numpy(float),
            "front_street": reg.index.map(street),
            "corner": corner,
            "corner_source": np.where(
                from_pluto, "pluto", np.where(from_geo, "geometry", "unknown")
            ),
        }
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot() -> Path:
    """Build the frontage table from the pinned inputs and write it, with its provenance, to
    EXTERNAL_ROOT/frontage/<date>-<commit>/."""
    commit = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    ).stdout.strip()
    out_dir = EXTERNAL_ROOT / "frontage" / f"{dt.date.today():%Y%m%d}-{commit}"
    out_dir.mkdir(parents=True, exist_ok=False)
    registry = pd.read_parquet(REGISTRY, columns=["building", "bbl", "bin"])
    footprints = pd.read_parquet(FOOTPRINTS, columns=["bin", "geometry"])
    streets = street_points(pd.read_parquet(BASEMAP))
    pluto = pd.read_parquet(PLUTO, columns=["bbl", "lottype"])
    table = frontage(registry, footprints, streets, pluto)
    table.to_parquet(out_dir / "frontage.parquet", index=False)
    inputs = {str(p): _sha(p) for p in (REGISTRY, FOOTPRINTS, BASEMAP, PLUTO)}
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "commit": commit,
                "inputs": inputs,
                "rows": len(table),
                "width_known": int(table.front_width_ft.notna().sum()),
                "corner_source": table.corner_source.value_counts().to_dict(),
            },
            indent=2,
        )
    )
    return out_dir


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="rentfrontier.frontage")
    parser.add_argument("command", choices=["snapshot"])
    parser.parse_args(argv)
    print(snapshot())


if __name__ == "__main__":
    main(sys.argv[1:])
