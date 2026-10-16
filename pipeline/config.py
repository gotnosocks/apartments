"""SQLMesh settings for the pipeline.

The pipeline reads the scraper's export of API records. Two environment variables give it its
files:

- `PIPELINE_EXPORT`: the export folder, holding manifest.ndjson. The build reads the ads and
  buildings files the manifest lists. A file the exporter is still writing has no line yet, so
  it stays out.
- `PIPELINE_STATE`: the folder for the DuckDB database, its spill files and SQLMesh's cache.

`PIPELINE_LEDGER` names the folder of the corrections ledger, `pipeline/ledger` unless set.
The config stops when the folder is missing, as a mistyped path would otherwise give a build
with no corrections. `models/ledger/entries.py` explains the ledger.

`PIPELINE_MEMORY` sets DuckDB's memory limit, 5GB unless set. The connection also turns off
DuckDB's insertion order, so the rows of a table come out in no set order, and large queries
stream with less memory.

Besides each export table's paths, the models get a version for it: a SHA-256 over the
manifest's path and hash for each of its files. SQLMesh fingerprints each model by its SQL as
written and by the values of the variables the SQL uses. The paths alone would miss a file
written again under its old name, so the raw views also use the versions. That holds when the
manifest's line for the file is replaced. An appended second line with another hash for the
same path stops the build, as `exported` raises. A new or rewritten export file thus gives a raw
view a new fingerprint, and the next plan rebuilds that view and every model below it. With the
same inputs, a plan rebuilds nothing.
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
STATE = Path(os.environ.get("PIPELINE_STATE", "/data1/apartments/pipeline/state"))

# ads.record_attributes runs `steps.attributes`, which imports these modules of the current chain
# from the repo's src. Its code version covers their files in this checkout.
PIPELINE = Path(__file__).resolve().parent
SRC = PIPELINE.parent / "src"
LEDGER = Path(os.environ.get("PIPELINE_LEDGER") or PIPELINE / "ledger")
ATTRIBUTES_MODULES = (
    "steps.attributes",
    "apartments",
    "apartments.analytical",
    "apartments.attribute_evidence",
    "apartments.corrections",
    "apartments.historical_dataset",
    "apartments.research_pipeline",
)


def module_file(name):
    root = PIPELINE if name.startswith("steps.") else SRC
    path = root.joinpath(*name.split("."))
    return path / "__init__.py" if path.is_dir() else path.with_suffix(".py")


ATTRIBUTES_CODE = [module_file(name) for name in ATTRIBUTES_MODULES]


def exported(table):
    """The listed files of an export table, sorted by path, a SHA-256 over their lines, and
    each listed path with its file's SHA-256."""
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
    return [str(EXPORT / path) for path in paths], version, {p: files[p] for p in paths}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


ads, ads_version, ads_files = exported("ads")
buildings, buildings_version, buildings_files = exported("buildings")
if not LEDGER.is_dir():
    raise FileNotFoundError(f"no ledger folder at {LEDGER}")
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
        "buildings": buildings,
        "buildings_version": buildings_version,
        # ops/pipeline/build.py records these in its catalog line. No model reads them, so they
        # stay out of the models' fingerprints.
        "export_files": {"ads": ads_files, "buildings": buildings_files},
        # Each ledger file with its SHA-256. ledger.entries reads them, and the catalog line
        # records them.
        "ledger": {
            str(path): file_sha256(path) for path in sorted(LEDGER.glob("*.ndjson"))
        },
        "attributes_code": {
            name: file_sha256(path)
            for name, path in zip(ATTRIBUTES_MODULES, ATTRIBUTES_CODE)
        },
    },
)
