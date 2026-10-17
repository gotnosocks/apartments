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

`captures` passes over the records of a listing whose own history holds no dated ACTIVE event,
as the build's ads file marks it with `no_dated_own_active_event`. The pipeline leaves these
ads out of its rows for the same reason. About half are drafts and ads held for review, which
never went on the market, and the rest ended with no ACTIVE event in their own history. Taking
the ads file from the same catalog line keeps the builders, the ads file and the rows on one set
of listings. A draft or an ad under review with a dated ACTIVE event of its own stays in, since
the rows can hold it too. A listing missing from the ads file is skipped as well.

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

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
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
# The ads file's reason for an ad whose own history holds no dated ACTIVE event.
NEVER_LISTED = "no_dated_own_active_event"


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
    """The records file of the newest clean build under `root`, checked, with the same build's
    ads file, checked, under `ads`."""
    entry = catalog_entry(root)
    source = checked(entry, "records", root)
    source["ads"] = checked(entry, "ads_file", root)
    return source


def listed(ads: dict) -> np.ndarray:
    """The listing ids of the checked ads file `ads`, as sorted integers, leaving out each ad
    marked `NEVER_LISTED`."""
    table = pq.read_table(ads["path"], columns=["listing_id", "exclusion_reasons"])
    reasons = table["exclusion_reasons"].combine_chunks()
    flagged = pc.filter(
        pc.list_parent_indices(reasons),
        pc.equal(pc.list_flatten(reasons), NEVER_LISTED),
    )
    keep = np.ones(table.num_rows, dtype=bool)
    keep[flagged.to_numpy()] = False
    return np.sort(pc.cast(table["listing_id"], pa.int64()).to_numpy()[keep])


def among(ids: np.ndarray, listing_ids: pa.Array) -> np.ndarray:
    """A mask over `listing_ids` marking each id found in the sorted array `ids`."""
    wanted = pc.cast(listing_ids, pa.int64()).to_numpy(zero_copy_only=False)
    at = np.searchsorted(ids, wanted)
    found = at < len(ids)
    found[found] = ids[at[found]] == wanted[found]
    return found


def captures(
    source: dict, columns: Iterable[str], batch_size: int = 2_000
) -> Iterator[dict]:
    """Each row of the checked records file `source` as a granular capture with `columns`, for
    the listings its ads file shows on the market. `source` comes from `records_file`, which
    adds the ads file under `ads`, and I skip a listing the ads file lacks."""
    columns = list(columns)
    ids = listed(source["ads"])
    file = pq.ParquetFile(source["path"])
    read = list(dict.fromkeys([*(NAMES[c] for c in columns), "listing_id"]))
    for batch in file.iter_batches(batch_size=batch_size, columns=read):
        keep = among(ids, batch["listing_id"])
        for row in batch.filter(pa.array(keep)).to_pylist():
            out = {c: row[NAMES[c]] for c in columns}
            if "listing_id" in out:
                out["listing_id"] = str(out["listing_id"])
            yield out


def observations(
    crawl: str, columns: Iterable[str], records: dict | None = None
) -> Iterator[dict]:
    """The rows of a granular crawl's `listing_observations` with `columns`, a Parquet file at a
    time in name order, or the records file's rows when `crawl` is `CRAWL`. `records` is the
    checked records file from `records_file`, and without it I read the catalog."""
    columns = list(columns)
    if crawl == CRAWL:
        yield from captures(records or records_file(), columns)
        return
    for path in sorted(
        glob.glob(f"{crawl}/listing_observations/**/*.parquet", recursive=True)
    ):
        yield from pq.read_table(path, columns=columns).to_pylist()
