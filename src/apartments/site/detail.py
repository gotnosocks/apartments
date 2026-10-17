"""Listing detail read when a page asks for it.

A build with SITE_DETAIL_ON_REQUEST=1 leaves each fitted listing's dollar
parts out of the `listings` table. It copies them instead from the bundle's
rows.parquet into detail.parquet beside site.sqlite: a row per listing, sorted
by audit_id in small row groups, so DuckDB reads one group per lookup. Each
row holds the estimate, its median and a single list of the parts: every
term's mean part and 95% bounds in the terms' order, as the summary wrote
them. The term names go in the file's key-value metadata. `parts` scales the
values on the way out exactly as `build.listing_rows` does for a build that
stores them.

On the all-scraped bundle (1.75M rows, 30 terms) the copy took 20 s and wrote
778 MB, and a lookup took 15 to 35 ms after the first. A column per term made
lookups take 110 ms, since DuckDB then reads 93 column chunks per lookup.

The listing page and the research story call `lookup` for a listing's parts
when its row holds none. Ads priced from the kit (captures.py) keep
their parts in the table, since the bundle has no row for them.

Each process holds one DuckDB connection per build, with one thread and a
small memory limit, and caches lookups by the bundle's sha and the audit id.
Everything the lookup reads sits inside the build, so a rollback of
site/current brings its own detail back.
"""

from __future__ import annotations

import functools
import json
import tempfile
import threading
from pathlib import Path

import duckdb

FILE = "detail.parquet"
# Rows per row group: 2048 and 32768 both made lookups slower at 1.75M rows.
ROW_GROUP_ROWS = 8192
SIDES = ("", "_lower_95", "_upper_95")


def parts(row: dict, names: list[str]) -> list[dict]:
    """The listing's dollar parts, a dict per term in the terms' order. The
    estimate is the predictive median, never the mean: with Student-t
    apartment effects of low nu the mean of a new apartment's rent barely
    exists. The parts add up to the mean, so they are scaled to add up to the
    median."""
    median = row["estimate_median"]
    scale = median / row["estimate"] if row["estimate"] else 1.0
    return [
        {
            "term": name,
            "usd": round(scale * row[f"{name}_usd"], 2),
            "lower": round(scale * row[f"{name}_usd_lower_95"], 2),
            "upper": round(scale * row[f"{name}_usd_upper_95"], 2),
        }
        for name in names
    ]


def write(bundle: Path, names: list[str], target: Path) -> dict:
    """Copy the parts of every bundle row to `target`, sorted by audit_id.
    Returns the file's row count and size for the build's record."""
    values = ", ".join(f'"{name}_usd{side}"' for name in names for side in SIDES)
    terms = json.dumps(names).replace("'", "''")
    connection = duckdb.connect()
    try:
        connection.execute("SET memory_limit = '2GB'")
        connection.execute("SET threads = 2")
        connection.execute("SET preserve_insertion_order = true")
        connection.execute("SET temp_directory = ?", [tempfile.gettempdir()])
        # DuckDB's COPY takes no bound parameters for the paths.
        source = str(bundle / "rows.parquet").replace("'", "''")
        out = str(target).replace("'", "''")
        connection.execute(
            "COPY (SELECT audit_id, estimate, estimate_median, "
            f"[{values}]::DOUBLE[] AS parts "
            f"FROM read_parquet('{source}') ORDER BY audit_id) "
            f"TO '{out}' (FORMAT parquet, COMPRESSION zstd, "
            f"ROW_GROUP_SIZE {ROW_GROUP_ROWS}, KV_METADATA {{terms: '{terms}'}})"
        )
        (rows,) = connection.execute(
            f"SELECT COUNT(*) FROM read_parquet('{out}')"
        ).fetchone()
    finally:
        connection.close()
    return {"file": FILE, "rows": rows, "bytes": target.stat().st_size}


class Detail:
    """The detail file of a build, opened once per process."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._connection = duckdb.connect()
        self._connection.execute("SET threads = 1")
        self._connection.execute("SET memory_limit = '128MB'")
        self._connection.execute("SET enable_object_cache = true")
        quoted = str(path).replace("'", "''")
        self._connection.execute(
            f"CREATE VIEW detail AS SELECT * FROM read_parquet('{quoted}')"
        )
        (terms,) = self._connection.execute(
            "SELECT value FROM parquet_kv_metadata(?) WHERE key = 'terms'",
            [str(path)],
        ).fetchone()
        self.names = json.loads(terms)

    def row(self, audit_id: str) -> dict | None:
        """The listing's estimate, median and `{name}_usd{side}` values."""
        with self._lock:
            found = self._connection.execute(
                "SELECT estimate, estimate_median, parts FROM detail "
                "WHERE audit_id = ?",
                [audit_id],
            ).fetchone()
        if found is None:
            return None
        estimate, median, values = found
        keys = (f"{name}_usd{side}" for name in self.names for side in SIDES)
        return {
            "estimate": estimate,
            "estimate_median": median,
            **dict(zip(keys, values, strict=True)),
        }


_open: dict[Path, Detail] = {}
_open_lock = threading.Lock()


def opened(path: Path) -> Detail:
    """The process's connection to the detail file at `path`. A build
    published since replaces the old connection, which closes once no request
    still holds it."""
    path = path.resolve()
    with _open_lock:
        found = _open.get(path)
        if found is None:
            _open.clear()
            found = _open[path] = Detail(path)
        return found


@functools.lru_cache(maxsize=2048)
def _cached_parts(path: Path, sha: str, audit_id: str) -> tuple | None:
    detail = opened(path)
    row = detail.row(audit_id)
    if row is None:
        return None
    return tuple(tuple(p.items()) for p in parts(row, detail.names))


def lookup(build_dir: Path, sha: str, audit_id: str) -> list[dict] | None:
    """The listing's parts from the build's detail file, cached by the
    bundle's sha and the audit id; None when the file has no such row."""
    found = _cached_parts((build_dir / FILE).resolve(), sha, audit_id)
    return None if found is None else [dict(p) for p in found]
