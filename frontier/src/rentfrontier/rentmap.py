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
is the posterior median with a 90% interval. Years before a building's first
listing in the fit are extrapolated by its walk and marked in `first_year`.

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
DEFINITION = (
    "A typical apartment with that many bedrooms: bathrooms, size, views and "
    "ad-text features at Chelsea's average for its bedroom count; floor and "
    "building amenities at the building's own average; plus the building's own "
    "level, path over time and bedroom premium, and the market that year. "
    "Posterior median of the typical asking rent, with a 90% interval."
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


def building_table(prep: model.Prepared, years) -> list[dict]:
    registry = pd.read_parquet(features.REGISTRY_FILE).set_index("building")
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


def grid_layout(buildings: list[dict]) -> dict:
    """Adds each building's grid coordinates (x across the avenues, y up the
    streets, metres from the buildings' centre) and returns guide positions
    for a few streets and the avenues, from the buildings' own addresses
    (median over the buildings on each, at least two)."""
    known = [b for b in buildings if b["lat"] is not None]
    lat0 = sum(b["lat"] for b in known) / len(known)
    lon0 = sum(b["lon"] for b in known) / len(known)
    phi, metres = math.radians(GRID_BEARING_DEG), 111_320.0
    streets, avenues = {}, {}
    for b in buildings:
        if b["lat"] is None:
            b["x"] = b["y"] = None
            continue
        east = (b["lon"] - lon0) * metres * math.cos(math.radians(lat0))
        north = (b["lat"] - lat0) * metres
        b["x"] = round(east * math.cos(phi) - north * math.sin(phi), 1)
        b["y"] = round(east * math.sin(phi) + north * math.cos(phi), 1)
        address = b["label"].upper()
        if m := SIDE_STREET.match(address):
            streets.setdefault(int(m.group(1)), []).append(b["y"])
        elif "AVENUE OF THE AMERICAS" in address:
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


def compute(name: str) -> dict:
    _, result, kept = explain.load_run(name)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load(Path(result["dataset"]))
    heldout = splits.SPLITS[result["split"]](frame)
    frame = data.apply_rules(frame, result.get("data_rules", ()))
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    if not (config.building_walk or config.building_trend):
        raise SystemExit("the rent map needs a building walk or trend design")
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
    out_rent, chelsea = {}, {}
    for key, (x, beds) in typical_rows(prep).items():
        log = (
            market[:, None, :]
            + path
            + (level + np.einsum("bf,df->db", x, kept["beta"]) + slope * beds)[
                ..., None
            ]
        )  # (d, B, Y)
        q = np.quantile(np.exp(log), PROBABILITIES, axis=0)  # (3, B, Y)
        out_rent[key] = np.rint(np.moveaxis(q, 0, -1)).astype(int).tolist()
        c = np.quantile(np.exp(log).mean(1), PROBABILITIES, axis=0)  # (3, Y)
        chelsea[key] = np.rint(c.T).astype(int).tolist()
    months = (by_year > 0).sum(1)
    buildings = building_table(prep, years)
    grid = grid_layout(buildings)
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
        "rent": out_rent,
        "chelsea_average": chelsea,
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
