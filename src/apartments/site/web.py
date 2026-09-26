"""The listings site: a read-only Flask app over the published SQLite snapshot.

Each request opens <root>/current/site.sqlite read-only (immutable), so a new
publish (`apartments.site.build`) is picked up by the next request. Filters are
parsed leniently: an invalid value is ignored, never an error page.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import logging
import math
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    render_template,
    request,
    stream_with_context,
    url_for,
)

from . import charts

log = logging.getLogger("apartments.site")

PER_PAGE = (25, 50, 100)
BEDROOMS = {"0": "Studio", "1": "1 BR", "2": "2 BR", "3": "3 BR", "4": "4+ BR"}
STATUS = {"all": "All listings", "current": "Available now", "past": "Past listings"}
BANDS = {
    "all": "Any price",
    "below": "Below typical",
    "typical": "Typical",
    "above": "Above typical",
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
        self.beds = [b for b in args.getlist("beds") if b in BEDROOMS]
        self.min_ask = _number(args.get("min_ask"))
        self.max_ask = _number(args.get("max_ask"))
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
            "beds": self.beds or None,
            "min_ask": _fmt_number(self.min_ask),
            "max_ask": _fmt_number(self.max_ask),
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
            or self.beds
            or self.min_ask is not None
            or self.max_ask is not None
            or self.year_from
            or self.year_to
            or self.status != "all"
            or self.band != "all"
        )


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


def create_app(root: Path | str | None = None, *, allowed_hosts=None) -> Flask:
    root = Path(root or os.environ.get("SITE_ROOT", "/data1/apartments/site"))
    app = Flask(__name__)
    if allowed_hosts is None:
        allowed_hosts = os.environ.get("SITE_ALLOWED_HOSTS", "").split(",")
    hosts = [h.strip().lower() for h in allowed_hosts if h.strip()]
    if any(h.startswith(".") or "*" in h for h in hosts):
        raise ValueError("Site allowed hosts must be exact hostnames")
    app.config["TRUSTED_HOSTS"] = [*DEFAULT_HOSTS, *hosts]
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 365 * 24 * 3600
    versions = _asset_versions(Path(app.static_folder))

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
            request.headers.get("X-Forwarded-For", request.remote_addr),
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

        return {
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
        }

    def listings_query(filters: Filters):
        where, params = filters.where()
        joined = " FROM listings l JOIN buildings b ON b.id = l.building_id"
        needs_join = "b." in where
        count_sql = "SELECT COUNT(*)" + (joined if needs_join else " FROM listings l")
        total = db().execute(count_sql + where, params).fetchone()[0]
        pages = max(1, math.ceil(total / filters.per))
        filters.page = min(filters.page, pages)
        rows = (
            db()
            .execute(
                "SELECT l.*, b.name AS building_name, b.address AS building_address"
                + joined
                + where
                + filters.order_by()
                + " LIMIT ? OFFSET ?",
                [*params, filters.per, (filters.page - 1) * filters.per],
            )
            .fetchall()
        )
        return rows, total, pages

    @app.get("/")
    def index():
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
            "index.html",
            meta=m,
            current=current,
            market=market,
            market_chart=chart,
        )

    @app.get("/listings")
    def listings():
        filters = Filters(request.args)
        rows, total, pages = listings_query(filters)
        return render_template(
            "listings.html",
            meta=meta(),
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
        filters = Filters(request.args)
        where, params = filters.where()
        cursor = db().execute(
            "SELECT "
            + ", ".join(f"l.{c}" for c in CSV_COLUMNS)
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
                writer.writerow(CSV_COLUMNS)
                for row in cursor:
                    writer.writerow(row)
                    if buffer.tell() > 64 * 1024:
                        yield buffer.getvalue()
                        buffer.seek(0)
                        buffer.truncate()
                yield buffer.getvalue()
            finally:
                connection.close()

        return Response(
            stream_with_context(generate()),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=listings.csv"},
        )

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
            abort(404, description="No listing with that id.")
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
        return render_template(
            "listing.html",
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
            "the estimate's 95% range",
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
            abort(404, description="No unit with that id.")
        rows = (
            db()
            .execute(
                "SELECT * FROM listings WHERE unit_id = ? ORDER BY period", (unit_id,)
            )
            .fetchall()
        )
        return render_template(
            "unit.html", meta=meta(), unit=row, rows=rows, chart=unit_chart(rows)
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
        where, params = "", []
        if q:
            where = " WHERE b.search LIKE ? ESCAPE '\\'"
            params = ["%" + _escape_like(q.lower()) + "%"]
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
                "sort": None if sort == "name" else sort,
                "order": None if order == default else order,
                "page": None if page == 1 else page,
            }
            args.update(changes)
            query = _query({k: v for k, v in args.items() if v is not None})
            return url_for("buildings") + (f"?{query}" if query else "")

        return render_template(
            "buildings.html",
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
            abort(404, description="No building with that id.")
        units = (
            db()
            .execute("SELECT * FROM units WHERE building_id = ?", (building_id,))
            .fetchall()
        )
        units = sorted(units, key=lambda u: _natural(u["label"] or ""))
        filters = Filters(request.args)
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
            meta=meta(),
            b=row,
            units=units,
            rows=rows,
            total=total,
            pages=pages,
            filters=filters,
            chart=chart,
        )

    @app.get("/model")
    def model_page():
        coefficients = (
            db()
            .execute("SELECT * FROM coefficients ORDER BY feature_group, feature")
            .fetchall()
        )
        terms = db().execute("SELECT * FROM terms ORDER BY position").fetchall()
        labels = {t["name"]: t["label"] for t in terms}
        return render_template(
            "model.html",
            meta=meta(),
            coefficients=coefficients,
            terms=terms,
            labels=labels,
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


def beds_label(value) -> str:
    if value is None:
        return "—"
    beds = round(value)
    return "Studio" if beds == 0 else f"{beds} BR"


def attr_label(kind: str, value) -> str | None:
    if value in (None, "", "unknown"):
        return None
    return LABELS.get(kind, {}).get(value, str(value).replace("_", " ").capitalize())
