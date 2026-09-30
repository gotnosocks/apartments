"""Snapshots of external data, joined to our buildings through the registry.

    python -m rentfrontier.external pluto

Each source is a dated snapshot under
/data1/apartments/external/<source>/<date>-<commit>/ with the rows used and
provenance.json (URL, query, dataset version, retrieval time, sha256).
Feature sets (features.py) name the snapshot they read, so a run records
exactly which external data it saw. Refuses a dirty tree.

Sources:
- pluto: MapPLUTO (NYC Department of City Planning, NYC Open Data 64uk-42ks),
  one row per tax lot (BBL) in the registry. Assessed values are not kept:
  for rental buildings they are derived from rental income, which would make
  the feature partly circular.
- subway: MTA Subway Stations (data.ny.gov 39hk-dx4f), every station stop with
  its daytime routes and coordinates (transit access).
- basemap: the map under the rent map, around the registry's buildings (their
  bounding box plus BASEMAP_MARGIN_M): street centerlines with width, lanes,
  speed and roadway type (NYC Open Data inkn-q76z), parks (enfh-gkve) and
  Manhattan's shoreline (borough boundary, gthc-hcne). One row per feature,
  geometry as GeoJSON.
- hpd: HPD Housing Maintenance Code Violations (NYC Open Data wvxf-dwi5) of
  the registry's buildings, by BIN, and by tax lot (BBL) for placeholder BINs
  (n000000): class (A non-hazardous, B hazardous, C immediately hazardous, I
  information), when the inspection found it and when the notice was issued,
  and its current status.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import itertools
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from .registry import EXTERNAL_ROOT
from .run import git

REGISTRY = EXTERNAL_ROOT / "registry" / "20260925-6b67137" / "buildings.parquet"
NYC_OPEN_DATA = "https://data.cityofnewyork.us"
SOCRATA = f"{NYC_OPEN_DATA}/resource"
PLUTO_ID = "64uk-42ks"
PLUTO_COLUMNS = (
    "bbl",
    "address",
    "version",
    "yearbuilt",
    "yearalter1",
    "yearalter2",
    "numfloors",
    "numbldgs",
    "unitsres",
    "unitstotal",
    "lotarea",
    "bldgarea",
    "resarea",
    "comarea",
    "retailarea",
    "lotfront",
    "lotdepth",
    "bldgfront",
    "bldgdepth",
    "bldgclass",
    "landuse",
    "landmark",
    "histdist",
    "zonedist1",
    "builtfar",
    "residfar",
    "proxcode",
    "irrlotcode",
    "lottype",
    "bsmtcode",
    "pfirm15_flag",
    "firm07_flag",
    "schooldist",
    "policeprct",
    "latitude",
    "longitude",
)


def _socrata(dataset: str, params: dict) -> list[dict]:
    url = f"{SOCRATA}/{dataset}.json?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def fetch_pluto(bbls, batch: int = 100) -> tuple[pd.DataFrame, list[str]]:
    rows, queries = [], []
    bbls = sorted(set(bbls))
    for i in range(0, len(bbls), batch):
        where = f"bbl in ({', '.join(bbls[i : i + batch])})"
        params = {"$select": ", ".join(PLUTO_COLUMNS), "$where": where, "$limit": 5000}
        rows += _socrata(PLUTO_ID, params)
        queries.append(urllib.parse.urlencode(params))
    table = pd.DataFrame(rows, columns=list(PLUTO_COLUMNS))
    table["bbl"] = table.bbl.astype(float).astype("int64").astype(str)
    return table, queries


NY_SOCRATA = "https://data.ny.gov"
SUBWAY_ID = "39hk-dx4f"
SUBWAY_COLUMNS = (
    "gtfs_stop_id",
    "station_id",
    "complex_id",
    "stop_name",
    "line",
    "daytime_routes",
    "structure",
    "borough",
    "ada",
    "gtfs_latitude",
    "gtfs_longitude",
)


def fetch_subway() -> tuple[pd.DataFrame, list[str], dict]:
    params = {"$select": ", ".join(SUBWAY_COLUMNS), "$limit": 5000}
    url = f"{NY_SOCRATA}/resource/{SUBWAY_ID}.json?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        rows = json.loads(r.read())
    with urllib.request.urlopen(
        f"{NY_SOCRATA}/api/views/{SUBWAY_ID}.json", timeout=60
    ) as r:
        meta = json.loads(r.read())
    table = pd.DataFrame(rows, columns=list(SUBWAY_COLUMNS))
    for c in ("gtfs_latitude", "gtfs_longitude"):
        table[c] = table[c].astype(float)
    version = {
        "name": meta.get("name"),
        "rows_updated_at": dt.datetime.fromtimestamp(
            meta["rowsUpdatedAt"], dt.UTC
        ).isoformat(),
    }
    return table, [urllib.parse.urlencode(params)], version


CENTERLINE_ID = "inkn-q76z"
PARKS_ID = "enfh-gkve"
BOROUGHS_ID = "gthc-hcne"
BASEMAP_MARGIN_M = 400.0
CENTERLINE_COLUMNS = (
    "physicalid",
    "full_street_name",
    "stname_label",
    "streetwidth",
    "number_travel_lanes",
    "posted_speed",
    "rw_type",
    "trafdir",
    "the_geom",
)


def basemap_box(registry: pd.DataFrame) -> tuple[float, float, float, float]:
    """(north, west, south, east) degrees around the registry's buildings."""
    lat, lon = registry.latitude.dropna(), registry.longitude.dropna()
    dlat = BASEMAP_MARGIN_M / 111_320.0
    dlon = dlat / math.cos(math.radians(lat.mean()))
    return lat.max() + dlat, lon.min() - dlon, lat.min() - dlat, lon.max() + dlon


def fetch_basemap(box) -> tuple[pd.DataFrame, list[str], dict]:
    n, w, s, e = box
    rows, queries, versions = [], [], {}
    for layer, dataset, params in (
        (
            "street",
            CENTERLINE_ID,
            {
                "$select": ", ".join(CENTERLINE_COLUMNS),
                "$where": f"within_box(the_geom, {n}, {w}, {s}, {e})",
                "$limit": 20000,
            },
        ),
        (
            "park",
            PARKS_ID,
            {
                "$select": "signname, typecategory, multipolygon",
                "$where": f"within_box(multipolygon, {n}, {w}, {s}, {e})",
                "$limit": 5000,
            },
        ),
        ("land", BOROUGHS_ID, {"$select": "boroname, the_geom", "borocode": 1}),
    ):
        for r in _socrata(dataset, params):
            geometry = r.pop("the_geom", None) or r.pop("multipolygon", None)
            name = r.pop("full_street_name", None) or r.pop("signname", None)
            rows.append(
                {
                    "layer": layer,
                    "name": name or r.get("boroname"),
                    "attributes": json.dumps(r, sort_keys=True),
                    "geometry": json.dumps(geometry),
                }
            )
        queries.append(f"{dataset}?{urllib.parse.urlencode(params)}")
        with urllib.request.urlopen(
            f"{NYC_OPEN_DATA}/api/views/{dataset}.json", timeout=60
        ) as r:
            meta = json.loads(r.read())
        versions[dataset] = {
            "name": meta.get("name"),
            "rows_updated_at": dt.datetime.fromtimestamp(
                meta["rowsUpdatedAt"], dt.UTC
            ).isoformat(),
        }
    return pd.DataFrame(rows), queries, versions


HPD_ID = "wvxf-dwi5"
HPD_COLUMNS = (
    "violationid",
    "bin",
    "bbl",
    "class",
    "inspectiondate",
    "novissueddate",
    "currentstatus",
    "currentstatusdate",
    "violationstatus",
    "rentimpairing",
)


def fetch_hpd(registry: pd.DataFrame, batch: int = 100, page: int = 50_000):
    bins = registry.bin.dropna().astype(str)
    placeholder = bins.str.fullmatch(r"[1-5]000000")
    rows, queries = [], []
    for field, values in (
        ("bin", sorted(set(bins[~placeholder]))),
        ("bbl", sorted(set(registry.bbl[placeholder.to_numpy()].dropna().astype(str)))),
    ):
        for i in range(0, len(values), batch):
            where = f"{field} in ({', '.join(repr(v) for v in values[i : i + batch])})"
            for offset in itertools.count(0, page):
                params = {
                    "$select": ", ".join(HPD_COLUMNS),
                    "$where": where,
                    "$order": "violationid",
                    "$limit": page,
                    "$offset": offset,
                }
                got = _socrata(HPD_ID, params)
                rows += [{k: r.get(k) for k in HPD_COLUMNS} for r in got]
                queries.append(f"{HPD_ID}?{urllib.parse.urlencode(params)}")
                if len(got) < page:
                    break
    table = pd.DataFrame(rows, columns=list(HPD_COLUMNS)).drop_duplicates("violationid")
    with urllib.request.urlopen(
        f"{NYC_OPEN_DATA}/api/views/{HPD_ID}.json", timeout=60
    ) as r:
        meta = json.loads(r.read())
    version = {
        "name": meta.get("name"),
        "rows_updated_at": dt.datetime.fromtimestamp(
            meta["rowsUpdatedAt"], dt.UTC
        ).isoformat(),
    }
    return table.reset_index(drop=True), queries, version


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source", choices=("pluto", "subway", "basemap", "hpd"))
    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY,
        help="registry buildings.parquet to join through (default: the first snapshot)",
    )
    args = parser.parse_args(argv)
    registry_path = args.registry
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    out_dir = EXTERNAL_ROOT / args.source / f"{started:%Y%m%d}-{commit[:7]}"
    path = out_dir / f"{args.source}.parquet"
    if args.source == "pluto":
        registry = pd.read_parquet(registry_path)
        table, queries = fetch_pluto(registry.bbl.dropna())
        missing = sorted(set(registry.bbl.dropna()) - set(table.bbl))
        details = {
            "source": f"{SOCRATA}/{PLUTO_ID}",
            "dataset": "MapPLUTO (NYC DCP) via NYC Open Data",
            "versions": sorted(table.version.dropna().unique().tolist()),
            "registry": str(registry_path),
            "lots": len(table),
            "registry_lots_missing": missing,
        }
        summary = f"{len(table)} lots, {len(missing)} registry lots missing"
    elif args.source == "hpd":
        registry = pd.read_parquet(registry_path)
        table, queries, version = fetch_hpd(registry)
        details = {
            "source": f"{SOCRATA}/{HPD_ID}",
            "dataset": "HPD Housing Maintenance Code Violations via NYC Open Data",
            "version": version,
            "registry": str(registry_path),
            "violations": len(table),
            "buildings": int(table.bin.nunique()),
        }
        summary = f"{len(table)} violations in {table.bin.nunique()} buildings"
    elif args.source == "basemap":
        box = basemap_box(pd.read_parquet(registry_path))
        table, queries, versions = fetch_basemap(box)
        counts = table.layer.value_counts().to_dict()
        details = {
            "source": SOCRATA,
            "dataset": "NYC Open Data: street centerlines, parks, borough boundary",
            "versions": versions,
            "registry": str(registry_path),
            "box_north_west_south_east": box,
            "features": counts,
        }
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    else:
        table, queries, version = fetch_subway()
        details = {
            "source": f"{NY_SOCRATA}/resource/{SUBWAY_ID}",
            "dataset": "MTA Subway Stations via data.ny.gov",
            "version": version,
            "stops": len(table),
        }
        summary = f"{len(table)} station stops"
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path)
    provenance = {
        **details,
        "queries": queries,
        "retrieved_at": started.isoformat(),
        "commit": commit,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    print(f"wrote {path}: {summary}")


if __name__ == "__main__":
    main()
