"""The Today section's table: what the served drift model expects each apartment to ask today.

`python -m rentfrontier.drift_today publish` writes the site's `today/` folder: `today.parquet`,
one row per apartment the market fit knows, with the predictive median and 50%, 80% and 95%
intervals of an ad for it on the publish's day, and then `meta.json` (the model, the run and
its gate, the day, where the fit's market trend ends, the check against the fit's own
predictions, and the table's sha256), written last. An apartment's row takes the columns of
its newest ad, so the price is for that apartment as it was last advertised.

The pages read this folder and nothing else. A table whose sha256 is not the one its meta
names is refused (`Refused`), as `estimates.py` refuses one. Queries go through DuckDB over
the parquet with one connection per process and published file, one thread and a small
memory limit.

Finding an apartment. The search box takes an address, a building id, a StreetEasy link (a
rental's `/rental/<id>` or a building's `/building/<slug>/<unit>`) or a listing id, and the
unit box narrows it to a unit. A listing id finds the apartment whose newest ad it is.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

import duckdb

from .deals import LISTING, hood_label
from .estimates import BEDROOMS, _finite, _number, _page, _text, areas

FOLDER = "today"
TABLE = "today.parquet"
META = "meta.json"
PER_PAGE = 50
# Each order of the list: its SQL and its words. `apartment` breaks ties.
SORTS = {
    "address": ("address ASC NULLS LAST, NULLIF(unit, '') ASC NULLS LAST", "Address"),
    "recent": ("last_day DESC", "Newest last ad"),
    "low": ("median ASC", "Lowest price today"),
    "high": ("median DESC", "Highest price today"),
}
WHICH = {
    "all": "All apartments",
    "market": "On the market now",
    "known": "With an ad the model learned from",
}


class Refused(Exception):
    """The folder holds a table that is not the one its meta describes."""


@dataclasses.dataclass
class Choice:
    """The search from a query string. Anything unreadable is left out."""

    q: str = ""
    unit: str = ""
    nb: str | None = None
    beds: list[str] = dataclasses.field(default_factory=list)
    min_price: float | None = None
    max_price: float | None = None
    which: str = "all"
    sort: str = "address"
    page: int = 1
    hoods: list[str] | None = None

    def args(self, **changes) -> dict:
        items = {
            "q": self.q or None,
            "unit": self.unit or None,
            "nb": self.nb,
            "beds": self.beds or None,
            "min": None if self.min_price is None else f"{self.min_price:g}",
            "max": None if self.max_price is None else f"{self.max_price:g}",
            "which": None if self.which == "all" else self.which,
            "sort": None if self.sort == "address" else self.sort,
            "page": None if self.page == 1 else self.page,
        }
        items.update(changes)
        return {k: v for k, v in items.items() if v not in (None, [], "")}

    def active(self) -> bool:
        return bool(
            self.q
            or self.unit
            or self.nb
            or self.beds
            or self.min_price is not None
            or self.max_price is not None
            or self.which != "all"
        )


def choice(args, hoods: dict[str, int]) -> Choice:
    """The search of a query string, against the table's neighbourhoods."""
    out = Choice(
        q=(args.get("q") or "").strip()[:200],
        unit=(args.get("unit") or "").strip()[:20],
        nb=(args.get("nb") or "").strip()[:60] or None,
        beds=[b for b in dict.fromkeys(args.getlist("beds")) if b in BEDROOMS],
        min_price=_number(args.get("min")),
        max_price=_number(args.get("max")),
        which=args.get("which") if args.get("which") in WHICH else "all",
        sort=args.get("sort") if args.get("sort") in SORTS else "address",
        page=_page(args.get("page")),
    )
    out.hoods = areas(out.nb, hoods)
    if out.hoods is None:
        out.nb = None
    return out


def parse_query(q: str) -> dict:
    """What a search box's text names: a `listing` id, a building `slug` with an optional
    `unit` from a StreetEasy link, or free `text`."""
    q = q.strip()
    if re.fullmatch(r"\d{4,12}", q):
        return {"listing": q}
    if "streeteasy.com" in q.lower() or q.startswith("/"):
        path = urlparse(q if "//" in q else "https://" + q.lstrip("/")).path
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "rental" and re.fullmatch(r"\d+", parts[1]):
            return {"listing": parts[1]}
        if len(parts) >= 2 and parts[0] == "building":
            return {
                "slug": parts[1].lower(),
                "unit": parts[2] if len(parts) > 2 else "",
            }
    return {"text": q}


def _like(text: str) -> str:
    text = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + text + "%"


def unit_key(unit: str) -> str:
    """A unit label as the search compares it: lower case, letters and digits only, so that
    '6-B', '#6b' and '6B' match."""
    return re.sub(r"[^0-9a-z]", "", unit.lower())


# The table's `unit` is the label from the ad's page ("6B"); its unit_id is the pipeline's id.
UNIT_SQL = "regexp_replace(lower(unit), '[^0-9a-z]', '', 'g')"


def where(c: Choice) -> tuple[str, list]:
    """The SQL filter of a search and its parameters."""
    clauses, params = [], []
    named = parse_query(c.q) if c.q else {}
    unit = c.unit or named.get("unit", "")
    if "listing" in named:
        clauses.append("listing_id = ?")
        params.append(named["listing"])
    elif "slug" in named:
        clauses.append("lower(building) = ?")
        params.append(named["slug"])
    elif "text" in named:
        like = _like(named["text"])
        clauses.append(
            "(lower(address) LIKE ? ESCAPE '\\' OR lower(building) LIKE ? ESCAPE '\\')"
        )
        # Building ids spell an address with dashes: "134-west-23-street-new_york".
        params += [like, like.replace(" ", "-")]
    if unit and unit_key(unit):
        clauses.append(f"{UNIT_SQL} = ?")
        params.append(unit_key(unit))
    if c.hoods:
        clauses.append("neighbourhood IN (" + ", ".join("?" * len(c.hoods)) + ")")
        params += c.hoods
    if c.beds:
        parts = []
        for b in c.beds:
            if b == "4":
                parts.append("bedrooms >= 4")
            else:
                parts.append("bedrooms = ?")
                params.append(float(b))
        clauses.append("(" + " OR ".join(parts) + ")")
    if c.min_price is not None:
        clauses.append("median >= ?")
        params.append(c.min_price)
    if c.max_price is not None:
        clauses.append("median <= ?")
        params.append(c.max_price)
    if c.which == "market":
        clauses.append("on_market")
    elif c.which == "known":
        clauses.append("unit_ads > 0")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def shown(row: dict) -> dict:
    """A table row with the page's words and links."""
    listing = str(row.get("listing_id") or "")
    full, half = _finite(row.get("full_baths")), _finite(row.get("half_baths"))
    unit = _text(row.get("unit"))
    last, median = _finite(row.get("last_ask")), _finite(row.get("median"))
    return row | {
        "address": _text(row.get("address")),
        "neighbourhood": _text(row.get("neighbourhood")),
        "hood_label": hood_label(_text(row.get("neighbourhood"))),
        "unit_label": unit.upper() if unit else None,
        "bedrooms": _finite(row.get("bedrooms")),
        "baths": None if full is None else full + 0.5 * (half or 0),
        "unit_ads": int(_finite(row.get("unit_ads")) or 0),
        "url": LISTING + listing if re.fullmatch(r"\d+", listing) else None,
        "change_pct": None
        if not last or median is None
        else 100.0 * (median / last - 1.0),
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
            f"CREATE VIEW today AS SELECT * FROM read_parquet('{quoted}')"
        )
        self._hoods = None

    def _rows(self, sql: str, params: list) -> list[dict]:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            names = [d[0] for d in cursor.description]
            return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]

    def _one(self, sql: str, params: list):
        with self._lock:
            return self._connection.execute(sql, params).fetchone()

    def page(self, c: Choice) -> tuple[list[dict], int, int]:
        """The search's page of rows, its count and its number of pages. A page past the
        last is read as the last."""
        sql, params = where(c)
        total = self._one(f"SELECT COUNT(*) FROM today{sql}", params)[0]
        pages = max(1, math.ceil(total / PER_PAGE))
        c.page = min(c.page, pages)
        rows = self._rows(
            f"SELECT * FROM today{sql} ORDER BY {SORTS[c.sort][0]}, apartment "
            "LIMIT ? OFFSET ?",
            [*params, PER_PAGE, (c.page - 1) * PER_PAGE],
        )
        return [shown(r) for r in rows], total, pages

    def row(self, listing_id: str) -> dict | None:
        """The apartment whose newest ad is `listing_id`."""
        rows = self._rows(
            "SELECT * FROM today WHERE listing_id = ? LIMIT 1", [listing_id]
        )
        return shown(rows[0]) if rows else None

    def building(self, building: str, but: str | None = None) -> list[dict]:
        """The building's other apartments, by unit."""
        return [
            shown(r)
            for r in self._rows(
                "SELECT * FROM today WHERE building = ? AND listing_id <> ? "
                "ORDER BY NULLIF(unit, '') NULLS LAST, apartment LIMIT 200",
                [building, but or ""],
            )
        ]

    def hoods(self) -> dict[str, int]:
        """The table's neighbourhood values and their row counts."""
        if self._hoods is None:
            with self._lock:
                self._hoods = dict(
                    self._connection.execute(
                        "SELECT neighbourhood, COUNT(*) FROM today "
                        "WHERE neighbourhood IS NOT NULL AND neighbourhood <> '' "
                        "GROUP BY neighbourhood ORDER BY neighbourhood"
                    ).fetchall()
                )
        return self._hoods

    def hood_names(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for value, n in self.hoods().items():
            out[hood_label(value)] = out.get(hood_label(value), 0) + n
        return dict(sorted(out.items()))


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
    """The published table, or None when none has been published. Raises `Refused` when
    the table is not the one its meta names. A table is hashed once per file version."""
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
            "The published prices for today do not match their record, so they are not "
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
        if meta.get("today_sha256") != _sha256(path):
            _refused.clear()
            _refused.add(stamp)
            raise refused
        _open.clear()
        found = _open[stamp] = Table(path, meta)
        return found


def horizon(meta: dict) -> dict:
    """How far the day lies past the fit's market trend, in the page's words: the trend's
    last day, the days past it, and the sd it adds to the log rent."""
    weeks = _finite(meta.get("weeks_past_grid")) or 0.0
    walk = meta.get("walk") or {}
    added = _finite(walk.get("added_sd")) or 0.0
    return {
        "grid_end": meta.get("grid_end"),
        "last_ad_day": meta.get("last_ad_day"),
        "days_past": round(7 * weeks),
        "added_pct": 100 * (math.exp(added) - 1) if added else 0.0,
        "drift_pct_month": 100
        * (math.exp(4.348 * (_finite(walk.get("drift_per_week")) or 0.0)) - 1),
    }


def checked(meta: dict) -> dict | None:
    """The check of the method against the fit's own predictions, in the page's words."""
    c = meta.get("check")
    if not isinstance(c, dict):
        return None
    gap = (c.get("median_gap") or {}).get("median_abs")
    cover = c.get("coverage") or {}
    return {
        "rows": c.get("rows"),
        "elpd_today": (c.get("elpd") or {}).get("today"),
        "elpd_fit": (c.get("elpd") or {}).get("fit"),
        "median_gap_pct": None if gap is None else 100 * (math.exp(gap) - 1),
        "width_ratio": c.get("width80_ratio"),
        "cover80_today": 100 * ((cover.get("today") or {}).get("80") or 0),
        "cover80_fit": 100 * ((cover.get("fit") or {}).get("80") or 0),
    }
