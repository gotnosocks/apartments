"""The Workbench section: held-out residuals, signals, triage queue, and buildings.

`python -m rentfrontier.drift_diagnostics publish` writes the `diagnostics/` folder:
- `ads.parquet`: one row per held-out ad with its ask, predictive intervals, log gap,
  `miss` (the gap over the predictive spread), PIT, normal score `z`, prediction basis
  (`unit`, `building`, `area`), previous ad fields, detector flags, and attribute
  columns;
- `buildings.parquet`: one row per building in the latest fit with its posterior level
  and standard deviation, training and held-out ad counts, mean held-out gap, miss
  and z, and building-level attributes;
- `history.parquet`: one row per ad, ordered by building, unit, and day;
- `meta.json`: the runs, convergence gates, attribute definitions (`name`, `label`,
  `kind`, `level`, `in_model`, `after`), counts, and the SHA-256 digests of the three
  parquet tables.

This module opens a read-only DuckDB connection over those three parquet files with one
thread and a small memory limit, verifies their SHA-256 digests against `meta.json`
before serving any query, and registers the Workbench views on the Flask application
via `register(app, root_fn)`.

The pages order and threshold ads by `miss`. `z` comes from a finite number of draws
and stops near 3.5, so the pages read it only in the calibration table. `gap` is
ln(ask / middle); the pages show it as the percent difference of the ask from the
middle, 100 * (exp(gap) - 1), and the CSV keeps the log value. Each `Diagnostics`
object keeps its computed aggregates in a small cache, because the overview and the
signals page tabulate every attribute on each request.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import hashlib
import io
import json
import logging
import math
import re
import threading
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

import duckdb
from flask import Flask, Response, abort, render_template, request, url_for
from markupsafe import Markup, escape

from . import boroughs, charts, facts, tags
from .deals import LISTING, hood_label

log = logging.getLogger("apartments.site.workbench")

FOLDER = "diagnostics"
FILES = ("ads", "buildings", "history")
META = "meta.json"
PER_PAGE = 50
# A phone shows this many rows of a triage page until the reader asks for the rest.
PHONE_ROWS = 25
CSV_CHUNK = 5000
# A bin enters the rankings and gets an SE score with at least this many rows in at
# least this many buildings.
MIN_BIN_ADS = 30
MIN_BIN_BUILDINGS = 10
# The share of variance explained is shown for an attribute with at most this many bins.
MAX_EXPLAINED_BINS = 20
# The buildings list opens on buildings with at least this many held-out ads.
DEFAULT_MIN_ADS = 5
# List views draw at most this many bins of an attribute; its own page shows them all.
LIST_BINS = 6
# A strip label longer than this is cut, with the whole label in its title.
STRIP_LABEL_CHARS = 21
# A calibration slice with fewer ads than this is never marked off nominal.
MIN_CALIBRATION_ADS = 100
CACHE_ENTRIES = 64
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PIECE_RE = re.compile(r"~\d+$")

AD_CORE_COLUMNS = (
    "listing_id",
    "source",
    "building",
    "address",
    "unit_id",
    "unit",
    "neighbourhood",
    "day",
    "status",
    "bedrooms",
    "full_baths",
    "half_baths",
    "ask",
    "model_median",
    "model_lo95",
    "model_lo80",
    "model_lo50",
    "model_hi50",
    "model_hi80",
    "model_hi95",
    "gap",
    "miss",
    "pit",
    "z",
    "unit_ads",
    "building_ads",
    "basis",
    "prev_ask",
    "prev_day",
    "prev_bedrooms",
    "square_feet",
    "floor",
    "months_free",
    "first_ask",
    "days_on_market",
    "latitude",
    "longitude",
    "flags",
)

BUILDING_CORE_COLUMNS = (
    "building",
    "address",
    "latitude",
    "longitude",
    "neighbourhood",
    "zone",
    "level",
    "level_sd",
    "train_ads",
    "heldout_ads",
    "heldout_gap",
    "heldout_miss",
    "heldout_z",
)

HISTORY_CORE_COLUMNS = (
    "listing_id",
    "building",
    "unit_id",
    "unit",
    "day",
    "ask",
    "bedrooms",
    "full_baths",
    "heldout",
    "market",
)

# Detector code: the label a chip shows, and the rule behind it.
FLAGS = {
    "beds_conflict": (
        "bedroom counts conflict",
        "The unit's ads carry more than one bedroom count.",
    ),
    "beds_jump": (
        "bedrooms changed",
        "This ad's bedroom count differs from the unit's previous ad.",
    ),
    "ask_jump": (
        "ask jumped",
        "The ask is over twice or under half the unit's previous ask.",
    ),
    "ppsf": (
        "rent per sq ft out of range",
        "The ask per square foot is outside a plausible range.",
    ),
    "extreme": (
        "extreme miss",
        "The ask is more than 4 predictive spreads from the model's middle.",
    ),
    "building_side": (
        "building one-sided",
        "The building has at least 5 held-out ads, and at least 80% of them "
        "sit on the same side of the model's 80% range.",
    ),
}

# Attribute group: heading and the sentence under it on the signals page.
SIGNAL_GROUPS = {
    "none": (
        "No term in the model",
        "A trend here is a candidate for a new term.",
    ),
    "term": (
        "Already a term",
        "A trend here says the form of the term is wrong or the coded value is wrong.",
    ),
    "after": (
        "Known only after the ad has run",
        "These cannot be used for prediction. They help in reading asks: an ad "
        "that sat long was asking too much.",
    ),
}

SOURCES = {
    "latest": "Past ads",
    "market": "On the market",
}
SOURCE_ALIASES = {
    "latest": "latest",
    "past": "latest",
    "market": "market",
    "current": "market",
}

BASES = {
    "unit": "unit history",
    "building": "building",
    "area": "area",
    "non_unit": "no unit history",
}
BASIS_RULES = {
    "unit": "The fit read earlier ads of this unit.",
    "building": "The fit read at least 5 ads in the building and none of this unit.",
    "area": "The fit read fewer than 5 ads in the building and none of this unit.",
}

SIGNS = {
    "low": "Ask below the model's middle",
    "high": "Ask above the model's middle",
}

BEDROOMS = {
    "0": "Studio",
    "1": "1 BR",
    "2": "2 BR",
    "3": "3 BR",
    "4": "4+ BR",
}

SCOPES = {
    "non_unit": "Ads of units with no earlier ads",
    "latest": "Held-out past ads",
    "market": "Ads on the market",
    "all": "All held-out ads",
}
SCOPE_ALIASES = {
    "non_unit": "non_unit",
    "no_unit": "non_unit",
    "c": "non_unit",
    "latest": "latest",
    "past": "latest",
    "a": "latest",
    "market": "market",
    "current": "market",
    "b": "market",
    "all": "all",
}

GAP_TITLE = (
    "Percent difference of the ask from the model's middle: 100 * (ask / middle - 1)."
)
MEAN_GAP_TITLE = (
    "Mean of ln(ask / middle) over the ads, shown as a percent: 100 * (exp(mean) - 1)."
)
MISS_TITLE = (
    "Miss is ln(ask / middle) divided by the predictive spread. z is the same reading "
    "from the ask's quantile in the predictive distribution, and it stops near 3.5 "
    "because the fit has a finite number of draws, so miss orders the largest misses."
)
MAX_SCORE_TITLE = (
    f"Largest |bin mean minus the mean of all ads in scope| / SE, over bins of at "
    f"least {MIN_BIN_ADS} ads in at least {MIN_BIN_BUILDINGS} buildings, with "
    "standard errors clustered by building."
)
EXPLAINED_TITLE = (
    "Share of the variance of ln(ask / middle) explained by bin means, for an "
    f"attribute with at most {MAX_EXPLAINED_BINS} bins."
)
SMALL_BIN_TITLE = (
    f"Fewer than {MIN_BIN_ADS} rows or {MIN_BIN_BUILDINGS} buildings: no SE score."
)
MISS_SCORE_TITLE = (
    "|mean miss| times the square root of the held-out ads: the mean miss of a "
    "building in units of its standard error."
)


def _ratio_pct(log_value: float | None) -> float | None:
    """A log ratio as a percent difference, 100 * (exp(x) - 1)."""
    if log_value is None:
        return None
    try:
        return 100.0 * math.expm1(log_value)
    except OverflowError:
        return None


BUILDING_SORTS = {
    "miss": (
        "ABS(COALESCE(heldout_miss, 0)) "
        "* SQRT(GREATEST(COALESCE(heldout_ads, 0), 0)) DESC, building ASC",
        "Held-out miss (largest first)",
    ),
    "level": (
        "level DESC NULLS LAST, building ASC",
        "Building level (highest first)",
    ),
    "level_low": (
        "level ASC NULLS LAST, building ASC",
        "Building level (lowest first)",
    ),
}


class Refused(Exception):
    """The diagnostics folder holds a table that does not match its meta record."""


@dataclasses.dataclass
class SignalChoice:
    """Filters for `/workbench/signals` and `/workbench/signals/<feature>`."""

    scope: str = "non_unit"
    nb: str | None = None
    beds: list[str] = dataclasses.field(default_factory=list)
    hoods: list[str] | None = None

    def args(self, **changes) -> dict:
        items = {
            "scope": None if self.scope == "non_unit" else self.scope,
            "nb": self.nb,
            "beds": self.beds or None,
        }
        items.update(changes)
        return {k: v for k, v in items.items() if v not in (None, [], "")}

    def active(self) -> bool:
        return bool(self.scope != "non_unit" or self.nb or self.beds)

    def triage_args(self, feature: str, bin_key: str) -> dict:
        """Query parameters that open `/workbench/triage` on this signal bin."""
        out: dict[str, object] = {"feature": feature, "bin": bin_key}
        if self.scope == "non_unit":
            out["basis"] = "non_unit"
        elif self.scope in ("latest", "market"):
            out["source"] = self.scope
        if self.nb:
            out["nb"] = self.nb
        if self.beds:
            out["beds"] = self.beds
        return out


@dataclasses.dataclass
class TriageChoice:
    """Filters for `/workbench/triage` and `/workbench/triage.csv`."""

    source: str = ""
    flag: str = ""
    basis: str = ""
    sign: str = ""
    beds: list[str] = dataclasses.field(default_factory=list)
    nb: str | None = None
    feature: str | None = None
    bin: str | None = None
    min_miss: float | None = None
    q: str = ""
    untagged: bool = False
    page: int = 1
    hoods: list[str] | None = None
    # Listing ids with a current tag, read from the ledger when `untagged` is set.
    tagged: list[str] = dataclasses.field(default_factory=list)

    def args(self, **changes) -> dict:
        items = {
            "source": self.source or None,
            "flag": self.flag or None,
            "basis": self.basis or None,
            "sign": self.sign or None,
            "beds": self.beds or None,
            "nb": self.nb,
            "feature": self.feature,
            "bin": self.bin,
            "min_miss": _fmt(self.min_miss),
            "q": self.q or None,
            "untagged": "1" if self.untagged else None,
            "page": None if self.page == 1 else self.page,
        }
        items.update(changes)
        return {k: v for k, v in items.items() if v not in (None, [], "")}

    def active(self) -> bool:
        return bool(
            self.source
            or self.flag
            or self.basis
            or self.sign
            or self.beds
            or self.nb
            or self.feature
            or self.bin
            or self.min_miss is not None
            or self.q
            or self.untagged
        )


@dataclasses.dataclass
class BuildingChoice:
    """Filters for `/workbench/buildings`."""

    nb: str | None = None
    min_ads: int = DEFAULT_MIN_ADS
    sort: str = "miss"
    q: str = ""
    page: int = 1
    hoods: list[str] | None = None

    def args(self, **changes) -> dict:
        items = {
            "nb": self.nb,
            "min_ads": None if self.min_ads == DEFAULT_MIN_ADS else self.min_ads,
            "sort": None if self.sort == "miss" else self.sort,
            "q": self.q or None,
            "page": None if self.page == 1 else self.page,
        }
        items.update(changes)
        return {k: v for k, v in items.items() if v not in (None, [], "")}

    def active(self) -> bool:
        return bool(
            self.nb or self.min_ads != DEFAULT_MIN_ADS or self.sort != "miss" or self.q
        )


def _ident(name: str) -> str:
    """Quote a whitelisted SQL identifier."""
    if not IDENT_RE.fullmatch(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


def _finite(value) -> float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def _number(value) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _nonneg_int(value) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _page(value) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _fmt(value: float | None) -> str | None:
    return None if value is None else f"{value:g}"


def _fmt_num(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "-"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    if abs(value) >= 100:
        return f"{float(f'{value:.2g}'):,.0f}"
    return f"{value:,.2g}"


def _text(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return None if text.lower() in ("", "nan", "<na>", "null") else text


def areas(nb: str | None, hoods: dict[str, int]) -> list[str] | None:
    """The neighbourhood values a choice stands for, by value, label, or borough."""
    if not nb:
        return None
    named: dict[str, list[str]] = {}
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


def signal_choice(args, hoods: dict[str, int]) -> SignalChoice:
    """Parse filters for the signals pages from a query string."""
    raw_scope = (args.get("scope") or "").strip().lower()
    scope = SCOPE_ALIASES.get(raw_scope, "non_unit")
    nb = (args.get("nb") or "").strip()[:60] or None
    beds = [b for b in dict.fromkeys(args.getlist("beds")) if b in BEDROOMS]
    out = SignalChoice(scope=scope, nb=nb, beds=beds)
    out.hoods = areas(out.nb, hoods)
    if out.hoods is None:
        out.nb = None
    return out


def triage_choice(
    args,
    hoods: dict[str, int],
    valid_flags: set[str],
    valid_features: dict[str, dict],
) -> TriageChoice:
    """Parse filters for the triage queue from a query string."""
    raw_source = (args.get("source") or "").strip().lower()
    source = SOURCE_ALIASES.get(raw_source, "")
    raw_flag = (args.get("flag") or "").strip()
    flag = raw_flag if raw_flag in valid_flags or raw_flag == "any" else ""
    raw_basis = (args.get("basis") or "").strip().lower()
    basis = raw_basis if raw_basis in BASES else ""
    raw_sign = (args.get("sign") or "").strip().lower()
    sign = raw_sign if raw_sign in SIGNS else ""
    beds = [b for b in dict.fromkeys(args.getlist("beds")) if b in BEDROOMS]
    nb = (args.get("nb") or "").strip()[:60] or None
    raw_feat = (args.get("feature") or "").strip()
    feature = raw_feat if raw_feat in valid_features else None
    raw_bin = (args.get("bin") or "").strip()[:80] or None
    bin_key = raw_bin if feature is not None else None
    min_miss = _number(args.get("min_miss"))
    if min_miss is not None and min_miss < 0:
        min_miss = None
    q = (args.get("q") or "").strip()[:80]
    untagged = (args.get("untagged") or "").strip().lower() in ("1", "on", "true")
    out = TriageChoice(
        source=source,
        flag=flag,
        basis=basis,
        sign=sign,
        beds=beds,
        nb=nb,
        feature=feature,
        bin=bin_key,
        min_miss=min_miss,
        q=q,
        untagged=untagged,
        page=_page(args.get("page")),
    )
    out.hoods = areas(out.nb, hoods)
    if out.hoods is None:
        out.nb = None
    return out


def building_choice(args, hoods: dict[str, int]) -> BuildingChoice:
    """Parse filters for the buildings list from a query string."""
    nb = (args.get("nb") or "").strip()[:60] or None
    min_ads = _nonneg_int(args.get("min_ads"))
    if min_ads is None:
        min_ads = DEFAULT_MIN_ADS
    raw_sort = (args.get("sort") or "").strip().lower()
    sort = raw_sort if raw_sort in BUILDING_SORTS else "miss"
    q = (args.get("q") or "").strip()[:80]
    out = BuildingChoice(
        nb=nb,
        min_ads=min_ads,
        sort=sort,
        q=q,
        page=_page(args.get("page")),
    )
    out.hoods = areas(out.nb, hoods)
    if out.hoods is None:
        out.nb = None
    return out


def _beds_clause(beds: list[str]) -> tuple[str, list]:
    parts, params = [], []
    for b in beds:
        if b == "4":
            parts.append("bedrooms >= 4")
        else:
            parts.append("bedrooms = ?")
            params.append(float(b))
    return "(" + " OR ".join(parts) + ")", params


def _is_numeric_type(col_type: str) -> bool:
    upper = col_type.upper()
    return any(
        k in upper
        for k in ("DOUBLE", "FLOAT", "REAL", "DECIMAL", "INT", "BIGINT", "HUGEINT")
    )


def _missing_cond(col_sql: str, kind: str, col_type: str) -> str:
    """SQL condition matching rows where a feature value is missing."""
    if kind == "number" or _is_numeric_type(col_type):
        return f"({col_sql} IS NULL OR isnan(CAST({col_sql} AS DOUBLE)))"
    if "BOOL" in col_type.upper():
        return f"({col_sql} IS NULL)"
    return (
        f"({col_sql} IS NULL OR trim(CAST({col_sql} AS VARCHAR)) = '' "
        f"OR lower(trim(CAST({col_sql} AS VARCHAR))) IN ('nan', '<na>', 'null'))"
    )


def _flag_bin_expr(col_sql: str, col_type: str) -> str:
    """SQL CASE expression mapping a flag column to 'yes', 'no', or 'missing'."""
    upper = col_type.upper()
    if "BOOL" in upper:
        return (
            f"CASE WHEN {col_sql} IS NULL THEN 'missing' "
            f"WHEN {col_sql} THEN 'yes' ELSE 'no' END"
        )
    if _is_numeric_type(upper):
        return (
            f"CASE WHEN {col_sql} IS NULL OR isnan(CAST({col_sql} AS DOUBLE)) "
            f"THEN 'missing' WHEN CAST({col_sql} AS DOUBLE) <> 0 THEN 'yes' "
            f"ELSE 'no' END"
        )
    missing = _missing_cond(col_sql, "flag", col_type)
    return (
        f"CASE WHEN {missing} THEN 'missing' "
        f"WHEN lower(trim(CAST({col_sql} AS VARCHAR))) "
        f"IN ('true', '1', '1.0', 'yes', 't') "
        f"THEN 'yes' ELSE 'no' END"
    )


def _category_bin_expr(col_sql: str, col_type: str) -> str:
    """SQL CASE expression mapping a category column to trimmed text or 'missing'."""
    missing = _missing_cond(col_sql, "category", col_type)
    return (
        f"CASE WHEN {missing} THEN 'missing' ELSE trim(CAST({col_sql} AS VARCHAR)) END"
    )


def _number_bin_expr(
    col_sql: str, col_type: str, cuts: list[float]
) -> tuple[str, list]:
    """SQL CASE expression and parameters mapping a numeric column into bins."""
    missing = _missing_cond(col_sql, "number", col_type)
    parts = [f"WHEN {missing} THEN 'missing'"]
    params: list[float] = []
    for idx, cut in enumerate(cuts, start=1):
        parts.append(f"WHEN CAST({col_sql} AS DOUBLE) <= ? THEN 'q{idx}'")
        params.append(cut)
    parts.append(f"ELSE 'q{len(cuts) + 1}'")
    return "CASE " + " ".join(parts) + " END", params


def _calibration_mark(
    ads: int, in50: float | None, in80: float | None, in95: float | None
) -> dict:
    """Whether a slice's empirical interval coverage diverges from nominal.

    A slice with fewer than `MIN_CALIBRATION_ADS` ads gets no mark, since its
    coverage shares move by several points with each ad.
    """
    small = ads < MIN_CALIBRATION_ADS
    off_50 = not small and in50 is not None and abs(in50 - 50.0) >= 5.0
    off_80 = not small and in80 is not None and abs(in80 - 80.0) >= 5.0
    off_95 = not small and in95 is not None and abs(in95 - 95.0) >= 3.0
    return {
        "small": small,
        "off_50": off_50,
        "off_80": off_80,
        "off_95": off_95,
        "off_nominal": bool(off_50 or off_80 or off_95),
    }


def _flag(code: str) -> dict:
    """The label and rule of a detector code, for a chip."""
    label, rule = FLAGS.get(code, (code.replace("_", " "), ""))
    return {"code": code, "label": label, "rule": rule}


def _shown_ad(row: dict) -> dict:
    """Format a row from `ads.parquet` for template display."""
    listing_id = str(row.get("listing_id") or "")
    gap = _finite(row.get("gap"))
    miss = _finite(row.get("miss"))
    beds = _finite(row.get("bedrooms"))
    prev_beds = _finite(row.get("prev_bedrooms"))
    full = _finite(row.get("full_baths"))
    half = _finite(row.get("half_baths"))
    baths = None if full is None else full + 0.5 * (half or 0)
    raw_flags = row.get("flags")
    if isinstance(raw_flags, (list, tuple)):
        flags = [_flag(str(f)) for f in raw_flags if f]
    else:
        flags = []
    hood = _text(row.get("neighbourhood"))
    basis = _text(row.get("basis"))
    return row | {
        "listing_id": listing_id,
        "address": _text(row.get("address")),
        "unit": _text(row.get("unit")),
        "unit_id": _text(row.get("unit_id")),
        "neighbourhood": hood,
        "hood_label": hood_label(hood) if hood else None,
        "bedrooms": beds,
        "prev_bedrooms": prev_beds,
        "baths": baths,
        "gap": gap,
        "gap_pct": _ratio_pct(gap),
        "miss": miss,
        "basis_label": BASES.get(basis, basis) if basis else None,
        "basis_rule": BASIS_RULES.get(basis, "") if basis else "",
        "unit_ads": int(_finite(row.get("unit_ads")) or 0),
        "building_ads": int(_finite(row.get("building_ads")) or 0),
        "prev_ask": _finite(row.get("prev_ask")),
        "square_feet": _finite(row.get("square_feet")),
        "floor": _finite(row.get("floor")),
        "flags": flags,
        "source_words": SOURCES.get(
            str(row.get("source") or ""), str(row.get("source") or "")
        ),
        "url": LISTING + listing_id if re.fullmatch(r"\d+", listing_id) else None,
    }


def _shown_building(row: dict) -> dict:
    """Format a row from `buildings.parquet` for template display."""
    level = _finite(row.get("level"))
    level_sd = _finite(row.get("level_sd"))
    h_gap = _finite(row.get("heldout_gap"))
    h_miss = _finite(row.get("heldout_miss"))
    h_ads = int(_finite(row.get("heldout_ads")) or 0)
    t_ads = int(_finite(row.get("train_ads")) or 0)
    hood = _text(row.get("neighbourhood"))
    score = None if h_miss is None else abs(h_miss) * math.sqrt(max(h_ads, 0))
    return row | {
        "address": _text(row.get("address")),
        "neighbourhood": hood,
        "hood_label": hood_label(hood) if hood else None,
        "zone": _text(row.get("zone")),
        "level": level,
        "level_pct": None if level is None else 100.0 * level,
        "level_sd": level_sd,
        "level_sd_pct": None if level_sd is None else 100.0 * level_sd,
        "train_ads": t_ads,
        "heldout_ads": h_ads,
        "heldout_gap": h_gap,
        "heldout_gap_pct": _ratio_pct(h_gap),
        "heldout_miss": h_miss,
        "miss_score": score,
    }


def _signal_rank(signal: dict) -> tuple:
    """Sort key placing the signal with the largest sized-bin score first."""
    peak = signal.get("peak_bin")
    return (
        signal["strength"] or 0.0,
        signal["explained_share"] or 0.0,
        abs(peak["mean"]) if peak else 0.0,
    )


def signal_strip(bins: list[dict], scale: float | None = None) -> Markup:
    """Build an inline SVG dot-and-whisker strip of bin means and 95% intervals.

    A label longer than `STRIP_LABEL_CHARS` is cut, and its `<title>` holds the whole
    label. A bin below the size floor is drawn faded with no whisker.
    """
    valid = [b for b in bins if _finite(b.get("mean_pct")) is not None]
    if not valid:
        return Markup("")
    width = 320
    row_h = 18
    top_pad = 6
    bot_pad = 6
    left = 132
    right = width - 12
    mid = (left + right) / 2
    half_span = (right - left) / 2 - 4
    height = top_pad + row_h * len(bins) + bot_pad

    def interval(b: dict) -> tuple[float, float] | None:
        lo, hi = _finite(b.get("lo_pct")), _finite(b.get("hi_pct"))
        if lo is None or hi is None or not b.get("sized", True):
            return None
        return lo, hi

    if scale is None or scale <= 0:
        extents = []
        for b in valid:
            ends = interval(b) or ()
            extents.append(max(abs(float(v)) for v in (b["mean_pct"], *ends)))
        scale = max(extents, default=5.0)
        scale = max(scale, 2.0)

    def x_at(pct_val: float) -> float:
        clamped = max(-scale, min(scale, pct_val))
        return mid + (clamped / scale) * half_span

    parts = [
        f'<line class="zero" x1="{mid:.1f}" x2="{mid:.1f}" y1="2" y2="{height - 2}"/>'
    ]
    for i, b in enumerate(bins):
        y = top_pad + i * row_h + row_h / 2
        label = str(b.get("label") or b.get("key") or "")
        short = (
            label
            if len(label) <= STRIP_LABEL_CHARS
            else label[: STRIP_LABEL_CHARS - 2] + ".."
        )
        parts.append(
            f'<text class="strip-label" x="{left - 6}" y="{y + 3.5:.1f}" '
            f'text-anchor="end"><title>{escape(label)}</title>{escape(short)}</text>'
        )
        mean_pct = _finite(b.get("mean_pct"))
        if mean_pct is None:
            continue
        ends = interval(b)
        if ends is not None and ends[1] > ends[0]:
            parts.append(
                f'<line class="whisker" x1="{x_at(ends[0]):.1f}" '
                f'x2="{x_at(ends[1]):.1f}" y1="{y:.1f}" y2="{y:.1f}"/>'
            )
        cx = x_at(mean_pct)
        cls = "up" if mean_pct > 0.5 else ("down" if mean_pct < -0.5 else "neutral")
        if b.get("is_missing"):
            cls += " missing"
        if not b.get("sized", True):
            cls += " small"
        tip = f"{label}: {charts.pct(mean_pct, digits=1)}"
        se_pct = _finite(b.get("se_pct"))
        if ends is not None and se_pct is not None:
            tip += f" (SE {se_pct:.1f}%)"
        parts.append(
            f'<circle class="dot {cls}" cx="{cx:.1f}" cy="{y:.1f}" r="3.5">'
            f"<title>{escape(tip)}</title></circle>"
        )
    return Markup(
        f'<svg class="signal-strip" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Bin means and 95% cluster intervals">' + "".join(parts) + "</svg>"
    )


def building_history_scatter(rows: list[dict]) -> Markup:
    """Build an SVG scatter of a building's ads over time with a log ask axis.

    Points are colored by bedroom count, held-out ads carry an outer ring, and
    points belonging to the same unit are joined in chronological order by a thin line.
    """
    valid = []
    for r in rows:
        ask = _finite(r.get("ask"))
        day = _text(r.get("day"))
        if ask is None or ask <= 0 or not day:
            continue
        try:
            ordinal = dt.date.fromisoformat(day[:10]).toordinal()
        except ValueError:
            continue
        valid.append((ordinal, ask, r))
    if not valid:
        return Markup("")

    width, height = 720, 280
    left, right = 68, width - 20
    top, bottom = 18, height - 32

    ordinals = [item[0] for item in valid]
    x0, x1 = min(ordinals), max(ordinals)
    if x0 == x1:
        x0, x1 = x0 - 180, x1 + 180

    asks = [item[1] for item in valid]
    lo_ask, hi_ask = min(asks), max(asks)
    if lo_ask == hi_ask:
        lo_ask, hi_ask = lo_ask * 0.8, hi_ask * 1.25
    log_lo, log_hi = math.log(lo_ask), math.log(hi_ask)
    log_pad = max((log_hi - log_lo) * 0.08, 0.06)
    y0, y1 = log_lo - log_pad, log_hi + log_pad

    def x_at(ord_day: int) -> float:
        return left + (ord_day - x0) / (x1 - x0) * (right - left)

    def y_at(ask_val: float) -> float:
        return bottom - (math.log(ask_val) - y0) / (y1 - y0) * (bottom - top)

    # Choose dollar ticks on the log scale.
    candidates = (
        1000,
        1250,
        1500,
        1750,
        2000,
        2500,
        3000,
        3500,
        4000,
        5000,
        6000,
        7500,
        10000,
        12500,
        15000,
        20000,
        25000,
        30000,
        40000,
        50000,
    )
    y_ticks = [t for t in candidates if y0 <= math.log(t) <= y1]
    if len(y_ticks) > 6:
        step = max(1, math.ceil(len(y_ticks) / 5))
        y_ticks = y_ticks[::step]
    if not y_ticks:
        y_ticks = [round(lo_ask, -2) or lo_ask, round(hi_ask, -2) or hi_ask]

    parts: list[str] = []
    for tick in y_ticks:
        y = y_at(tick)
        parts.append(
            f'<line class="grid" x1="{left}" x2="{right}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{left - 8}" y="{y + 4:.1f}" '
            f'text-anchor="end">{escape(charts.usd(tick))}</text>'
        )

    # Time ticks along the horizontal axis.
    span = x1 - x0
    if span < 500:
        d = dt.date.fromordinal(x0).replace(day=1)
        months = []
        while d.toordinal() <= x1:
            if d.toordinal() >= x0:
                months.append(d)
            d = (d + dt.timedelta(days=32)).replace(day=1)
        every = max(1, math.ceil(len(months) / 7))
        for m in months[::every]:
            tx = x_at(m.toordinal())
            parts.append(
                f'<text class="tick" x="{tx:.1f}" y="{bottom + 18}" '
                f'text-anchor="middle">{m.strftime("%b %Y")}</text>'
            )
    else:
        first_y = dt.date.fromordinal(x0).year
        last_y = dt.date.fromordinal(x1).year
        years = list(range(first_y, last_y + 1))
        every = max(1, math.ceil(len(years) / 8))
        for yr in years[::every]:
            ord_y = dt.date(yr, 1, 1).toordinal()
            if x0 <= ord_y <= x1:
                tx = x_at(ord_y)
                parts.append(
                    f'<text class="tick" x="{tx:.1f}" y="{bottom + 18}" '
                    f'text-anchor="middle">{yr}</text>'
                )

    parts.append(
        f'<line class="axis" x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}"/>'
    )

    # Thin lines joining ads of the same unit over time.
    by_unit: dict[str, list[tuple[int, float, dict]]] = {}
    for item in valid:
        uid = _text(item[2].get("unit_id"))
        if uid:
            by_unit.setdefault(uid, []).append(item)
    for unit_items in by_unit.values():
        if len(unit_items) < 2:
            continue
        unit_items.sort(key=lambda it: (it[0], str(it[2].get("listing_id") or "")))
        pts = " ".join(f"{x_at(it[0]):.1f},{y_at(it[1]):.1f}" for it in unit_items)
        parts.append(f'<polyline class="unit-line" points="{pts}"/>')

    # Scatter dots and rings for held-out ads.
    seen_beds: set[str] = set()
    has_heldout = False
    hover: list[dict] = []
    for ord_day, ask, r in valid:
        cx, cy = x_at(ord_day), y_at(ask)
        beds_val = _finite(r.get("bedrooms"))
        bed_key = "u" if beds_val is None else str(min(4, max(0, round(beds_val))))
        seen_beds.add(bed_key)
        heldout = bool(r.get("heldout"))
        if heldout:
            has_heldout = True
            parts.append(
                f'<circle class="heldout-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="7.5"/>'
            )
        unit_str = _text(r.get("unit")) or _text(r.get("unit_id")) or "Unit"
        day_str = _text(r.get("day")) or ""
        bed_words = BEDROOMS.get(bed_key, "Unknown BR")
        title = f"{unit_str} · {day_str} · {charts.usd(ask)} · {bed_words}"
        if heldout:
            title += " (held out)"
        cls = f"dot beds-{bed_key}" + (" heldout" if heldout else "")
        parts.append(
            f'<circle class="{cls}" cx="{cx:.1f}" cy="{cy:.1f}" r="4.5">'
            f"<title>{escape(title)}</title></circle>"
        )
        hover.append(
            {
                "x": round(cx, 1),
                "y": round(cy, 1),
                "title": f"{unit_str} ({day_str})",
                "rows": [
                    ["Ask", charts.usd(ask)],
                    ["Bedrooms", bed_words],
                    ["Split", "Held out" if heldout else "In training fit"],
                ],
            }
        )

    legend_items = []
    for k in ("0", "1", "2", "3", "4"):
        if k in seen_beds:
            legend_items.append(
                f'<span class="key"><span class="key-dot beds-{k}"></span>'
                f"{escape(BEDROOMS[k])}</span>"
            )
    if has_heldout:
        legend_items.append(
            '<span class="key"><span class="key-ring"></span>Held-out ad</span>'
        )
    if any(len(v) >= 2 for v in by_unit.values()):
        legend_items.append(
            '<span class="key"><span class="key-unit-line"></span>'
            "Same unit over time</span>"
        )
    legend = (
        f'<div class="legend">{"".join(legend_items)}</div>' if legend_items else ""
    )

    svg = (
        f'<svg class="history-scatter" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Building ads over time on a log rent scale">'
        + "".join(parts)
        + "</svg>"
    )
    return charts._figure("points", svg, hover, legend)


class Diagnostics:
    """Read-only DuckDB views and query methods over a `diagnostics/` folder."""

    def __init__(self, folder: Path, meta: dict):
        self.folder = folder
        self.meta = meta
        self._lock = threading.Lock()
        self._connection = duckdb.connect()
        self._connection.execute("SET threads = 1")
        self._connection.execute("SET memory_limit = '256MB'")

        for name in FILES:
            quoted = str((folder / f"{name}.parquet").resolve()).replace("'", "''")
            self._connection.execute(
                f"CREATE VIEW {name}_raw AS SELECT * FROM read_parquet('{quoted}')"
            )

        # Normalize `flags` on `ads` if a fixture wrote strings instead of VARCHAR[].
        ad_desc = self._connection.execute("DESCRIBE ads_raw").fetchall()
        raw_ad_types = {row[0]: str(row[1]) for row in ad_desc}
        flag_type = raw_ad_types.get("flags", "").upper()
        if "[]" in flag_type or "LIST" in flag_type:
            self._connection.execute("CREATE VIEW ads AS SELECT * FROM ads_raw")
        elif "VARCHAR" in flag_type:
            self._connection.execute(
                "CREATE VIEW ads AS SELECT * REPLACE ("
                "CASE WHEN flags IS NULL OR trim(flags) = '' THEN []::VARCHAR[] "
                "WHEN starts_with(trim(flags), '[') "
                "THEN from_json(flags, '[\"VARCHAR\"]') "
                "ELSE list_filter(string_split(flags, ','), x -> x <> '') END AS flags"
                ") FROM ads_raw"
            )
        else:
            self._connection.execute(
                "CREATE VIEW ads AS SELECT *, []::VARCHAR[] AS flags FROM ads_raw"
            )

        bld_desc = self._connection.execute("DESCRIBE buildings_raw").fetchall()
        raw_bld_types = {row[0]: str(row[1]) for row in bld_desc}
        extra_bld = []
        if "zone" not in raw_bld_types:
            extra_bld.append("NULL::VARCHAR AS zone")
        if "level" not in raw_bld_types:
            extra_bld.append("NULL::DOUBLE AS level")
        if "level_sd" not in raw_bld_types:
            extra_bld.append("NULL::DOUBLE AS level_sd")
        bld_select = (
            "SELECT *, " + ", ".join(extra_bld) + " FROM buildings_raw"
            if extra_bld
            else "SELECT * FROM buildings_raw"
        )
        self._connection.execute(f"CREATE VIEW buildings AS {bld_select}")
        self._connection.execute("CREATE VIEW history AS SELECT * FROM history_raw")

        self.ad_types = {
            r[0]: str(r[1]) for r in self._connection.execute("DESCRIBE ads").fetchall()
        }
        self.building_types = {
            r[0]: str(r[1])
            for r in self._connection.execute("DESCRIBE buildings").fetchall()
        }
        self.history_types = {
            r[0]: str(r[1])
            for r in self._connection.execute("DESCRIBE history").fetchall()
        }

        self.features: list[dict] = []
        self.features_by_name: dict[str, dict] = {}
        for item in meta.get("features") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            kind = str(item.get("kind") or "").strip().lower()
            level = str(item.get("level") or "").strip().lower()
            if not IDENT_RE.fullmatch(name):
                continue
            if kind not in ("number", "category", "flag"):
                continue
            if level not in ("ad", "unit", "building"):
                continue
            if name not in self.ad_types and name not in self.building_types:
                continue
            feat = {
                "name": name,
                "label": str(item.get("label") or name.replace("_", " ").capitalize()),
                "kind": kind,
                "level": level,
                "in_model": bool(item.get("in_model", False)),
                "after": bool(item.get("after", False)),
            }
            feat["group"] = (
                "after" if feat["after"] else "term" if feat["in_model"] else "none"
            )
            feat["group_label"] = SIGNAL_GROUPS[feat["group"]][0]
            if name not in self.features_by_name:
                self.features.append(feat)
                self.features_by_name[name] = feat

        self._cache: dict[tuple, object] = {}
        self._cache_lock = threading.Lock()
        self._ad_hoods: dict[str, int] | None = None
        self._building_hoods: dict[str, int] | None = None
        self._valid_flags: set[str] | None = None

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _rows(self, sql: str, params: list | tuple = ()) -> list[dict]:
        with self._lock:
            cursor = self._connection.execute(sql, list(params))
            names = [d[0] for d in cursor.description]
            return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]

    def _one(self, sql: str, params: list | tuple = ()):
        with self._lock:
            return self._connection.execute(sql, list(params)).fetchone()

    def _all(self, sql: str, params: list | tuple = ()) -> list[tuple]:
        with self._lock:
            return self._connection.execute(sql, list(params)).fetchall()

    def _cached(self, key: tuple, compute: Callable[[], object]):
        """Return the aggregate stored under `key`, computing it on the first call.

        This object reads one publish of the folder, and `load` replaces it when the
        folder's stamp changes, so the key only carries the query. Two requests
        arriving together may both compute a value; the later one overwrites the
        earlier with an equal result. Callers treat the returned value as read-only.
        """
        with self._cache_lock:
            if key in self._cache:
                return self._cache[key]
        value = compute()
        with self._cache_lock:
            self._cache[key] = value
            while len(self._cache) > CACHE_ENTRIES:
                self._cache.pop(next(iter(self._cache)))
        return value

    def ad_hoods(self) -> dict[str, int]:
        """Neighbourhood values in `ads.parquet` and their row counts."""
        if self._ad_hoods is None:
            self._ad_hoods = {
                name: int(n)
                for name, n in self._all(
                    "SELECT neighbourhood, COUNT(*) FROM ads "
                    "WHERE neighbourhood IS NOT NULL AND trim(neighbourhood) <> '' "
                    "GROUP BY neighbourhood ORDER BY neighbourhood"
                )
            }
        return self._ad_hoods

    def ad_hood_names(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for value, n in self.ad_hoods().items():
            label = hood_label(value)
            out[label] = out.get(label, 0) + n
        return dict(sorted(out.items()))

    def building_hoods(self) -> dict[str, int]:
        """Neighbourhood values in `buildings.parquet` and their building counts."""
        if self._building_hoods is None:
            self._building_hoods = {
                name: int(n)
                for name, n in self._all(
                    "SELECT neighbourhood, COUNT(*) FROM buildings "
                    "WHERE neighbourhood IS NOT NULL AND trim(neighbourhood) <> '' "
                    "GROUP BY neighbourhood ORDER BY neighbourhood"
                )
            }
        return self._building_hoods

    def building_hood_names(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for value, n in self.building_hoods().items():
            label = hood_label(value)
            out[label] = out.get(label, 0) + n
        return dict(sorted(out.items()))

    def flag_counts(self) -> list[dict]:
        """Counts of ads per detector flag, keeping standard flags in contract order."""
        return self._cached(("flags",), self._flag_counts)

    def _flag_counts(self) -> list[dict]:
        found = {
            str(code): int(n)
            for code, n in self._all(
                "SELECT f, COUNT(*) FROM (SELECT unnest(flags) AS f FROM ads) "
                "WHERE f IS NOT NULL AND f <> '' GROUP BY f ORDER BY COUNT(*) DESC, f"
            )
        }
        ordered_codes = list(FLAGS) + [c for c in found if c not in FLAGS]
        return [_flag(code) | {"count": found.get(code, 0)} for code in ordered_codes]

    def valid_flags(self) -> set[str]:
        if self._valid_flags is None:
            self._valid_flags = {item["code"] for item in self.flag_counts()}
        return self._valid_flags

    def overview_counts(self) -> dict:
        """Counts of ads by source and by basis, plus table totals."""
        return self._cached(("counts",), self._overview_counts)

    def _overview_counts(self) -> dict:
        total_ads = int(self._one("SELECT COUNT(*) FROM ads")[0] or 0)
        total_buildings = int(self._one("SELECT COUNT(*) FROM buildings")[0] or 0)
        total_history = int(self._one("SELECT COUNT(*) FROM history")[0] or 0)
        flagged_ads = int(
            self._one("SELECT COUNT(*) FROM ads WHERE len(flags) > 0")[0] or 0
        )

        by_source_raw = {
            str(k): int(n)
            for k, n in self._all("SELECT source, COUNT(*) FROM ads GROUP BY source")
            if k is not None
        }
        by_source = [
            {
                "key": k,
                "label": SOURCES.get(k, k),
                "count": by_source_raw.get(k, 0),
            }
            for k in list(SOURCES) + [s for s in by_source_raw if s not in SOURCES]
            if k in by_source_raw or k in SOURCES
        ]

        by_basis_raw = {
            str(k): int(n)
            for k, n in self._all("SELECT basis, COUNT(*) FROM ads GROUP BY basis")
            if k is not None
        }
        base_keys = ("unit", "building", "area")
        by_basis = [
            {
                "key": k,
                "label": BASES.get(k, k),
                "count": by_basis_raw.get(k, 0),
            }
            for k in list(base_keys) + [b for b in by_basis_raw if b not in base_keys]
            if k in by_basis_raw or k in base_keys
        ]

        matrix_raw = {
            (str(s), str(b)): int(n)
            for s, b, n in self._all(
                "SELECT source, basis, COUNT(*) FROM ads GROUP BY source, basis"
            )
            if s is not None and b is not None
        }
        matrix = [
            {
                "source": s["key"],
                "source_label": s["label"],
                "cells": [
                    {
                        "basis": b["key"],
                        "count": matrix_raw.get((s["key"], b["key"]), 0),
                    }
                    for b in by_basis
                ],
                "total": s["count"],
            }
            for s in by_source
        ]

        return {
            "ads": total_ads,
            "buildings": total_buildings,
            "history": total_history,
            "flagged": flagged_ads,
            "by_source": by_source,
            "by_basis": by_basis,
            "matrix": matrix,
        }

    _CALIBRATION_STATS = (
        "COUNT(*), "
        "100.0 * AVG(CASE WHEN ask BETWEEN model_lo50 AND model_hi50 "
        "THEN 1.0 ELSE 0.0 END), "
        "100.0 * AVG(CASE WHEN ask BETWEEN model_lo80 AND model_hi80 "
        "THEN 1.0 ELSE 0.0 END), "
        "100.0 * AVG(CASE WHEN ask BETWEEN model_lo95 AND model_hi95 "
        "THEN 1.0 ELSE 0.0 END), "
        "median(ABS(gap)), "
        "AVG(gap), "
        "AVG(z)"
    )

    @staticmethod
    def _calibration_shown(
        group: str, label: str, stats: tuple, triage_args: dict
    ) -> dict | None:
        if not stats or not stats[0]:
            return None
        n, in50, in80, in95, med_abs_gap, mean_gap, mean_z = stats
        in50_f, in80_f, in95_f = _finite(in50), _finite(in80), _finite(in95)
        med_f, mean_f, z_f = (
            _finite(med_abs_gap),
            _finite(mean_gap),
            _finite(mean_z),
        )
        marks = _calibration_mark(int(n), in50_f, in80_f, in95_f)
        return {
            "group": group,
            "label": label,
            "ads": int(n),
            "in50": in50_f,
            "in80": in80_f,
            "in95": in95_f,
            "median_abs_gap": med_f,
            "median_abs_gap_pct": _ratio_pct(med_f),
            "mean_gap": mean_f,
            "mean_gap_pct": _ratio_pct(mean_f),
            "mean_z": z_f,
            "triage_args": triage_args,
            **marks,
        }

    def _calibration_row(
        self,
        group: str,
        label: str,
        where_sql: str,
        params: list,
        triage_args: dict,
    ) -> dict | None:
        stats = self._one(
            f"SELECT {self._CALIBRATION_STATS} FROM ads{where_sql}", params
        )
        return self._calibration_shown(group, label, stats, triage_args)

    def calibration(self) -> dict:
        """Calibration slices overall and by source, basis, bedrooms, and area.

        `new_units` holds the building and area basis rows, whose ads are of units
        the fit read no earlier ads of. `unit` holds the unit-history row, and `rest`
        the overall, source and bedroom slices. `main` is those three in page order.
        `hoods` holds every neighbourhood, and `hoods_off` the neighbourhoods marked
        off nominal. `unit_share` is the percent of held-out ads on the unit basis.
        """
        return self._cached(("calibration", MIN_CALIBRATION_ADS), self._calibration)

    def _calibration(self) -> dict:
        by_basis: dict[str, dict] = {}
        for key in ("building", "area", "unit"):
            r = self._calibration_row(
                "Basis",
                BASES[key].capitalize(),
                " WHERE basis = ?",
                [key],
                {"basis": key},
            )
            if r:
                by_basis[key] = r
        new_units = [by_basis[k] for k in ("building", "area") if k in by_basis]
        unit = [by_basis["unit"]] if "unit" in by_basis else []

        rest: list[dict] = []
        overall = self._calibration_row("All", "All held-out ads", "", [], {})
        if overall:
            rest.append(overall)

        for key, label in SOURCES.items():
            r = self._calibration_row(
                "Source", label, " WHERE source = ?", [key], {"source": key}
            )
            if r:
                rest.append(r)

        for key, label in BEDROOMS.items():
            clause, params = _beds_clause([key])
            r = self._calibration_row(
                "Bedrooms", label, f" WHERE {clause}", params, {"beds": key}
            )
            if r:
                rest.append(r)

        hoods: list[dict] = []
        for value, *stats in self._all(
            f"SELECT neighbourhood, {self._CALIBRATION_STATS} FROM ads "
            "WHERE neighbourhood IS NOT NULL AND trim(neighbourhood) <> '' "
            "GROUP BY neighbourhood"
        ):
            r = self._calibration_shown(
                "Neighbourhood", hood_label(value), tuple(stats), {"nb": value}
            )
            if r:
                hoods.append(r)
        hoods.sort(key=lambda r: r["label"])

        unit_ads = sum(r["ads"] for r in unit)
        all_ads = overall["ads"] if overall else 0
        return {
            "new_units": new_units,
            "unit": unit,
            "rest": rest,
            "main": new_units + unit + rest,
            "hoods": hoods,
            "hoods_off": [r for r in hoods if r["off_nominal"]],
            "unit_share": 100.0 * unit_ads / all_ads if all_ads else None,
        }

    def _signal_where(self, c: SignalChoice) -> tuple[str, list]:
        clauses, params = [], []
        if c.scope == "non_unit":
            clauses.append("basis <> ?")
            params.append("unit")
        elif c.scope in ("latest", "market"):
            clauses.append("source = ?")
            params.append(c.scope)
        if c.hoods:
            clauses.append("neighbourhood IN (" + ", ".join("?" * len(c.hoods)) + ")")
            params.extend(c.hoods)
        if c.beds:
            bed_sql, bed_params = _beds_clause(c.beds)
            clauses.append(bed_sql)
            params.extend(bed_params)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _number_cuts(
        self,
        table: str,
        col_name: str,
        where_sql: str,
        params: list,
    ) -> tuple[float | None, float | None, list[float]]:
        """Compute deduplicated quantile cutpoints for a numeric column in `table`."""
        col_sql = _ident(col_name)
        col_type = (
            self.ad_types[col_name] if table == "ads" else self.building_types[col_name]
        )
        missing = _missing_cond(col_sql, "number", col_type)
        non_null = f"NOT {missing}"
        full_where = (
            f"{where_sql} AND {non_null}" if where_sql else f" WHERE {non_null}"
        )
        row = self._one(
            f"SELECT COUNT(*), COUNT(DISTINCT building), "
            f"MIN(CAST({col_sql} AS DOUBLE)), MAX(CAST({col_sql} AS DOUBLE)), "
            f"quantile_disc(CAST({col_sql} AS DOUBLE), [0.2, 0.4, 0.6, 0.8]), "
            f"quantile_disc(CAST({col_sql} AS DOUBLE), [0.3333333, 0.6666667]), "
            f"quantile_disc(CAST({col_sql} AS DOUBLE), [0.5]) "
            f"FROM {table}{full_where}",
            params,
        )
        if not row or not row[0] or row[2] is None or row[3] is None:
            return None, None, []
        n_rows, n_buildings, lo, hi, q5, q3, q2 = row
        lo_f, hi_f = float(lo), float(hi)
        if lo_f >= hi_f:
            return lo_f, hi_f, []
        if n_rows >= 15 and n_buildings >= 10:
            chosen = q5 or []
        elif n_rows >= 9 and n_buildings >= 6:
            chosen = q3 or []
        elif n_rows >= 2:
            chosen = q2 or []
        else:
            chosen = []
        cuts = sorted(
            {
                float(q)
                for q in chosen
                if q is not None and math.isfinite(float(q)) and lo_f <= float(q) < hi_f
            }
        )
        return lo_f, hi_f, cuts

    def tabulate_feature(
        self,
        table: str,
        feature: dict,
        *,
        value_col: str,
        miss_col: str,
        where_sql: str = "",
        params: list | None = None,
        as_ratio: bool = False,
    ) -> dict:
        """Tabulate `value_col` and `miss_col` against `feature` with cluster SEs.

        The overview and the signals pages call this on `ads` (`value_col='gap'`,
        `miss_col='miss'`, `as_ratio=True`), and the buildings page on `buildings`
        (`value_col='level'`, `miss_col='heldout_miss'`).

        The reference population is every row the filters keep, with or without a
        value of the attribute. `ref_mean` is its mean of `value_col` and `ref_ads`
        its size. Each bin's `mean` is its own mean (`raw_mean`) minus `ref_mean`,
        and `ratio` is |mean| / SE. With `as_ratio` the percents are
        100 * (exp(x) - 1) of the log values, and otherwise 100 * x.

        A bin is `sized` when it has at least `MIN_BIN_ADS` rows in at least
        `MIN_BIN_BUILDINGS` buildings. `strength` and `peak_bin` read the sized bins
        only. A bin below the floor has no `ratio`, and `bins` lists it after the
        sized bins.

        `list_bins` holds the bins a list view draws: all of them up to `LIST_BINS`,
        and past that the `LIST_BINS` sized bins with the largest ratio. `more_bins`
        counts the bins left out of `list_bins`. `explained_share` is None for an
        attribute with more than `MAX_EXPLAINED_BINS` bins, where the share mostly
        counts the bins.
        """
        if table not in ("ads", "buildings"):
            raise ValueError(f"Unsupported table: {table!r}")
        col_types = self.ad_types if table == "ads" else self.building_types
        name = feature["name"]
        if (
            name not in self.features_by_name
            or name not in col_types
            or value_col not in col_types
            or miss_col not in col_types
        ):
            raise ValueError(f"Column not whitelisted for {table}: {name!r}")

        col_sql = _ident(name)
        val_sql = _ident(value_col)
        miss_sql = _ident(miss_col)
        col_type = col_types[name]
        kind = feature["kind"]
        query_params = list(params or [])

        if kind == "number":
            _, _, cuts = self._number_cuts(table, name, where_sql, query_params)
            bin_expr, bin_params = _number_bin_expr(col_sql, col_type, cuts)
            missing = _missing_cond(col_sql, "number", col_type)
            num_expr = (
                f"CASE WHEN {missing} THEN NULL ELSE CAST({col_sql} AS DOUBLE) END"
            )
        elif kind == "flag":
            cuts = []
            bin_expr = _flag_bin_expr(col_sql, col_type)
            bin_params = []
            num_expr = "NULL::DOUBLE"
        else:
            cuts = []
            bin_expr = _category_bin_expr(col_sql, col_type)
            bin_params = []
            num_expr = "NULL::DOUBLE"

        sql = f"""
        WITH base AS (
            SELECT
                {bin_expr} AS bin_id,
                building,
                CAST({val_sql} AS DOUBLE) AS val,
                CAST({miss_sql} AS DOUBLE) AS z_val,
                {num_expr} AS num_val
            FROM {table}
            {where_sql}
        ),
        valid AS (
            SELECT * FROM base
            WHERE val IS NOT NULL AND NOT isnan(val)
        ),
        per_building AS (
            SELECT
                bin_id,
                building,
                COUNT(*) AS b_n,
                SUM(val) AS b_sum,
                SUM(val * val) AS b_sum_sq,
                SUM(
                    CASE WHEN z_val IS NOT NULL AND NOT isnan(z_val)
                    THEN z_val ELSE 0.0 END
                ) AS b_z_sum,
                COUNT(
                    CASE WHEN z_val IS NOT NULL AND NOT isnan(z_val) THEN 1 END
                ) AS b_z_n,
                MIN(num_val) AS b_min,
                MAX(num_val) AS b_max
            FROM valid
            GROUP BY bin_id, building
        ),
        with_totals AS (
            SELECT
                *,
                SUM(b_n) OVER (PARTITION BY bin_id) AS bin_n,
                SUM(b_sum) OVER (PARTITION BY bin_id)
                    / SUM(b_n) OVER (PARTITION BY bin_id) AS bin_mean,
                SUM(b_z_sum) OVER (PARTITION BY bin_id)
                    / NULLIF(SUM(b_z_n) OVER (PARTITION BY bin_id), 0) AS bin_z
            FROM per_building
        )
        SELECT
            bin_id,
            CAST(MAX(bin_n) AS BIGINT) AS ads,
            COUNT(*) AS buildings,
            MAX(bin_mean) AS mean_val,
            CASE WHEN COUNT(*) >= 2
                 THEN SQRT(
                     (COUNT(*) * 1.0 / (COUNT(*) - 1))
                     * SUM(POWER(b_sum - b_n * bin_mean, 2))
                 ) / MAX(bin_n)
                 ELSE NULL END AS se_val,
            MAX(bin_z) AS mean_miss,
            SUM(b_sum_sq) AS sum_sq,
            MIN(b_min) AS min_num,
            MAX(b_max) AS max_num
        FROM with_totals
        GROUP BY bin_id
        """
        raw_rows = self._rows(sql, [*bin_params, *query_params])

        bins: list[dict] = []
        for r in raw_rows:
            bin_key = str(r["bin_id"])
            is_missing = bin_key == "missing"
            ads_n = int(r["ads"] or 0)
            bld_n = int(r["buildings"] or 0)
            raw_mean = _finite(r["mean_val"]) or 0.0
            se_v = _finite(r["se_val"])
            mean_miss = _finite(r["mean_miss"])
            min_n = _finite(r["min_num"])
            max_n = _finite(r["max_num"])
            sum_sq = _finite(r["sum_sq"]) or 0.0

            if is_missing:
                label = "Missing"
            elif kind == "number":
                if min_n is not None and max_n is not None:
                    if abs(max_n - min_n) < 1e-9:
                        label = _fmt_num(min_n)
                    else:
                        label = f"{_fmt_num(min_n)} to {_fmt_num(max_n)}"
                else:
                    label = bin_key
            elif kind == "flag":
                label = "Yes" if bin_key == "yes" else "No"
            else:
                label = bin_key.replace("_", " ")

            bins.append(
                {
                    "key": bin_key,
                    "label": label,
                    "ads": ads_n,
                    "buildings": bld_n,
                    "raw_mean": raw_mean,
                    "se": se_v,
                    "mean_miss": mean_miss,
                    "min_val": min_n,
                    "max_val": max_n,
                    "is_missing": is_missing,
                    "sized": ads_n >= MIN_BIN_ADS and bld_n >= MIN_BIN_BUILDINGS,
                    "_sum_sq": sum_sq,
                }
            )

        total_ads = sum(b["ads"] for b in bins)
        missing_ads = sum(b["ads"] for b in bins if b["is_missing"])
        non_missing_ads = total_ads - missing_ads

        if total_ads > 0:
            total_sum = sum(b["ads"] * b["raw_mean"] for b in bins)
            overall_mean = total_sum / total_ads
            total_sum_sq = sum(b["_sum_sq"] for b in bins)
            sst = total_sum_sq - total_ads * overall_mean * overall_mean
            ssb = sum(b["ads"] * (b["raw_mean"] - overall_mean) ** 2 for b in bins)
            explained_share = max(0.0, min(1.0, ssb / sst)) if sst > 1e-12 else 0.0
        else:
            overall_mean = 0.0
            explained_share = 0.0
        if len(bins) > MAX_EXPLAINED_BINS:
            explained_share = None

        def shown_pct(log_value: float) -> float | None:
            return _ratio_pct(log_value) if as_ratio else 100.0 * log_value

        for b in bins:
            b.pop("_sum_sq", None)
            mean_v = b["raw_mean"] - overall_mean
            se_v = b["se"]
            has_se = se_v is not None and se_v > 1e-12
            b["mean"] = mean_v
            b["mean_pct"] = shown_pct(mean_v)
            b["ratio"] = abs(mean_v) / se_v if b["sized"] and has_se else None
            if se_v is None:
                b["se_pct"] = b["lo_pct"] = b["hi_pct"] = None
            else:
                # The percent SE follows the slope of 100 * (exp(x) - 1) at the mean.
                b["se_pct"] = 100.0 * se_v * (math.exp(mean_v) if as_ratio else 1.0)
                b["lo_pct"] = shown_pct(mean_v - 1.96 * se_v)
                b["hi_pct"] = shown_pct(mean_v + 1.96 * se_v)

        if kind == "number":
            bins.sort(
                key=lambda b: (
                    not b["sized"],
                    b["is_missing"],
                    int(b["key"][1:])
                    if b["key"].startswith("q") and b["key"][1:].isdigit()
                    else 999,
                )
            )
        elif kind == "flag":
            order = {"yes": 0, "no": 1, "missing": 2}
            bins.sort(key=lambda b: (not b["sized"], order.get(b["key"], 99)))
        else:
            bins.sort(
                key=lambda b: (
                    not b["sized"],
                    b["is_missing"],
                    -(b["ratio"] or 0.0),
                    -b["ads"],
                    b["key"],
                )
            )

        sized_bins = [b for b in bins if b["ratio"] is not None]
        strength = max((float(b["ratio"]) for b in sized_bins), default=None)
        peak_bin = max(
            sized_bins,
            key=lambda b: (b["ratio"], abs(b["mean"])),
            default=None,
        )

        if len(bins) <= LIST_BINS:
            list_bins = bins
        else:
            ranked = sorted(sized_bins, key=lambda b: -b["ratio"])
            list_bins = (
                ranked[:LIST_BINS] or sorted(bins, key=lambda b: -b["ads"])[:LIST_BINS]
            )

        return {
            **feature,
            "bins": bins,
            "list_bins": list_bins,
            "more_bins": len(bins) - len(list_bins),
            "cuts": cuts,
            "total_ads": total_ads,
            "non_missing_ads": non_missing_ads,
            "missing_ads": missing_ads,
            "ref_ads": total_ads,
            "ref_mean": overall_mean,
            "ref_mean_pct": shown_pct(overall_mean),
            "small_bins": sum(1 for b in bins if not b["sized"]),
            "strength": strength,
            "explained_share": explained_share,
            "explained_pct": (
                None if explained_share is None else 100.0 * explained_share
            ),
            "peak_bin": peak_bin,
            "svg": signal_strip(list_bins),
        }

    def signals(self, c: SignalChoice) -> list[dict]:
        """Tabulate and rank every feature in `meta['features']` in `ads.parquet`."""
        key = ("signals", c.scope, tuple(c.hoods or ()), tuple(c.beds))
        return self._cached(key, lambda: self._signals(c))

    def signal_groups(self, c: SignalChoice) -> list[dict]:
        """The ranked signals split into the groups of `SIGNAL_GROUPS`, in order."""
        ranked = self.signals(c)
        return [
            {
                "key": key,
                "heading": heading,
                "note": note,
                "signals": [s for s in ranked if s["group"] == key],
            }
            for key, (heading, note) in SIGNAL_GROUPS.items()
        ]

    def top_signals(self, limit: int = 10) -> list[dict]:
        """The strongest signals for the overview, those with no model term first."""
        ranked = self.signals(SignalChoice())
        first = [s for s in ranked if s["group"] == "none"][: limit // 2 + 1]
        rest = [s for s in ranked if s["group"] != "none"]
        return first + rest[: limit - len(first)]

    def _signals(self, c: SignalChoice) -> list[dict]:
        where_sql, params = self._signal_where(c)
        results = [
            self.tabulate_feature(
                "ads",
                feat,
                value_col="gap",
                miss_col="miss",
                where_sql=where_sql,
                params=params,
                as_ratio=True,
            )
            for feat in self.features
            if feat["name"] in self.ad_types
        ]
        results.sort(key=_signal_rank, reverse=True)
        return results

    def signal_detail(self, name: str, c: SignalChoice) -> dict | None:
        """Tabulate one feature in `ads.parquet` by name."""
        feat = self.features_by_name.get(name)
        if feat is None or name not in self.ad_types:
            return None
        where_sql, params = self._signal_where(c)
        key = ("signal", name, c.scope, tuple(c.hoods or ()), tuple(c.beds))
        return self._cached(
            key,
            lambda: self.tabulate_feature(
                "ads",
                feat,
                value_col="gap",
                miss_col="miss",
                where_sql=where_sql,
                params=params,
                as_ratio=True,
            ),
        )

    def _feature_bin_clause(
        self,
        feature_name: str,
        bin_key: str,
        base_clauses: list[str],
        base_params: list,
    ) -> tuple[str | None, list]:
        """Build the SQL filter clause for a feature bin on `ads`."""
        feat = self.features_by_name.get(feature_name)
        if feat is None or feature_name not in self.ad_types:
            return None, []
        col_sql = _ident(feature_name)
        col_type = self.ad_types[feature_name]
        kind = feat["kind"]
        missing = _missing_cond(col_sql, kind, col_type)

        if bin_key == "missing":
            return missing, []

        if kind == "flag":
            expr = _flag_bin_expr(col_sql, col_type)
            if bin_key in ("yes", "no"):
                return f"({expr}) = ?", [bin_key]
            return None, []

        if kind == "category":
            return (
                f"(NOT {missing} AND trim(CAST({col_sql} AS VARCHAR)) = ?)",
                [bin_key],
            )

        # Numeric feature bin: either 'q1'..'q5' or 'lo..hi'.
        if ".." in bin_key:
            parts = bin_key.split("..", 1)
            lo_v, hi_v = _number(parts[0]), _number(parts[1])
            if lo_v is not None and hi_v is not None:
                return (
                    f"(NOT {missing} AND CAST({col_sql} AS DOUBLE) BETWEEN ? AND ?)",
                    [min(lo_v, hi_v), max(lo_v, hi_v)],
                )
            return None, []

        key_norm = bin_key if bin_key.startswith("q") else f"q{bin_key}"
        if not (key_norm.startswith("q") and key_norm[1:].isdigit()):
            return None, []
        idx = int(key_norm[1:])
        where_sql = (" WHERE " + " AND ".join(base_clauses)) if base_clauses else ""
        _, _, cuts = self._number_cuts("ads", feature_name, where_sql, base_params)
        n_bins = len(cuts) + 1
        if idx < 1 or idx > n_bins:
            return None, []
        if not cuts:
            return f"(NOT {missing})", []
        if idx == 1:
            return f"(NOT {missing} AND CAST({col_sql} AS DOUBLE) <= ?)", [cuts[0]]
        if idx == n_bins:
            return f"(NOT {missing} AND CAST({col_sql} AS DOUBLE) > ?)", [cuts[-1]]
        return (
            f"(NOT {missing} AND CAST({col_sql} AS DOUBLE) > ? "
            f"AND CAST({col_sql} AS DOUBLE) <= ?)",
            [cuts[idx - 2], cuts[idx - 1]],
        )

    def _triage_where(self, c: TriageChoice) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if c.source:
            clauses.append("source = ?")
            params.append(c.source)
        if c.basis == "non_unit":
            clauses.append("basis <> ?")
            params.append("unit")
        elif c.basis:
            clauses.append("basis = ?")
            params.append(c.basis)
        if c.hoods:
            clauses.append("neighbourhood IN (" + ", ".join("?" * len(c.hoods)) + ")")
            params.extend(c.hoods)
        if c.beds:
            bed_sql, bed_params = _beds_clause(c.beds)
            clauses.append(bed_sql)
            params.extend(bed_params)

        # Evaluate feature-bin cutpoints on the scope before narrowing by miss or flag.
        if c.feature and c.bin:
            bin_sql, bin_params = self._feature_bin_clause(
                c.feature, c.bin, list(clauses), list(params)
            )
            if bin_sql:
                clauses.append(bin_sql)
                params.extend(bin_params)

        if c.flag == "any":
            clauses.append("len(flags) > 0")
        elif c.flag:
            clauses.append("list_contains(flags, ?)")
            params.append(c.flag)
        if c.sign == "low":
            clauses.append("gap < 0")
        elif c.sign == "high":
            clauses.append("gap > 0")
        if c.min_miss is not None:
            clauses.append("ABS(miss) >= ?")
            params.append(c.min_miss)
        if c.untagged and c.tagged:
            clauses.append(
                "NOT list_contains(CAST(? AS VARCHAR[]), CAST(listing_id AS VARCHAR))"
            )
            params.append(list(c.tagged))
        if c.q:
            esc = (
                c.q.lower()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            like = f"%{esc}%"
            clauses.append(
                "(lower(COALESCE(address, '')) LIKE ? ESCAPE '\\' "
                "OR lower(COALESCE(building, '')) LIKE ? ESCAPE '\\' "
                "OR lower(COALESCE(unit, '')) LIKE ? ESCAPE '\\' "
                "OR lower(COALESCE(listing_id, '')) LIKE ? ESCAPE '\\')"
            )
            params.extend([like, like.replace(" ", "-"), like, like])
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def triage_page(self, c: TriageChoice) -> tuple[list[dict], int, int]:
        """Return one page of triage rows ordered by |miss| descending."""
        where_sql, params = self._triage_where(c)
        total = int(self._one(f"SELECT COUNT(*) FROM ads{where_sql}", params)[0] or 0)
        pages = max(1, math.ceil(total / PER_PAGE))
        c.page = min(c.page, pages)
        rows = self._rows(
            f"SELECT * FROM ads{where_sql} "
            "ORDER BY ABS(COALESCE(miss, 0)) DESC, "
            "ABS(COALESCE(gap, 0)) DESC, listing_id ASC "
            "LIMIT ? OFFSET ?",
            [*params, PER_PAGE, (c.page - 1) * PER_PAGE],
        )
        return [_shown_ad(r) for r in rows], total, pages

    def triage_csv_columns(self) -> list[str]:
        return [c for c in AD_CORE_COLUMNS if c in self.ad_types] + [
            c for c in self.ad_types if c not in AD_CORE_COLUMNS
        ]

    def triage_csv_rows(self, c: TriageChoice):
        """Stream matching triage rows in chunks for CSV download."""
        where_sql, params = self._triage_where(c)
        cols = self.triage_csv_columns()
        select_list = ", ".join(_ident(col) for col in cols)
        offset = 0
        while True:
            chunk = self._all(
                f"SELECT {select_list} FROM ads{where_sql} "
                "ORDER BY ABS(COALESCE(miss, 0)) DESC, "
                "ABS(COALESCE(gap, 0)) DESC, listing_id ASC "
                "LIMIT ? OFFSET ?",
                [*params, CSV_CHUNK, offset],
            )
            for row in chunk:
                formatted = [
                    ";".join(str(x) for x in val)
                    if isinstance(val, (list, tuple))
                    else facts.csv_cell(val)
                    for val in row
                ]
                yield formatted
            if len(chunk) < CSV_CHUNK:
                return
            offset += CSV_CHUNK

    def _buildings_where(
        self, c: BuildingChoice, min_ads: bool = True
    ) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if c.hoods:
            clauses.append("neighbourhood IN (" + ", ".join("?" * len(c.hoods)) + ")")
            params.extend(c.hoods)
        if min_ads and c.min_ads > 0:
            clauses.append("COALESCE(heldout_ads, train_ads, 0) >= ?")
            params.append(c.min_ads)
        if c.q:
            esc = (
                c.q.lower()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            like = f"%{esc}%"
            clauses.append(
                "(lower(COALESCE(address, '')) LIKE ? ESCAPE '\\' "
                "OR lower(COALESCE(building, '')) LIKE ? ESCAPE '\\')"
            )
            params.extend([like, like.replace(" ", "-")])
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def buildings_page(self, c: BuildingChoice) -> tuple[list[dict], int, int]:
        """Return one page of buildings, total count, and page count."""
        where_sql, params = self._buildings_where(c)
        total = int(
            self._one(f"SELECT COUNT(*) FROM buildings{where_sql}", params)[0] or 0
        )
        pages = max(1, math.ceil(total / PER_PAGE))
        c.page = min(c.page, pages)
        order_sql = BUILDING_SORTS[c.sort][0]
        rows = self._rows(
            f"SELECT * FROM buildings{where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            [*params, PER_PAGE, (c.page - 1) * PER_PAGE],
        )
        return [_shown_building(r) for r in rows], total, pages

    def building_level_signals(self, c: BuildingChoice) -> list[dict]:
        """Tabulate building `level` against building-level features.

        The tabulation reads every building the neighbourhood and address filters
        keep, whatever its count of held-out ads, since a level comes from the
        training ads.
        """
        key = ("levels", tuple(c.hoods or ()), c.q)
        return self._cached(key, lambda: self._building_level_signals(c))

    def _building_level_signals(self, c: BuildingChoice) -> list[dict]:
        where_sql, params = self._buildings_where(c, min_ads=False)
        results = [
            self.tabulate_feature(
                "buildings",
                feat,
                value_col="level",
                miss_col="heldout_miss",
                where_sql=where_sql,
                params=params,
            )
            for feat in self.features
            if feat["level"] == "building" and feat["name"] in self.building_types
        ]
        results.sort(key=_signal_rank, reverse=True)
        return results

    def has_building(self, building_id: str | None) -> bool:
        """Whether `building_id` has a page under `/workbench/buildings/`."""
        bldg = _text(building_id)
        if not bldg:
            return False
        row = self._one(
            "SELECT 1 FROM buildings WHERE building = ? "
            "UNION ALL SELECT 1 FROM ads WHERE building = ? "
            "UNION ALL SELECT 1 FROM history WHERE building = ? LIMIT 1",
            [bldg, bldg, bldg],
        )
        return row is not None

    def building_detail(self, building_id: str) -> dict | None:
        """Load one building's row, history, grouped units, and held-out ads."""
        b_rows = self._rows(
            "SELECT * FROM buildings WHERE building = ? LIMIT 1", [building_id]
        )
        history_rows = self._rows(
            "SELECT * FROM history WHERE building = ? "
            "ORDER BY COALESCE(unit_id, ''), day ASC, listing_id ASC",
            [building_id],
        )
        ad_rows = self._rows(
            "SELECT * FROM ads WHERE building = ? ORDER BY day DESC, listing_id ASC",
            [building_id],
        )
        if not b_rows and not history_rows and not ad_rows:
            return None

        if b_rows:
            building_row = _shown_building(b_rows[0])
        else:
            sample = ad_rows[0] if ad_rows else history_rows[0]
            building_row = _shown_building(
                {
                    "building": building_id,
                    "address": sample.get("address") or building_id,
                    "neighbourhood": sample.get("neighbourhood"),
                    "zone": None,
                    "level": None,
                    "level_sd": None,
                    "train_ads": sum(1 for r in history_rows if not r.get("heldout")),
                    "heldout_ads": len(ad_rows),
                    "heldout_gap": None,
                    "heldout_miss": None,
                }
            )

        building_features = []
        for feat in self.features:
            if feat["level"] == "building" and feat["name"] in building_row:
                val = building_row.get(feat["name"])
                if val is not None and str(val).lower() not in (
                    "",
                    "nan",
                    "<na>",
                    "null",
                ):
                    building_features.append(
                        {
                            "name": feat["name"],
                            "label": feat["label"],
                            "kind": feat["kind"],
                            "value": (
                                val.replace("_", " ") if isinstance(val, str) else val
                            ),
                        }
                    )

        # Group history rows by unit_id and detect label mismatches and bed conflicts.
        units_by_id: dict[str, list[dict]] = {}
        for h in history_rows:
            uid = (
                _text(h.get("unit_id"))
                or _text(h.get("unit"))
                or str(h.get("listing_id") or "")
            )
            units_by_id.setdefault(uid, []).append(h)

        # Check if multiple unit_ids share a base id or normalized label.
        base_id_counts: dict[str, set[str]] = {}
        base_beds: dict[str, set[int]] = {}
        norm_label_units: dict[str, set[str]] = {}
        for uid, u_ads in units_by_id.items():
            base = PIECE_RE.sub("", uid)
            base_id_counts.setdefault(base, set()).add(uid)
            for ad in u_ads:
                b_val = _finite(ad.get("bedrooms"))
                if b_val is not None:
                    base_beds.setdefault(base, set()).add(round(b_val))
                lbl = _text(ad.get("unit"))
                if lbl:
                    norm = re.sub(r"[^A-Z0-9]", "", lbl.upper())
                    if norm:
                        norm_label_units.setdefault(norm, set()).add(uid)

        units: list[dict] = []
        for uid, u_ads in units_by_id.items():
            u_ads.sort(
                key=lambda r: (
                    str(r.get("day") or ""),
                    str(r.get("listing_id") or ""),
                )
            )
            labels_seen: list[str] = []
            beds_seen: list[int] = []
            formatted_ads: list[dict] = []
            for ad in u_ads:
                lbl = _text(ad.get("unit"))
                if lbl and lbl not in labels_seen:
                    labels_seen.append(lbl)
                b_val = _finite(ad.get("bedrooms"))
                if b_val is not None:
                    b_int = round(b_val)
                    if b_int not in beds_seen:
                        beds_seen.append(b_int)
                formatted_ads.append(
                    {
                        "listing_id": str(ad.get("listing_id") or ""),
                        "day": _text(ad.get("day")),
                        "unit": lbl,
                        "ask": _finite(ad.get("ask")),
                        "bedrooms": b_val,
                        "full_baths": _finite(ad.get("full_baths")),
                        "heldout": bool(ad.get("heldout")),
                    }
                )
            base = PIECE_RE.sub("", uid)
            norm_shared = any(
                len(norm_label_units.get(re.sub(r"[^A-Z0-9]", "", l.upper()), set()))
                > 1
                for l in labels_seen
            )
            label_mismatch = len(labels_seen) > 1 or norm_shared
            bedroom_conflict = len(beds_seen) > 1 or len(base_beds.get(base, set())) > 1
            units.append(
                {
                    "unit_id": uid,
                    "labels": labels_seen,
                    "display_label": " / ".join(labels_seen) if labels_seen else uid,
                    "beds_seen": beds_seen,
                    "label_mismatch": label_mismatch,
                    "bedroom_conflict": bedroom_conflict,
                    "ads": formatted_ads,
                }
            )

        units.sort(
            key=lambda u: (
                not (u["bedroom_conflict"] or u["label_mismatch"]),
                u["display_label"],
            )
        )

        return {
            "building": building_row,
            "features": building_features,
            "history": history_rows,
            "units": units,
            "conflict_units": sum(1 for u in units if u["bedroom_conflict"]),
            "mismatch_units": sum(1 for u in units if u["label_mismatch"]),
            "heldout_ads": [_shown_ad(r) for r in ad_rows],
            "scatter": building_history_scatter(history_rows),
        }


_open: dict[tuple, Diagnostics] = {}
_open_lock = threading.Lock()
_refused: set[tuple] = set()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _expected_sha(meta: dict, stem: str) -> str | None:
    """Read the expected SHA-256 for `<stem>.parquet` from `meta.json`."""
    sha_map = meta.get("sha256")
    if isinstance(sha_map, dict):
        val = sha_map.get(stem) or sha_map.get(f"{stem}.parquet")
        if isinstance(val, str) and val:
            return val
    direct = meta.get(f"{stem}_sha256")
    if isinstance(direct, str) and direct:
        return direct
    files_map = meta.get("files")
    if isinstance(files_map, dict):
        val = files_map.get(f"{stem}.parquet") or files_map.get(stem)
        if isinstance(val, str) and val:
            return val
    return None


def load(root: Path) -> Diagnostics | None:
    """Open the published `diagnostics/` folder under `root`, or None when absent.

    Raises `Refused` when `ads.parquet`, `buildings.parquet`, or `history.parquet`
    fails to match the SHA-256 recorded in `meta.json`.
    """
    folder = Path(root) / FOLDER
    meta_path = folder / META
    paths = {stem: folder / f"{stem}.parquet" for stem in FILES}
    try:
        meta_stat = meta_path.stat()
        stats = {stem: p.stat() for stem, p in paths.items()}
    except OSError:
        return None

    stamp = (
        str(folder.resolve()),
        meta_stat.st_mtime_ns,
        meta_stat.st_size,
        *(
            item
            for stem in FILES
            for item in (stats[stem].st_mtime_ns, stats[stem].st_size)
        ),
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
        for stem, path in paths.items():
            expected = _expected_sha(meta, stem)
            if not expected or expected != _sha256(path):
                _refused.clear()
                _refused.add(stamp)
                raise refused
        for old in _open.values():
            old.close()
        _open.clear()
        found = _open[stamp] = Diagnostics(folder, meta)
        return found


def _usd(value, signed: bool = False) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return charts.usd(value, signed=signed)


def _pct(value, signed: bool = True, digits: int = 0) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return charts.pct(value, signed=signed, digits=digits)


def _day_label(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d:%b} {d.day}, {d.year}"


def _beds_label(value) -> str:
    val = _finite(value)
    if val is None:
        return "-"
    beds = round(val)
    return "Studio" if beds == 0 else f"{beds} BR"


def _trim_float(value) -> str:
    val = _finite(value)
    if val is None:
        return "-"
    return f"{val:g}"


def _render(template: str, **context) -> str:
    return render_template(
        template,
        section="workbench",
        usd=_usd,
        pct=_pct,
        day=_day_label,
        beds_label=_beds_label,
        min_calibration_ads=MIN_CALIBRATION_ADS,
        min_bin_ads=MIN_BIN_ADS,
        min_bin_buildings=MIN_BIN_BUILDINGS,
        max_explained_bins=MAX_EXPLAINED_BINS,
        list_bins=LIST_BINS,
        gap_title=GAP_TITLE,
        mean_gap_title=MEAN_GAP_TITLE,
        miss_title=MISS_TITLE,
        miss_score_title=MISS_SCORE_TITLE,
        max_score_title=MAX_SCORE_TITLE,
        explained_title=EXPLAINED_TITLE,
        small_bin_title=SMALL_BIN_TITLE,
        **context,
    )


def register(app: Flask, root_fn: Callable[[], Path] | Path) -> None:
    """Register the Workbench routes on `app`, reading `<root>/diagnostics/`."""

    def _root() -> Path:
        return Path(root_fn() if callable(root_fn) else root_fn)

    def _diag_or_503() -> Diagnostics:
        try:
            diag = load(_root())
        except Refused as refused:
            log.error("diagnostics refused: %s", refused)
            abort(503, description=str(refused))
        if diag is None:
            abort(503, description="No diagnostics have been published yet.")
        return diag

    def _triage_choice(diag: Diagnostics) -> TriageChoice:
        c = triage_choice(
            request.args, diag.ad_hoods(), diag.valid_flags(), diag.features_by_name
        )
        if c.untagged:
            c.tagged = sorted(tags.current_tags(_root()))
        return c

    def _url_with(endpoint: str, choice_obj, **changes) -> str:
        query = urlencode(choice_obj.args(**changes), doseq=True)
        base = url_for(endpoint, **(request.view_args or {}))
        return f"{base}?{query}" if query else base

    @app.get("/workbench")
    def workbench():
        diag = _diag_or_503()
        default_signals = diag.top_signals()
        return _render(
            "workbench_overview.html",
            info=diag.meta,
            counts=diag.overview_counts(),
            calibration=diag.calibration(),
            signals=default_signals,
            flags=diag.flag_counts(),
        )

    @app.get("/workbench/signals")
    def workbench_signals():
        diag = _diag_or_503()
        c = signal_choice(request.args, diag.ad_hoods())
        names = diag.ad_hood_names()
        groups = diag.signal_groups(c)
        ranked = [s for g in groups for s in g["signals"]]
        return _render(
            "workbench_signals.html",
            info=diag.meta,
            choice=c,
            groups=groups,
            attribute_count=len(ranked),
            bin_count=sum(len(s["bins"]) for s in ranked),
            scopes=SCOPES,
            bedrooms=BEDROOMS,
            hood_groups=boroughs.grouped(names),
            show_hoods=len(names) > 1,
            page_link=lambda **changes: _url_with("workbench_signals", c, **changes),
        )

    @app.get("/workbench/signals/<feature>")
    def workbench_signal(feature: str):
        diag = _diag_or_503()
        c = signal_choice(request.args, diag.ad_hoods())
        detail = diag.signal_detail(feature, c)
        if detail is None:
            abort(404, description=f"No attribute named {feature!r}.")
        names = diag.ad_hood_names()
        return _render(
            "workbench_signal.html",
            info=diag.meta,
            choice=c,
            signal=detail,
            scopes=SCOPES,
            bedrooms=BEDROOMS,
            hood_groups=boroughs.grouped(names),
            show_hoods=len(names) > 1,
            page_link=lambda **changes: _url_with("workbench_signal", c, **changes),
        )

    def _stream_triage_csv(diag: Diagnostics, c: TriageChoice) -> Response:
        columns = diag.triage_csv_columns()

        def generate():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for row in diag.triage_csv_rows(c):
                writer.writerow(row)
                if buffer.tell() > 64 * 1024:
                    yield buffer.getvalue()
                    buffer.seek(0)
                    buffer.truncate()
            yield buffer.getvalue()

        return Response(
            generate(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=triage.csv"},
        )

    @app.get("/workbench/triage")
    def workbench_triage():
        diag = _diag_or_503()
        c = _triage_choice(diag)
        if request.args.get("format") == "csv":
            return _stream_triage_csv(diag, c)
        rows, total, pages = diag.triage_page(c)
        names = diag.ad_hood_names()
        csv_query = urlencode(c.args(page=None), doseq=True)
        csv_url = url_for("workbench_triage_csv") + (
            f"?{csv_query}" if csv_query else ""
        )
        feature_info = diag.features_by_name.get(c.feature) if c.feature else None
        return _render(
            "workbench_triage.html",
            info=diag.meta,
            choice=c,
            rows=rows,
            total=total,
            pages=pages,
            per_page=PER_PAGE,
            sources=SOURCES,
            bases=BASES,
            signs=SIGNS,
            flags=sorted(
                diag.flag_counts(), key=lambda f: (f["count"] == 0, f["count"])
            ),
            phone_rows=PHONE_ROWS,
            bedrooms=BEDROOMS,
            feature_info=feature_info,
            hood_groups=boroughs.grouped(names),
            show_hoods=len(names) > 1,
            list_url=lambda **changes: _url_with("workbench_triage", c, **changes),
            csv_url=csv_url,
        )

    @app.get("/workbench/triage.csv")
    def workbench_triage_csv():
        diag = _diag_or_503()
        c = _triage_choice(diag)
        return _stream_triage_csv(diag, c)

    @app.get("/workbench/buildings")
    def workbench_buildings():
        diag = _diag_or_503()
        c = building_choice(request.args, diag.building_hoods())
        rows, total, pages = diag.buildings_page(c)
        level_signals = diag.building_level_signals(c)
        names = diag.building_hood_names()
        return _render(
            "workbench_buildings.html",
            info=diag.meta,
            choice=c,
            rows=rows,
            total=total,
            pages=pages,
            per_page=PER_PAGE,
            sorts=BUILDING_SORTS,
            default_min_ads=DEFAULT_MIN_ADS,
            signals=level_signals,
            hood_groups=boroughs.grouped(names),
            show_hoods=len(names) > 1,
            list_url=lambda **changes: _url_with("workbench_buildings", c, **changes),
        )

    @app.get("/workbench/buildings/<path:building>")
    def workbench_building(building: str):
        diag = _diag_or_503()
        detail = diag.building_detail(building)
        if detail is None:
            abort(404, description=f"No building named {building!r}.")
        return _render(
            "workbench_building.html",
            info=diag.meta,
            detail=detail,
            b=detail["building"],
        )
