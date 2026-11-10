"""The Estimates section's table: what the served drift model expected for ads it never saw.

`python -m rentfrontier.drift_estimates publish` writes the site's `estimates/` folder:
`estimates.parquet`, one row per ad a fit held out, and `meta.json` (the model, its two runs
and their convergence gates, the latest fit's held-out scores, the counts, and the table's
sha256), written last. A row's `source` says which fit held the ad out:

- "latest": a past ad, the newest ad of its apartment, whose final ask the fit on the latest
  split never saw;
- "market": an ad on the market on the scoring day, held out by the fit on the market split.

Every other ad (an apartment's earlier ads, which the fits learned from) has no estimate here,
since a prediction for an ask the model saw would not be a fair test.

The pages read this folder and nothing else. A table whose sha256 is not the one its meta
names is refused (`Refused`), so a page never mixes one publish's meta with another's rows.
Queries go through DuckDB over the parquet: one connection per process and published file,
one thread and a small memory limit, as `detail.py` reads its files. Ben chose to rebuild the
section on drift-building's held-out estimates, without the earlier model's per-listing
dollar parts, estimate form or rent map (2026-11-10).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import threading
from pathlib import Path

import duckdb

from . import boroughs
from .deals import LISTING, hood_label, lower_words

FOLDER = "estimates"
TABLE = "estimates.parquet"
META = "meta.json"
# The table's columns, as `rentfrontier.drift_estimates.COLUMNS` writes them. The site's
# environment has no rentfrontier, so they are named here too.
BOUNDS = ("lo95", "lo80", "lo50", "hi50", "hi80", "hi95")
COLUMNS = (
    "listing_id",
    "audit_id",
    "source",
    "building",
    "address",
    "latitude",
    "longitude",
    "neighbourhood",
    "unit_id",
    "bedrooms",
    "full_baths",
    "half_baths",
    "day",
    "status",
    "ask",
    "model_median",
    *(f"model_{b}" for b in BOUNDS),
    "discount_pct",
    "below_share",
    "unit_ads",
)
PER_PAGE = 50
# The list's `status` choices: the query key and words of the earlier listings page, so its
# links keep working. "current" is the market fit's ads, "past" the latest fit's.
STATUS = {"all": "All estimates", "current": "On the market", "past": "Past ads"}
SOURCE_OF = {"current": "market", "past": "latest"}
SOURCE_WORDS = {"market": "On the market", "latest": "Past ad"}
BEDROOMS = {"0": "Studio", "1": "1 BR", "2": "2 BR", "3": "3 BR", "4": "4+ BR"}
# Each order of the list: its SQL and its words. `listing_id` breaks ties.
SORTS = {
    "date": ("day DESC", "Newest first"),
    "low": ("below_share ASC", "Lowest ask against the model"),
    "high": ("below_share DESC", "Highest ask against the model"),
    "ask": ("ask ASC", "Lowest ask"),
    "ask_desc": ("ask DESC", "Highest ask"),
}
# The earlier listings page's sort keys, read as the nearest order here.
OLD_SORTS = {"diff_pct": "low", "diff": "low", "estimate": "ask"}
# Rows per read while the CSV streams, so a download never holds the whole table.
CSV_CHUNK = 5000


class Refused(Exception):
    """The folder holds a table that is not the one its meta describes."""


@dataclasses.dataclass
class Choice:
    """The list's filters from a query string. Anything unreadable is left out."""

    q: str = ""
    nb: str | None = None
    beds: list[str] = dataclasses.field(default_factory=list)
    min_ask: float | None = None
    max_ask: float | None = None
    year_from: int | None = None
    year_to: int | None = None
    status: str = "all"
    sort: str = "date"
    page: int = 1
    # The neighbourhood values `nb` stands for, set by `choice`.
    hoods: list[str] | None = None

    def args(self, **changes) -> dict:
        """Query-string items for a link with some filters changed."""
        items = {
            "q": self.q or None,
            "nb": self.nb,
            "beds": self.beds or None,
            "min_ask": _fmt(self.min_ask),
            "max_ask": _fmt(self.max_ask),
            "from": self.year_from,
            "to": self.year_to,
            "status": None if self.status == "all" else self.status,
            "sort": None if self.sort == "date" else self.sort,
            "page": None if self.page == 1 else self.page,
        }
        items.update(changes)
        return {k: v for k, v in items.items() if v not in (None, [], "")}

    def active(self) -> bool:
        return bool(
            self.q
            or self.nb
            or self.beds
            or self.min_ask is not None
            or self.max_ask is not None
            or self.year_from
            or self.year_to
            or self.status != "all"
        )


def _number(value) -> float | None:
    try:
        value = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _fmt(value: float | None) -> str | None:
    return None if value is None else f"{value:g}"


def _year(value) -> int | None:
    value = str(value or "").strip()
    return int(value) if re.fullmatch(r"(19|20)\d\d", value) else None


def _page(value) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _sort(args) -> str:
    sort, order = args.get("sort") or "date", args.get("order")
    sort = OLD_SORTS.get(sort, sort)
    if sort == "low" and order == "desc":
        return "high"
    if sort == "ask" and order == "desc":
        return "ask_desc"
    return sort if sort in SORTS else "date"


def areas(nb: str | None, hoods: dict[str, int]) -> list[str] | None:
    """The table's neighbourhood values a choice stands for: one by its value or its
    name, or a borough's when the table covers several boroughs; None for no choice."""
    if not nb:
        return None
    named = {}
    for value in hoods:
        named.setdefault(hood_label(value), []).append(value)
    counts = {name: sum(hoods[v] for v in values) for name, values in named.items()}
    if nb in hoods:
        return [nb]
    found = next((n for n in named if n.lower() == nb.lower()), None)
    if found is not None:
        return named[found]
    names = boroughs.areas(nb, counts)
    return None if names is None else [v for n in names for v in named[n]]


def choice(args, hoods: dict[str, int]) -> Choice:
    """The filters of a query string, against the table's neighbourhoods."""
    out = Choice(
        q=(args.get("q") or "").strip()[:80],
        nb=(args.get("nb") or "").strip()[:60] or None,
        beds=[b for b in dict.fromkeys(args.getlist("beds")) if b in BEDROOMS],
        min_ask=_number(args.get("min_ask")),
        max_ask=_number(args.get("max_ask")),
        year_from=_year(args.get("from")),
        year_to=_year(args.get("to")),
        status=args.get("status") if args.get("status") in STATUS else "all",
        sort=_sort(args),
        page=_page(args.get("page")),
    )
    out.hoods = areas(out.nb, hoods)
    if out.hoods is None:
        out.nb = None
    return out


def where(c: Choice) -> tuple[str, list]:
    """The SQL filter of a choice and its parameters."""
    clauses, params = [], []
    if c.hoods:
        clauses.append("neighbourhood IN (" + ", ".join("?" * len(c.hoods)) + ")")
        params += c.hoods
    if c.q:
        like = "%" + c.q.lower().replace("\\", "\\\\").replace("%", "\\%") + "%"
        like = like.replace("_", "\\_")
        clauses.append(
            "(lower(address) LIKE ? ESCAPE '\\' OR lower(building) LIKE ? ESCAPE '\\')"
        )
        # Building ids spell an address with dashes: "134-west-23-street-new_york".
        params += [like, like.replace(" ", "-")]
    if c.beds:
        parts = []
        for b in c.beds:
            if b == "4":
                parts.append("bedrooms >= 4")
            else:
                parts.append("bedrooms = ?")
                params.append(float(b))
        clauses.append("(" + " OR ".join(parts) + ")")
    if c.min_ask is not None:
        clauses.append("ask >= ?")
        params.append(c.min_ask)
    if c.max_ask is not None:
        clauses.append("ask <= ?")
        params.append(c.max_ask)
    if c.year_from is not None:
        clauses.append("day >= ?")
        params.append(f"{c.year_from}-01-01")
    if c.year_to is not None:
        clauses.append("day <= ?")
        params.append(f"{c.year_to}-12-31")
    if c.status in SOURCE_OF:
        clauses.append("source = ?")
        params.append(SOURCE_OF[c.status])
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _order(c: Choice) -> str:
    return f" ORDER BY {SORTS[c.sort][0]}, listing_id"


def _finite(value) -> float | None:
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def _text(value) -> str | None:
    value = "" if value is None else str(value).strip()
    return None if value.lower() in ("", "nan", "none", "<na>", "null") else value


def shown(row: dict) -> dict:
    """A table row with the page's words and links."""
    share = _finite(row.get("below_share"))
    listing = str(row.get("listing_id") or "")
    beds = _finite(row.get("bedrooms"))
    full, half = _finite(row.get("full_baths")), _finite(row.get("half_baths"))
    baths = None if full is None else full + 0.5 * (half or 0)
    return row | {
        "address": _text(row.get("address")),
        "neighbourhood": _text(row.get("neighbourhood")),
        "hood_label": hood_label(_text(row.get("neighbourhood"))),
        "bedrooms": beds,
        "baths": baths,
        "unit_ads": int(_finite(row.get("unit_ads")) or 0),
        "lower_than": None if share is None else 100 * (1 - share),
        "lower_words": None if share is None else lower_words(100 * (1 - share)),
        "url": LISTING + listing if re.fullmatch(r"\d+", listing) else None,
        "source_words": SOURCE_WORDS.get(row.get("source"), row.get("source")),
    }


class Table:
    """One published table and its meta, with a DuckDB connection over the table."""

    def __init__(self, path: Path, meta: dict):
        self.path, self.meta = path, meta
        self._lock = threading.Lock()
        self._connection = duckdb.connect()
        self._connection.execute("SET threads = 1")
        self._connection.execute("SET memory_limit = '256MB'")
        quoted = str(path).replace("'", "''")
        self._connection.execute(
            f"CREATE VIEW estimates AS SELECT * FROM read_parquet('{quoted}')"
        )
        described = self._connection.execute("SELECT * FROM estimates LIMIT 0")
        self.columns = [d[0] for d in described.description]
        self._hoods = None

    def _rows(self, sql: str, params: list) -> list[dict]:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            names = [d[0] for d in cursor.description]
            return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]

    def _one(self, sql: str, params: list):
        with self._lock:
            return self._connection.execute(sql, params).fetchone()

    def count(self, c: Choice) -> int:
        sql, params = where(c)
        return self._one(f"SELECT COUNT(*) FROM estimates{sql}", params)[0]

    def page(self, c: Choice) -> tuple[list[dict], int, int]:
        """The choice's page of rows, its count and its number of pages. A page past the
        last is read as the last."""
        total = self.count(c)
        pages = max(1, math.ceil(total / PER_PAGE))
        c.page = min(c.page, pages)
        sql, params = where(c)
        rows = self._rows(
            f"SELECT * FROM estimates{sql}{_order(c)} LIMIT ? OFFSET ?",
            [*params, PER_PAGE, (c.page - 1) * PER_PAGE],
        )
        return [shown(r) for r in rows], total, pages

    def csv_rows(self, c: Choice):
        """The choice's rows as tuples of COLUMNS, in its order, read a chunk at a time."""
        sql, params = where(c)
        columns = ", ".join(f'"{name}"' for name in self.csv_columns())
        offset = 0
        while True:
            with self._lock:
                chunk = self._connection.execute(
                    f"SELECT {columns} FROM estimates{sql}{_order(c)} LIMIT ? OFFSET ?",
                    [*params, CSV_CHUNK, offset],
                ).fetchall()
            yield from chunk
            if len(chunk) < CSV_CHUNK:
                return
            offset += CSV_CHUNK

    def csv_columns(self) -> list[str]:
        """Every column of the table: COLUMNS first, then any a later publish added."""
        return [c for c in COLUMNS if c in self.columns] + [
            c for c in self.columns if c not in COLUMNS
        ]

    def row(self, key: str) -> dict | None:
        """The row of an ad by its listing id, else by its audit id."""
        for column in ("listing_id", "audit_id"):
            rows = self._rows(
                f"SELECT * FROM estimates WHERE {column} = ? ORDER BY day DESC LIMIT 1",
                [key],
            )
            if rows:
                return shown(rows[0])
        return None

    def hoods(self) -> dict[str, int]:
        """The table's neighbourhood values and their row counts."""
        if self._hoods is None:
            self._hoods = {
                name: n
                for name, n in self._one_all(
                    "SELECT neighbourhood, COUNT(*) FROM estimates "
                    "WHERE neighbourhood IS NOT NULL AND neighbourhood <> '' "
                    "GROUP BY neighbourhood ORDER BY neighbourhood"
                )
            }
        return self._hoods

    def _one_all(self, sql: str, params=()) -> list:
        with self._lock:
            return self._connection.execute(sql, list(params)).fetchall()

    def hood_names(self) -> dict[str, int]:
        """The table's neighbourhoods by name ('West Village'), with their row counts."""
        out: dict[str, int] = {}
        for value, n in self.hoods().items():
            out[hood_label(value)] = out.get(hood_label(value), 0) + n
        return dict(sorted(out.items()))

    def summary(self, c: Choice) -> dict | None:
        """The choice's rows in brief: their count, median ask and median of the model's
        medians, and for the past ads among them the share of asks inside the model's 80%
        and 95% intervals. None when nothing matches."""
        sql, params = where(c)
        past = "source = 'latest'"
        n, ask, model, past_n, in80, in95 = self._one(
            "SELECT COUNT(*), median(ask), median(model_median), "
            f"COUNT(*) FILTER ({past}), "
            f"AVG(CASE WHEN ask BETWEEN model_lo80 AND model_hi80 THEN 1.0 ELSE 0.0 END) "
            f"FILTER ({past}), "
            f"AVG(CASE WHEN ask BETWEEN model_lo95 AND model_hi95 THEN 1.0 ELSE 0.0 END) "
            f"FILTER ({past}) FROM estimates{sql}",
            params,
        )
        if not n:
            return None
        return {
            "n": n,
            "median_ask": ask,
            "median_model": model,
            "past": past_n,
            "inside_80": in80,
            "inside_95": in95,
        }


_open: dict[tuple, Table] = {}
_open_lock = threading.Lock()
_refused: set[tuple] = set()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(root: Path) -> Table | None:
    """The published table, or None when none has been published. Raises `Refused`
    when the table is not the one its meta names. A table is hashed once per file
    version (its path, size and change time), and a newer publish replaces the old
    connection."""
    folder = Path(root) / FOLDER
    path, meta_path = folder / TABLE, folder / META
    try:
        stat, meta_stat = path.stat(), meta_path.stat()
    except OSError:
        return None
    stamp = (
        str(path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        meta_stat.st_mtime_ns,
        meta_stat.st_size,
    )
    with _open_lock:
        found = _open.get(stamp)
        if found is not None:
            return found
        refused = Refused(
            "The published estimates do not match their record, so they are not "
            "shown until the next publish."
        )
        if stamp in _refused:
            raise refused
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(meta, dict):
            return None
        if meta.get("estimates_sha256") != _sha256(path):
            # A table is hashed once per version, refused or not.
            _refused.clear()
            _refused.add(stamp)
            raise refused
        _open.clear()
        found = _open[stamp] = Table(path, meta)
        return found


def held_out(meta: dict) -> dict | None:
    """The latest fit's held-out accuracy in the page's terms: the median error as a
    percent of the ask, and each interval's coverage beside its nominal share."""
    h = meta.get("heldout")
    if not isinstance(h, dict):
        return None
    mae = _finite(h.get("median_abs_error"))
    coverage = h.get("coverage") or {}
    return {
        "rows": h.get("rows"),
        "elpd": _finite(h.get("elpd")),
        # The error is on the log scale: exp(x) - 1 is the typical miss as a share.
        "median_error_pct": None if mae is None else 100 * (math.exp(mae) - 1),
        "coverage": [
            {"nominal": int(k), "share": 100 * float(coverage[k])}
            for k in ("50", "80", "90", "95")
            if _finite(coverage.get(k)) is not None
        ],
    }
