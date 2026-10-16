"""SQLMesh settings for the pipeline.

The pipeline reads the scraper's export of API records and, until the event log takes their
place, the analysis rows of the current chain. Three environment variables give it its files:

- `PIPELINE_EXPORT`: the export folder, holding manifest.ndjson. The build reads the ads files
  the manifest lists. A file the exporter is still writing has no line yet, so it stays out.
- `PIPELINE_ROWS`: a Parquet file of analysis rows, as `ops/pipeline/analysis_rows.py` writes it.
- `PIPELINE_STATE`: the folder for the DuckDB database, its spill files and SQLMesh's cache.

`PIPELINE_MEMORY` sets DuckDB's memory limit, 5GB unless set. The connection also turns off
DuckDB's insertion order, so the rows of a table come out in no set order, and large queries
stream with less memory.

Besides each input's path, the models get a version for it: a SHA-256 over the manifest's path
and hash for each ads file, and the rows file's own SHA-256. SQLMesh fingerprints each model by
its SQL as written and by the values of the variables the SQL uses. The paths alone would miss a
file written again under its old name, so the raw views also use the versions. That holds when
the manifest's line for the file is replaced. An appended second line with another hash for the
same path stops the build, as `exported` raises. A new or
rewritten export file, or a changed rows file, thus gives a raw view a new fingerprint, and the
next plan rebuilds that view and every model below it. With the same inputs, a plan rebuilds
nothing.
"""

import hashlib
import json
import os
from pathlib import Path

from sqlmesh.core.config import (
    Config,
    DuckDBConnectionConfig,
    GatewayConfig,
    ModelDefaultsConfig,
)

EXPORT = Path(
    os.environ.get("PIPELINE_EXPORT", "/data1/apartments/archive/crawls/api/export")
)
ROWS = Path(
    os.environ.get(
        "PIPELINE_ROWS",
        "/data1/apartments/pipeline/inputs/analysis-rows-20261015-13f5968-api.parquet",
    )
)
STATE = Path(os.environ.get("PIPELINE_STATE", "/data1/apartments/pipeline/state"))


def exported(table):
    """The listed files of an export table, sorted by path, and a SHA-256 over their lines."""
    files = {}
    for line in (EXPORT / "manifest.ndjson").read_text().splitlines(keepends=True):
        # The exporter writes each line whole and drops a cut-off last line on its next start.
        if not line.endswith("\n") or not line.strip():
            continue
        entry = json.loads(line)
        if entry["table"] != table:
            continue
        if files.setdefault(entry["path"], entry["sha256"]) != entry["sha256"]:
            raise ValueError(f"manifest gives {entry['path']} two hashes")
    if not files:
        raise ValueError(f"manifest lists no {table} files in {EXPORT}")
    paths = sorted(files)
    listing = "".join(f"{path} {files[path]}\n" for path in paths)
    version = hashlib.sha256(listing.encode()).hexdigest()
    return [str(EXPORT / path) for path in paths], version


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


ads, ads_version = exported("ads")
STATE.mkdir(parents=True, exist_ok=True)

config = Config(
    gateways={
        "local": GatewayConfig(
            connection=DuckDBConnectionConfig(
                database=str(STATE / "pipeline.duckdb"),
                connector_config={
                    "TimeZone": "UTC",
                    "memory_limit": os.environ.get("PIPELINE_MEMORY", "5GB"),
                    "preserve_insertion_order": False,
                    "temp_directory": str(STATE / "spill"),
                },
            )
        )
    },
    default_gateway="local",
    model_defaults=ModelDefaultsConfig(dialect="duckdb"),
    cache_dir=str(STATE / "cache"),
    variables={
        "ads": ads,
        "ads_version": ads_version,
        "rows": str(ROWS),
        "rows_version": file_sha256(ROWS),
    },
)
