"""The listings site: a Flask app over the published tables.

Deals (`/` and `/deals`) reads `<root>/deals/`, Estimates (`/estimates`, `/listings`,
`/listings.csv` and `/listings/<key>`) reads `<root>/estimates/`, Workbench and
`/about` read `<root>/diagnostics/`, Tags reads and appends `<root>/tags/tags.jsonl`,
and `/new-jersey` reads the `observed` table in `<root>/current/site.sqlite` when
present. Filters are parsed leniently: invalid values are ignored rather than turned
into error pages.
"""

from __future__ import annotations

import csv
import datetime as dt
import functools
import gzip
import hashlib
import io
import json
import logging
import math
import os
import sqlite3
import statistics
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
    url_for,
)

from . import (
    boroughs,
    charts,
    deals,
    facts,
    observed,
    streetview,
    tags,
    workbench,
)
from . import estimates as estimates_table

log = logging.getLogger("apartments.site")

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
DEFAULT_HOSTS = ("localhost", "127.0.0.1", "[::1]")

SECTIONS = {
    "deals": ("index", "deals_page"),
    "estimates": (
        "estimates",
        "listings",
        "listing",
        "observed_listings",
        "about",
    ),
    "workbench": (
        "workbench",
        "workbench_signals",
        "workbench_signal",
        "workbench_triage",
        "workbench_buildings",
        "workbench_building",
    ),
    "tags": (
        "tags_ledger",
        "tags_post",
        "tags_jsonl",
        "tags_csv",
    ),
}


def section_of(endpoint: str | None) -> str | None:
    return next((k for k, v in SECTIONS.items() if endpoint in v), None)


def _default_order(sort: str) -> str:
    return "desc" if sort == "date" else "asc"


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
        default_order = _default_order(self.sort)
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
            "order": None if self.order == _default_order(self.sort) else self.order,
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


def _query(args: dict) -> str:
    return urlencode(args, doseq=True)


def _asset_versions(static: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:10]
        for p in static.iterdir()
        if p.is_file()
    }


def _footer_meta(root: Path) -> dict[str, str] | None:
    """Model name and scoring day from `estimates/meta.json` or `diagnostics/meta.json`."""
    for folder in ("estimates", "diagnostics"):
        data, _ = deals._file(root / folder, "meta.json")
        if not isinstance(data, dict):
            continue
        model = str(data.get("model") or "").strip()
        scoring_day = str(data.get("scoring_day") or "").strip()[:10]
        if model or scoring_day:
            return {"model": model, "scoring_day": scoring_day}
    return None


@functools.lru_cache(maxsize=2)
def _rent_map(path: str, mtime: float) -> dict:
    """A build's map.json, read once per file version, with a building index."""
    data = json.loads(Path(path).read_text())
    data["_index"] = {b["id"]: i for i, b in enumerate(data.get("buildings", []))}
    return data


def create_app(
    root: Path | str | None = None,
    *,
    allowed_hosts=None,
) -> Flask:
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

    def db_or_none() -> sqlite3.Connection | None:
        if "db" not in g:
            path = database_path()
            if not path.is_file():
                return None
            conn = sqlite3.connect(
                f"file:{quote(str(path))}?mode=ro&immutable=1", uri=True
            )
            conn.row_factory = sqlite3.Row
            g.db = conn
        return g.db

    def sqlite_meta() -> dict:
        conn = db_or_none()
        if conn is None:
            return {}
        if "sqlite_meta" not in g:
            try:
                g.sqlite_meta = {
                    row["key"]: json.loads(row["value"])
                    for row in conn.execute(
                        "SELECT key, value FROM meta "
                        "WHERE key NOT IN ('story_checks', 'story_scans')"
                    )
                }
            except sqlite3.Error:
                g.sqlite_meta = {}
        return g.sqlite_meta

    def street_view(building_id, latitude=None, longitude=None, address=None):
        """A Street View link from the building's street, facing it."""
        path = database_path().parent / "map.json"
        try:
            data = _rent_map(str(path), path.stat().st_mtime)
        except (OSError, ValueError):
            data = None
        return streetview.link(data, building_id, latitude, longitude, address)

    app.jinja_env.globals["street_view"] = street_view

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
            return Response(
                f"{error.code} {error.name}\n", error.code, mimetype="text/plain"
            )
        page = render_template("error.html", code=error.code, message=error.description)
        return page, error.code

    @app.errorhandler(500)
    def server_error(error):
        log.exception("server error")
        return render_template(
            "error.html", code=500, message="Something went wrong."
        ), 500

    app.jinja_env.filters["trim_float"] = trim_float
    app.jinja_env.filters["minus"] = lambda text: str(text).replace("-", "−")
    app.jinja_env.tests["finite"] = lambda v: (
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    )

    @app.context_processor
    def helpers():
        def static_url(name):
            return url_for("static", filename=name, v=versions.get(name))

        def page_url(endpoint, filters, **changes):
            query = _query(filters.args(**changes))
            base = url_for(endpoint, **(request.view_args or {}))
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
            "section": section_of(request.endpoint),
            "footer_meta": _footer_meta(root),
            "sort_url": sort_url,
            "page_url": page_url,
            "static_url": static_url,
            "usd": charts.usd,
            "pct": charts.pct,
            "month": charts.month_label,
            "day": day_label,
            "beds_label": beds_label,
            "BEDROOMS": BEDROOMS,
            "STATUS": STATUS,
        }

    def _render_deals():
        try:
            data = deals.load(root)
        except facts.Refused as refused:
            log.error("diagnostics refused: %s", refused)
            abort(503, description=str(refused))
        if data is None:
            abort(503, description="No deals table has been published yet.")
        c = deals.choice(request.args)
        rows = deals.choose(data["rows"], c)
        hidden = deals.hidden_counts(data["rows"], c, len(rows))
        page_rows, cur_page, pages = deals.paginate(rows, c.page)
        c.page = cur_page
        base_url = url_for(request.endpoint or "index")

        def deals_url(**changes) -> str:
            query = _query(c.args(**changes))
            return f"{base_url}?{query}" if query else base_url

        return render_template(
            "deals.html",
            info=data["meta"],
            validation=data["validation"],
            hood_groups=data["hood_groups"],
            multi_borough=len(set(data["hood_groups"]) & set(boroughs.BOROUGHS)) > 1,
            has_diagnostics=data["has_diagnostics"],
            rows=page_rows,
            pages=pages,
            page_size=deals.SHOWN,
            base_url=base_url,
            next_url=deals_url(),
            total=len(rows),
            current=len(data["rows"]),
            hidden=hidden,
            deals_url=deals_url,
            choice=c,
            sorts=deals.SORTS,
            bedrooms=deals.BEDROOMS,
        )

    @app.get("/")
    def index():
        return _render_deals()

    @app.get("/deals")
    def deals_page():
        return _render_deals()

    def estimates_or_503() -> estimates_table.Table:
        """The published estimates, or 503 when absent or mismatched."""
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
            abort(
                404,
                description="The model holds an estimate only for the ads it held out: "
                "the newest ad of each apartment, and the ads on the market. This ad is "
                "not one of them, or its id is not one the site knows.",
            )
        info = table.meta
        try:
            diag = facts.load(root)
        except facts.Refused as refused:
            log.error("diagnostics refused: %s", refused)
            abort(503, description=str(refused))
        try:
            wb = workbench.load(root)
        except workbench.Refused as refused:
            log.error("workbench diagnostics refused: %s", refused)
            abort(503, description=str(refused))
        has_workbench_building = wb is not None and wb.has_building(row.get("building"))
        ad_facts = diag.ad(str(row["listing_id"])) if diag is not None else None
        unit_ads = (
            ad_facts["unit_ads"]
            if ad_facts is not None
            else int(row.get("unit_ads") or 0)
        )
        building_ads = ad_facts["building_ads"] if ad_facts is not None else None
        basis_kind = ad_facts["basis"] if ad_facts is not None else None
        basis = facts.basis_sentence(unit_ads, building_ads, basis_kind)
        evidence = None
        if diag is not None:
            evidence = diag.evidence(
                listing_id=str(row["listing_id"]),
                building=row.get("building"),
                unit_id=(ad_facts or {}).get("unit_id") or row.get("unit_id"),
                bedrooms=row.get("bedrooms"),
                current_day=row.get("day") or info.get("scoring_day"),
                current_ask=row.get("ask"),
                beds_text=beds_label(row.get("bedrooms")),
            )
        lo, hi = row["model_lo95"], row["model_hi95"]
        mid_est = row["model_median"]
        gap_pct = (
            100.0 * (mid_est - row["ask"]) / mid_est
            if mid_est and mid_est > 0
            else None
        )
        current_tag, tag_history = tags.for_listing(root, str(row["listing_id"]))
        return render_template(
            "listing.html",
            info=info,
            row=row,
            ad_facts=ad_facts,
            basis=basis,
            evidence=evidence,
            has_workbench_building=has_workbench_building,
            current_tag=current_tag,
            tag_history=tag_history,
            under_words=deals.under_words(gap_pct) if gap_pct is not None else None,
            run=(info.get("runs") or {}).get(row["source"]),
            gate=(info.get("gate") or {}).get(row["source"]),
            chart=charts.interval_strip(
                row["ask"],
                mid_est,
                [
                    (50, row["model_lo50"], row["model_hi50"]),
                    (80, row["model_lo80"], row["model_hi80"]),
                    (95, lo, hi),
                ],
            ),
        )

    def has_observed() -> bool:
        conn = db_or_none()
        if conn is None:
            return False
        try:
            return (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'observed'"
                ).fetchone()
                is not None
            )
        except sqlite3.Error:
            return False

    def observed_areas() -> dict[str, int]:
        if not has_observed():
            return {}
        conn = db_or_none()
        if conn is None:
            return {}
        return dict(
            conn.execute(
                "SELECT neighbourhood, COUNT(*) FROM observed "
                "GROUP BY neighbourhood ORDER BY neighbourhood"
            ).fetchall()
        )

    @app.get("/new-jersey")
    def observed_listings():
        areas = observed_areas()
        filters = ObservedFilters(request.args, areas)
        where, params = filters.where()
        rows, total, medians = [], 0, []
        conn = db_or_none()
        if areas and conn is not None:
            total = conn.execute(
                "SELECT COUNT(*) FROM observed" + where, params
            ).fetchone()[0]
            asks: dict[int, list[float]] = {}
            for beds, ask in conn.execute(
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
        if areas and conn is not None:
            rows = conn.execute(
                "SELECT * FROM observed"
                + where
                + filters.order_by()
                + " LIMIT ? OFFSET ?",
                [*params, filters.per, (filters.page - 1) * filters.per],
            ).fetchall()
        status = sqlite_meta().get("stats", {}).get("observed", {})
        query = _query(filters.args(page=None))
        csv_base = url_for("observed_csv")
        return render_template(
            "observed.html",
            areas=areas,
            filters=filters,
            rows=rows,
            total=total,
            pages=pages,
            medians=medians,
            left_out=status.get("left_out", {}),
            HIDDEN=observed.HIDDEN,
            csv_url=f"{csv_base}?{query}" if query else csv_base,
        )

    @app.get("/new-jersey.csv")
    def observed_csv():
        filters = ObservedFilters(request.args, observed_areas())
        where, params = filters.where()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(OBSERVED_CSV_COLUMNS)
        conn = db_or_none()
        if has_observed() and conn is not None:
            writer.writerows(
                conn.execute(
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

    @app.get("/about")
    def about():
        try:
            diag = facts.load(root)
        except facts.Refused as refused:
            log.error("diagnostics refused: %s", refused)
            abort(503, description=str(refused))
        return render_template(
            "about.html",
            diag=diag.about() if diag is not None else None,
        )

    @app.get("/healthz")
    def healthz():
        try:
            deals_data = deals.load(root)
            est_table = estimates_table.load(root)
        except (facts.Refused, estimates_table.Refused) as refused:
            response = jsonify(status="error", error=str(refused))
            response.headers["Cache-Control"] = "no-store"
            return response, 503
        if deals_data is None and est_table is None:
            response = jsonify(status="error", error="No published tables yet.")
            response.headers["Cache-Control"] = "no-store"
            return response, 503
        info = (
            est_table.meta
            if est_table is not None
            else (deals_data["meta"] if deals_data is not None else {})
        )
        response = jsonify(
            status="ok",
            model=info.get("model"),
            scoring_day=info.get("scoring_day"),
            deals=len(deals_data["rows"]) if deals_data is not None else 0,
            estimates=int((info.get("ads") or {}).get("all") or 0)
            if est_table is not None
            else 0,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/robots.txt")
    def robots():
        return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")

    workbench.register(app, lambda: root)
    tags.register(app, lambda: root)
    return app


def trim_float(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):g}"


def day_label(iso: str) -> str:
    """'2026-04-21' -> 'Apr 21, 2026'."""
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d:%b} {d.day}, {d.year}"


def beds_label(value) -> str:
    if value is None:
        return "—"
    beds = round(value)
    return "Studio" if beds == 0 else f"{beds} BR"
