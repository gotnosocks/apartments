"""The listings site: a read-only Flask app over the published files.

Each request opens <root>/current/site.sqlite read-only (immutable), so a new
publish (`apartments.site.build`) is picked up by the next request. The Estimates
pages (/estimates, /listings and each estimate's page) read instead the served
drift model's held-out estimates in <root>/estimates/ (`estimates.py`), and the
Deals page <root>/deals/ (`deals.py`). Filters are parsed leniently: an invalid
value is ignored, never an error page.
"""

from __future__ import annotations

import csv
import datetime as dt
import functools
import gzip
import hashlib
import io
import itertools
import json
import logging
import math
import os
import re
import sqlite3
import statistics
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from markupsafe import Markup

from . import (
    best,
    boroughs,
    charts,
    deals,
    detail,
    exposure,
    observed,
    reads,
    story,
    streetview,
    summary,
)
from . import estimates as estimates_table
from .anatomy import LEVELS as ANATOMY_LEVELS
from .anatomy import describe, differences
from .research import (
    BOARD_ORDERS,
    BOARD_SORTS,
    ELEGANCE_CELLS,
    LINES,
    SUBSET_MINUTES,
    TARGET_HARDWARE,
    TARGET_MINUTES,
    TIERS,
    Plan,
    Research,
    best_over_time,
    board_rows,
    compute_by_line,
    default_hardware,
    descriptive_share,
    designs,
    elegance_pairs,
    elegance_standings,
    elegance_summary,
    entry_by_key,
    entry_for_run,
    frontier_view,
    full_fits_of,
    hardware_classes,
    implementations,
    judgements,
    latest_milestones,
    outlier_floor,
    run_of,
    serve_status,
    snapshot_days,
    spearman,
    subset_fit,
    tier_of,
    validation_pairs,
    verdicts,
)
from .selection import SELECTION, selection_note

log = logging.getLogger("apartments.site")
NEW_YORK = ZoneInfo("America/New_York")

PER_PAGE = (25, 50, 100)
OBSERVED_CSV_COLUMNS = (
    "listing_id",
    "neighbourhood",
    "building",
    "unit_label",
    "period",
    "is_current",
    "ask",
    "bedrooms",
    "bathrooms",
    "square_feet",
    "floor",
    "elevator",
    "laundry",
    "doorman",
    "pets",
    "concession",
    "listing_url",
)
BEDROOMS = {"0": "Studio", "1": "1 BR", "2": "2 BR", "3": "3 BR", "4": "4+ BR"}
STATUS = {"all": "All listings", "current": "Available now", "past": "Past listings"}
BEST_SHOWN = 100  # rows on /best; the CSV has them all
BANDS = {
    "all": "Any price",
    "below": "Below typical",
    "typical": "Typical",
    "above": "Above typical",
}
# The divergence review's actions (config/reviews/), as a renter would put them.
QUARANTINE_ACTIONS = {
    "quarantine_nonresidential": "Not a home",
    "quarantine_location_conflict": "Placed elsewhere",
    "quarantine_product_scope": "Not a whole apartment on the open market",
    "quarantine_explicit_short_term_offer": "Short stay only",
    "quarantine_price_basis": "Ask is not the rent",
    "quarantine_attribute_conflict": "Bedrooms contradict the ad",
}
SORTS = {
    "date": ("l.period", "Date"),
    "ask": ("l.ask", "Ask"),
    "estimate": ("l.estimate", "Estimate"),
    "diff": ("l.residual_usd", "Ask − estimate ($)"),
    "diff_pct": ("l.residual_pct", "Ask − estimate (%)"),
}
BUILDING_SORTS = {
    "name": ("b.sort_key", "Name"),
    "listings": ("b.listings", "Listings"),
    "level": ("b.level_pct", "Building level"),
    "diff_pct": ("b.median_residual_pct", "Median ask vs estimate"),
    "recent": ("b.last_period", "Most recent listing"),
}
LABELS = {
    "doorman": {
        "full_time": "Full-time doorman",
        "part_time": "Part-time doorman",
        "virtual": "Virtual doorman",
        "unspecified": "Doorman (kind not stated)",
        "none": "No doorman",
    },
    "laundry": {
        "in_unit": "In-unit laundry",
        "in_building": "Laundry in building",
        "none": "No laundry",
    },
    "hvac": {"central_ac": "Central air"},
    "pets": {
        "allowed": "Pets allowed",
        "not_allowed": "No pets",
        "approval_required": "Pets on approval",
        "allowed_restrictions_unknown": "Pets allowed (restrictions unknown)",
    },
}
DEFAULT_HOSTS = ("localhost", "127.0.0.1", "[::1]")


class Filters:
    """Listing filters from the query string; invalid values are dropped."""

    def __init__(self, args):
        self.q = (args.get("q") or "").strip()[:80]
        # Checked against the build's neighbourhoods by the route.
        self.nb = (args.get("nb") or "").strip()[:60] or None
        self.beds = [b for b in args.getlist("beds") if b in BEDROOMS]
        self.min_ask = _number(args.get("min_ask"))
        self.max_ask = _number(args.get("max_ask"))
        self.min_baths = args.get("baths") if args.get("baths") in BATHS else None
        self.min_sqft = _number(args.get("min_sqft"))
        self.max_sqft = _number(args.get("max_sqft"))
        self.elevator = (
            args.get("elevator") if args.get("elevator") in ELEVATOR else None
        )
        self.laundry = args.get("laundry") if args.get("laundry") in LAUNDRY else None
        self.doorman = args.get("doorman") if args.get("doorman") in DOORMAN else None
        self.outdoor = args.get("outdoor") == "yes"
        # Cleared by the route when the build has no exposure labels.
        self.faces = args.get("faces") if args.get("faces") in FACES else None
        self.year_from = _year(args.get("from"))
        self.year_to = _year(args.get("to"))
        self.status = args.get("status") if args.get("status") in STATUS else "all"
        self.band = args.get("price") if args.get("price") in BANDS else "all"
        self.sort = args.get("sort") if args.get("sort") in SORTS else "date"
        default_order = "desc" if self.sort == "date" else "asc"
        order = args.get("order")
        self.order = order if order in ("asc", "desc") else default_order
        self.per = _int(args.get("per"), 50)
        if self.per not in PER_PAGE:
            self.per = 50
        self.page = max(1, _int(args.get("page"), 1))
        self.building = None
        # The neighbourhoods `nb` stands for, set by the route.
        self.areas = None

    def where(self):
        clauses, params = [], []
        if self.building:
            clauses.append("l.building_id = ?")
            params.append(self.building)
        if self.areas:
            clauses.append(
                "l.neighbourhood IN (" + ", ".join("?" * len(self.areas)) + ")"
            )
            params += self.areas
        if self.q:
            clauses.append(
                "(b.search LIKE ? ESCAPE '\\' OR l.unit_label LIKE ? ESCAPE '\\')"
            )
            like = "%" + _escape_like(self.q.lower()) + "%"
            params += [like, _escape_like(self.q.upper())]
        if self.beds:
            parts = []
            for b in self.beds:
                if b == "4":
                    parts.append("l.bedrooms >= 4")
                else:
                    parts.append("l.bedrooms = ?")
                    params.append(float(b))
            clauses.append("(" + " OR ".join(parts) + ")")
        if self.min_ask is not None:
            clauses.append("l.ask >= ?")
            params.append(self.min_ask)
        if self.max_ask is not None:
            clauses.append("l.ask <= ?")
            params.append(self.max_ask)
        if self.min_baths is not None:
            clauses.append("l.bathrooms >= ?")
            params.append(float(self.min_baths))
        if self.min_sqft is not None:
            clauses.append("l.square_feet >= ?")
            params.append(self.min_sqft)
        if self.max_sqft is not None:
            clauses.append("l.square_feet <= ?")
            params.append(self.max_sqft)
        if self.elevator == "yes_or_unstated":
            clauses.append("(l.elevator IS NULL OR l.elevator <> 'no')")
        elif self.elevator is not None:
            clauses.append("l.elevator = ?")
            params.append(self.elevator)
        for column, value, options in (
            ("laundry", self.laundry, LAUNDRY),
            ("doorman", self.doorman, DOORMAN),
        ):
            if value is not None:
                values = options[value][1]
                clauses.append(f"l.{column} IN ({', '.join('?' * len(values))})")
                params += values
        if self.outdoor:
            # The model's own reading of the ad: an "outdoor:<kind>" input.
            clauses.append("l.inputs LIKE '%\"outdoor:%'")
        if self.faces is not None:
            values = FACES[self.faces][1]
            clauses.append(
                "l.unit_id IN (SELECT unit_id FROM exposure WHERE exposure IN "
                f"({', '.join('?' * len(values))}))"
            )
            params += values
        if self.year_from is not None:
            clauses.append("l.period >= ?")
            params.append(f"{self.year_from}-01-01")
        if self.year_to is not None:
            clauses.append("l.period <= ?")
            params.append(f"{self.year_to}-12-31")
        if self.status == "current":
            clauses.append("l.is_current = 1")
        elif self.status == "past":
            clauses.append("l.is_current = 0")
        if self.band != "all":
            clauses.append("l.price_band = ?")
            params.append(self.band)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def order_by(self):
        column = SORTS[self.sort][0]
        direction = "DESC" if self.order == "desc" else "ASC"
        return f" ORDER BY {column} {direction}, l.id {direction}"

    def args(self, **changes):
        """Query-string items for a link with some filters changed."""
        items = {
            "q": self.q or None,
            "nb": self.nb,
            "beds": self.beds or None,
            "min_ask": _fmt_number(self.min_ask),
            "max_ask": _fmt_number(self.max_ask),
            "baths": self.min_baths,
            "min_sqft": _fmt_number(self.min_sqft),
            "max_sqft": _fmt_number(self.max_sqft),
            "elevator": self.elevator,
            "laundry": self.laundry,
            "doorman": self.doorman,
            "outdoor": "yes" if self.outdoor else None,
            "faces": self.faces,
            "from": self.year_from,
            "to": self.year_to,
            "status": None if self.status == "all" else self.status,
            "price": None if self.band == "all" else self.band,
            "sort": None if self.sort == "date" else self.sort,
            "order": self.order if self.order != _default_order(self.sort) else None,
            "per": None if self.per == 50 else self.per,
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
            or self.min_baths is not None
            or self.min_sqft is not None
            or self.max_sqft is not None
            or self.elevator is not None
            or self.laundry is not None
            or self.doorman is not None
            or self.outdoor
            or self.year_from
            or self.year_to
            or self.status != "all"
            or self.band != "all"
        )


# Feature filters: the option's label and, for laundry and doorman, the
# column values it keeps. A listing that doesn't state the feature is left
# out, except by "Yes or not stated" (playtest round 6: walk-ups in the West
# Village often don't say).
ELEVATOR = {
    "yes": "Yes",
    "yes_or_unstated": "Yes or not stated",
    "no": "No (walk-up)",
}
LAUNDRY = {
    "in_unit": ("In the unit", ("in_unit",)),
    "any": ("In the unit or building", ("in_unit", "in_building")),
}
DOORMAN = {
    "full_time": ("Full-time", ("full_time",)),
    "any": ("Any kind", ("full_time", "part_time", "virtual", "unspecified")),
}
# Which way the apartment faces (`exposure`), its own or its line's label.
FACES = {
    "rear": ("The rear or a courtyard", ("rear",)),
    "rear_or_both": ("The rear, or both sides", ("rear", "both")),
    "street": ("The street", ("street",)),
}

# Minimum bathrooms the listings filter offers.
BATHS = ("1", "1.5", "2", "3")
LISTING_JOIN = " JOIN buildings b ON b.id = l.building_id"


# Count words for "all eight neighbourhoods".
COUNT_WORDS = (
    None,
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)


def count_query(filters: Filters):
    where, params = filters.where()
    join = LISTING_JOIN if "b." in where else ""
    return f"SELECT COUNT(*) FROM listings l{join}{where}", params


def page_query(filters: Filters):
    """One page of listings: the page's ids first (the sort holds only keys
    and walks an index), then their full rows."""
    where, params = filters.where()
    join = LISTING_JOIN if "b." in where else ""
    ids = (
        f"SELECT l.id FROM listings l{join}{where}{filters.order_by()} LIMIT ? OFFSET ?"
    )
    sql = (
        "SELECT l.*, b.name AS building_name, b.address AS building_address "
        f"FROM ({ids}) page JOIN listings l ON l.id = page.id{LISTING_JOIN}"
        f"{filters.order_by()}"
    )
    return sql, [*params, filters.per, (filters.page - 1) * filters.per]


def _default_order(sort):
    return "desc" if sort == "date" else "asc"


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ObservedFilters:
    """Filters of the observed listings (`/new-jersey`); invalid values are dropped."""

    SORTS = {"date": "period", "ask": "ask"}

    def __init__(self, args, areas):
        nb = (args.get("nb") or "").strip()
        self.nb = nb if nb in areas else None
        self.beds = [b for b in args.getlist("beds") if b in BEDROOMS]
        self.min_ask = _number(args.get("min_ask"))
        self.max_ask = _number(args.get("max_ask"))
        self.status = args.get("status") if args.get("status") in STATUS else "all"
        self.sort = args.get("sort") if args.get("sort") in self.SORTS else "date"
        default_order = "desc" if self.sort == "date" else "asc"
        order = args.get("order")
        self.order = order if order in ("asc", "desc") else default_order
        self.per = 50
        self.page = max(1, _int(args.get("page"), 1))

    def where(self):
        clauses, params = [], []
        if self.nb:
            clauses.append("neighbourhood = ?")
            params.append(self.nb)
        if self.beds:
            parts = []
            for b in self.beds:
                if b == "4":
                    parts.append("bedrooms >= 4")
                else:
                    parts.append("bedrooms = ?")
                    params.append(float(b))
            clauses.append("(" + " OR ".join(parts) + ")")
        if self.min_ask is not None:
            clauses.append("ask >= ?")
            params.append(self.min_ask)
        if self.max_ask is not None:
            clauses.append("ask <= ?")
            params.append(self.max_ask)
        if self.status == "current":
            clauses.append("is_current = 1")
        elif self.status == "past":
            clauses.append("is_current = 0")
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def order_by(self):
        key, order = self.SORTS[self.sort], self.order.upper()
        return f" ORDER BY {key} {order}, listing_id {order}"

    def args(self, **changes):
        values = {
            "nb": self.nb,
            "beds": self.beds,
            "min_ask": None if self.min_ask is None else f"{self.min_ask:g}",
            "max_ask": None if self.max_ask is None else f"{self.max_ask:g}",
            "status": None if self.status == "all" else self.status,
            "sort": None if self.sort == "date" else self.sort,
            "order": None
            if self.order == ("desc" if self.sort == "date" else "asc")
            else self.order,
            "page": None if self.page == 1 else self.page,
        }
        values.update(changes)
        return {k: v for k, v in values.items() if v not in (None, [], "")}


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value):
    try:
        number = float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _fmt_number(value):
    return None if value is None else f"{value:g}"


def _year(value):
    year = _int(value, None)
    return year if year is not None and 1990 <= year <= 2100 else None


def _query(args: dict) -> str:
    return urlencode(args, doseq=True)


ZOOM_KEYS = ("x0", "x1", "y0", "y1")
# "fp" and "ep" zoom the charts of fits scored on the earlier data.
ZOOM_ANCHORS = {
    "f": "full-fits",
    "e": "exploration-fits",
    "fp": "f-earlier",
    "ep": "e-earlier",
}


def best_so_far(points, eligible) -> set[int]:
    """Indexes of the points no eligible point beats: none at least as fast
    and at least as accurate, and better on one. Only for display (the
    earlier-data charts); the board computes the real frontiers."""
    pool = [(i, p) for i, p in enumerate(points) if eligible(p)]
    return {
        i
        for i, p in pool
        if not any(
            q["x"] <= p["x"]
            and q["y"] >= p["y"]
            and (q["x"], q["y"]) != (p["x"], p["y"])
            for _, q in pool
        )
    }


def zoom_box(args, prefix: str):
    """A chart's zoomed (x, y) ranges from its query parameters (prefix + x0,
    x1, y0, y1); a range missing either end, empty, reversed, not finite,
    beyond 1e9 or narrower than a millionth of its values is left unzoomed."""
    values = []
    for k in ZOOM_KEYS:
        try:
            v = float(args.get(prefix + k, ""))
        except ValueError:
            v = None
        values.append(v if v is not None and math.isfinite(v) else None)
    ranges = []
    for lo, hi in (values[:2], values[2:]):
        # Bounded and not vanishingly narrow, so the ticks can be laid out.
        ok = (
            lo is not None
            and hi is not None
            and max(abs(lo), abs(hi)) <= 1e9
            and hi - lo > 1e-6 * max(abs(lo), abs(hi), 1.0)
        )
        ranges.append((lo, hi) if ok else None)
    return tuple(ranges)


def zoom_url(args, prefix: str, box) -> str:
    """This page with a chart zoomed to box ((x0, x1), (y0, y1)), or unzoomed
    for None; the other parameters, the other chart's zoom too, are kept."""
    kept = [
        (k, v)
        for k, v in args.items(multi=True)
        if k not in {prefix + z for z in ZOOM_KEYS}
    ]
    if box:
        (x0, x1), (y0, y1) = box
        kept += [(prefix + k, f"{v:.6g}") for k, v in zip(ZOOM_KEYS, (x0, x1, y0, y1))]
    return ("?" + urlencode(kept) if kept else "?") + "#" + ZOOM_ANCHORS[prefix]


def frontier_box(points):
    """The box around a chart's frontier and served fits, with a margin, for
    its "zoom to the frontier" link; None when it has none to show."""
    near = [p for p in points if p["kind"] in ("frontier", "served")]
    if not near:
        return None
    xs, ys = [p["x"] for p in near], [p["y"] for p in near]
    xpad = (max(xs) - min(xs)) * 0.15 or max(xs) * 0.15 or 1.0
    ypad = (max(ys) - min(ys)) * 0.15 or abs(max(ys)) * 0.02 or 1.0
    return (max(0.0, min(xs) - xpad), max(xs) + xpad), (min(ys) - ypad, max(ys) + ypad)


def _asset_versions(static: Path) -> dict:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:10]
        for p in static.iterdir()
        if p.is_file()
    }


# The site's two sections and the endpoints in each (navigation and titles).
SECTIONS = {
    "estimates": (
        "estimates",
        "listings",
        "listing",
        "unit",
        "buildings",
        "building",
        "quarantined",
        "observed_listings",
        "best_listings",
        "deals_page",
        "about",
        "estimates_map",
        "estimate_apartment",
        "estimates_map_data",
    ),
    "research": (
        "research_frontier",
        "research_board",
        "research_fit",
        "research_history",
        "research_validation",
        "research_data_quality",
        "research_plan_page",
        "research_glossary",
        "research_model",
        "research_elegance",
        "research_story",
    ),
}


def list_ranges() -> bool:
    """Whether the listing tables of building pages carry each listing's range.
    They do with SITE_LIST_RANGES=1."""
    return os.environ.get("SITE_LIST_RANGES") == "1"


def section_of(endpoint: str | None) -> str | None:
    return next((k for k, v in SECTIONS.items() if endpoint in v), None)


def create_app(
    root: Path | str | None = None,
    *,
    allowed_hosts=None,
    research_data=None,
    research_plan=None,
    feature_tests=None,
    cleaning_steps=None,
    group_items=None,
) -> Flask:
    root = Path(root or os.environ.get("SITE_ROOT", "/data1/apartments/site"))
    research = Research(research_data)
    plan = Plan(research_plan)
    ledger = story.Ledger(feature_tests)
    cleaning_file = story.Cleaning(cleaning_steps)
    group_file = story.GroupItems(group_items)
    app = Flask(__name__)
    if allowed_hosts is None:
        allowed_hosts = os.environ.get("SITE_ALLOWED_HOSTS", "").split(",")
    hosts = [h.strip().lower() for h in allowed_hosts if h.strip()]
    if any(h.startswith(".") or "*" in h for h in hosts):
        raise ValueError("Site allowed hosts must be exact hostnames")
    app.config["TRUSTED_HOSTS"] = [*DEFAULT_HOSTS, *hosts]
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 365 * 24 * 3600
    versions = _asset_versions(Path(app.static_folder))
    best_cache: dict = {}
    read_log = reads.ReadLog.from_env(root, os.environ.get("SITE_READS_LOG"))

    def street_view(building_id, latitude=None, longitude=None, address=None):
        """A Street View link from the building's street, facing it."""
        path = database_path().parent / "map.json"
        try:
            data = _rent_map(str(path), path.stat().st_mtime)
        except (OSError, ValueError):
            data = None
        return streetview.link(data, building_id, latitude, longitude, address)

    app.jinja_env.globals["street_view"] = street_view
    app.jinja_env.globals["list_ranges"] = list_ranges

    def building_typical(building_id: str) -> dict | None:
        """The building's typical rent by bedroom count in the rent map's
        latest year: {year, months, extrapolated, rows: [{label, rent, low,
        high}]}; None without a map or when the map lacks the building."""
        path = database_path().parent / "map.json"
        try:
            data = _rent_map(str(path), path.stat().st_mtime)
            index = data["_index"].get(building_id)
            if index is None:
                return None
            b = data["buildings"][index]
            yi = len(data["years"]) - 1
            year = data["years"][yi]
            rows = []
            for bed in data["bedrooms"]:
                low, mid, high = data["rent"][bed["key"]][index][yi]
                rows.append(
                    {"label": bed["label"], "rent": mid, "low": low, "high": high}
                )
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return None  # no map, or one this code does not understand
        return {
            "fit_listings": b.get("fit_listings"),
            "year": year,
            "months": data["year_months"][yi],
            "extrapolated": not (b["first_year"] <= year <= b["last_year"]),
            "last_year": b["last_year"],
            "interval": data.get("interval", "90%"),
            "rows": rows,
        }

    def database_path() -> Path:
        return (root / "current" / "site.sqlite").resolve()

    def db() -> sqlite3.Connection:
        if "db" not in g:
            path = database_path()
            if not path.is_file():
                abort(503, description="No published build yet.")
            g.db = sqlite3.connect(
                f"file:{quote(str(path))}?mode=ro&immutable=1", uri=True
            )
            g.db.row_factory = read_log.row
            if g.get("reads") is not None:
                read_log.watch(g.db, g.queried)
            g.build = path.parent.name
            g.build_dir = path.parent
        return g.db

    def parts_of(row) -> list[dict]:
        """The listing's dollar parts: from its row, or from the build's
        detail file when the build left them out of the table (detail.py)."""
        if row["contributions"] is not None:
            return json.loads(row["contributions"])
        meta()  # opens the request's build, as the row's query did
        found = detail.lookup(g.build_dir, g.meta["summary_sha256"], row["audit_id"])
        if found is None:
            raise LookupError(f"{row['audit_id']} has no parts in the build")
        return found

    def likely_of(row) -> dict | None:
        """The listing's likely ask ranges: from its row, or worked out from
        the build's range atoms when the bundle has those in their place
        (detail.py); None when neither has them, or when the atoms or noise
        tables can't be read, so the page leaves the range out."""
        if row["pred_lower_80"] is not None:
            return {
                k: row[k]
                for k in (
                    "pred_lower_80",
                    "pred_upper_80",
                    "pred_lower_95",
                    "pred_upper_95",
                )
            }
        meta()
        try:
            return detail.likely_ask(
                g.build_dir, g.meta["summary_sha256"], row["audit_id"]
            )
        except Exception:
            log.exception("no likely ask range for %s", row["audit_id"])
            return None

    def meta() -> dict:
        if "meta" not in g:
            g.meta = {
                row["key"]: json.loads(row["value"])
                for row in db().execute(
                    "SELECT key, value FROM meta "
                    "WHERE key NOT IN ('story_checks', 'story_scans')"
                )
            }
        return g.meta

    @app.teardown_appcontext
    def close_db(error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.before_request
    def start_timer():
        g.started = time.perf_counter()
        g.queried = set()
        g.reads = read_log.start()

    @app.after_request
    def finish(response):
        read_log.finish(
            g.pop("reads", None),
            endpoint=request.endpoint,
            remote=request.remote_addr,
            status=response.status_code,
            queried=g.get("queried", set()),
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )
        if request.endpoint != "static" and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"
        if (
            response.status_code == 200
            and not response.direct_passthrough
            and not response.is_streamed
            and request.endpoint != "static"
        ):
            response.add_etag()
            response.make_conditional(request)
            _compress(response)
        elapsed = (time.perf_counter() - g.get("started", time.perf_counter())) * 1e3
        log.info(
            "%s %s %s %d %.1fms",
            request.remote_addr,
            request.method,
            request.full_path.rstrip("?"),
            response.status_code,
            elapsed,
        )
        return response

    def _compress(response):
        if (
            "gzip" not in request.headers.get("Accept-Encoding", "")
            or response.status_code != 200
            or not (response.mimetype or "").startswith(("text/", "application/json"))
        ):
            return
        body = response.get_data()
        if len(body) < 1024:
            return
        response.set_data(gzip.compress(body, compresslevel=5))
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Vary"] = "Accept-Encoding"

    @app.errorhandler(400)
    @app.errorhandler(410)
    @app.errorhandler(404)
    @app.errorhandler(503)
    def http_error(error):
        if request.url_rule is None and error.code == 400:
            # Refused before routing (an untrusted Host): no page to link from.
            return Response(
                f"{error.code} {error.name}\n", error.code, mimetype="text/plain"
            )
        page = render_template(
            "error.html", code=error.code, message=error.description, meta=None
        )
        return page, error.code

    @app.errorhandler(500)
    def server_error(error):
        log.exception("server error")
        return render_template(
            "error.html", code=500, message="Something went wrong.", meta=None
        ), 500

    app.jinja_env.filters["trim_float"] = trim_float
    app.jinja_env.filters["hood"] = summary.hood_name
    app.jinja_env.filters["mid"] = mid
    app.jinja_env.filters["minus"] = lambda text: str(text).replace("-", "−")
    app.jinja_env.tests["finite"] = lambda v: (
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    )

    app.jinja_env.globals["elegance_summary"] = elegance_summary
    app.jinja_env.globals["verdicts"] = verdicts
    app.jinja_env.globals["elegance_cells"] = ELEGANCE_CELLS
    app.jinja_env.globals["tier_of"] = tier_of
    app.jinja_env.globals["anatomy_levels"] = ANATOMY_LEVELS
    app.jinja_env.globals["design_label"] = design_label
    app.jinja_env.globals["chosen_by"] = chosen_by
    app.jinja_env.filters["term_id"] = term_id

    @app.context_processor
    def helpers():
        def static_url(name):
            return url_for("static", filename=name, v=versions.get(name))

        def page_url(endpoint, filters, **changes):
            query = _query(filters.args(**changes))
            base = url_for(endpoint, **request.view_args)
            return f"{base}?{query}" if query else base

        def sort_url(endpoint, filters, key):
            default = _default_order(key)
            if filters.sort == key:
                order = "asc" if filters.order == "desc" else "desc"
            else:
                order = default
            return page_url(
                endpoint,
                filters,
                sort=None if key == "date" else key,
                order=None if order == default else order,
                page=None,
            )

        host = urlsplit("//" + request.host).hostname or "localhost"
        try:
            nbs = neighbourhoods() if getattr(g, "db", None) is not None else {}
        except sqlite3.Error:
            nbs = {}
        return {
            "neighbourhoods": nbs,
            "boroughs": boroughs.grouped(nbs),
            # Several neighbourhoods are named by their count, not listed (Ben, 2026-10-09).
            "all_areas": (
                "both neighbourhoods"
                if len(nbs) == 2
                else f"all {COUNT_WORDS[len(nbs)] if len(nbs) < len(COUNT_WORDS) else len(nbs)} neighbourhoods"
                if len(nbs) > 2
                else None
            ),
            "host_name": f"[{host}]" if ":" in host else host,
            "section": section_of(request.endpoint),
            "sort_url": sort_url,
            "ordinal": ordinal,
            "usd": charts.usd,
            "pct": charts.pct,
            "month": charts.month_label,
            "day": day_label,
            "static_url": static_url,
            "page_url": page_url,
            "beds_label": beds_label,
            "attr_label": attr_label,
            "BEDROOMS": BEDROOMS,
            "STATUS": STATUS,
            "BANDS": BANDS,
            "ELEVATOR": ELEVATOR,
            "LAUNDRY": LAUNDRY,
            "DOORMAN": DOORMAN,
            "features": lambda row: features(row, exposures().get(row["unit_id"])),
            "FACES": FACES,
            "has_exposure": has_exposure,
            "SORTS": SORTS,
            "PER_PAGE": PER_PAGE,
            "QUARANTINE_ACTIONS": QUARANTINE_ACTIONS,
        }

    def listings_query(filters: Filters):
        total = db().execute(*count_query(filters)).fetchone()[0]
        pages = max(1, math.ceil(total / filters.per))
        filters.page = min(filters.page, pages)
        rows = db().execute(*page_query(filters)).fetchall()
        return rows, total, pages

    def served_selection(m: dict) -> dict | None:
        """Why the published bundle is served. Builds from before the build
        recorded it fall back to the repository's selection, if it names the
        published bundle."""
        if "selection" in m:
            return m["selection"]
        return selection_note(SELECTION, m.get("summary_sha256"))

    @app.get("/")
    def index():
        m = meta()
        data = research.load()
        counts = {
            "quarantined": db()
            .execute("SELECT COUNT(*) FROM quarantined")
            .fetchone()[0]
            if has_quarantine()
            else 0
        }
        entry = entry_for_run(data, m["provenance"]["run"])
        anatomy = (
            describe(entry.get("model"), entry.get("sizes")) if entry else None
        ) or describe(m["provenance"].get("model"))
        return render_template(
            "home.html",
            anatomy=anatomy,
            coverage=current_coverage(),
            meta=m,
            selection=served_selection(m),
            counts=counts,
            entry=entry,
            milestones=latest_milestones(data),
            research_at=data.get("generated_at") if data else None,
        )

    def estimates_or_503() -> estimates_table.Table:
        """The published estimates, or a 503 when none are, or when the table is not
        the one its meta names."""
        try:
            table = estimates_table.load(root)
        except estimates_table.Refused as refused:
            log.error("estimates refused: %s", refused)
            abort(503, description=str(refused))
        if table is None:
            abort(503, description="No estimates have been published yet.")
        return table

    def estimate_list_url(endpoint: str, c, **changes) -> str:
        query = _query(c.args(**changes))
        base = url_for(endpoint)
        return f"{base}?{query}" if query else base

    @app.get("/estimates")
    def estimates():
        table = estimates_or_503()
        info = table.meta
        return render_template(
            "estimates.html",
            meta=None,
            info=info,
            heldout=estimates_table.held_out(info),
            summary=table.summary(estimates_table.Choice()),
            hoods=table.hood_names(),
        )

    @app.get("/listings")
    def listings():
        table = estimates_or_503()
        c = estimates_table.choice(request.args, table.hoods())
        rows, total, pages = table.page(c)
        names = table.hood_names()
        return render_template(
            "listings.html",
            meta=None,
            info=table.meta,
            rows=rows,
            total=total,
            pages=pages,
            choice=c,
            summary=table.summary(c) if c.active() else None,
            hood_groups=boroughs.grouped(names),
            show_hoods=len(names) > 1,
            list_url=lambda **changes: estimate_list_url("listings", c, **changes),
            csv_url=estimate_list_url("listings_csv", c, page=None),
            sorts=estimates_table.SORTS,
            statuses=estimates_table.STATUS,
            bedrooms=estimates_table.BEDROOMS,
            per_page=estimates_table.PER_PAGE,
        )

    @app.get("/listings.csv")
    def listings_csv():
        table = estimates_or_503()
        c = estimates_table.choice(request.args, table.hoods())
        columns = table.csv_columns()

        def generate():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for row in table.csv_rows(c):
                writer.writerow(row)
                if buffer.tell() > 64 * 1024:
                    yield buffer.getvalue()
                    buffer.seek(0)
                    buffer.truncate()
            yield buffer.getvalue()

        return Response(
            generate(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=estimates.csv"},
        )

    @app.get("/listings/<path:key>")
    def listing(key):
        table = estimates_or_503()
        row = table.row(key)
        if row is None:
            # A quarantined ad of the earlier build keeps its page explaining why.
            held = None
            if database_path().is_file() and has_quarantine():
                held = (
                    db()
                    .execute("SELECT * FROM quarantined WHERE audit_id = ?", (key,))
                    .fetchone()
                )
            if held is not None:
                return render_template(
                    "quarantined_listing.html",
                    meta=meta(),
                    row=held,
                    has_building=building_exists(held["building_id"]),
                )
            # Building, unit and best pages still link the earlier build's ads; an ad
            # the model saw in fitting gets a page saying why it has no estimate.
            seen = None
            if database_path().is_file():
                seen = (
                    db()
                    .execute(
                        "SELECT l.*, b.name AS building_name, "
                        "b.address AS building_address "
                        "FROM listings l JOIN buildings b ON b.id = l.building_id "
                        "WHERE l.audit_id = ?",
                        (key,),
                    )
                    .fetchone()
                )
            if seen is not None:
                return render_template("unestimated_listing.html", meta=None, row=seen)
            abort(
                404,
                description="The model holds an estimate only for the ads it held out: "
                "the newest ad of each apartment, and the ads on the market. This ad is "
                "not one of them, or its id is not one the site knows.",
            )
        info = table.meta
        lo, hi = row["model_lo95"], row["model_hi95"]
        return render_template(
            "listing.html",
            meta=None,
            info=info,
            row=row,
            run=(info.get("runs") or {}).get(row["source"]),
            gate=(info.get("gate") or {}).get(row["source"]),
            chart=charts.interval_strip(
                row["ask"],
                row["model_median"],
                [
                    (50, row["model_lo50"], row["model_hi50"]),
                    (80, row["model_lo80"], row["model_hi80"]),
                    (95, lo, hi),
                ],
            ),
        )

    def retired(what: str):
        """A 410 for a page of the earlier model that was retired."""
        message = (
            f"The {what} came from the earlier model and were retired on 2026-11-10, "
            "when the Estimates section moved to the served drift model's held-out "
            "estimates."
        )
        return render_template("retired.html", meta=None, message=message), 410

    @app.get("/estimate")
    def estimate_apartment():
        return retired("estimate form and its results")

    @app.get("/estimates/map")
    def estimates_map():
        return retired("rent map and its figures")

    @app.get("/estimates/map.json")
    def estimates_map_data():
        return jsonify(
            {
                "error": "gone",
                "message": "The rent map came from the earlier model and was retired "
                "on 2026-11-10.",
                "see": [url_for("listings"), url_for("deals_page")],
            }
        ), 410

    def ranked(profile_name: str) -> dict:
        """The profile and every current listing scored by it, cached per
        build and per version of the sheet; 404 for an unknown profile."""
        path = best.profile_path(profile_name)
        try:
            stamp = path.stat().st_mtime_ns if path else None
        except OSError:
            stamp = None
        if stamp is None:
            abort(404, description=f"No preference sheet named {profile_name!r}.")
        commute_file = best.commute_path()
        try:
            commute_stamp = commute_file.stat().st_mtime_ns if commute_file else None
        except OSError:
            commute_file = commute_stamp = None
        bed_file = best.bed_size_path()
        try:
            bed_stamp = bed_file.stat().st_mtime_ns if bed_file else None
        except OSError:
            bed_file = bed_stamp = None
        key = (
            str(database_path()),
            profile_name,
            stamp,
            str(commute_file),
            commute_stamp,
            str(bed_file),
            bed_stamp,
        )
        if key not in best_cache:
            try:
                profile = best.load_profile(path)
            except (OSError, ValueError, AttributeError) as error:
                abort(503, description=f"The preference sheet can't be read: {error}")
            best_cache.clear()
            commute = best.load_commute(commute_file)
            best_cache[key] = {
                "profile": profile,
                "commute": commute,
                **best.rank(db(), profile, commute, best.load_bed_size(bed_file)),
            }
        return best_cache[key]

    def best_choice() -> tuple[str, dict, dict]:
        args = request.args
        beds = args.get("beds", "")
        choice = {
            "beds": int(beds) if beds in ("0", "1", "2", "3") else None,
            "max_rent": _number(args.get("max")),
            "income": args.get("income") == "1",
            "sort": args.get("sort")
            if args.get("sort") in best.SORTS
            else best.DEFAULT_SORT,
        }
        name = args.get("profile") or best.DEFAULT_PROFILE
        return name, ranked(name), choice

    @app.get("/best")
    def best_listings():
        name, data, choice = best_choice()
        rows = best.choose(data["rows"], **choice)
        shown = rows[:BEST_SHOWN]
        excluded = sum(r["income_restricted"] for r in data["rows"])
        query = {k: v for k, v in request.args.items() if v}
        return render_template(
            "best.html",
            meta=meta(),
            profile=data["profile"],
            profile_name=name,
            not_modelled=data["not_modelled"],
            everywhere=data["everywhere"],
            usual_floor=data.get("usual_floor"),
            capture_days=data.get("capture_days", []),
            ordinal=best.ordinal,
            commute=data["commute"],
            rows=shown,
            total=len(rows),
            current=len(data["rows"]),
            income_listings=excluded,
            choice=choice,
            sorts=best.SORTS,
            label=best.label,
            csv_url=url_for("best_csv") + ("?" + _query(query) if query else ""),
        )

    @app.get("/deals")
    def deals_page():
        data = deals.load(root)
        if data is None:
            abort(503, description="No deals table has been published yet.")
        choice = deals.choice(request.args)
        rows = deals.choose(data["rows"], **choice)
        # How many ads the other filters keep that a caution leaves out.
        with_cautioned = deals.choose(data["rows"], **(choice | {"cautioned": True}))
        return render_template(
            "deals.html",
            left_out=len(with_cautioned) - len(rows),
            show_all=url_for(
                "deals_page",
                **{k: request.args[k] for k in deals.FILTERS if request.args.get(k)},
                all="1",
            ),
            meta=meta(),
            info=data["meta"],
            validation=data["validation"],
            hoods=data["hoods"],
            rows=rows[: deals.SHOWN],
            total=len(rows),
            current=len(data["rows"]),
            choice=choice,
            sorts=deals.SORTS,
        )

    @app.get("/best.csv")
    def best_csv():
        _, data, choice = best_choice()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "rank", "audit_id", "building", "unit", "neighbourhood", "bedrooms",
                "ask", "estimate", "ask_vs_estimate_pct", "fit_pct", "score",
                "value", "deal", "pros", "cons", "not_stated", "streeteasy", "commute",
                "bed_size",
            ]
        )  # fmt: skip
        for i, r in enumerate(best.choose(data["rows"], **choice), 1):
            writer.writerow(
                [
                    i, r["audit_id"], r["building"], r["unit"], r["neighbourhood"],
                    r["bedrooms"], r["ask"], round(r["estimate"], 2),
                    None if r["vs_estimate"] is None else round(100 * r["vs_estimate"], 2),
                    round(r["fit_pct"], 2), round(r["score"], 5), round(r["value"], 5),
                    round(r["deal"], 5),
                    "; ".join(t["label"] for t in r["pros"]),
                    "; ".join(t["label"] for t in r["cons"]),
                    "; ".join(r["unknown"] + data["everywhere"]),
                    r["listing_url"],
                    "; ".join(t["label"] for t in r["commute"]),
                    r["bed_size"],
                ]
            )  # fmt: skip
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=best.csv"},
        )

    def building_exists(building_id) -> bool:
        return (
            db()
            .execute("SELECT 1 FROM buildings WHERE id = ?", (building_id,))
            .fetchone()
            is not None
        )

    def layout_changes(rows) -> list[dict]:
        """Where a unit's listed layout jumps between consecutive listings
        (oldest first): a different bedroom count, or a size that changes by
        more than 15%. A renovation, or a data error in one of the ads."""
        out = []
        for before, after in itertools.pairwise(rows):
            beds = before["bedrooms"] != after["bedrooms"]
            a, b = before["square_feet"], after["square_feet"]
            size = bool(a and b and abs(b - a) / a > 0.15)
            if beds or size:
                out.append({"before": before, "after": after})
        return out

    def opposite_moves(rows) -> list[dict]:
        """Consecutive listings of a unit (oldest first) whose ask and
        estimate each moved more than 5%, in opposite directions (about 1 pair
        in 20). Each estimate leaves
        out its own ask but uses the unit's other listings, so a high ask one
        time and a low one another pull each estimate the other way."""
        out = []
        for before, after in itertools.pairwise(rows):
            asks = before["ask"], after["ask"]
            ests = before["estimate"], after["estimate"]
            if not (all(asks) and all(ests)):
                continue
            ask = asks[1] / asks[0] - 1
            est = ests[1] / ests[0] - 1
            if ask * est < 0 and min(abs(ask), abs(est)) > 0.05:
                out.append({"before": before, "after": after})
        return out

    def current_coverage() -> list[dict]:
        """Which neighbourhoods have listings on the market in the latest
        capture, how many, and when they were captured: [{neighbourhood,
        listings, captured}], every neighbourhood of the build included (0 and
        None where there is no current capture)."""
        have = {r["name"] for r in db().execute("PRAGMA table_info(listings)")}
        if "neighbourhood" not in have:
            row = (
                db()
                .execute(
                    "SELECT COUNT(*), MAX(collected_at) FROM listings WHERE is_current = 1"
                )
                .fetchone()
            )
            return [
                {
                    "neighbourhood": None,
                    "listings": row[0],
                    "captured": capture_day(row[1]),
                    "age_days": capture_age(row[1]),
                }
            ]
        found = {
            r[0]: (r[1], r[2])
            for r in db().execute(
                "SELECT neighbourhood, COUNT(*), MAX(collected_at) FROM listings"
                " WHERE is_current = 1 GROUP BY neighbourhood"
            )
        }
        names = sorted(set(neighbourhoods()) | set(found))
        return [
            {
                "neighbourhood": n,
                "listings": found.get(n, (0, None))[0],
                "captured": capture_day(found.get(n, (0, None))[1]),
                "age_days": capture_age(found.get(n, (0, None))[1]),
            }
            for n in names
        ]

    def capture_day(at: str | None) -> str | None:
        """A capture time (ISO, UTC) as its New York day, "18 Sep 2026"."""
        if not at:
            return None
        try:
            t = dt.datetime.fromisoformat(at)
        except ValueError:
            return at[:10]
        if t.tzinfo is not None:
            t = t.astimezone(NEW_YORK)
        return f"{t.day} {t:%b %Y}"

    def capture_age(at: str | None) -> int | None:
        """Calendar days since a capture (ISO time), counted on New York
        dates like the capture day shown; None when unknown."""
        if not at:
            return None
        try:
            t = dt.datetime.fromisoformat(at)
        except ValueError:
            return None
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.UTC)
        today = dt.datetime.now(NEW_YORK).date()
        return max(0, (today - t.astimezone(NEW_YORK).date()).days)

    def neighbourhoods() -> dict:
        """The build's neighbourhoods and their listing counts ({} for builds
        from before neighbourhoods)."""
        return meta().get("stats", {}).get("neighbourhoods") or {}

    def checked(filters: Filters) -> Filters:
        filters.areas = boroughs.areas(filters.nb, neighbourhoods())
        if filters.areas is None:
            filters.nb = None
        if not has_exposure():
            filters.faces = None
        return filters

    def has_exposure() -> bool:
        """Builds before the exposure labels have no exposure table."""
        if "has_exposure" not in g:
            g.has_exposure = (
                db()
                .execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'exposure'"
                )
                .fetchone()
                is not None
            )
        return g.has_exposure

    def exposures() -> dict[str, str]:
        """Every labelled unit's short words, for listing tables; read once
        per build."""
        if not has_exposure():
            return {}
        cached = exposure_short.get("cached")
        if cached is None or cached[0] != g.build:
            # One tuple swapped in whole, so a request racing a build
            # rollover reads either the old or the new words, never neither.
            cached = (
                g.build,
                {
                    r["unit_id"]: exposure.describe(r)["short"]
                    for r in db().execute("SELECT * FROM exposure")
                },
            )
            exposure_short["cached"] = cached
        return cached[1]

    exposure_short: dict = {}
    story_cache: dict = {}

    def story_checks() -> tuple:
        """The story's held-out accuracy, rent jumps, unit examples and
        borders, which scan every listing. Builds work them out into meta;
        older builds get them worked out here. Read once per build, swapped
        in whole like exposures()."""
        conn = db()  # also sets g.build
        cached = story_cache.get("cached")
        if cached is None or cached[0] != g.build:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'story_checks'"
            ).fetchone()
            cached = (
                g.build,
                tuple(json.loads(row["value"]))
                if row
                else (
                    story.accuracy(conn),
                    story.rent_jumps(conn),
                    story.unit_examples(conn),
                    story.borders(conn),
                ),
            )
            story_cache["cached"] = cached
        return cached[1]

    def story_scans() -> tuple:
        """The story's example listing, the neighbourhoods and the fit's
        counts. Builds work them out into meta (story.scans); older builds get
        them worked out here, once per build like story_checks()."""
        conn = db()
        cached = story_cache.get("scans")
        if cached is None or cached[0] != g.build:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'story_scans'"
            ).fetchone()
            cached = (g.build, json.loads(row["value"]) if row else story.scans(conn))
            story_cache["scans"] = cached
        found = cached[1]
        listing = (
            None
            if found["listing"] is None
            else conn.execute(
                "SELECT * FROM listings WHERE id = ?", (found["listing"],)
            ).fetchone()
        )
        return listing, found["current"], set(found["areas"]), found["counts"]

    def has_quarantine() -> bool:
        """Builds before schema 2 have no quarantined table."""
        return (
            db()
            .execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'quarantined'"
            )
            .fetchone()
            is not None
        )

    def quarantined_for(column, value):
        if not has_quarantine():
            return []
        return (
            db()
            .execute(
                f"SELECT * FROM quarantined WHERE {column} = ? ORDER BY period",
                (value,),
            )
            .fetchall()
        )

    def has_observed() -> bool:
        """Builds before the observed table have no NJ listings."""
        return (
            db()
            .execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'observed'"
            )
            .fetchone()
            is not None
        )

    def observed_areas() -> dict[str, int]:
        if not has_observed():
            return {}
        return dict(
            db()
            .execute(
                "SELECT neighbourhood, COUNT(*) FROM observed "
                "GROUP BY neighbourhood ORDER BY neighbourhood"
            )
            .fetchall()
        )

    @app.get("/new-jersey")
    def observed_listings():
        areas = observed_areas()
        filters = ObservedFilters(request.args, areas)
        where, params = filters.where()
        rows, total, medians = [], 0, []
        if areas:
            total = (
                db()
                .execute("SELECT COUNT(*) FROM observed" + where, params)
                .fetchone()[0]
            )
            # The median ask of each layout among the matching listings.
            asks: dict[int, list[float]] = {}
            for beds, ask in db().execute(
                "SELECT bedrooms, ask FROM observed" + where, params
            ):
                if beds is not None:
                    asks.setdefault(min(round(beds), 4), []).append(ask)
            medians = [
                (BEDROOMS[str(b)], statistics.median(v), len(v))
                for b, v in sorted(asks.items())
            ]
        pages = max(1, math.ceil(total / filters.per))
        filters.page = min(filters.page, pages)
        if areas:
            rows = (
                db()
                .execute(
                    "SELECT * FROM observed"
                    + where
                    + filters.order_by()
                    + " LIMIT ? OFFSET ?",
                    [*params, filters.per, (filters.page - 1) * filters.per],
                )
                .fetchall()
            )
        status = meta().get("stats", {}).get("observed", {})
        return render_template(
            "observed.html",
            meta=meta(),
            areas=areas,
            filters=filters,
            rows=rows,
            total=total,
            pages=pages,
            medians=medians,
            left_out=status.get("left_out", {}),
            HIDDEN=observed.HIDDEN,
            csv_url=url_for("observed_csv") + "?" + _query(filters.args(page=None)),
        )

    @app.get("/new-jersey.csv")
    def observed_csv():
        filters = ObservedFilters(request.args, observed_areas())
        where, params = filters.where()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(OBSERVED_CSV_COLUMNS)
        if has_observed():
            writer.writerows(
                db().execute(
                    "SELECT "
                    + ", ".join(OBSERVED_CSV_COLUMNS)
                    + " FROM observed"
                    + where
                    + filters.order_by(),
                    params,
                )
            )
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=new-jersey.csv"},
        )

    @app.get("/quarantined")
    def quarantined():
        building_id = request.args.get("building")
        unit_id = request.args.get("unit")
        if building_id:
            rows, within = quarantined_for("building_id", building_id), "building"
        elif unit_id:
            rows, within = quarantined_for("unit_id", unit_id), "unit"
        else:
            rows, within = (
                db()
                .execute("SELECT * FROM quarantined ORDER BY period DESC, audit_id")
                .fetchall()
                if has_quarantine()
                else [],
                None,
            )
        if within and not rows:
            abort(404, description="No quarantined listings there.")
        linked = (
            {
                r["id"]
                for r in db().execute(
                    "SELECT id FROM buildings WHERE id IN "
                    "(SELECT building_id FROM quarantined)"
                )
            }
            if has_quarantine()
            else set()
        )
        return render_template(
            "quarantined.html",
            meta=meta(),
            rows=rows,
            within=within,
            linked=linked,
        )

    def unit_chart(rows):
        return charts.asks_and_estimates(
            [
                {
                    "period": r["period"],
                    "ask": r["ask"],
                    "estimate": r["estimate"],
                    "lower": r["estimate_lower"],
                    "upper": r["estimate_upper"],
                    "title": charts.month_label(r["period"]),
                    "href": url_for("listing", key=r["audit_id"]),
                }
                for r in rows
            ],
            label="Each listing's ask and its leave-own-row-out estimate with "
            "the 95% range of the typical rent",
        )

    @app.get("/units/<path:unit_id>")
    def unit(unit_id):
        row = (
            db()
            .execute(
                "SELECT u.*, b.name AS building_name, b.address AS building_address "
                "FROM units u JOIN buildings b ON b.id = u.building_id WHERE u.id = ?",
                (unit_id,),
            )
            .fetchone()
        )
        if row is None:
            if quarantined_for("unit_id", unit_id):
                return redirect(url_for("quarantined", unit=unit_id))
            abort(404, description="No unit with that id.")
        rows = (
            db()
            .execute(
                "SELECT * FROM listings WHERE unit_id = ? ORDER BY period, id",
                (unit_id,),
            )
            .fetchall()
        )
        changes = layout_changes(rows)
        aliases = sorted(
            {r["unit_label"] for r in rows if r["unit_label"]} - {row["label"]}
        )
        return render_template(
            "unit.html",
            aliases=aliases,
            layout_changes=changes,
            opposite=opposite_moves(rows),
            meta=meta(),
            unit=row,
            rows=rows,
            chart=unit_chart(rows),
            quarantined=quarantined_for("unit_id", unit_id),
        )

    @app.get("/buildings")
    def buildings():
        q = (request.args.get("q") or "").strip()[:80]
        sort = request.args.get("sort")
        sort = sort if sort in BUILDING_SORTS else "name"
        default = "asc" if sort == "name" else "desc"
        order = request.args.get("order")
        order = order if order in ("asc", "desc") else default
        page = max(1, _int(request.args.get("page"), 1))
        nb = request.args.get("nb")
        areas = boroughs.areas(nb, neighbourhoods())
        nb = nb if areas else None
        clauses, params = [], []
        if q:
            clauses.append("b.search LIKE ? ESCAPE '\\'")
            params.append("%" + _escape_like(q.lower()) + "%")
        if areas:
            clauses.append("b.neighbourhood IN (" + ", ".join("?" * len(areas)) + ")")
            params += areas
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        total = (
            db()
            .execute("SELECT COUNT(*) FROM buildings b" + where, params)
            .fetchone()[0]
        )
        per = 50
        pages = max(1, math.ceil(total / per))
        page = min(page, pages)
        direction = "DESC" if order == "desc" else "ASC"
        rows = (
            db()
            .execute(
                f"SELECT * FROM buildings b{where} ORDER BY {BUILDING_SORTS[sort][0]} "
                f"{direction} NULLS LAST, b.sort_key LIMIT ? OFFSET ?",
                [*params, per, (page - 1) * per],
            )
            .fetchall()
        )

        def link(**changes):
            args = {
                "q": q or None,
                "nb": nb,
                "sort": None if sort == "name" else sort,
                "order": None if order == default else order,
                "page": None if page == 1 else page,
            }
            args.update(changes)
            query = _query({k: v for k, v in args.items() if v is not None})
            return url_for("buildings") + (f"?{query}" if query else "")

        return render_template(
            "buildings.html",
            nb=nb,
            meta=meta(),
            rows=rows,
            q=q,
            sort=sort,
            order=order,
            page=page,
            pages=pages,
            total=total,
            link=link,
            sorts=BUILDING_SORTS,
        )

    @app.get("/buildings/<building_id>")
    def building(building_id):
        row = (
            db()
            .execute("SELECT * FROM buildings WHERE id = ?", (building_id,))
            .fetchone()
        )
        if row is None:
            if quarantined_for("building_id", building_id):
                return redirect(url_for("quarantined", building=building_id))
            abort(404, description="No building with that id.")
        units = (
            db()
            .execute("SELECT * FROM units WHERE building_id = ?", (building_id,))
            .fetchall()
        )
        units = sorted(units, key=lambda u: _natural(u["label"] or ""))
        filters = checked(Filters(request.args))
        filters.building = building_id
        rows, total, pages = listings_query(filters)
        points = (
            db()
            .execute(
                "SELECT audit_id, period, residual_pct, ask, estimate, unit_label, bedrooms "
                "FROM listings WHERE building_id = ? ORDER BY period",
                (building_id,),
            )
            .fetchall()
        )
        chart = charts.residual_scatter(
            [
                {
                    "period": p["period"],
                    "residual_pct": p["residual_pct"],
                    "title": f"{p['unit_label'] or 'Unit'} · {charts.month_label(p['period'])}",
                    "rows": [
                        ["Ask", charts.usd(p["ask"])],
                        ["Estimate", charts.usd(p["estimate"])],
                    ],
                    "href": url_for("listing", key=p["audit_id"]),
                }
                for p in points
            ],
            label="Each listing's ask against its leave-own-row-out estimate, "
            "in percent, over time",
        )
        return render_template(
            "building.html",
            typical=building_typical(building_id),
            meta=meta(),
            b=row,
            units=units,
            rows=rows,
            total=total,
            pages=pages,
            filters=filters,
            chart=chart,
            # The page's status filter applies to its quarantined listings too.
            quarantined=[
                q
                for q in quarantined_for("building_id", building_id)
                if filters.status == "all"
                or bool(q["is_current"]) == (filters.status == "current")
            ],
        )

    @app.get("/buildings.json")
    def building_suggestions():
        """Up to eight buildings matching what's typed, most listed first, for the
        search boxes' suggestions (playtest round 4: no autocomplete)."""
        q = (request.args.get("q") or "").strip()[:80]
        rows = (
            db()
            .execute(
                "SELECT id, name, address, listings FROM buildings "
                "WHERE search LIKE ? ESCAPE '\\' ORDER BY listings DESC, sort_key "
                "LIMIT 8",
                ("%" + _escape_like(q.lower()) + "%",),
            )
            .fetchall()
            if len(q) >= 2
            else []
        )
        return jsonify(
            [
                {
                    "id": r["id"],
                    "value": r["name"] or r["address"],
                    "label": " · ".join(
                        [
                            *([r["address"]] if r["name"] else []),
                            f"{r['listings']:,} listings",
                        ]
                    ),
                }
                for r in rows
            ]
        )

    @app.get("/about")
    def about():
        return render_template("about.html", meta=meta(), terms=terms_list())

    def terms_list():
        return [
            dict(r, label=lay_label(r["name"], r["label"]))
            for r in db().execute("SELECT * FROM terms ORDER BY position")
        ]

    def fit_rows(f) -> list:
        """A fit's hover card: the key facts only (the fit's page and the
        table below the chart have the rest)."""
        rows = []
        if f["entry"].get("other_target"):
            rows.append(["PSIS-LOO ΔELPD", "other target"])
        elif f["delta"] is not None:
            se = f" ± {f['delta_se']:,.1f}" if f["delta_se"] is not None else ""
            rows.append(["PSIS-LOO ΔELPD", f"{f['delta']:+,.1f}{se}"])
        rows.append(["Fit time", f"{f['minutes']:.1f} min"])
        rows.append(["Tier", TIERS[f["tier"]]])
        return rows

    def design_of(key: str) -> str:
        """A fit's design, for a hover card's title: its key up to the
        commit and data choices (model/rows/sampler@commit+choices)."""
        return key.split("@")[0]

    @app.get("/research")
    def research_frontier():
        m = meta()
        data = research.load()
        if not data:
            abort(503, description="The research data is not available yet.")
        classes = hardware_classes(data)
        if not classes:
            abort(503, description="The board has no fits yet.")
        hardware = request.args.get("hardware")
        if hardware not in classes:
            hardware = default_hardware(data, m["provenance"]["run"])
        days = snapshot_days(data)
        day = request.args.get("as_of")
        day = day if day in days else None
        subsets = request.args.get("subsets") == "1"
        full = request.args.get("range") == "full"
        view = frontier_view(data, hardware, day, m["provenance"]["run"], subsets)
        # A fit on another price target than the baseline's has no comparable
        # delta, so it is left off the charts (the table lists it).
        scored = [
            f
            for f in view["fits"]
            if f["delta"] is not None and not f["entry"].get("other_target")
        ]
        floor = None if full else outlier_floor([f["delta"] for f in scored])
        target = hardware == TARGET_HARDWARE
        device = "the RTX 2060" if target else hardware
        time_points = [
            {
                "x": f["minutes"],
                "y": f["delta"],
                # Each chart marks its own tier's frontier.
                "kind": f["kind"]
                if f["kind"] not in ("frontier", "other")
                else "frontier"
                if f["tier_frontier"]
                else "other",
                "tier": f["tier"],
                "on_line": f["tier_frontier"],
                "draws": f["draws"],
                "group": f["group"],
                "faded": f["faded"],
                "title": design_of(f["entry"]["key"]),
                "rows": fit_rows(f),
                "href": url_for("research_fit", key=f["entry"]["key"]),
            }
            for f in scored
        ]
        charts_by_tier = {}
        for prefix, tier in (("f", "full"), ("e", "exploration")):
            points = [
                p
                for p in time_points
                if (p["tier"] == "exploration") == (tier == "exploration")
            ]
            x_range, y_range = zoom_box(request.args, prefix)
            charts_by_tier[tier] = {
                "prefix": prefix,
                "count": len(points),
                "zoomed": bool(x_range or y_range),
                "x_range": x_range,
                "y_range": y_range,
                "shown": sum(
                    1
                    for p in points
                    if (not x_range or x_range[0] <= p["x"] <= x_range[1])
                    and (not y_range or y_range[0] <= p["y"] <= y_range[1])
                ),
                "reset": zoom_url(request.args, prefix, None),
                "keep": [
                    (k, v)
                    for k, v in request.args.items(multi=True)
                    if k not in {prefix + z for z in ZOOM_KEYS}
                ],
                "focus": zoom_url(request.args, prefix, box)
                if (box := frontier_box(points))
                else None,
                "floored": floor is not None and any(p["y"] < floor for p in points),
                "line": sum(1 for p in points if p["on_line"]) > 1,
                "unscored": sum(
                    f["delta"] is None and not f["prior"]
                    for f in view["fits"]
                    if (f["tier"] == "exploration") == (tier == "exploration")
                ),
                "chart": charts.fit_scatter(
                    points,
                    label=f"Accuracy against fit time on {device}, "
                    f"{TIERS[tier].lower()}s, one mark per fit",
                    x_title=f"Fit time on {device}, full dataset (minutes)",
                    y_title="PSIS-LOO ΔELPD (higher is more accurate)",
                    x_format=lambda v: f"{v:g}",
                    y_format=charts.signed,
                    y_floor=floor,
                    x_line=(TARGET_MINUTES, "2-hour limit for a full fit")
                    if target and tier == "full"
                    else None,
                    x_range=x_range,
                    y_range=y_range,
                    zoom=prefix,
                    # The exploration line includes unconverged fits.
                    frontier_line="solid" if tier == "full" else "dashed",
                ),
            }
            # Fits trained on the data before the board's re-baseline: drawn
            # apart, on their own axis, never on any frontier.
            earlier = [
                f
                for f in view["fits"]
                if f["prior"]
                and (f["tier"] == "exploration") == (tier == "exploration")
            ]
            charts_by_tier[tier]["earlier"] = len(earlier)
            charts_by_tier[tier]["earlier_data"] = (
                earlier[0]["prior"]["dataset"] if earlier else None
            )
            earlier_floor = (
                None if full else outlier_floor([f["prior"]["delta"] for f in earlier])
            )
            charts_by_tier[tier]["earlier_floored"] = earlier_floor is not None and any(
                f["prior"]["delta"] < earlier_floor for f in earlier
            )
            earlier_points = [
                {
                    "x": f["minutes"],
                    "y": f["prior"]["delta"],
                    "kind": "failing" if f["kind"] == "failing" else "other",
                    "tier": f["tier"],
                    "title": design_of(f["entry"]["key"]),
                    "rows": [
                        [
                            "ΔELPD, earlier data",
                            (f"{f['prior']['delta']:+,.1f} ± {f['prior']['se']:,.1f}"),
                        ],
                        *fit_rows(f),
                    ],
                    "href": url_for("research_fit", key=f["entry"]["key"]),
                }
                for f in earlier
            ]
            # The best fits on the earlier data, joined as on the charts
            # above: every exploration fit, only converged full fits.
            best = best_so_far(
                earlier_points,
                lambda p, t=tier: t == "exploration" or p["kind"] != "failing",
            )
            for i, p in enumerate(earlier_points):
                p["on_line"] = i in best
            ex_range, ey_range = zoom_box(request.args, prefix + "p")
            charts_by_tier[tier]["earlier_chart"] = (
                charts.fit_scatter(
                    earlier_points,
                    label=f"{TIERS[tier]}s scored on the earlier data, "
                    "against its own baseline: not comparable with the chart above",
                    x_title=f"Fit time on {device}, full dataset (minutes)",
                    y_title="PSIS-LOO ΔELPD against the earlier baseline",
                    x_format=lambda v: f"{v:g}",
                    y_format=charts.signed,
                    y_floor=earlier_floor,
                    x_range=ex_range,
                    y_range=ey_range,
                    zoom=prefix + "p",
                    frontier_line="solid" if tier == "full" else "dashed",
                    line_label="The best fits on the earlier data, joined"
                    + (
                        "; it includes fits that fail the convergence checks"
                        if tier == "exploration"
                        else ""
                    ),
                )
                if earlier
                else None
            )
        return render_template(
            "research_frontier.html",
            meta=m,
            view=view,
            classes=classes,
            hardware=hardware,
            days=days,
            day=day,
            subsets=subsets,
            full=full,
            floor=floor,
            target=target,
            target_minutes=TARGET_MINUTES,
            subset_minutes=SUBSET_MINUTES,
            judged_pairs=len(judgements(data)),
            exploration=data.get("exploration"),
            tiers=TIERS,
            tier_charts=charts_by_tier,
        )

    def research_data_or_503() -> dict:
        data = research.load()
        if not data:
            abort(503, description="The research data is not available yet.")
        return data

    @app.get("/research/board")
    def research_board():
        m = meta()
        data = research_data_or_503()
        classes = hardware_classes(data)
        hardware = request.args.get("hardware")
        hardware = hardware if hardware in classes else None
        line = request.args.get("line")
        line = line if line in LINES else None
        sort = request.args.get("sort")
        sort = sort if sort in BOARD_SORTS else "delta"
        order = request.args.get("order")
        order = order if order in ("asc", "desc") else BOARD_ORDERS[sort]
        q = (request.args.get("q") or "").strip()[:80]
        servable = request.args.get("servable") == "1"
        subsets = request.args.get("subsets") == "1"
        tier = request.args.get("tier")
        tier = tier if tier in TIERS else None
        rows = board_rows(
            data,
            hardware=hardware,
            line=line,
            q=q,
            servable=servable,
            subsets=subsets,
            tier=tier,
            sort=sort,
            descending=order == "desc",
        )

        def board_url(**changes):
            args = {
                "hardware": hardware,
                "line": line,
                "q": q or None,
                "servable": "1" if servable else None,
                "subsets": "1" if subsets else None,
                "tier": tier,
                "sort": None if sort == "delta" else sort,
                "order": None if order == BOARD_ORDERS[sort] else order,
            }
            args.update(changes)
            query = _query({k: v for k, v in args.items() if v is not None})
            return url_for("research_board") + (f"?{query}" if query else "")

        return render_template(
            "research_board.html",
            meta=m,
            rows=rows,
            total=len(data.get("entries", [])),
            tier=tier,
            tiers=TIERS,
            classes=classes,
            lines=LINES,
            hardware=hardware,
            line=line,
            q=q,
            servable=servable,
            subsets=subsets,
            sort=sort,
            order=order,
            board_url=board_url,
            board_orders=BOARD_ORDERS,
            served_run=m["provenance"]["run"],
            run_of=run_of,
            serve_status=serve_status,
            descriptive_share=descriptive_share,
        )

    @app.get("/research/fits/<path:key>")
    def research_fit(key):
        m = meta()
        data = research_data_or_503()
        entry = entry_by_key(data, key)
        if entry is None:
            abort(404, description="No fit with that key on the board.")
        serve, why_not = serve_status(entry)
        anatomy = describe(entry.get("model"), entry.get("sizes"))
        served_entry = entry_for_run(data, m["provenance"]["run"])
        base = (
            describe(served_entry.get("model"), served_entry.get("sizes"))
            if served_entry
            else None
        )
        return render_template(
            "research_fit.html",
            meta=m,
            e=entry,
            anatomy=anatomy,
            diffs=differences(anatomy, base) if anatomy and base else None,
            served_design=bool(
                served_entry and served_entry.get("design") == entry.get("design")
            ),
            run=run_of(entry),
            serve=serve,
            why_not=why_not,
            served=run_of(entry) == m["provenance"]["run"],
            groups=data.get("variance_groups", []),
            baseline=data.get("baseline"),
            lines=LINES,
            design_fits=design_fits(data),
            tier=(entry.get("tier") or {}) if tier_of(entry) == "exploration" else None,
            full_fits=full_fits_of(data, entry)
            if tier_of(entry) == "exploration"
            else [],
        )

    def design_fits(data: dict) -> dict:
        """Each judged design's fits on the board, to link the other side of a
        judgement."""
        return {d["id"]: d["fits"] for p in elegance_pairs(data) for d in p["designs"]}

    @app.get("/research/designs")
    def research_designs():
        m = meta()
        data = research_data_or_503()
        rows, unrecorded = designs(data, m["provenance"]["run"])
        return render_template(
            "research_designs.html",
            meta=m,
            rows=rows,
            unrecorded=unrecorded,
            columns=[p for p in rows[0]["anatomy"].parts if p.key != "intercept"]
            if rows
            else [],
        )

    @app.get("/research/elegance")
    def research_elegance():
        data = research_data_or_503()
        pending = (data.get("autoselect") or {}).get("pending_judgements") or []
        pairs = elegance_pairs(data)
        q = (request.args.get("design") or "").strip()[:120]
        shown = [
            p
            for p in pairs
            if not q or any(q.lower() in d["id"].lower() for d in p["designs"])
        ]
        per = 50
        pages = max(1, -(-len(shown) // per))
        try:
            page = min(max(int(request.args.get("page", 1)), 1), pages)
        except ValueError:
            page = 1
        return render_template(
            "research_elegance.html",
            meta=meta(),
            pairs=shown[(page - 1) * per : page * per],
            total=len(pairs),
            matched=len(shown),
            q=q,
            page=page,
            pages=pages,
            standings=elegance_standings(pairs),
            pending=pending,
        )

    @app.get("/research/history")
    def research_history():
        m = meta()
        data = research_data_or_503()
        classes = hardware_classes(data)
        if not classes:
            abort(503, description="The board has no fits yet.")
        hardware = request.args.get("hardware")
        if hardware not in classes:
            hardware = default_hardware(data, m["provenance"]["run"])
        served_run = m["provenance"]["run"]
        best = best_over_time(data, hardware)
        fits = []
        for e in data.get("entries", []):
            if e["hardware_class"] != hardware or not e.get("available_at"):
                continue
            run = run_of(e)
            kind = (
                "served"
                if run and run == served_run
                else "subset"
                if subset_fit(e)
                else "frontier"
                if e.get("frontier")
                else "failing"
                if not e.get("passes_checks")
                else "other"
            )
            fits.append(
                {
                    "key": e["key"],
                    "at": e["available_at"],
                    "y": e["fit_seconds"] / 60,
                    "kind": kind,
                    "tier": tier_of(e),
                    "title": design_of(e["key"]),
                    "rows": [["Fit time", f"{e['fit_seconds'] / 60:.1f} min"]],
                    "href": url_for("research_fit", key=e["key"]),
                }
            )
        compute = compute_by_line(data)
        only = request.args.get("changes")
        only = only if only in ("switches",) else None
        milestones = sorted(
            (
                ms
                for ms in data.get("milestones", [])
                if not only or ms.get("kind") == "selection"
            ),
            key=lambda ms: (ms.get("at", ""), ms.get("kind") == "selection"),
            reverse=True,
        )
        return render_template(
            "research_history.html",
            predictions=predictions_made(data),
            meta=m,
            classes=classes,
            hardware=hardware,
            best=best,
            compute=compute,
            milestones=milestones,
            only=only,
            fits=sorted(fits, key=lambda f: f["at"], reverse=True),
            best_chart=charts.lines_over_time(
                [{"name": "Best fit", "points": best, "step": True}],
                label=f"The best fit's accuracy on {hardware} over time",
                y_title="PSIS-LOO ΔELPD of the best fit",
                y_format=charts.signed,
                zero=False,  # the steps, not their distance from the baseline
            ),
            time_chart=charts.dated_points(
                fits,
                label=f"Fit time of each fit on {hardware}, by the day it landed",
                y_title="Fit time (minutes)",
                y_format=lambda v: f"{v:,.0f}",
                clamp_zero=True,
            ),
            compute_chart=charts.lines_over_time(
                compute,
                label="Cumulative hours of fitting by model line",
                y_title="Hours of fitting, cumulative",
                y_format=lambda v: f"{v:,.0f}",
                clamp_zero=True,
            ),
        )

    @app.get("/research/validation")
    def research_validation():
        m = meta()
        data = research_data_or_503()
        classes = hardware_classes(data)
        if not classes:
            abort(503, description="The board has no fits yet.")
        hardware = request.args.get("hardware")
        if hardware not in classes:
            hardware = default_hardware(data, m["provenance"]["run"])
        served_run = m["provenance"]["run"]
        pairs = validation_pairs(data, hardware)
        floor = outlier_floor([p["psis"] for p in pairs])
        shown = [p for p in pairs if floor is None or p["psis"] >= floor]
        rho = spearman([p["psis"] for p in shown], [p["heldout"] for p in shown])
        points = []
        for p in shown:
            e = p["entry"]
            kind = (
                "served"
                if run_of(e) == served_run
                else "frontier"
                if e.get("frontier")
                else "failing"
                if not e.get("passes_checks")
                else "other"
            )
            se = p["heldout_se"]
            points.append(
                {
                    "x": p["psis"],
                    "y": p["heldout"],
                    "kind": kind,
                    "title": design_of(e["key"]),
                    "rows": [
                        ["PSIS-LOO ΔELPD", f"{p['psis']:+,.1f}"],
                        [
                            "Held-out ΔELPD",
                            f"{p['heldout']:+,.1f}"
                            + (f" ± {se:,.1f}" if se is not None else ""),
                        ],
                    ],
                    "href": url_for("research_fit", key=e["key"]),
                }
            )
        frontier = [
            e
            for e in data.get("entries", [])
            if e["hardware_class"] == hardware
            and e.get("frontier")
            and e.get("variance")
        ]
        frontier.sort(key=lambda e: -((e.get("psis") or {}).get("delta") or 0))
        served_entry = entry_for_run(data, served_run)
        return render_template(
            "research_validation.html",
            meta=m,
            served_entry=served_entry,
            classes=classes,
            hardware=hardware,
            rho=rho,
            shown=shown,
            left_out=len(pairs) - len(shown),
            chart=charts.fit_scatter(
                points,
                label="Each fit's PSIS-LOO score against its genuine held-out score",
                x_title="PSIS-LOO ΔELPD against the simplest baseline (from the fit itself)",
                y_title="Held-out ΔELPD against the reference model",
                x_format=charts.signed,
                y_format=charts.signed,
                x_zero=False,
            ),
            variance=frontier,
            groups=data.get("variance_groups", []),
            implementations=implementations(data),
        )

    @app.get("/research/data")
    def research_data_quality():
        m = meta()
        data = research_data_or_503()
        quality = data.get("data_quality") or {}
        quarantined = (
            db().execute("SELECT COUNT(*) FROM quarantined").fetchone()[0]
            if has_quarantine()
            else 0
        )
        return render_template(
            "research_data.html",
            meta=m,
            quality=quality,
            quarantined=quarantined,
        )

    @app.get("/research/plan")
    def research_plan_page():
        m = meta()
        current = plan.load()
        if current is None:
            abort(503, description="The research plan is not available.")
        return render_template(
            "research_plan.html",
            meta=m,
            plan=Markup(current["html"]),
            toc=current["toc"],
            modified=dt.datetime.fromtimestamp(current["modified"], dt.UTC),
            fallback=current["fallback"],
        )

    @app.get("/research/glossary")
    def research_glossary():
        return render_template(
            "research_glossary.html", meta=meta(), terms=terms_list()
        )

    @app.get("/research/story")
    def research_story():
        m = meta()
        terms = terms_list()
        labels = {t["name"]: t["label"] for t in terms}
        data = research.load()
        entry = entry_for_run(data, m["provenance"]["run"])
        anatomy = (
            describe(entry.get("model"), entry.get("sizes")) if entry else None
        ) or describe(m["provenance"].get("model"))
        variance = (entry or {}).get("variance")
        coefficients = db().execute("SELECT * FROM coefficients").fetchall()
        listing, current, areas, counts = story_scans()
        named = {
            c["feature"] for c in coefficients if c["feature_group"] == "neighbourhood"
        }
        reference_area = (
            next(iter(areas - named), None) if len(areas - named) == 1 else None
        )
        effects = story.headline_effects(coefficients, labels, reference_area)
        # the ad-text concession term, and its 2020-on split once a fit has it
        concession = {
            c["feature"]: c for c in coefficients if "concession" in c["feature"]
        }
        build = story.build_up(
            listing,
            parts_of(listing) if listing is not None else None,
            labels,
            current=current,
            likely=likely_of(listing) if listing is not None else None,
        )
        accuracy, jumps, units, borders = story_checks()
        rows = story.composition(anatomy, variance)
        explained = story.explained(entry)
        trials = story.theories(ledger.load())
        switches = story.design_history((data or {}).get("milestones") or [])
        lives = story.term_lives(switches)
        cleaning = story.cleaning(cleaning_file.load(), m["provenance"]["run"])
        groups = story.group_items(
            group_file.load(),
            trials,
            m["provenance"]["run"],
            {c["feature"] for c in coefficients},
        )
        return render_template(
            "research_story.html",
            meta=m,
            entry=entry,
            anatomy=anatomy,
            composition=rows,
            composition_svg=story.composition_svg(rows),
            variance=variance,
            effects=effects,
            effects_svg=story.effects_svg(effects),
            reference_area=reference_area,
            build=build,
            build_svg=story.build_up_svg(build),
            accuracy=accuracy,
            coverage_svg=story.coverage_svg(accuracy["groups"] if accuracy else []),
            jumps=jumps,
            units=units,
            borders=borders,
            borders_svg=story.borders_svg(borders),
            explained=explained,
            explained_svg=story.explained_svg(explained),
            border_tests=story.border_tests(trials),
            counts=counts,
            trials=trials,
            trials_svg=story.theories_svg(trials),
            verdict_words=story.VERDICT_WORDS,
            kinds=story.KINDS,
            switches=switches,
            eras=story.eras(switches),
            lives=lives,
            prevprice=story.served_spells(switches, "prevprice"),
            history_svg=story.history_svg(switches, lives),
            cleaning=cleaning,
            concession=concession.get("text:concession"),
            concession_2020=concession.get("text:concession, 2020 on"),
            areas=sorted(a for a in areas if a),
            cleaning_svg=story.cleaning_svg(cleaning),
            groups=groups,
            attrs_svg=story.group_items_svg(
                groups["attributes"]["items"] if groups else [], "whose ad states it"
            ),
            places_svg=story.group_items_svg(
                groups["places"]["items"] if groups else [],
                f"within {groups['near_m']:.0f} m" if groups else "",
            ),
            terms=terms,
            labels=labels,
        )

    @app.get("/research/model")
    def research_model():
        m = meta()
        coefficients = (
            db()
            .execute("SELECT * FROM coefficients ORDER BY feature_group, feature")
            .fetchall()
        )
        terms = terms_list()
        labels = {t["name"]: t["label"] for t in terms}
        data = research.load()
        entry = entry_for_run(data, m["provenance"]["run"])
        # The board entry's record (with data sizes) when the research data
        # has it, else the served bundle's own ModelConfig.
        anatomy = (
            describe(entry.get("model"), entry.get("sizes")) if entry else None
        ) or describe(m["provenance"].get("model"))
        return render_template(
            "research_model.html",
            anatomy=anatomy,
            runners_up=sorted(
                (
                    e
                    for e in (data or {}).get("entries", [])
                    if e.get("vs_served") and run_of(e) != m["provenance"]["run"]
                )
                if (data or {}).get("vs_served_run") == m["provenance"]["run"]
                else (),
                # Fits on another price target have no delta and go last.
                key=lambda e: (
                    e["vs_served"].get("delta") is None,
                    -(e["vs_served"].get("delta") or 0.0),
                ),
            )[:8],
            meta=m,
            selection=served_selection(m),
            coefficients=coefficients,
            terms=terms,
            labels=labels,
            entry=entry,
            baseline=data.get("baseline") if data else None,
            autoselect=data.get("autoselect") if data else None,
        )

    @app.get("/healthz")
    def healthz():
        try:
            m = meta()
            count = db().execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        except sqlite3.Error as error:
            return jsonify(status="error", error=str(error)), 503
        response = jsonify(
            status="ok",
            build=g.build,
            run=m["provenance"]["run"],
            listings=count,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/robots.txt")
    def robots():
        return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")

    return app


def rules_of(entry: dict) -> list[str]:
    """The data rules a board key names after its commit ("...@abc1234+rule+rule")."""
    return entry["key"].split(" [")[0].split("@", 1)[-1].split("+")[1:]


def design_label(entry: dict) -> str:
    """What an entry's design adds to the basic hierarchy, in a few words
    (`Anatomy.label`); "" when its record holds no structure."""
    a = describe(entry.get("model"), entry.get("sizes"))
    return a.label if a else ""


def term_id(name: str) -> str:
    """A glossary anchor for an estimate part: "building size" -> "part-building-size"."""
    return "part-" + (
        re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "term"
    )


@functools.lru_cache(maxsize=2)
def _rent_map(path: str, mtime: float) -> dict:
    """A build's map.json, read once per file version, with a building index."""
    data = json.loads(Path(path).read_text())
    data["_index"] = {b["id"]: i for i, b in enumerate(data.get("buildings", []))}
    return data


def chosen_by(selected_by: str) -> str:
    """Who chose the served model, in words: the automatic rule with its
    date ("rentfrontier.autoselect, 2026-10-04 (Ben, …)"), else as written."""
    if selected_by.startswith("rentfrontier.autoselect"):
        day = re.search(r"\d{4}-\d{2}-\d{2}", selected_by)
        return "the automatic selection rule" + (f", {day.group()}" if day else "")
    return selected_by


def ordinal(n: int) -> str:
    n = int(n)
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


def predictions_made(data: dict) -> list[dict]:
    """The predictions written before each fit, newest first; malformed lines
    (kept by the research data as {"error": ...}) are left out."""
    rows = [p for p in data.get("predictions") or [] if "error" not in p]
    return sorted(rows, key=lambda p: p.get("written") or "", reverse=True)


def mid(share: dict | None) -> float | None:
    """A variance share's central value: the median over draws, or the mean
    in records written before the median was kept (the Fable review asks for
    medians, 2026-10-10)."""
    if not share:
        return None
    return share.get("median", share.get("mean"))


def trim_float(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):g}"


def _natural(text: str):
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text.upper())]


# Plain words for the bundle's term labels that read as jargon to renters (playtest
# round 4: "Building size and bath slopes", "HVAC", "Price basis"). Research pages
# name terms by these too; the glossary's anchors use the term names.
LAY_LABELS = {
    "hvac": "Heating and cooling",
    "price_basis": "How the price was recorded",
    "building era": "When the building was built",
    "bedroom_market_curve": "Market trend for this many bedrooms",
    "building_drift": "This building's change over time",
    "building_bedroom_premium": "This building's premium for more bedrooms",
    "building_feature_slopes": "This building's price for extra space and baths",
}


def lay_label(name: str, label: str) -> str:
    return LAY_LABELS.get(name, label)


FEATURE_WORDS = {
    ("laundry", "in_unit"): "W/D in unit",
    ("laundry", "in_building"): "laundry in bldg",
    ("doorman", "full_time"): "doorman",
    ("doorman", "part_time"): "part-time doorman",
    ("doorman", "virtual"): "virtual doorman",
    ("doorman", "unspecified"): "doorman",
    ("elevator", "yes"): "elevator",
    ("elevator", "no"): "walk-up",
}


def features(row, faces: str | None = None) -> list[str]:
    """A listing's floor and stated amenities in a few short words, for a
    line under its layout in listing tables (playtest round 6), with which way
    the apartment faces when it is known."""
    inputs = json.loads(row["inputs"] or "{}")
    floor = row["floor"] if row["floor"] is not None else read_floor(row, inputs)
    out = [f"floor {floor}"] if floor is not None else []
    for kind in ("elevator", "laundry", "doorman"):
        word = FEATURE_WORDS.get((kind, row[kind]))
        if word:
            out.append(word)
    if summary.has_outdoor(inputs):
        out.append("outdoor space")
    if faces:
        out.append(faces)
    return out


def read_floor(row, inputs: dict[str, float]) -> int | None:
    """The floor from the unit's label (see summary.label_floor)."""
    return summary.label_floor(row["floor"], inputs)


def day_label(iso: str) -> str:
    """'2026-04-21' -> 'Apr 21, 2026'."""
    d = dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def beds_label(value) -> str:
    if value is None:
        return "—"
    beds = round(value)
    return "Studio" if beds == 0 else f"{beds} BR"


def attr_label(kind: str, value) -> str | None:
    if value in (None, "", "unknown"):
        return None
    return LABELS.get(kind, {}).get(value, str(value).replace("_", " ").capitalize())
