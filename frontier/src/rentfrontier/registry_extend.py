"""Geocode the buildings a pipeline build references and the registry lacks, and write a new
registry snapshot holding the old rows and the new ones.

    python -m rentfrontier.registry_extend [--base DIR] [--catalog FILE] [--check] [--pause S]

The registry snapshots under EXTERNAL_ROOT/registry give each building slug a lot (BBL, BIN)
and a point. Until 2026-10-19 they came from building lists cut once by hand, so buildings whose
StreetEasy records arrived later had no row, and B0.4 counted their ads as unlocated.
apartments-registry-extend.service runs this module after each pipeline build. It works in
these steps:

1. It reads the newest line of the pipeline's catalog. From it I take the build's rows file, for
   the buildings its ads name, and the export's building files, for each building's StreetEasy
   record: its slug, its `geoCenter` point and the city of its address.
2. It reads the base snapshot, the newest `registry.parquet` under EXTERNAL_ROOT/registry unless
   given, and lists the buildings of the export and of the rows file with no row there. A rows
   file slug missing from the export takes its point from the export record of the same
   `building_id`.
3. With `--check` it prints the count and the first few slugs, then exits 1 if any building is
   missing and 0 if none is.
4. Otherwise it geocodes each missing building with `registry.locate`, giving GeoSearch the
   borough of the record's city (NEW YORK is Manhattan), and writes
   EXTERNAL_ROOT/registry/<date>-<commit>-extend/registry.parquet: the base rows unchanged, then
   the new rows. A building GeoSearch can't place gets a row of method `none`, so the next run
   skips it and the count of such rows stays visible in provenance.json. When nothing is
   missing, it writes nothing.

Model code reads a fixed snapshot path, so a new snapshot changes no fit until a model names it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from .registry import EXTERNAL_ROOT, GEOSEARCH, MAX_DISTANCE_M, locate
from .run import git

CATALOG = Path("/data1/apartments/pipeline/datasets/catalog.ndjson")
COLUMNS = [
    "building",
    "method",
    "query",
    "label",
    "bbl",
    "bin",
    "pad_version",
    "latitude",
    "longitude",
    "distance_m",
]
CITY_BOROUGH = {"NEW YORK": "Manhattan", "MANHATTAN": "Manhattan"}


def borough_of(city: str | None) -> str:
    """The place name GeoSearch gets with the address: the borough for New York's mail city, the
    city itself (Brooklyn, Ridgewood) otherwise."""
    if not city:
        return "New York"
    return CITY_BOROUGH.get(city.upper(), city.title())


def newest_registry(root: Path = EXTERNAL_ROOT / "registry") -> Path:
    paths = sorted(root.glob("*/registry.parquet"), key=lambda p: p.stat().st_mtime)
    if not paths:
        raise SystemExit(f"no registry.parquet under {root}")
    return paths[-1].parent


def latest_build(catalog: Path = CATALOG) -> dict:
    lines = [line for line in catalog.read_text().splitlines() if line.strip()]
    return json.loads(lines[-1])


def export_buildings(build: dict) -> pd.DataFrame:
    """Each building of the build's export at its latest record: building_id, building (slug),
    latitude, longitude, city."""
    root = Path(build["export"])
    parts = [
        pd.read_parquet(root / f, columns=["building_id", "fetched", "record"])
        for f in sorted(build["buildings"]["files"])
    ]
    frame = pd.concat(parts, ignore_index=True).dropna(subset=["record"])
    frame = frame.sort_values("fetched").drop_duplicates("building_id", keep="last")
    records = [json.loads(r) for r in frame.record]
    point = [r.get("geoCenter") or {} for r in records]
    return pd.DataFrame(
        {
            "building_id": frame.building_id.to_numpy(),
            "building": [r.get("slug") for r in records],
            "latitude": [p.get("latitude") for p in point],
            "longitude": [p.get("longitude") for p in point],
            "city": [(r.get("address") or {}).get("city") for r in records],
        }
    )


def wanted(export: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """The export's buildings, then each rows-file slug the export lacks, at the point of the
    export record with its building_id (or none)."""
    named = rows.dropna(subset=["building"]).drop_duplicates("building")
    extra = named[~named.building.isin(export.building)][["building", "building_id"]]
    extra = extra.merge(
        export.drop(columns="building"), on="building_id", how="left"
    ).drop_duplicates("building")
    out = pd.concat([export, extra], ignore_index=True)
    return out.dropna(subset=["building"]).drop_duplicates("building")


def missing(base: pd.DataFrame, buildings: pd.DataFrame) -> pd.DataFrame:
    return buildings[~buildings.building.isin(base.building)]


def geocode(todo: pd.DataFrame, pause: float = 0.1) -> pd.DataFrame:
    out = []
    for b in todo.itertuples():
        if pd.isna(b.latitude) or pd.isna(b.longitude):
            out.append({"building": b.building, "method": "none", "query": None})
            continue
        city = b.city if isinstance(b.city, str) else None
        out.append(
            locate(b.building, float(b.latitude), float(b.longitude), borough_of(city))
        )
        time.sleep(pause)
    return pd.DataFrame(out, columns=COLUMNS)


def extend(base: pd.DataFrame, todo: pd.DataFrame, pause: float = 0.1):
    """The base rows, then a geocoded row for each building of `todo`, with the base's dtypes."""
    added = geocode(todo, pause)
    table = pd.concat([base[COLUMNS], added], ignore_index=True)
    return table.astype(base[COLUMNS].dtypes.to_dict()), added


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", type=Path, help="snapshot dir to extend")
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--check", action="store_true", help="count, don't geocode")
    parser.add_argument("--pause", type=float, default=0.1)
    args = parser.parse_args(argv)
    base_dir = args.base or newest_registry()
    base = pd.read_parquet(base_dir / "registry.parquet")
    build = latest_build(args.catalog)
    rows = pd.read_parquet(
        args.catalog.parent / build["rows"]["path"], columns=["building", "building_id"]
    )
    todo = missing(base, wanted(export_buildings(build), rows))
    print(
        f"{base_dir.name}: {len(todo)} buildings of the {build['built']} build have no row"
        + (f", e.g. {', '.join(todo.building.head(5))}" if len(todo) else "")
    )
    if args.check:
        raise SystemExit(1 if len(todo) else 0)
    if todo.empty:
        return
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    table, added = extend(base, todo, args.pause)
    out_dir = EXTERNAL_ROOT / "registry" / f"{started:%Y%m%d}-{commit[:7]}-extend"
    if out_dir.exists():
        out_dir = out_dir.with_name(f"{out_dir.name}-{started:%H%M%S}")
    out_dir.mkdir(parents=True)
    path = out_dir / "registry.parquet"
    table.to_parquet(path, index=False)
    base_path = base_dir / "registry.parquet"
    provenance = {
        "base": str(base_dir),
        "base_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        "build": {"built": build["built"], "rows": build["rows"]["path"]},
        "source": GEOSEARCH,
        "retrieved_at": started.isoformat(),
        "commit": commit,
        "buildings": len(table),
        "added": len(added),
        "added_methods": added.method.value_counts().to_dict(),
        "added_boroughs": added.bbl.dropna().str[0].value_counts().to_dict(),
        "max_distance_m": MAX_DISTANCE_M,
        "added_median_distance_m": float(added.distance_m.median()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    print(f"wrote {path}: {len(added)} added, {provenance['added_methods']}")


if __name__ == "__main__":
    main()
