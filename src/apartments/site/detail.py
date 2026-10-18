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

On the all-scraped bundle (1.75M rows, 30 terms) the copy took 30 s on one
thread, held 1.2 GB resident and wrote 779 MB, and a lookup took 12 to 35 ms
after the first. The copy runs inside the build while the build holds about
2.5 GB, so it keeps to one thread and a 1 GB limit: at 2 GB it took 24 s and
1.8 GB, and several threads under a tight limit fail to pin blocks in the sort. A column per term made
lookups take 110 ms, since DuckDB then reads 93 column chunks per lookup.

The listing page and the research story call `lookup` for a listing's parts
when its row holds none. Ads priced from the kit (captures.py) keep
their parts in the table, since the bundle has no row for them.

A bundle summarized with range atoms (`rentfrontier.summary --range-atoms`)
holds no likely ask ranges for most rows. For such a bundle the build copies
each row's atoms and noise group into ranges.parquet the same way, and the
bundle's noise.json beside it. `likely_ask` works the ranges out for a listing
with `ranges.likely_ask` when its page asks, and gives None when the file,
the row or its noise group is missing, so the page leaves the range out.

A build with SITE_KIT_ON_REQUEST=1 puts the estimate form's per-building
draws in kit_buildings.parquet the same way (`estimate_build.write_kit_file`),
and the form reads one building's with `KitBuildings`.

Each process holds one DuckDB connection per file of a build, with one thread
and a small memory limit, and caches lookups by the bundle's sha and the audit
id. Everything the lookup reads sits inside the build, so a rollback of
site/current brings its own detail back.
"""

from __future__ import annotations

import functools
import json
import tempfile
import threading
from pathlib import Path

import duckdb

from apartments.site import ranges

FILE = "detail.parquet"
RANGES_FILE = "ranges.parquet"
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
    values = ", ".join(
        '"{}"'.format(f"{name}_usd{side}".replace('"', '""'))
        for name in names
        for side in SIDES
    )
    terms = json.dumps(names).replace("'", "''")
    connection = duckdb.connect()
    try:
        connection.execute("SET memory_limit = '1GB'")
        connection.execute("SET threads = 1")
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


def has_atoms(bundle: Path) -> bool:
    """Whether the bundle's rows carry range atoms."""
    source = str(bundle / "rows.parquet").replace("'", "''")
    return bool(
        duckdb.sql(
            f"SELECT COUNT(*) FROM parquet_schema('{source}') "
            "WHERE name = 'estimate_atoms'"
        ).fetchone()[0]
    )


def write_ranges(bundle: Path, target: Path) -> dict:
    """Copy the atoms and noise group of every bundle row that has them to
    `target`, sorted by audit_id, and the bundle's noise.json beside it.
    Returns the file's row count and size for the build's record."""
    connection = duckdb.connect()
    try:
        connection.execute("SET memory_limit = '1GB'")
        connection.execute("SET threads = 1")
        connection.execute("SET preserve_insertion_order = true")
        connection.execute("SET temp_directory = ?", [tempfile.gettempdir()])
        source = str(bundle / "rows.parquet").replace("'", "''")
        out = str(target).replace("'", "''")
        connection.execute(
            "COPY (SELECT audit_id, noise_group, estimate_atoms AS atoms "
            f"FROM read_parquet('{source}') WHERE estimate_atoms IS NOT NULL "
            f"ORDER BY audit_id) TO '{out}' (FORMAT parquet, COMPRESSION zstd, "
            f"ROW_GROUP_SIZE {ROW_GROUP_ROWS})"
        )
        (rows,) = connection.execute(
            f"SELECT COUNT(*) FROM read_parquet('{out}')"
        ).fetchone()
    finally:
        connection.close()
    noise = target.parent / ranges.NOISE_FILE
    noise.write_bytes((bundle / ranges.NOISE_FILE).read_bytes())
    return {
        "file": RANGES_FILE,
        "rows": rows,
        "bytes": target.stat().st_size,
        "noise_bytes": noise.stat().st_size,
    }


class _File:
    """A Parquet file of a build, opened once per process, with a row per
    value of its KEY column."""

    KEY = "audit_id"

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

    def fetch(self, columns: str, key: str):
        with self._lock:
            return self._connection.execute(
                f"SELECT {columns} FROM detail WHERE {self.KEY} = ?", [key]
            ).fetchone()


class Detail(_File):
    """The detail file of a build."""

    def __init__(self, path: Path):
        super().__init__(path)
        (terms,) = self._connection.execute(
            "SELECT value FROM parquet_kv_metadata(?) WHERE key = 'terms'",
            [str(path)],
        ).fetchone()
        self.names = json.loads(terms)

    def row(self, audit_id: str) -> dict | None:
        """The listing's estimate, median and `{name}_usd{side}` values."""
        found = self.fetch("estimate, estimate_median, parts", audit_id)
        if found is None:
            return None
        estimate, median, values = found
        keys = (f"{name}_usd{side}" for name in self.names for side in SIDES)
        return {
            "estimate": estimate,
            "estimate_median": median,
            **dict(zip(keys, values, strict=True)),
        }


class Ranges(_File):
    """The ranges file of a build, with the noise tables beside it."""

    def __init__(self, path: Path):
        super().__init__(path)
        self.noise = ranges.load_noise(path.parent / ranges.NOISE_FILE)

    def likely_ask(self, audit_id: str) -> dict | None:
        """The listing's likely ask ranges in dollars, as `ranges.likely_ask`
        gives them; None without atoms or a noise table for its group."""
        found = self.fetch("noise_group, atoms", audit_id)
        if found is None or found[0] is None or found[1] is None:
            return None
        noise = self.noise.get(int(found[0]))
        return None if noise is None else ranges.likely_ask(list(found[1]), noise)


class KitBuildings(_File):
    """The kit file of a build (`estimate_build.write_kit_file`)."""

    KEY = "building_id"

    def terms(self, building_id: str) -> tuple | None:
        """The building's levels, bedroom slopes and feature slopes over the
        kit's draws, as the kit_buildings table holds them."""
        found = self.fetch("level, bedroom_slope, fslope, width", building_id)
        if found is None:
            return None
        level, bedroom_slope, flat, width = found
        fslope = [flat[s * width : (s + 1) * width] for s in range(len(level))]
        return level, bedroom_slope, fslope


_open: dict[tuple[type, Path], _File] = {}
_open_lock = threading.Lock()


def opened(path: Path, kind: type = Detail):
    """The process's connection to the build's file at `path`. A build
    published since replaces the old connections, which close once no request
    still holds them."""
    path = path.resolve()
    with _open_lock:
        found = _open.get((kind, path))
        if found is None:
            if any(p.parent != path.parent for _, p in _open):
                _open.clear()
            found = _open[kind, path] = kind(path)
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


@functools.lru_cache(maxsize=2048)
def _cached_ranges(path: Path, sha: str, audit_id: str) -> tuple | None:
    found = opened(path, Ranges).likely_ask(audit_id)
    return None if found is None else tuple(found.items())


def likely_ask(build_dir: Path, sha: str, audit_id: str) -> dict | None:
    """The listing's likely ask ranges from the build's ranges file, cached by
    the bundle's sha and the audit id; None when the build has no ranges file
    or the file has no ranges for the listing."""
    path = (build_dir / RANGES_FILE).resolve()
    if not path.is_file():
        return None
    found = _cached_ranges(path, sha, audit_id)
    return None if found is None else dict(found)
