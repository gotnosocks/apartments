"""Diagnostics tables for individual ads and building ad histories.

`python -m rentfrontier.drift_diagnostics publish` writes the site's `diagnostics/`
folder: `ads.parquet` (one row per held-out ad with basis counts, unmodeled ad
attributes and detector flags), `buildings.parquet`, `history.parquet` (every ad in
the latest dataset, sorted by building, unit and day) and `meta.json` (written last
with the sha256 of each parquet file).

`facts.py` opens `ads.parquet` and `history.parquet` through DuckDB with one thread
and a small memory limit, keyed by `listing_id` and by `building`. When the folder
is absent, `load` returns `None` so every page renders without diagnostics. When a
parquet file's sha256 does not match `meta.json`, `load` raises `Refused` so a page
never mixes files from two publishes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import threading
from collections.abc import Iterable
from pathlib import Path

import duckdb
from markupsafe import Markup, escape

FOLDER = "diagnostics"
ADS_TABLE = "ads.parquet"
HISTORY_TABLE = "history.parquet"
META = "meta.json"
HISTORY_CAP = 30
SERIES_CAP = 500

# Columns read from `ads.parquet` when enriching the Deals table.
DEAL_COLUMNS = (
    "listing_id",
    "unit_id",
    "unit",
    "unit_ads",
    "building_ads",
    "basis",
    "square_feet",
    "floor",
    "months_free",
    "first_ask",
    "days_on_market",
    "miss",
    "flags",
    "model_lo95",
    "model_lo80",
    "model_lo50",
    "model_hi50",
    "model_hi80",
    "model_hi95",
    "full_baths",
    "half_baths",
    "prev_ask",
)

CORE_FEATURE_NAMES = frozenset(
    {"square_feet", "floor", "months_free", "days_on_market", "first_ask"}
)

RENTER_FEATURE_LABELS: dict[str, str] = {
    "doorman": "Doorman",
    "building_doorman": "Doorman",
    "building_elevator": "Elevator",
    "laundry": "Laundry",
    "pet_policy": "Pet policy",
    "lease_term": "Lease term (months)",
    "year_built": "Year built",
}

# Detector codes in `ads.parquet["flags"]`: (chip label, explanation).
FLAGS: dict[str, tuple[str, str]] = {
    "beds_conflict": (
        "beds conflict",
        "The unit's ads carry more than one bedroom count.",
    ),
    "beds_jump": (
        "beds jump",
        "This ad's bedroom count differs from the unit's previous ad.",
    ),
    "ask_jump": (
        "ask jump",
        "The ask is over twice or under half the unit's previous ask.",
    ),
    "ppsf": (
        "price/ft²",
        "The ask per square foot is outside a plausible range.",
    ),
    "extreme": (
        "extreme gap",
        "The ask sits more than 4 standard deviations from the model.",
    ),
    "building_side": (
        "building side",
        "At least 80% of the building's held-out ads sit on one side of the 80% range.",
    ),
}

NO_TEXT = frozenset({"", "nan", "none", "<na>", "null"})


class Refused(Exception):
    """The diagnostics folder holds a table that does not match `meta.json`."""


def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _text(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return None if text.lower() in NO_TEXT else text


def _day(value) -> str | None:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = _text(value)
    return text[:10] if text else None


def _ordinal_day(iso_day: str | None) -> int | None:
    if not iso_day:
        return None
    try:
        return dt.date.fromisoformat(iso_day[:10]).toordinal()
    except ValueError:
        return None


def _usd(value: float) -> str:
    text = f"${abs(value):,.0f}"
    return ("−" if value < 0 and text != "$0" else "") + text


def _nice_ticks(lo: float, hi: float, count: int = 4) -> list[float]:
    if hi <= lo:
        hi = lo + max(abs(lo) * 0.1, 100.0)
    raw = (hi - lo) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(lo / step) * step
    ticks: list[float] = []
    value = start
    while value <= hi + step * 1e-9:
        ticks.append(round(value, 10))
        value += step
    if ticks[-1] < hi:
        ticks.append(ticks[-1] + step)
    return ticks


def flag_items(codes) -> list[dict[str, str]]:
    """Normalized detector flag dicts (`code`, `label`, `description`)."""
    if isinstance(codes, str):
        stripped = codes.strip()
        if stripped.startswith("["):
            try:
                codes = json.loads(stripped)
            except ValueError:
                codes = [stripped]
        else:
            codes = [stripped] if stripped else []
    elif isinstance(codes, (list, tuple)):
        codes = list(codes)
    else:
        codes = []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in codes:
        if not isinstance(raw, str):
            continue
        code = raw.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        if code in FLAGS:
            label, description = FLAGS[code]
        else:
            label = code[:24]
            description = f"Detector flag ({code[:40]})."
        out.append({"code": code, "label": label, "description": description})
    return out


def resolve_basis(
    unit_ads: int,
    building_ads: int | None = None,
    basis: str | None = None,
) -> str:
    """The estimate's basis: `unit`, `building`, or `area`."""
    if basis in ("unit", "building", "area"):
        return basis
    if unit_ads > 0:
        return "unit"
    if building_ads is not None and building_ads >= 5:
        return "building"
    return "area"


def basis_sentence(
    unit_ads: int,
    building_ads: int | None = None,
    basis: str | None = None,
) -> Markup:
    """One sentence stating what training ads the apartment's estimate rests on."""
    kind = resolve_basis(unit_ads, building_ads, basis)
    if kind == "unit" or unit_ads > 0:
        ads_word = "ad" if unit_ads == 1 else "ads"
        bldg = (
            f" ({building_ads:,} in the building)" if building_ads is not None else ""
        )
        return Markup(
            f"From <strong>{unit_ads:,}</strong> earlier {ads_word} the model "
            f"trained on for this unit{bldg}, its range is narrower than for a "
            "new apartment."
        )
    if kind == "building" and building_ads is not None:
        return Markup(
            "With <strong>none</strong> of its own earlier ads the model trained "
            f"on, this new apartment gets its estimate from <strong>{building_ads:,}"
            "</strong> training ads in the building."
        )
    if building_ads is not None:
        bldg_words = (
            "0 training ads in the building"
            if building_ads == 0
            else f"only {building_ads:,} training {'ad' if building_ads == 1 else 'ads'} in the building"
        )
        return Markup(
            "With <strong>none</strong> of its own earlier ads the model trained "
            f"on and {bldg_words}, this new apartment gets its estimate from its "
            "area, layout and date."
        )
    return Markup(
        "With <strong>none</strong> of its own earlier ads the model trained on, "
        "this new apartment gets its estimate from its building, area, layout and "
        "date."
    )


def _extra_features(raw: dict, meta: dict) -> list[dict[str, str]]:
    """Concise renter-relevant ad and building attributes from `meta["features"]`."""
    specs = meta.get("features")
    if not isinstance(specs, list):
        return []
    seen_labels: set[str] = set()
    out: list[dict[str, str]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if (
            not isinstance(name, str)
            or name in CORE_FEATURE_NAMES
            or name not in RENTER_FEATURE_LABELS
            or name not in raw
        ):
            continue
        label = RENTER_FEATURE_LABELS[name]
        if label in seen_labels:
            continue
        kind = spec.get("kind")
        val = raw.get(name)
        if kind == "flag":
            if val is True or (_finite(val) or 0.0) > 0.0:
                seen_labels.add(label)
                out.append({"name": name, "label": label, "value": "yes"})
        elif kind == "number":
            num = _finite(val)
            if num is not None and not (name == "lease_term" and num == 12.0):
                seen_labels.add(label)
                out.append({"name": name, "label": label, "value": f"{num:g}"})
        else:
            txt = _text(val)
            if txt is not None and txt.lower() not in {"unstated", "none", "no"}:
                seen_labels.add(label)
                out.append(
                    {"name": name, "label": label, "value": txt.replace("_", " ")}
                )
    return out


def _normalize_ad(raw: dict, meta: dict) -> dict:
    unit_ads = int(_finite(raw.get("unit_ads")) or 0)
    b_num = _finite(raw.get("building_ads"))
    building_ads = int(b_num) if b_num is not None else None
    basis = resolve_basis(unit_ads, building_ads, _text(raw.get("basis")))
    ask = _finite(raw.get("ask"))
    first_ask = _finite(raw.get("first_ask"))
    if first_ask is not None and first_ask <= 0:
        first_ask = None
    months_free = _finite(raw.get("months_free"))
    if months_free is not None and months_free <= 0:
        months_free = None
    sqft = _finite(raw.get("square_feet"))
    if sqft is not None and sqft <= 0:
        sqft = None
    dom = _finite(raw.get("days_on_market"))
    if dom is not None and dom < 0:
        dom = None
    cut_usd = cut_pct = None
    if (
        ask is not None
        and first_ask is not None
        and not months_free
        and first_ask - ask >= 1.0
    ):
        cut_usd = first_ask - ask
        cut_pct = 100.0 * cut_usd / first_ask
    return {
        "listing_id": _text(raw.get("listing_id")),
        "source": _text(raw.get("source")),
        "building": _text(raw.get("building")),
        "address": _text(raw.get("address")),
        "unit_id": _text(raw.get("unit_id")),
        "unit": _text(raw.get("unit")),
        "neighbourhood": _text(raw.get("neighbourhood")),
        "day": _day(raw.get("day")),
        "status": _text(raw.get("status")),
        "bedrooms": _finite(raw.get("bedrooms")),
        "full_baths": _finite(raw.get("full_baths")),
        "half_baths": _finite(raw.get("half_baths")),
        "ask": ask,
        "model_median": _finite(raw.get("model_median")),
        "model_lo95": _finite(raw.get("model_lo95")),
        "model_lo80": _finite(raw.get("model_lo80")),
        "model_lo50": _finite(raw.get("model_lo50")),
        "model_hi50": _finite(raw.get("model_hi50")),
        "model_hi80": _finite(raw.get("model_hi80")),
        "model_hi95": _finite(raw.get("model_hi95")),
        "gap": _finite(raw.get("gap")),
        "miss": _finite(raw.get("miss")),
        "pit": _finite(raw.get("pit")),
        "z": _finite(raw.get("z")),
        "unit_ads": unit_ads,
        "building_ads": building_ads,
        "basis": basis,
        "prev_ask": _finite(raw.get("prev_ask")),
        "prev_day": _day(raw.get("prev_day")),
        "prev_bedrooms": _finite(raw.get("prev_bedrooms")),
        "square_feet": sqft,
        "floor": _finite(raw.get("floor")),
        "months_free": months_free,
        "first_ask": first_ask,
        "cut_usd": cut_usd,
        "cut_pct": cut_pct,
        "days_on_market": dom,
        "flags": flag_items(raw.get("flags")),
        "extra_features": _extra_features(raw, meta),
    }


def _normalize_history_row(raw: dict) -> dict:
    beds = _finite(raw.get("bedrooms"))
    baths = _finite(raw.get("full_baths"))
    return {
        "listing_id": _text(raw.get("listing_id")),
        "building": _text(raw.get("building")),
        "unit_id": _text(raw.get("unit_id")),
        "unit": _text(raw.get("unit")),
        "day": _day(raw.get("day")),
        "ask": _finite(raw.get("ask")),
        "bedrooms": beds,
        "full_baths": baths,
        "heldout": bool(raw.get("heldout")),
    }


def building_asks_svg(
    series: list[dict],
    *,
    listing_id: str,
    unit_id: str | None,
    current_day: str | None,
    current_ask: float | None,
    beds_text: str,
) -> Markup:
    """Small SVG scatter of a building's asks over time for one bedroom count,
    with the current ad marked."""
    others: list[tuple[int, float, dict]] = []
    for row in series:
        if row.get("listing_id") == listing_id:
            continue
        ord_day = _ordinal_day(row.get("day"))
        ask = _finite(row.get("ask"))
        if ord_day is not None and ask is not None and ask > 0:
            others.append((ord_day, ask, row))
    cur_ord = _ordinal_day(current_day)
    cur_ask = _finite(current_ask)
    has_current = cur_ord is not None and cur_ask is not None and cur_ask > 0
    if not others and not (series and has_current):
        return Markup("")

    xs = [d for d, _, _ in others] + ([cur_ord] if has_current else [])
    ys = [a for _, a, _ in others] + ([cur_ask] if has_current else [])
    x0, x1 = min(xs), max(xs)
    if x1 == x0:
        x0, x1 = x0 - 180, x1 + 180
    else:
        pad_x = max(14, round((x1 - x0) * 0.04))
        x0, x1 = x0 - pad_x, x1 + pad_x

    ylo, yhi = min(ys), max(ys)
    ypad = (yhi - ylo) * 0.08 or yhi * 0.08 or 100.0
    yticks = _nice_ticks(max(0.0, ylo - ypad), yhi + ypad, count=4)
    y0, y1 = yticks[0], yticks[-1]

    width, height = 640, 185
    left, right, top, bottom = 60, width - 16, 14, height - 28

    def sx(day_ord: int) -> float:
        return left + (day_ord - x0) / (x1 - x0) * (right - left)

    def sy(val: float) -> float:
        return bottom - (val - y0) / (y1 - y0) * (bottom - top)

    parts: list[str] = []
    for tick in yticks:
        y = sy(tick)
        parts.append(
            f'<line class="grid" x1="{left}" x2="{right}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{left - 8}" y="{y + 4:.1f}" '
            f'text-anchor="end">{escape(_usd(tick))}</text>'
        )

    span = x1 - x0
    if span < 700:
        months: list[dt.date] = []
        cursor = dt.date.fromordinal(x0).replace(day=1)
        while cursor.toordinal() <= x1:
            if cursor.toordinal() >= x0:
                months.append(cursor)
            cursor = (cursor + dt.timedelta(days=32)).replace(day=1)
        step = max(1, math.ceil(len(months) / 6))
        xticks = [(sx(m.toordinal()), m.strftime("%b %Y")) for m in months[::step]]
    else:
        first_y = dt.date.fromordinal(x0).year
        last_y = dt.date.fromordinal(x1).year
        years = list(range(first_y, last_y + 1))
        step = max(1, math.ceil(len(years) / 6))
        xticks = [
            (sx(dt.date(y, 1, 1).toordinal()), str(y))
            for y in years[::step]
            if x0 <= dt.date(y, 1, 1).toordinal() <= x1
        ]
    for x, text in xticks:
        parts.append(
            f'<text class="tick" x="{x:.1f}" y="{bottom + 18}" '
            f'text-anchor="middle">{escape(text)}</text>'
        )
    parts.append(
        f'<line class="axis" x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}"/>'
    )

    hover: list[dict] = []
    has_same_unit = False
    has_other_unit = False
    for ord_day, ask, row in others:
        x, y = sx(ord_day), sy(ask)
        same_unit = bool(unit_id and row.get("unit_id") == unit_id)
        if same_unit:
            has_same_unit = True
            cls, radius = "dot s3", 4.5
        else:
            has_other_unit = True
            cls, radius = "dot s1", 3.8
        unit_name = row.get("unit") or row.get("unit_id") or "Unit"
        day_str = row.get("day") or ""
        tip = f"{unit_name} ({day_str}): {_usd(ask)}"
        parts.append(
            f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{radius}">'
            f"<title>{escape(tip)}</title></circle>"
        )
        hover.append(
            {
                "x": round(x, 1),
                "y": round(y, 1),
                "title": f"{unit_name} · {day_str}",
                "rows": [["Ask", _usd(ask)]],
                "href": f"/listings/{row['listing_id']}"
                if row.get("heldout") and row.get("listing_id")
                else None,
            }
        )

    if has_current and cur_ord is not None and cur_ask is not None:
        cx, cy = sx(cur_ord), sy(cur_ask)
        cur_tip = f"This ad ({current_day}): {_usd(cur_ask)}"
        parts.append(
            f'<circle class="this-ad-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="8.5"/>'
            f'<circle class="dot s2 this-ad" cx="{cx:.1f}" cy="{cy:.1f}" r="5.2">'
            f"<title>{escape(cur_tip)}</title></circle>"
        )
        hover.append(
            {
                "x": round(cx, 1),
                "y": round(cy, 1),
                "title": f"This ad · {current_day}",
                "rows": [["Ask", _usd(cur_ask)]],
            }
        )

    legend_items: list[str] = []
    if has_current and cur_ask is not None:
        legend_items.append(
            f'<span class="key"><span class="key-dot s2"></span>'
            f"This ad ({escape(_usd(cur_ask))})</span>"
        )
    if has_same_unit:
        legend_items.append(
            '<span class="key"><span class="key-dot s3"></span>'
            "Earlier ads of this unit</span>"
        )
    if has_other_unit:
        legend_items.append(
            f'<span class="key"><span class="key-dot s1"></span>'
            f"Other {escape(beds_text)} ads in building</span>"
        )
    legend = f'<div class="legend">{"".join(legend_items)}</div>'
    label = f"{beds_text} asks over time in this building, with this ad marked"
    data_json = json.dumps(hover, separators=(",", ":")).replace("<", "\\u003c")
    svg = (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)}" preserveAspectRatio="xMidYMid meet">'
        + "".join(parts)
        + "</svg>"
    )
    return Markup(
        f'<figure class="chart history-chart" data-chart="points" tabindex="0">'
        f"{legend}{svg}"
        f'<div class="chart-tip" hidden></div>'
        f'<script type="application/json" class="chart-data">{data_json}</script>'
        f"</figure>"
    )


class Table:
    """Published diagnostics tables (`ads.parquet` and `history.parquet`) over one
    single-threaded DuckDB connection."""

    def __init__(
        self,
        ads_path: Path,
        history_path: Path,
        meta: dict,
        stamp: tuple | None = None,
    ):
        self.ads_path = ads_path
        self.history_path = history_path
        self.meta = meta
        self.stamp = stamp
        self._lock = threading.Lock()
        self._connection = duckdb.connect()
        self._connection.execute("SET threads = 1")
        self._connection.execute("SET memory_limit = '256MB'")
        ads_quoted = str(ads_path).replace("'", "''")
        hist_quoted = str(history_path).replace("'", "''")
        self._connection.execute(
            f"CREATE VIEW ads AS SELECT * FROM read_parquet('{ads_quoted}')"
        )
        self._connection.execute(
            f"CREATE VIEW history AS SELECT * FROM read_parquet('{hist_quoted}')"
        )
        self.ad_columns = [
            d[0]
            for d in self._connection.execute("SELECT * FROM ads LIMIT 0").description
        ]
        self.history_columns = [
            d[0]
            for d in self._connection.execute(
                "SELECT * FROM history LIMIT 0"
            ).description
        ]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _rows(self, sql: str, params: list) -> list[dict]:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            names = [d[0] for d in cursor.description]
            return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]

    def _one(self, sql: str, params: list):
        with self._lock:
            return self._connection.execute(sql, params).fetchone()

    def ad(self, listing_id: str) -> dict | None:
        """Diagnostics row for one held-out ad by `listing_id`, or `None`."""
        key = str(listing_id or "").strip()
        if not key:
            return None
        order = " ORDER BY day DESC" if "day" in self.ad_columns else ""
        rows = self._rows(
            f"SELECT * FROM ads WHERE CAST(listing_id AS VARCHAR) = ?{order} LIMIT 1",
            [key],
        )
        return _normalize_ad(rows[0], self.meta) if rows else None

    def ads_by_id(self, listing_ids: Iterable[str]) -> dict[str, dict]:
        """Diagnostics fields keyed by `listing_id` for a set of market ads."""
        ids = sorted({str(i).strip() for i in listing_ids if i})
        if not ids:
            return {}
        cols = [c for c in DEAL_COLUMNS if c in self.ad_columns]
        if "listing_id" not in cols:
            return {}
        select_cols = ", ".join(f'"{c}"' for c in cols)
        rows = self._rows(
            f"SELECT {select_cols} FROM ads WHERE CAST(listing_id AS VARCHAR) = ANY(?)",
            [ids],
        )
        out: dict[str, dict] = {}
        for raw in rows:
            norm = _normalize_ad(raw, {})
            if norm["listing_id"]:
                out[norm["listing_id"]] = norm
        return out

    def evidence(
        self,
        *,
        listing_id: str,
        building: str | None,
        unit_id: str | None = None,
        bedrooms: float | None = None,
        current_day: str | None = None,
        current_ask: float | None = None,
        beds_text: str = "same-bedroom",
    ) -> dict:
        """Unit history, same-bedroom building ads (newest first, capped at 30) and
        an inline SVG of the building's asks over time for that bedroom count."""
        lid = str(listing_id or "").strip()
        bldg = _text(building)
        uid = _text(unit_id)
        if not bldg:
            return {
                "unit_rows": [],
                "unit_total": 0,
                "building_rows": [],
                "building_total": 0,
                "chart": Markup(""),
            }

        unit_rows: list[dict] = []
        unit_total = 0
        if uid:
            u_clauses = [
                "building = ?",
                "CAST(unit_id AS VARCHAR) = ?",
                "CAST(listing_id AS VARCHAR) <> ?",
            ]
            u_params: list = [bldg, uid, lid]
            if current_day:
                u_clauses.append("(day IS NULL OR CAST(day AS VARCHAR) <= ?)")
                u_params.append(current_day)
            u_where = " AND ".join(u_clauses)
            unit_total = int(
                self._one(f"SELECT COUNT(*) FROM history WHERE {u_where}", u_params)[0]
            )
            raw_unit = self._rows(
                f"SELECT * FROM history WHERE {u_where} "
                f"ORDER BY day DESC NULLS LAST, listing_id DESC LIMIT ?",
                [*u_params, HISTORY_CAP],
            )
            unit_rows = [_normalize_history_row(r) for r in raw_unit]

        building_rows: list[dict] = []
        building_total = 0
        chart = Markup("")
        if bedrooms is not None and math.isfinite(bedrooms):
            beds_num = round(float(bedrooms))
            b_clauses = [
                "building = ?",
                "bedrooms IS NOT NULL",
                "ROUND(bedrooms) = ?",
                "CAST(listing_id AS VARCHAR) <> ?",
            ]
            b_params: list = [bldg, beds_num, lid]
            if uid:
                b_clauses.append("(unit_id IS NULL OR CAST(unit_id AS VARCHAR) <> ?)")
                b_params.append(uid)
            b_where = " AND ".join(b_clauses)
            building_total = int(
                self._one(f"SELECT COUNT(*) FROM history WHERE {b_where}", b_params)[0]
            )
            raw_bldg = self._rows(
                f"SELECT * FROM history WHERE {b_where} "
                f"ORDER BY day DESC NULLS LAST, listing_id DESC LIMIT ?",
                [*b_params, HISTORY_CAP],
            )
            building_rows = [_normalize_history_row(r) for r in raw_bldg]

            raw_series = self._rows(
                "SELECT * FROM history "
                "WHERE building = ? AND bedrooms IS NOT NULL AND ROUND(bedrooms) = ? "
                "AND day IS NOT NULL AND ask IS NOT NULL AND ask > 0 "
                "ORDER BY day ASC, listing_id ASC LIMIT ?",
                [bldg, beds_num, SERIES_CAP],
            )
            series = [_normalize_history_row(r) for r in raw_series]
            chart = building_asks_svg(
                series,
                listing_id=lid,
                unit_id=uid,
                current_day=current_day,
                current_ask=current_ask,
                beds_text=beds_text,
            )

        return {
            "unit_rows": unit_rows,
            "unit_total": unit_total,
            "building_rows": building_rows,
            "building_total": building_total,
            "chart": chart,
        }


_open: dict[tuple, Table] = {}
_open_lock = threading.Lock()
_refused: set[tuple] = set()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_sha(meta: dict, stem: str, filename: str) -> str | None:
    """The sha256 recorded in `meta` for `filename` (`ads.parquet` or `ads`)."""
    shas = meta.get("sha256")
    if isinstance(shas, dict):
        found = shas.get(filename) or shas.get(stem)
        if isinstance(found, str):
            return found
    direct = meta.get(f"{stem}_sha256")
    if isinstance(direct, str):
        return direct
    files = meta.get("files")
    if isinstance(files, dict):
        found = files.get(filename) or files.get(stem)
        if isinstance(found, str):
            return found
    return None


def load(root: Path) -> Table | None:
    """Open the published `diagnostics/` tables, or return `None` when absent.
    Raises `Refused` when a parquet file does not match its sha256 in `meta.json`."""
    folder = Path(root) / FOLDER
    ads_path = folder / ADS_TABLE
    history_path = folder / HISTORY_TABLE
    meta_path = folder / META
    try:
        ads_stat = ads_path.stat()
        hist_stat = history_path.stat()
        meta_stat = meta_path.stat()
    except OSError:
        return None

    stamp = (
        str(folder.resolve()),
        ads_stat.st_mtime_ns,
        ads_stat.st_size,
        hist_stat.st_mtime_ns,
        hist_stat.st_size,
        meta_stat.st_mtime_ns,
        meta_stat.st_size,
    )
    with _open_lock:
        found = _open.get(stamp)
        if found is not None:
            return found
        refused = Refused(
            "The published diagnostics do not match their record, so they are not "
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
        ads_ok = expected_sha(meta, "ads", ADS_TABLE) == _sha256(ads_path)
        hist_ok = expected_sha(meta, "history", HISTORY_TABLE) == _sha256(history_path)
        if not (ads_ok and hist_ok):
            _refused.clear()
            _refused.add(stamp)
            raise refused
        for old in _open.values():
            old.close()
        _open.clear()
        found = _open[stamp] = Table(ads_path, history_path, meta, stamp=stamp)
        return found
