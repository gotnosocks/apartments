"""What a typical apartment rents for in each building, each year: the data of
the rent map (research dashboard).

    uv run python -m rentfrontier.rentmap <run-name>

Reads a recorded run's kept joint draws and the dataset it was fit on; never
fits. For every building, calendar year and bedroom group (studio, 1, 2, 3+),
the posterior of the typical asking rent of an apartment with:

- the apartment's own attributes (bedrooms, bathrooms, size, laundry, heating
  and cooling, views, windows, unit label, ad-text flags) at Chelsea's average
  over the fit's listings with that many bedrooms;
- the building's attributes (floor, elevator, doorman, pets and the building
  facts of the feature set) at the building's own average over its listings;
- the building's level, its path over time and its own bedroom premium;
- the market that year (trend averaged over the year's months, no season);
- a first advertised price (price basis at its reference).

Rents are exp of the log-scale mean, i.e. the typical (median) ask. Each value
is the posterior median with a 90% interval. Years outside a building's
listings in the fit (before `first_year`, after `last_year`) are the walk's
extrapolation. Designs whose terms this does not model (bedroom-group market
curves, per-building feature slopes, market drift, a trend on top of a walk,
sum-to-zero, masked or anchored walks) are refused.
`chelsea_median` is the median building's value per draw (all buildings),
again as a posterior median and 90% interval.

The map under the buildings comes from the basemap snapshot
(`rentfrontier.external basemap`): streets at their recorded width, paths,
parks and the shoreline, in the same grid coordinates as the buildings.

Writes /data1/apartments/frontier/maps/<run>-<commit>/map.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, explain, features, model, splits
from .run import git

MAPS = data.OUTPUT_ROOT / "maps"
VERSION = "rent-map-v1"
BEDROOMS = (
    ("studio", "Studio", (0,)),
    ("1", "1 bedroom", (1,)),
    ("2", "2 bedrooms", (2,)),
    ("3+", "3+ bedrooms", (3, 4)),
)
# Feature groups taken at the building's own average; every other group is an
# attribute of the apartment, taken at Chelsea's average for its bedroom count.
BUILDING_GROUPS = frozenset(
    {
        "floor",
        "elevator",
        "doorman",
        "pets",
        "building era",
        "building size",
        "building class",
        "building status",
        "location",
        "transit",
    }
)
PROBABILITIES = (0.05, 0.5, 0.95)
# Manhattan's street grid runs about 29 degrees east of true north; the map is
# drawn in grid coordinates (avenues vertical, streets horizontal).
GRID_BEARING_DEG = 29.0
GUIDE_STREETS = (14, 18, 23, 28, 34)
SIDE_STREET = re.compile(r"^\d+\s+WEST\s+(\d+)\s+STREET")
AVENUE = re.compile(r"^\d+\s+(\d+)\s+AVENUE")
AMERICAS = re.compile(r"AVENUE OF (THE )?AMERICAS|AMERICAS AVENUE")
# The map under the dots (`rentfrontier.external basemap`), clipped to the
# buildings' extent plus BASEMAP_PAD_M; street widths in feet, as recorded.
BASEMAP_FILE = features.BASEMAP_FILE
BASEMAP_PAD_M = 120.0
# Centerline roadway types drawn: street, highway, bridge, ramp; paths apart.
ROADS, PATHS = {"1", "2", "3", "9"}, {"6"}
DEFINITION = (
    "A typical apartment with that many bedrooms: bathrooms, size, laundry, views "
    "and ad-text features at Chelsea's average for its bedroom count; floor, "
    "elevator, doorman, pet policy and building facts at the building's own "
    "average; plus the building's own level, path over time and bedroom premium "
    "(and, in designs with them, its own size and bathroom slopes), and the market "
    "that year. Posterior median of the typical asking rent, with a "
    "90% interval."
)


def year_weights(periods: pd.DatetimeIndex, spacing: int):
    """(years, months) averaging weights of each calendar year's months, and
    (knots, years) weights that average each building's linearly interpolated
    walk over the year's months."""
    years = np.unique(periods.year)
    months = np.arange(len(periods))
    by_year = np.zeros((len(years), len(periods)))
    for i, y in enumerate(years):
        m = months[periods.year == y]
        by_year[i, m] = 1.0 / len(m)
    knot, frac = months // spacing, (months % spacing) / spacing
    n_knots = int(knot.max()) + 2
    interp = np.zeros((n_knots, len(periods)))
    interp[knot, months] += 1 - frac
    interp[knot + 1, months] += frac
    return years, by_year, interp @ by_year.T


def typical_rows(prep: model.Prepared) -> dict:
    """Per bedroom group: the apartment part of x (Chelsea's average over the
    fit's rows with that many bedrooms) and each building's own part, (buildings,
    features); plus the group's average centred bedroom count."""
    tr = prep.train
    groups = np.asarray(prep.features.groups)
    names = prep.features.names
    building_cols = np.isin(groups, list(BUILDING_GROUPS))
    price = np.array([n == "current_capture_ask" for n in names])
    n_b = len(prep.buildings)
    counts = np.bincount(tr.building, minlength=n_b)
    own = np.zeros((n_b, len(names)))
    np.add.at(own, tr.building, tr.x)
    own /= np.maximum(counts, 1)[:, None]
    beds = tr.beds_centered + 1
    out = {}
    for key, _, values in BEDROOMS:
        rows = np.isin(beds, values)
        apartment = tr.x[rows].mean(0)
        x = np.where(building_cols[None], own, apartment[None])
        x[:, price] = 0.0
        out[key] = (x, float(tr.beds_centered[rows].mean()))
    return out


def building_table(prep: model.Prepared, years, registry_file=None) -> list[dict]:
    registry = pd.read_parquet(registry_file or features.REGISTRY_FILE).set_index(
        "building"
    )
    tr = prep.train
    first = pd.Series(prep.periods[tr.month].year).groupby(tr.building).min()
    last = pd.Series(prep.periods[tr.month].year).groupby(tr.building).max()
    rows = np.bincount(tr.building, minlength=len(prep.buildings))
    out = []
    for i, b in enumerate(prep.buildings):
        r = registry.loc[b] if b in registry.index else None
        label = str(r.label).split(", New York")[0].title() if r is not None else b
        out.append(
            {
                "id": b,
                "label": label,
                "lat": None if r is None else round(float(r.latitude), 6),
                "lon": None if r is None else round(float(r.longitude), 6),
                "fit_listings": int(rows[i]),
                "first_year": int(first.get(i, years[-1])),
                "last_year": int(last.get(i, years[0])),
            }
        )
    return out


def grid_projection(buildings: list[dict]):
    """(lon, lat) -> grid (x across the avenues, y up the streets), metres from
    the buildings' centre, for the Manhattan grid's bearing."""
    known = [b for b in buildings if b["lat"] is not None]
    lat0 = sum(b["lat"] for b in known) / len(known)
    lon0 = sum(b["lon"] for b in known) / len(known)
    phi, metres = math.radians(GRID_BEARING_DEG), 111_320.0
    cos0 = math.cos(math.radians(lat0))

    def to_grid(lon, lat):
        east = (lon - lon0) * metres * cos0
        north = (lat - lat0) * metres
        return (
            east * math.cos(phi) - north * math.sin(phi),
            east * math.sin(phi) + north * math.cos(phi),
        )

    return to_grid


def grid_layout(buildings: list[dict]) -> dict:
    """Adds each building's grid coordinates (`grid_projection`) and returns
    guide positions for a few streets and the avenues, from the buildings' own
    addresses (median over the buildings on each, at least two)."""
    to_grid = grid_projection(buildings)
    streets, avenues = {}, {}
    for b in buildings:
        if b["lat"] is None:
            b["x"] = b["y"] = None
            continue
        x, y = to_grid(b["lon"], b["lat"])
        b["x"], b["y"] = round(x, 1), round(y, 1)
        address = b["label"].upper()
        if m := SIDE_STREET.match(address):
            streets.setdefault(int(m.group(1)), []).append(b["y"])
        elif AMERICAS.search(address):
            avenues.setdefault(6, []).append(b["x"])
        elif m := AVENUE.match(address):
            avenues.setdefault(int(m.group(1)), []).append(b["x"])
    median = lambda v: float(np.median(v))
    return {
        "bearing_deg": GRID_BEARING_DEG,
        "streets": [
            {"label": f"W {n} St", "y": round(median(streets[n]), 1)}
            for n in GUIDE_STREETS
            if len(streets.get(n, ())) >= 2
        ],
        "avenues": [
            {"label": f"{n}th Av", "x": round(median(v), 1)}
            for n, v in sorted(avenues.items())
            if len(v) >= 2
        ],
    }


def _clip_ring(ring, x0, x1, y0, y1):
    """Sutherland-Hodgman clip of a polygon ring to a rectangle."""
    edges = (
        (lambda p: p[0] >= x0, lambda a, b: _at_x(a, b, x0)),
        (lambda p: p[0] <= x1, lambda a, b: _at_x(a, b, x1)),
        (lambda p: p[1] >= y0, lambda a, b: _at_y(a, b, y0)),
        (lambda p: p[1] <= y1, lambda a, b: _at_y(a, b, y1)),
    )
    out = list(ring)
    for inside, cross in edges:
        points, out = out, []
        for i, cur in enumerate(points):
            prev = points[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        if not out:
            break
    return out


def _at_x(a, b, x):
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _at_y(a, b, y):
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def _thin(points, step=1.5):
    """Round to 0.1 m and drop points closer than `step` metres to the last kept."""
    out = []
    for x, y in points:
        if not out or math.hypot(x - out[-1][0], y - out[-1][1]) >= step:
            out.append((round(x, 1), round(y, 1)))
    if len(points) > 1 and out[-1] != (
        round(points[-1][0], 1),
        round(points[-1][1], 1),
    ):
        out.append((round(points[-1][0], 1), round(points[-1][1], 1)))
    return out


def basemap_layers(buildings: list[dict]) -> dict:
    """Streets, paths, parks and land from the basemap snapshot, in the map's
    grid coordinates, clipped to the buildings' extent plus BASEMAP_PAD_M."""
    to_grid = grid_projection(buildings)
    xs = [b["x"] for b in buildings if b["x"] is not None]
    ys = [b["y"] for b in buildings if b["y"] is not None]
    x0, x1 = min(xs) - BASEMAP_PAD_M, max(xs) + BASEMAP_PAD_M
    y0, y1 = min(ys) - BASEMAP_PAD_M, max(ys) + BASEMAP_PAD_M
    inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1
    table = pd.read_parquet(BASEMAP_FILE)
    out = {
        "extent": [x0, x1, y0, y1],
        "land": [],
        "parks": [],
        "streets": [],
        "paths": [],
    }
    for row in table.itertuples():
        geometry = json.loads(row.geometry)
        attrs = json.loads(row.attributes)
        if geometry is None:
            continue
        coords = geometry["coordinates"]
        if row.layer in ("land", "park"):
            polygons = coords if geometry["type"] == "MultiPolygon" else [coords]
            rings = []
            for polygon in polygons:
                for ring in polygon:
                    clipped = _clip_ring([to_grid(*p) for p in ring], x0, x1, y0, y1)
                    if len(clipped) >= 3:
                        rings.append(_thin(clipped))
            if rings:
                key = "land" if row.layer == "land" else "parks"
                out[key].append({"name": row.name, "rings": rings})
            continue
        kind = attrs.get("rw_type")
        if kind not in ROADS | PATHS:
            continue
        lines = coords if geometry["type"] == "MultiLineString" else [coords]
        for line in lines:
            points = [to_grid(*p) for p in line]
            if not any(inside(p) for p in points):
                continue
            width = attrs.get("streetwidth")
            out["paths" if kind in PATHS else "streets"].append(
                {
                    "name": attrs.get("stname_label") or row.name,
                    "width_ft": float(width) if width else None,
                    "points": _thin(points),
                }
            )
    out["extent"] = [round(v, 1) for v in out["extent"]]
    return out


def unsupported_terms(config: model.ModelConfig) -> list[str]:
    """The terms of a design that the rent map does not model (empty: supported)."""
    unsupported = {
        "no building walk or trend": not (
            config.building_walk or config.building_trend
        ),
        "both a walk and a trend": config.building_walk and config.building_trend,
        "bedroom-group market curves": config.bedroom_time,
        "market drift": config.market_drift,
        "sum-to-zero, masked or anchored walks": config.walk_zero_sum
        or bool(config.walk_min_rows_per_knot)
        or config.walk_anchor_data,
    }
    return [k for k, bad in unsupported.items() if bad]


def feature_slope_term(fslope, x, cols) -> np.ndarray:
    """Each building's own slopes times the typical apartment's values of those
    features: fslope (draws, buildings, slopes), x (buildings, features), cols
    the slopes' feature columns; (draws, buildings). As in the model's linear
    predictor, fslope[building] times x at the slopes' columns."""
    return np.einsum("dbj,bj->db", fslope, x[:, cols])


def compute(name: str) -> dict:
    _, result, kept = explain.load_run(name)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load(Path(result["dataset"]))
    heldout = splits.SPLITS[result["split"]](frame)
    frame, heldout = data.apply_rules(frame, heldout, data.recorded_rules(result))
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    missing = unsupported_terms(config)
    if missing:
        raise SystemExit(
            f"the rent map does not model this design: {', '.join(missing)}"
        )
    years, by_year, walk_year = year_weights(prep.periods, model.walk_spacing(config))
    market = prep.offset + kept["alpha"][:, None] + kept["trend"] @ by_year.T  # (d, Y)
    if config.building_walk:
        path = kept["walk"] @ walk_year[: kept["walk"].shape[2]]  # (d, B, Y)
    else:
        centre = kept["building_mean_month"]  # (d, B)
        mid = by_year @ np.arange(len(prep.periods))  # (Y,)
        path = (
            kept["building_trend"][..., None]
            * (mid[None, None] - centre[..., None])
            / 12
        )
    level = kept["building"]  # (d, B)
    slope = kept["bedroom_slope"] if config.bedroom_slope else np.zeros_like(level)
    fcols = [prep.features.names.index(n) for n in config.feature_slopes]
    out_rent, chelsea = {}, {}
    for key, (x, beds) in typical_rows(prep).items():
        log = (
            market[:, None, :]
            + path
            + (
                level
                + np.einsum("bf,df->db", x, kept["beta"])
                + slope * beds
                + (feature_slope_term(kept["fslope"], x, fcols) if fcols else 0.0)
            )[..., None]
        )  # (d, B, Y)
        q = np.quantile(np.exp(log), PROBABILITIES, axis=0)  # (3, B, Y)
        out_rent[key] = np.rint(np.moveaxis(q, 0, -1)).astype(int).tolist()
        # Chelsea's median building, per draw (robust to the dearest buildings).
        c = np.quantile(np.median(np.exp(log), axis=1), PROBABILITIES, axis=0)
        chelsea[key] = np.rint(c.T).astype(int).tolist()  # (Y, 3)
    months = (by_year > 0).sum(1)
    # The registry the run's features read (the first snapshot for older runs).
    recorded = (result.get("feature_sources") or {}).get("registry") or {}
    buildings = building_table(prep, years, recorded.get("path"))
    grid = grid_layout(buildings)
    basemap = basemap_layers(buildings)
    return {
        "version": VERSION,
        "run": name,
        "run_commit": result["commit"],
        "model": result["model"]["name"],
        "feature_set": result["feature_set"],
        "data_rules": list(result.get("data_rules", ())),
        "draws": int(kept["alpha"].shape[0]),
        "definition": DEFINITION,
        "interval": "90%",
        "years": [int(y) for y in years],
        "year_months": [int(m) for m in months],
        "bedrooms": [{"key": k, "label": label} for k, label, _ in BEDROOMS],
        "buildings": buildings,
        "grid": grid,
        "basemap": basemap,
        "basemap_source": {
            "path": BASEMAP_FILE,
            "sha256": data.sha256(Path(BASEMAP_FILE)),
        },
        "rent": out_rent,
        "chelsea_median": chelsea,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    out = compute(args.run)
    out["commit"] = commit
    out["created_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    out_dir = MAPS / f"{args.run}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "map.json"
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
