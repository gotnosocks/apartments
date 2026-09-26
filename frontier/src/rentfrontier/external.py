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
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import urllib.parse
import urllib.request

import pandas as pd

from .registry import EXTERNAL_ROOT
from .run import git

REGISTRY = EXTERNAL_ROOT / "registry" / "20260925-6b67137" / "buildings.parquet"
SOCRATA = "https://data.cityofnewyork.us/resource"
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source", choices=("pluto",))
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    registry = pd.read_parquet(REGISTRY)
    table, queries = fetch_pluto(registry.bbl.dropna())
    out_dir = EXTERNAL_ROOT / args.source / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.source}.parquet"
    table.to_parquet(path)
    missing = sorted(set(registry.bbl.dropna()) - set(table.bbl))
    provenance = {
        "source": f"{SOCRATA}/{PLUTO_ID}",
        "dataset": "MapPLUTO (NYC DCP) via NYC Open Data",
        "versions": sorted(table.version.dropna().unique().tolist()),
        "registry": str(REGISTRY),
        "queries": queries,
        "retrieved_at": started.isoformat(),
        "commit": commit,
        "lots": len(table),
        "registry_lots_missing": missing,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    print(f"wrote {path}: {len(table)} lots, {len(missing)} registry lots missing")


if __name__ == "__main__":
    main()
