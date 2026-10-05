"""The listings site: a read-only Flask app over the published SQLite snapshot.

Each request opens <root>/current/site.sqlite read-only (immutable), so a new
publish (`apartments.site.build`) is picked up by the next request. Filters are
parsed leniently: an invalid value is ignored, never an error page.
"""

from __future__ import annotations

import copy
import csv
import dataclasses
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
    stream_with_context,
    url_for,
)
from markupsafe import Markup

from . import charts, estimate, estimate_build
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
BEDROOMS = {"0": "Studio", "1": "1 BR", "2": "2 BR", "3": "3 BR", "4": "4+ BR"}
STATUS = {"all": "All listings", "current": "Available now", "past": "Past listings"}
# Fewer "Available now" matches than this point to the past listings too.
FEW_CURRENT = 10
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
CSV_COLUMNS = (
    "audit_id",
    "building_id",
    "neighbourhood",  # left out for builds from before neighbourhoods
    "unit_label",
    "period",
    "is_current",
    "ask",
    "estimate",
    "estimate_lower",
    "estimate_upper",
    "residual_usd",
    "residual_pct",
    "pit",
    "price_band",
    "reliable",
    "bedrooms",
    "bathrooms",
    "square_feet",
    "floor",
    "listing_url",
    "pred_lower_80",  # the likely ask range, when the build has it
    "pred_upper_80",
)
LABELS = {
    "doorman": {
        "full_time": "Full-time doorman",
        "part_time": "Part-time doorman",
        "virtual": "Virtual doorman",
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
            args.get("elevator") if args.get("elevator") in ("yes", "no") else None
        )
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

    def where(self):
        clauses, params = [], []
        if self.building:
            clauses.append("l.building_id = ?")
            params.append(self.building)
        if self.nb:
            clauses.append("l.neighbourhood = ?")
            params.append(self.nb)
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
        if self.elevator is not None:
            clauses.append("l.elevator = ?")
            params.append(self.elevator)
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
            or self.year_from
            or self.year_to
            or self.status != "all"
            or self.band != "all"
        )


# Minimum bathrooms the listings filter offers.
BATHS = ("1", "1.5", "2", "3")
LISTING_JOIN = " JOIN buildings b ON b.id = l.building_id"


def asks_summary(db, filters: Filters) -> dict | None:
    """The filtered listings' asks in brief: their median and middle 80%
    (10th to 90th percentile), and the median of their estimates; None when
    nothing matches."""
    where, params = filters.where()
    join = LISTING_JOIN if "b." in where else ""
    rows = db.execute(f"SELECT l.ask, l.estimate FROM listings l{join}{where}", params)
    asks, estimates = [], []
    for ask, est in rows:
        asks.append(ask)
        if est is not None:
            estimates.append(est)
    if not asks:
        return None
    asks.sort()
    out = {
        "n": len(asks),
        "median": statistics.median(asks),
        "low": None,
        "high": None,
        "estimate": statistics.median(estimates) if estimates else None,
    }
    if len(asks) >= 5:  # a middle 80% of fewer asks says little
        deciles = statistics.quantiles(asks, n=10, method="inclusive")
        out["low"], out["high"] = deciles[0], deciles[-1]
    return out


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
        "about",
        "estimates_map",
        "estimate_apartment",
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
    ),
}


def section_of(endpoint: str | None) -> str | None:
    return next((k for k, v in SECTIONS.items() if endpoint in v), None)


def create_app(
    root: Path | str | None = None,
    *,
    allowed_hosts=None,
    research_data=None,
    research_plan=None,
) -> Flask:
    root = Path(root or os.environ.get("SITE_ROOT", "/data1/apartments/site"))
    research = Research(research_data)
    plan = Plan(research_plan)
    app = Flask(__name__)
    if allowed_hosts is None:
        allowed_hosts = os.environ.get("SITE_ALLOWED_HOSTS", "").split(",")
    hosts = [h.strip().lower() for h in allowed_hosts if h.strip()]
    if any(h.startswith(".") or "*" in h for h in hosts):
        raise ValueError("Site allowed hosts must be exact hostnames")
    app.config["TRUSTED_HOSTS"] = [*DEFAULT_HOSTS, *hosts]
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 365 * 24 * 3600
    versions = _asset_versions(Path(app.static_folder))

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
            g.db.row_factory = sqlite3.Row
            g.build = path.parent.name
        return g.db

    def meta() -> dict:
        if "meta" not in g:
            g.meta = {
                row["key"]: json.loads(row["value"])
                for row in db().execute("SELECT key, value FROM meta")
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

    @app.after_request
    def finish(response):
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
            "host_name": f"[{host}]" if ":" in host else host,
            "section": section_of(request.endpoint),
            "sort_url": sort_url,
            "ordinal": ordinal,
            "usd": charts.usd,
            "pct": charts.pct,
            "month": charts.month_label,
            "static_url": static_url,
            "page_url": page_url,
            "beds_label": beds_label,
            "attr_label": attr_label,
            "BEDROOMS": BEDROOMS,
            "STATUS": STATUS,
            "BANDS": BANDS,
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
            estimate_form=estimate_build.available(db()),
            milestones=latest_milestones(data),
            research_at=data.get("generated_at") if data else None,
        )

    @app.get("/estimates")
    def estimates():
        m = meta()
        current = (
            db()
            .execute(
                "SELECT l.*, b.name AS building_name, b.address AS building_address "
                "FROM listings l JOIN buildings b ON b.id = l.building_id "
                "WHERE l.is_current = 1 ORDER BY l.residual_pct LIMIT 12"
            )
            .fetchall()
        )
        market = db().execute("SELECT * FROM market ORDER BY period").fetchall()
        quarantined = (
            db().execute("SELECT COUNT(*) FROM quarantined").fetchone()[0]
            if has_quarantine()
            else 0
        )
        chart = charts.band_line(
            [
                {
                    "period": r["period"],
                    "value": r["deseasoned"],
                    "lower": r["deseasoned_lower"],
                    "upper": r["deseasoned_upper"],
                }
                for r in market
            ],
            label="Market reference rent over time, seasonally adjusted, "
            "with its 95% interval",
            value_label="Reference rent",
        )
        return render_template(
            "estimates.html",
            meta=m,
            coverage=current_coverage(),
            current=current,
            quarantined=quarantined,
            market=market,
            market_chart=chart,
        )

    @app.get("/listings")
    def listings():
        filters = checked(Filters(request.args))
        rows, total, pages = listings_query(filters)
        # Few listings are on the market at once, so "Available now" with
        # narrow filters can leave one or none (playtest round 3): say how
        # many past listings match the same filters.
        past = None
        if filters.status == "current" and total < FEW_CURRENT:
            every = copy.copy(filters)
            every.status = "past"
            past = db().execute(*count_query(every)).fetchone()[0]
        return render_template(
            "listings.html",
            past=past,
            summary=asks_summary(db(), filters) if filters.active() else None,
            meta=meta(),
            coverage=current_coverage() if filters.status == "current" else [],
            rows=rows,
            total=total,
            pages=pages,
            filters=filters,
            csv_url=url_for("listings_csv")
            + "?"
            + _query(filters.args(page=None, per=None)),
        )

    @app.get("/listings.csv")
    def listings_csv():
        filters = checked(Filters(request.args))
        where, params = filters.where()
        have = {r["name"] for r in db().execute("PRAGMA table_info(listings)")}
        columns = [c for c in CSV_COLUMNS if c in have]
        cursor = db().execute(
            "SELECT "
            + ", ".join(f"l.{c}" for c in columns)
            + " FROM listings l JOIN buildings b ON b.id = l.building_id"
            + where
            + filters.order_by(),
            params,
        )
        connection = g.pop("db")  # the stream outlives the request context

        def generate():
            try:
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerow(columns)
                for row in cursor:
                    writer.writerow(row)
                    if buffer.tell() > 64 * 1024:
                        yield buffer.getvalue()
                        buffer.seek(0)
                        buffer.truncate()
                yield buffer.getvalue()
            finally:
                connection.close()

        response = Response(
            stream_with_context(generate()),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=listings.csv"},
        )
        response.call_on_close(connection.close)
        return response

    @app.get("/listings/<path:audit_id>")
    def listing(audit_id):
        row = (
            db()
            .execute(
                "SELECT l.*, b.name AS building_name, b.address AS building_address "
                "FROM listings l JOIN buildings b ON b.id = l.building_id "
                "WHERE l.audit_id = ?",
                (audit_id,),
            )
            .fetchone()
        )
        if row is None:
            held = (
                db()
                .execute("SELECT * FROM quarantined WHERE audit_id = ?", (audit_id,))
                .fetchone()
                if has_quarantine()
                else None
            )
            if held is None:
                abort(404, description="No listing with that id.")
            return render_template(
                "quarantined_listing.html",
                meta=meta(),
                row=held,
                has_building=building_exists(held["building_id"]),
            )
        terms = {
            r["name"]: r for r in db().execute("SELECT * FROM terms ORDER BY position")
        }
        contributions = json.loads(row["contributions"])
        market = next(c for c in contributions if c["term"] == "market")
        # Parts at their reference level contribute exactly nothing in every
        # draw; they are named in a note instead of drawn as empty rows.
        parts = [
            c
            for c in contributions
            if c["term"] != "market" and (c["lower"], c["upper"]) != (0, 0)
        ]
        reference = [
            terms[c["term"]]["label"] if c["term"] in terms else c["term"]
            for c in contributions
            if c["term"] != "market" and (c["lower"], c["upper"]) == (0, 0)
        ]
        scale = max((max(abs(c["lower"]), abs(c["upper"])) for c in parts), default=1)
        for c in parts:
            c["bar"] = charts.contribution_bar(c["usd"], c["lower"], c["upper"], scale)
        others = (
            db()
            .execute(
                "SELECT * FROM listings WHERE unit_id = ? ORDER BY period",
                (row["unit_id"],),
            )
            .fetchall()
        )
        inputs = json.loads(row["inputs"])
        # The same advertisement seen earlier: when it first appeared and at
        # what ask, so a price cut or rise shows (playtest round 3).
        ad_start = next(
            (
                o
                for o in others
                if row["listing_id"]
                and o["listing_id"] == row["listing_id"]
                and o["period"] < row["period"]
            ),
            None,
        )
        # The latest other listing of this apartment with a different bedroom
        # count: the ads relabelled it, or it was rebuilt.
        relabelled = next(
            (
                o
                for o in reversed(others)
                if o["id"] != row["id"]
                and o["bedrooms"] is not None
                and row["bedrooms"] is not None
                and o["bedrooms"] != row["bedrooms"]
            ),
            None,
        )
        return render_template(
            "listing.html",
            ad_start=ad_start,
            relabelled=relabelled,
            meta=meta(),
            row=row,
            terms=terms,
            market=market,
            parts=parts,
            reference=reference,
            others=others,
            views=_names(row["views"]),
            windows=_names(row["windows"]),
            flags=_flags(inputs, "text:"),
            label_flags=_flags(inputs, "label:"),
            chart=unit_chart(others) if len(others) > 1 else None,
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
        if filters.nb not in neighbourhoods():
            filters.nb = None
        return filters

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
                    "href": url_for("listing", audit_id=r["audit_id"]),
                }
                for r in rows
            ],
            label="Each listing's ask and its leave-own-row-out estimate with "
            "the 95% range for the typical rent",
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
        nb = nb if nb in neighbourhoods() else None
        clauses, params = [], []
        if q:
            clauses.append("b.search LIKE ? ESCAPE '\\'")
            params.append("%" + _escape_like(q.lower()) + "%")
        if nb:
            clauses.append("b.neighbourhood = ?")
            params.append(nb)
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
                    "href": url_for("listing", audit_id=p["audit_id"]),
                }
                for p in points
            ],
            label="Each listing's ask against its leave-own-row-out estimate, "
            "in percent, over time",
        )
        return render_template(
            "building.html",
            typical=building_typical(building_id),
            estimate_form=estimate_build.available(db()),
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

    @app.get("/estimate")
    def estimate_apartment():
        kit, unavailable = estimate_build.read(db())
        form = estimate.Form.parse(request.args)
        building_id = (request.args.get("building") or "").strip()[:200]
        q = (request.args.get("q") or "").strip()[:80]
        b = (
            db()
            .execute("SELECT * FROM buildings WHERE id = ?", (building_id,))
            .fetchone()
            if building_id
            else None
        )
        matches = []
        if b is None and q:
            matches = [
                dict(m_)
                for m_ in db()
                .execute(
                    "SELECT b.id, b.name, b.address, b.neighbourhood, b.bbl, "
                    "b.year_built, b.floors, b.listings, b.first_period, "
                    "(SELECT l.elevator FROM listings l WHERE l.building_id = b.id "
                    "AND l.elevator IS NOT NULL ORDER BY l.period DESC LIMIT 1) "
                    "AS elevator FROM buildings b "
                    "WHERE b.search LIKE ? ESCAPE '\\' ORDER BY b.sort_key LIMIT 25",
                    ("%" + _escape_like(q.lower()) + "%",),
                )
                .fetchall()
            ]
            # Two choices can share an address and tax lot (playtest round 4: "Ava
            # High Line" and "507 West Chelsea", separate towers with no units in
            # common); say so, so they can be told apart.
            for m_ in matches:
                m_["same"] = [
                    o["name"] or o["address"]
                    for o in matches
                    if o is not m_
                    and o["bbl"] is not None
                    and o["bbl"] == m_["bbl"]
                    and o["address"].lower() == m_["address"].lower()
                ]
            if len(matches) == 1:
                b = (
                    db()
                    .execute(
                        "SELECT * FROM buildings WHERE id = ?", (matches[0]["id"],)
                    )
                    .fetchone()
                )
        result = parts = facts = None
        if kit is not None and b is not None:
            terms = estimate_build.building(db(), b["id"])
            if terms is not None:
                x = estimate.encode(form, kit, terms.inputs)
                today = dt.datetime.now(dt.UTC).date()
                result = estimate.score(
                    kit,
                    terms,
                    x,
                    form.bedrooms,
                    today,
                    seed=f"{b['id']}|{today}|{form.canonical()}",  # not the ask
                    ask=form.ask,
                )
                result["day"] = today
                labels = dict(db().execute("SELECT name, label FROM terms"))
                labels["season"] = f"Season ({today.day} {today:%B})"
                parts = [
                    p | {"label": labels.get(p["group"], p["group"])}
                    for p in estimate.parts(kit, terms, x, form.bedrooms, today)
                ]
                facts = building_facts(x)
                # What the building's listings say, beside what the visitor set.
                facts["building"] = (
                    building_facts(
                        estimate.encode(
                            dataclasses.replace(form, elevator="", doorman=""),
                            kit,
                            terms.inputs,
                        )
                    )
                    if form.elevator or form.doorman
                    else dict(facts)
                )
                facts["set"] = {k for k in ("elevator", "doorman") if getattr(form, k)}

        def pick(chosen):
            args = {
                k: request.args.getlist(k)
                for k in estimate.FORM_KEYS
                if k in request.args
            }
            return (
                url_for("estimate_apartment", **(args | {"building": chosen}))
                + "#result"
            )

        return render_template(
            "estimate.html",
            meta=meta(),
            kit=kit,
            unavailable=unavailable,
            form=form,
            b=b,
            q=q,
            matches=matches,
            result=result,
            parts=parts,
            facts=facts,
            options=estimate,
            pick=pick,
        )

    @app.get("/estimates/map")
    def estimates_map():
        db()  # 503 before any publish
        return render_template(
            "estimates_map.html",
            meta=meta(),
            has_map=(database_path().parent / "map.json").is_file(),
        )

    @app.get("/estimates/map.json")
    def estimates_map_data():
        db()
        path = database_path().parent / "map.json"
        if not path.is_file():
            abort(404, description="No rent map for the served model yet.")
        response = Response(path.read_bytes(), mimetype="application/json")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/about")
    def about():
        return render_template("about.html", meta=meta(), terms=terms_list())

    def terms_list():
        return db().execute("SELECT * FROM terms ORDER BY position").fetchall()

    def fit_rows(f) -> list:
        rows = []
        if f["delta"] is not None:
            se = f" ± {f['delta_se']:,.1f}" if f["delta_se"] is not None else ""
            rows.append(["PSIS-LOO ΔELPD", f"{f['delta']:+,.1f}{se}"])
        rows.append(["Fit time", f"{f['minutes']:.1f} min"])
        if f["draws"]:
            rows.append(["Draws", f"{f['draws']:,}"])
        rows.append(["Tier", TIERS[f["tier"]]])
        rows.append(["Elegance", f["elegance"] or "not judged yet"])
        rows.append(
            [
                "Servable",
                {"yes": "yes", "unknown": "not known yet"}.get(
                    f["serve"], f"no: {f['why_not']}"
                ),
            ]
        )
        return rows

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
            hardware = TARGET_HARDWARE if TARGET_HARDWARE in classes else classes[0]
        days = snapshot_days(data)
        day = request.args.get("as_of")
        day = day if day in days else None
        subsets = request.args.get("subsets") == "1"
        full = request.args.get("range") == "full"
        view = frontier_view(data, hardware, day, m["provenance"]["run"], subsets)
        scored = [f for f in view["fits"] if f["delta"] is not None]
        floor = None if full else outlier_floor([f["delta"] for f in scored])
        target = hardware == TARGET_HARDWARE
        device = "the RTX 2060" if target else hardware
        time_points = [
            {
                "x": f["minutes"],
                "y": f["delta"],
                "kind": f["kind"],
                "tier": f["tier"],
                "draws": f["draws"],
                "group": f["group"],
                "faded": f["faded"],
                "title": f["entry"]["key"],
                "rows": fit_rows(f),
                "href": url_for("research_fit", key=f["entry"]["key"]),
            }
            for f in scored
        ]
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
            time_chart=charts.fit_scatter(
                time_points,
                label=f"Accuracy against fit time on {device}, one dot per fit",
                x_title=f"Fit time on {device}, full dataset (minutes)",
                y_title="PSIS-LOO ΔELPD (higher is more accurate)",
                x_format=lambda v: f"{v:g}",
                y_format=charts.signed,
                y_floor=floor,
                x_line=(TARGET_MINUTES, "2-hour limit for a full fit")
                if target
                else None,
            ),
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
            hardware = TARGET_HARDWARE if TARGET_HARDWARE in classes else classes[0]
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
                    "title": e["id"],
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
            hardware = TARGET_HARDWARE if TARGET_HARDWARE in classes else classes[0]
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
                    "title": e["key"],
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
            served_units=served_unit_split(data, served_entry),
            reference=data.get("reference"),
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
            units=[
                e
                for e in data.get("entries", [])
                if "units" in (e.get("splits") or {})
                and e["splits"]["units"].get("delta") is not None
            ],
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
                key=lambda e: -e["vs_served"]["delta"],
            )[:8],
            reference=data.get("reference") if data else None,
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


def served_unit_split(data: dict, served: dict | None) -> dict | None:
    """The unit-split score of the served design and feature set: a passing
    fit first, then the one whose data rules differ least from the served
    fit's, then the newest. {entry, split, missing_rules, extra_rules,
    missed}, where missed lists the gate thresholds the fit fell short of."""
    if not served:
        return None
    ours = rules_of(served)

    def candidate(e):
        theirs = rules_of(e)
        return {
            "entry": e,
            "split": e["splits"]["units"],
            "missing_rules": [r for r in ours if r not in theirs],
            "extra_rules": [r for r in theirs if r not in ours],
        }

    found = [
        candidate(e)
        for e in data.get("entries", [])
        if e.get("design") == served.get("design")
        and e.get("feature_set") == served.get("feature_set")
        and (e.get("splits") or {}).get("units", {}).get("delta") is not None
    ]
    if not found:
        return None
    best = max(
        found,
        key=lambda c: (
            c["split"].get("passes") is True,
            -(len(c["missing_rules"]) + len(c["extra_rules"])),
            c["split"].get("completed_at") or "",
        ),
    )
    best["missed"] = gate_misses(best["split"], data.get("gate") or {})
    return best


def gate_misses(split: dict, gate: dict) -> list[str]:
    """The convergence thresholds a fit fell short of, in words."""
    out = []
    rhat, ess = split.get("max_rhat"), split.get("min_ess")
    if isinstance(rhat, (int, float)) and gate.get("rhat") and rhat >= gate["rhat"]:
        out.append(f"largest R-hat {rhat:.3f}; the gate needs below {gate['rhat']}")
    if isinstance(ess, (int, float)) and gate.get("ess") and ess <= gate["ess"]:
        out.append(
            f"smallest effective sample size {ess:,.0f}; the gate needs more than "
            f"{gate['ess']:,}"
        )
    return out


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


def _names(value) -> list[str]:
    return [v.replace("_", " ") for v in json.loads(value)] if value else []


def _flags(inputs: dict, prefix: str) -> list[str]:
    return [
        name.removeprefix(prefix).replace("_", " ")
        for name, value in inputs.items()
        if name.startswith(prefix) and value
    ]


def ordinal(n: int) -> str:
    n = int(n)
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


def trim_float(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):g}"


def _natural(text: str):
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text.upper())]


def building_facts(x: dict[str, float]) -> dict:
    """The elevator and doorman an apartment's model inputs say, in words."""
    return {
        "elevator": "no"
        if x.get("elevator=no")
        else ("not stated" if x.get("elevator=unknown") else "yes"),
        "doorman": next(
            (
                n.split("=", 1)[1].replace("_", " ")
                for n in x
                if n.startswith("doorman=")
            ),
            "not stated",
        ),
    }


def beds_label(value) -> str:
    if value is None:
        return "—"
    beds = round(value)
    return "Studio" if beds == 0 else f"{beds} BR"


def attr_label(kind: str, value) -> str | None:
    if value in (None, "", "unknown"):
        return None
    return LABELS.get(kind, {}).get(value, str(value).replace("_", " ").capitalize())
