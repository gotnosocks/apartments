"""API listing records from the data pipeline's records file.

Each pipeline build appends a line to `catalog.ndjson` in its datasets folder and lists its files
there with their SHA-256. `records_file` takes the newest complete line from a clean checkout, as
the site's `apartments.site.captures.pipeline_files` does, and checks the records file against
that line. The file holds a row for each distinct record of each listing, with the times the
collector first and last fetched it.

The builders read these rows where they read a granular export's `listing_observations`, so
`captures` gives each row the granular column names:

- `listing_id` as text;
- `collected_at` from `last_collected_at`, so a listing's last capture is the record the
  collector fetched last, at the time it last fetched it;
- `snapshot_id` from `response_id`, the record's first answer;
- `listing_type` and `raw_listing_json` as the file has them.

`captures` reads the file a row group at a time, because its record text runs to a few
gigabytes. `observations` reads a crawl a builder names, either a granular export's folder or
`CRAWL` for the records file.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

import pyarrow.parquet as pq

DATASETS = Path(
    os.environ.get("PIPELINE_DATASETS", "/data1/apartments/pipeline/datasets")
)
# A builder's `--crawl` takes this word for the records file.
CRAWL = "records"
# Each granular column and the records file's column for it.
NAMES = {
    "listing_id": "listing_id",
    "listing_type": "listing_type",
    "collected_at": "last_collected_at",
    "snapshot_id": "response_id",
    "raw_listing_json": "raw_listing_json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog_entry(root: Path | None = None) -> dict:
    """The newest complete line of `root`'s catalog from a clean checkout.

    The pipeline appends a build's line with its line break, so a last line without one is still
    being written, and I read the lines before it. A build from a checkout with changes can write
    to the same catalog, and I leave its line out."""
    catalog = (root or DATASETS) / "catalog.ndjson"
    lines = catalog.read_text().split("\n")[:-1]
    clean = [
        entry
        for entry in map(json.loads, filter(str.strip, lines))
        if entry.get("code", {}).get("clean") is True
    ]
    if not clean:
        raise ValueError(f"{catalog} lists no build from a clean checkout")
    return clean[-1]


def checked(entry: dict, key: str, root: Path | None = None) -> dict:
    """The file a catalog line lists under `key`, once its SHA-256 matches the line: its path,
    SHA-256, row count and the build's time."""
    root = root or DATASETS
    if key not in entry:
        raise ValueError(f"the newest build in {root / 'catalog.ndjson'} has no {key}")
    path = root / entry[key]["path"]
    if _sha256(path) != entry[key]["sha256"]:
        raise ValueError(f"{path} differs from the pipeline's catalog")
    return {
        "path": str(path),
        "sha256": entry[key]["sha256"],
        "rows": entry[key]["rows"],
        "built": entry.get("built"),
    }


def records_file(root: Path | None = None) -> dict:
    """The records file of the newest clean build under `root`, checked."""
    return checked(catalog_entry(root), "records", root)


def captures(
    source: dict, columns: Iterable[str], batch_size: int = 2_000
) -> Iterator[dict]:
    """Each row of the checked records file `source` as a granular capture with `columns`."""
    columns = list(columns)
    file = pq.ParquetFile(source["path"])
    for batch in file.iter_batches(
        batch_size=batch_size, columns=[NAMES[c] for c in columns]
    ):
        for row in batch.to_pylist():
            out = {c: row[NAMES[c]] for c in columns}
            if "listing_id" in out:
                out["listing_id"] = str(out["listing_id"])
            yield out


def observations(
    crawl: str, columns: Iterable[str], records: dict | None = None
) -> Iterator[dict]:
    """The rows of a granular crawl's `listing_observations` with `columns`, a Parquet file at a
    time in name order, or the records file's rows when `crawl` is `CRAWL`. `records` is the
    checked records file, and without it I read the catalog."""
    columns = list(columns)
    if crawl == CRAWL:
        yield from captures(records or records_file(), columns)
        return
    for path in sorted(
        glob.glob(f"{crawl}/listing_observations/**/*.parquet", recursive=True)
    ):
        yield from pq.read_table(path, columns=columns).to_pylist()
