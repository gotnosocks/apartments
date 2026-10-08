"""The figures of the research story (/research/story).

Each figure is server-rendered SVG with classes for colour (static/site.css)
and no inline style, so the site's CSP holds; the build-up animates with CSS
only and stands still under prefers-reduced-motion. Every number comes from
the served bundle (site.sqlite) or the research data, and every figure has a
table with the same values beside it.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from pathlib import Path

from markupsafe import Markup, escape

from . import best, summary
from .charts import nice_ticks, pct, signed, usd

# The variance groups of rentfrontier.variance, in words, and the anatomy
# parts each one gathers.
GROUPS = (
    (
        "market and time",
        "The market",
        "where the whole market stood the month the ask was set",
        ("intercept", "market_drift", "trend", "season", "bedroom_time", "area_time"),
    ),
    (
        "features",
        "The apartment's features",
        "what the listing says: bedrooms, baths, size, floor, doorman, era and so on",
        ("features",),
    ),
    (
        "building",
        "The building",
        "what the building's apartments ask beyond their features",
        ("building",),
    ),
    (
        "building over time",
        "The building's drift",
        "how that premium has moved over the years",
        ("walk", "building_trend"),
    ),
    (
        "building slopes",
        "The building's own prices",
        "its own price for a bedroom or extra space",
        ("bedroom_slope", "feature_slopes"),
    ),
    (
        "unit",
        "The apartment itself",
        "what this apartment asks beyond everything above, from its other listings",
        ("line", "unit", "unit_drift"),
    ),
    (
        "residual",
        "What's left",
        "each ask's own scatter: the part no one could have predicted",
        ("noise",),
    ),
)
GROUP_CLASS = {
    "market and time": "g-market",
    "features": "g-features",
    "building": "g-building",
    "building over time": "g-building-time",
    "building slopes": "g-building-slopes",
    "unit": "g-unit",
    "residual": "g-residual",
}
# The estimate's terms (site.sqlite terms) in their variance group; any other
# term is a listing feature.
TERM_GROUP = {
    "market": "market and time",
    "bedroom_market_curve": "market and time",
    "building": "building",
    "building_drift": "building over time",
    "building_bedroom_premium": "building slopes",
    "building_feature_slopes": "building slopes",
    "unit": "unit",
}
# Each categorical feature group's reference level (rentfrontier.features),
# in words, so an effect reads "against" something a renter can picture.
REFERENCE = {
    "bedrooms": "a one-bedroom",
    "bathrooms": "one full bath",
    "building era": "a building from 1900–1929",
    "building class": "an elevator apartment building",
    "elevator": "an elevator",
    "laundry": "laundry in the building",
    "rooms beyond bedrooms": "two rooms beyond the bedrooms",
    "unit label": "an ordinary unit",
    "description": "an ad that doesn't mention it",
    "outdoor space": "no outdoor space stated",
}
ERA = {
    "pre-1900": "built before 1900",
    "1930-1959": "built 1930–1959",
    "1960-1989": "built 1960–1989",
    "1990-2009": "built 1990–2009",
    "2010+": "built 2010 or later",
}
WIDTH = 720


def _class_of(group: str) -> str:
    return GROUP_CLASS.get(group, "g-features")


# --- How a rent is composed -------------------------------------------------


def composition(anatomy, variance: dict | None) -> list[dict]:
    """The served design's parts gathered into the variance groups, with
    each group's share of the variance in asks when the fit has one."""
    present = {p.key: p for p in anatomy.present} if anatomy else {}
    rows = []
    for key, name, words, parts in GROUPS:
        found = [present[k] for k in parts if k in present]
        if not found:
            continue
        share = (variance or {}).get(key)
        rows.append(
            {
                "group": key,
                "name": name,
                "words": words,
                "parts": [p.label for p in found],
                "plain": [p.plain for p in found],
                "share": share,
                "css": _class_of(key),
            }
        )
    return rows


def composition_svg(rows: list[dict]) -> Markup:
    """The additive structure as stacked boxes: log ask = market + features
    + building + ... + what's left, each box with the design's parts in it
    and, when known, a bar for its share of the variance in asks."""
    if not rows:
        return Markup("")
    box_h, gap, left, bar_x = 58, 18, 34, 470
    height = len(rows) * (box_h + gap) - gap + 8
    has_share = any(r["share"] for r in rows)
    box_w = (bar_x - 16 - left) if has_share else WIDTH - left - 8
    out = []
    for i, r in enumerate(rows):
        y = 4 + i * (box_h + gap)
        op = "+" if i else "="
        out.append(
            f'<text class="op" x="12" y="{y + box_h / 2 + 6:.0f}" '
            f'text-anchor="middle">{op}</text>'
        )
        out.append(
            f'<g class="block {r["css"]} d{i}">'
            f'<rect class="box" x="{left}" y="{y}" width="{box_w}" height="{box_h}" rx="6"/>'
            f'<text class="box-title" x="{left + 12}" y="{y + 22}">{escape(r["name"])}</text>'
            f'<text class="box-parts" x="{left + 12}" y="{y + 42}">'
            f"{escape(' · '.join(r['parts']))}</text>"
        )
        share = r["share"]
        if share:
            scale = WIDTH - bar_x - 70
            mean = max(share["mean"], 0.0)
            lo = max(share.get("lower_90", share["mean"]), 0.0)
            hi = max(share.get("upper_90", share["mean"]), 0.0)
            cy = y + box_h / 2
            out.append(
                f'<rect class="share" x="{bar_x}" y="{cy - 9:.1f}" '
                f'width="{max(scale * mean, 1.5):.1f}" height="18" rx="3"/>'
                f'<line class="share-ci" x1="{bar_x + scale * lo:.1f}" y1="{cy:.1f}" '
                f'x2="{bar_x + scale * hi:.1f}" y2="{cy:.1f}"/>'
                f'<text class="share-label" x="{bar_x + scale * max(hi, mean) + 6:.1f}" '
                f'y="{cy + 4:.1f}">{100 * share["mean"]:.0f}%</text>'
            )
        out.append("</g>")
    if has_share:
        out.insert(
            0,
            f'<text class="axis-title" x="{bar_x}" y="0">share of the spread in asks</text>',
        )
    names = "; ".join(
        r["name"]
        + (f" ({100 * r['share']['mean']:.0f}% of the spread)" if r["share"] else "")
        for r in rows
    )
    label = f"An ask is built from {len(rows)} parts, added on the log scale: {names}."
    return Markup(
        f'<svg class="story-svg compose" viewBox="0 -14 {WIDTH} {height + 14}" '
        f'role="img" aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )


# --- What features are worth ---------------------------------------------------


def feature_words(feature: str, group: str, others: dict) -> str | None:
    """A coefficient's feature in renter words, or None for an indicator
    that only marks a missing detail (those aren't qualities of a home)."""
    if (
        feature.endswith(("unknown", "unspecified", "_missing"))
        or feature.startswith("log_")
        or feature in ("current_capture_ask", "first_listing_of_unit")
    ):
        return None
    if feature in best.LABELS:
        return best.LABELS[feature]
    level = feature.split("=", 1)[1] if "=" in feature else feature
    if group == "bedrooms" and feature.startswith("bedrooms="):
        if level == "0":
            return "a studio"
        return f"{level.replace('+', ' or more')} bedrooms"
    if group == "bathrooms" and feature.startswith("bathrooms="):
        return f"{level.replace('+', ' or more')} full baths"
    if group == "building era":
        return ERA.get(level)
    if group == "building class":
        return summary.CLASSES.get(level)
    if group == "neighbourhood":
        return "the West Village" if feature == "West Village" else feature
    if feature.startswith("text:"):
        words = summary.TEXT.get(feature[5:])
        return f"{words} (ad)" if words else None
    if feature.startswith("label:"):
        return summary.LABELS.get(feature[6:])
    if feature.startswith("outdoor:"):
        return "a " + feature[8:].replace("_", " ")
    if feature in ("landmark", "historic_district"):
        return {"landmark": "a landmark building", "historic_district": None}[feature]
    return None


def headline_effects(coefficients, labels: dict, reference_area: str | None):
    """The features whose 95% interval clears zero and moves rent by at
    least 2%, plus size beyond the typical per 10%, biggest premium first."""
    out = []
    for c in coefficients:
        c = dict(c)
        group = c["feature_group"]
        if c["pct_lower"] is None or c["pct_upper"] is None:
            continue
        if c["feature"] == "log_sqft_vs_bedroom_median":
            # Size always shows: it is the one continuous feature a renter
            # weighs directly.
            # The coefficient is per unit of log size; 10% more space is
            # log(1.1) of a unit.
            def per10(p):
                return 100 * ((1 + p / 100) ** math.log(1.1) - 1)

            out.append(
                {
                    "feature": c["feature"],
                    "words": "10% more space than usual for the bedrooms",
                    "against": "the usual size",
                    "pct": per10(c["pct"]),
                    "lower": per10(c["pct_lower"]),
                    "upper": per10(c["pct_upper"]),
                    "group": labels.get(group, group),
                }
            )
            continue
        words = feature_words(c["feature"], group, labels)
        if not words:
            continue
        if c["pct_lower"] <= 0 <= c["pct_upper"] or abs(c["pct"]) < 2:
            continue
        against = REFERENCE.get(group)
        if group == "neighbourhood" and reference_area:
            against = reference_area
        if c["feature"].startswith("text:"):
            against = REFERENCE["description"]
        out.append(
            {
                "feature": c["feature"],
                "words": words,
                "against": against,
                "pct": c["pct"],
                "lower": c["pct_lower"],
                "upper": c["pct_upper"],
                "group": labels.get(group, group),
            }
        )
    return sorted(out, key=lambda e: -e["pct"])


def effects_svg(effects: list[dict]) -> Markup:
    """A forest plot of headline effects: a dot at the posterior mean and a
    line across the 95% interval, on a percent axis around zero."""
    if not effects:
        return Markup("")
    row, top, label_w = 26, 22, 300
    lo = min(min(e["lower"] for e in effects), 0)
    hi = max(max(e["upper"] for e in effects), 0)
    ticks = nice_ticks(lo, hi, 6)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    span = hi - lo or 1
    plot = WIDTH - label_w - 16

    def x(v):
        return label_w + plot * (v - lo) / span

    height = top + row * len(effects) + 8
    out = [
        f'<line class="grid" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" '
        f'y2="{height - 4}"/><text class="tick" x="{x(t):.1f}" y="{top - 10}" '
        f'text-anchor="middle">{signed(t)}%</text>'
        for t in ticks
    ]
    out.append(
        f'<line class="zero" x1="{x(0):.1f}" y1="{top - 6}" x2="{x(0):.1f}" y2="{height - 4}"/>'
    )
    for i, e in enumerate(effects):
        y = top + row * i + row / 2
        side = "up" if e["pct"] > 0 else "down"
        out.append(
            f'<text class="eff-label" x="{label_w - 10}" y="{y + 4:.1f}" '
            f'text-anchor="end">{escape(e["words"])}</text>'
            f'<line class="ci {side}" x1="{x(e["lower"]):.1f}" y1="{y:.1f}" '
            f'x2="{x(e["upper"]):.1f}" y2="{y:.1f}"/>'
            f'<circle class="dot {side}" cx="{x(e["pct"]):.1f}" cy="{y:.1f}" r="4.5"/>'
        )
    label = "Feature effects on the typical ask, with 95% intervals: " + "; ".join(
        f"{e['words']} {pct(e['pct'], digits=1)}" for e in effects
    )
    return Markup(
        f'<svg class="story-svg effects" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )


# --- One estimate, term by term --------------------------------------------------


def pick_listing(db):
    """An ordinary apartment: among listings that were in the fit and
    reliably estimated, the one with the median ask (ties by id), from those
    available now when any are. Returns (listing, available now)."""
    for current in (True, False):
        rows = db.execute(
            "SELECT * FROM listings WHERE in_fit = 1 AND reliable = 1 "
            "AND contributions IS NOT NULL AND ask IS NOT NULL"
            + (" AND is_current = 1" if current else "")
            + " ORDER BY ask, id"
        ).fetchall()
        if rows:
            return rows[(len(rows) - 1) // 2], current
    return None, False


def build_up(listing, labels: dict, small: float = 40.0, current=False) -> dict | None:
    """The listing's estimate as steps: the market first, then each term in
    the estimate's order, with terms smaller than `small` dollars gathered
    into one step, so the bars end at the estimate."""
    if listing is None:
        return None
    contributions = json.loads(listing["contributions"] or "[]")
    if not contributions:
        return None
    steps, minor = [], []
    for c in contributions:
        term = c["term"]
        group = TERM_GROUP.get(term, "features")
        if term == "market" or abs(c["usd"]) >= small:
            steps.append(
                {
                    "term": term,
                    "label": labels.get(term, term),
                    "usd": c["usd"],
                    "lower": c["lower"],
                    "upper": c["upper"],
                    "group": group,
                    "css": _class_of(group),
                }
            )
        elif c["usd"]:
            minor.append(c)
    if minor:
        steps.append(
            {
                "term": "minor",
                "label": f"{len(minor)} smaller details",
                "usd": sum(c["usd"] for c in minor),
                "lower": None,
                "upper": None,
                "group": "features",
                "css": "g-minor",
                "names": [labels.get(c["term"], c["term"]) for c in minor],
            }
        )
    total = 0.0
    for s in steps:
        s["start"] = total
        total += s["usd"]
        s["end"] = total
    return {
        "listing": listing,
        "current": current,
        "steps": steps,
        "estimate": total,
        "ask": listing["ask"],
        "lower": listing["pred_lower_95"],
        "upper": listing["pred_upper_95"],
    }


def build_up_svg(b: dict | None) -> Markup:
    """A waterfall of the estimate that plays term by term: each bar runs
    from the running total before the term to the total after it, then the
    estimate's 95% range and the ask itself."""
    if not b:
        return Markup("")
    steps = b["steps"]
    row, top, label_w, right = 24, 24, 290, 70
    values = [0.0, b["estimate"], b["ask"]] + [s["end"] for s in steps]
    values += [v for v in (b["lower"], b["upper"]) if v is not None]
    ticks = nice_ticks(0, max(values), 5)
    hi = max(max(values), ticks[-1])
    plot = WIDTH - label_w - right

    def x(v):
        return label_w + plot * v / hi

    n = len(steps) + 2
    height = top + row * n + 10
    out = [
        f'<line class="grid" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" y2="{height - 6}"/>'
        f'<text class="tick" x="{x(t):.1f}" y="{top - 10}" text-anchor="middle">'
        f"{usd(t)}</text>"
        for t in ticks
    ]
    for i, s in enumerate(steps):
        y = top + row * i
        x0, x1 = sorted((x(s["start"]), x(s["end"])))
        sign = "" if s["term"] == "market" else usd(s["usd"], signed=True)
        out.append(
            f'<g class="step {s["css"]} d{min(i, 19)}">'
            f'<text class="eff-label" x="{label_w - 10}" y="{y + row / 2 + 4:.1f}" '
            f'text-anchor="end">{escape(s["label"])}</text>'
            f'<rect class="bar{" neg" if s["usd"] < 0 else ""}" x="{x0:.1f}" y="{y + 4}" '
            f'width="{max(x1 - x0, 1.5):.1f}" height="{row - 8}" rx="2"/>'
            f'<text class="step-value" x="{max(x1, x0) + 6:.1f}" y="{y + row / 2 + 4:.1f}">'
            f"{sign or usd(s['usd'])}</text></g>"
        )
        if i + 1 < len(steps):
            out.append(
                f'<line class="link d{min(i, 19)}" x1="{x(s["end"]):.1f}" y1="{y + row - 4}" '
                f'x2="{x(s["end"]):.1f}" y2="{y + row + 4}"/>'
            )
    i = len(steps)
    y = top + row * i + row / 2
    d = min(i, 19)
    out.append(
        f'<g class="step total d{d}"><text class="eff-label strong" x="{label_w - 10}" '
        f'y="{y + 4:.1f}" text-anchor="end">Estimate</text>'
    )
    if b["lower"] is not None and b["upper"] is not None:
        out.append(
            f'<line class="range" x1="{x(b["lower"]):.1f}" y1="{y:.1f}" '
            f'x2="{x(b["upper"]):.1f}" y2="{y:.1f}"/>'
        )
    out.append(
        f'<circle class="est" cx="{x(b["estimate"]):.1f}" cy="{y:.1f}" r="6"/>'
        f'<text class="step-value" x="{x(b["upper"] or b["estimate"]) + 8:.1f}" '
        f'y="{y + 4:.1f}">{usd(b["estimate"])}</text></g>'
    )
    y += row
    out.append(
        f'<g class="step ask d{min(i + 1, 19)}"><text class="eff-label strong" '
        f'x="{label_w - 10}" y="{y + 4:.1f}" text-anchor="end">The ask</text>'
        f'<path class="ask-mark" d="M{x(b["ask"]):.1f},{y - 7:.1f}l6,7l-6,7l-6,-7z"/>'
        f'<text class="step-value" x="{x(b["ask"]) + 10:.1f}" y="{y + 4:.1f}">'
        f"{usd(b['ask'])}</text></g>"
    )
    label = (
        f"The estimate for one apartment, built term by term: "
        + "; ".join(
            f"{s['label']} {usd(s['usd'], signed=s['term'] != 'market')}" for s in steps
        )
        + f"; estimate {usd(b['estimate'])}"
        + (
            f", 95% range {usd(b['lower'])} to {usd(b['upper'])}"
            if b["lower"] is not None
            else ""
        )
        + f"; the ask {usd(b['ask'])}."
    )
    return Markup(
        f'<svg class="story-svg buildup" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )


# --- Theories on trial ------------------------------------------------------------

# The feature-test ledger (rentfrontier.ledger), read from the checkout that
# follows master, so new tests show between site deploys.
LEDGER = Path(
    os.environ.get(
        "FEATURE_TESTS",
        "/data1/apartments/serve/master/docs/model/feature-tests.md",
    )
)
REPO_LEDGER = Path(__file__).resolve().parents[3] / "docs/model/feature-tests.md"
KINDS = (
    ("model", "The model's shape", "new terms in the model itself"),
    ("listing", "What the ad and records say", "features read from the listing"),
    ("unit", "The apartment's layout", "features of the unit within its building"),
    ("location", "Where the building is", "features read from the building's location"),
    ("data", "Data rules", "rules that fix or split the data, fitted with and without"),
)
VERDICT_WORDS = {
    "gain": "helped",
    "null": "no clear effect",
    "worse": "made it worse",
    "blocked": "set aside",
}
# Model terms in renter words (the ledger's own "about" is for modellers,
# and stays in the table).
PLAIN = {
    "+tunits": "a few apartments far off their building",
    "+yearnoise": "asks scatter more in some years",
    "+bednoise": "bigger apartments' asks scatter more",
    "+bedtime": "each size of apartment has its own trend",
    "+bedtime12": "the trend by size, in a finer variant",
    "+dayfourier": "a smooth season, at each ask's own date",
    "+dayfourier3": "a simpler smooth season",
    "+floorslope": "each building's own price for height",
    "+fourier": "a smooth season, by calendar month",
    "+2slopes": "each building's own price for two more features",
    "nb-prevprice-v1": "how the apartment's last ask was repriced",
    "nb3-prevprice-v2": "the same, on the richer coded-features model",
}
_DIFF = re.compile(r"([+\-−]?[\d,]+\.?\d*)\s*±\s*([\d,]+\.?\d*)")


def _number(text: str) -> float:
    return float(text.replace(",", "").replace("−", "-"))


def _verdict(text: str) -> str:
    text = text.strip().lower()
    if text.startswith("gain"):
        return "gain"
    if text.startswith("worse"):
        return "worse"
    if text.startswith("no clear gain"):
        return "null"
    return "blocked"


def parse_ledger(text: str) -> list[dict]:
    """The ledger's two tables as rows, read by column heading: every
    paired test with its date, change, ΔPSIS-LOO ± SE and verdict."""
    out, header, hand = [], None, False
    for line in text.splitlines():
        if line.startswith("## Paired by hand"):
            hand = True
        if not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set(line) <= set("|-: "):
            continue
        row = dict(zip(header, cells))
        m = _DIFF.search(row.get("ΔPSIS-LOO", ""))
        if not m or not row.get("Change"):
            continue
        change = row["Change"].strip("`")
        # The hand table holds data rules, and feature sets paired on a subset.
        kind = (
            ("listing" if change.startswith("nb") else "data")
            if hand
            else "model"
            if change.startswith("+")
            else row.get("Kind") or "listing"
        )
        out.append(
            {
                "date": row.get("Date", ""),
                "change": change,
                "about": row.get("What", ""),
                "kind": kind if kind in dict((k[0], k) for k in KINDS) else "listing",
                "diff": _number(m.group(1)),
                "se": _number(m.group(2)),
                "verdict": _verdict(row.get("Verdict", "")),
                "verdict_text": row.get("Verdict", ""),
                "pr": row.get("PR", "").lstrip("#") or None,
            }
        )
    return out


def theories(rows: list[dict]) -> list[dict]:
    """One entry per change: its tests (repeats on other fits included),
    and the latest test's verdict, which is the one that stands."""
    by = {}
    for r in sorted(rows, key=lambda r: r["date"]):
        t = by.setdefault(
            r["change"],
            {"change": r["change"], "kind": r["kind"], "tests": [], "about": ""},
        )
        t["tests"].append(r)
        t["about"] = r["about"] or t["about"]
        t["pr"] = r["pr"] or t.get("pr")
    out = []
    for t in by.values():
        last = t["tests"][-1]
        t.update(
            first=t["tests"][0]["date"],
            date=last["date"],
            diff=last["diff"],
            se=last["se"],
            verdict=last["verdict"],
            verdict_text=last["verdict_text"],
            words=PLAIN.get(t["change"]) or t["about"] or t["change"].lstrip("+"),
        )
        out.append(t)
    order = {k[0]: i for i, k in enumerate(KINDS)}
    out.sort(key=lambda t: (order.get(t["kind"], 9), -t["diff"]))
    # The order the theories were first tried, for the playback.
    for i, t in enumerate(sorted(out, key=lambda t: (t["first"], t["change"]))):
        t["seq"] = i
    return out


class Ledger:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else LEDGER
        self._key = None
        self._value = None
        self._lock = threading.Lock()

    def load(self) -> list[dict]:
        source = next((p for p in (self.path, REPO_LEDGER) if p.is_file()), None)
        if source is None:
            return []
        stat = source.stat()
        key = (str(source.resolve()), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key != self._key:
                self._key, self._value = key, parse_ledger(source.read_text())
            return self._value


def _signed_sqrt(v: float) -> float:
    return math.copysign(math.sqrt(abs(v)), v)


def theories_svg(entries: list[dict]) -> Markup:
    """Every theory as a row: a dot for each time it was tested, a band of
    two standard errors around the latest test, coloured by its verdict, on
    a square-root axis so +2,000 and +20 both read. Rows appear in the order
    the theories were first tried."""
    if not entries:
        return Markup("")
    row, top, label_w, head = 20, 26, 300, 22
    values = [0.0]
    for t in entries:
        values += [t["diff"] - 2 * t["se"], t["diff"] + 2 * t["se"]]
        values += [x["diff"] for x in t["tests"]]
    lo, hi = _signed_sqrt(min(values)), _signed_sqrt(max(values))
    pad = 0.04 * (hi - lo or 1)
    lo, hi = lo - pad, hi + pad
    plot = WIDTH - label_w - 12

    def x(v):
        return label_w + plot * (_signed_sqrt(v) - lo) / (hi - lo)

    ticks = [
        t
        for t in (-200, -50, 0, 50, 200, 500, 1000, 2000, 4000)
        if lo <= _signed_sqrt(t) <= hi
    ]
    kinds = []
    for t in entries:
        if not kinds or kinds[-1] != t["kind"]:
            kinds.append(t["kind"])
    height = top + row * len(entries) + head * len(kinds) + 8
    out = [
        f'<line class="grid" x1="{x(v):.1f}" y1="{top - 6}" x2="{x(v):.1f}" '
        f'y2="{height - 4}"/><text class="tick" x="{x(v):.1f}" y="{top - 12}" '
        f'text-anchor="middle">{signed(v)}</text>'
        for v in ticks
    ]
    out.append(
        f'<line class="zero" x1="{x(0):.1f}" y1="{top - 6}" x2="{x(0):.1f}" y2="{height - 4}"/>'
    )
    names = {k[0]: k[1] for k in KINDS}
    y, kind = top, None
    for t in entries:
        if t["kind"] != kind:
            kind = t["kind"]
            out.append(
                f'<text class="kind-head" x="0" y="{y + head - 6}">'
                f"{escape(names.get(kind, kind))}</text>"
            )
            y += head
        cy = y + row / 2
        words = t["words"] if len(t["words"]) <= 46 else t["words"][:45] + "…"
        lo2, hi2 = t["diff"] - 2 * t["se"], t["diff"] + 2 * t["se"]
        out.append(
            f'<g class="trial v-{t["verdict"]} d{min(t["seq"], 39)}">'
            f"<title>{escape(t['words'])}: {t['diff']:+,.0f} ± {t['se']:,.0f}, "
            f"{VERDICT_WORDS[t['verdict']]}</title>"
            f'<text class="eff-label" x="{label_w - 10}" y="{cy + 4:.1f}" '
            f'text-anchor="end">{escape(words)}</text>'
            f'<line class="ci" x1="{x(lo2):.1f}" y1="{cy:.1f}" x2="{x(hi2):.1f}" y2="{cy:.1f}"/>'
            + "".join(
                f'<circle class="rep" cx="{x(r["diff"]):.1f}" cy="{cy:.1f}" r="2.5"/>'
                for r in t["tests"][:-1]
            )
            + f'<circle class="dot" cx="{x(t["diff"]):.1f}" cy="{cy:.1f}" r="4.5"/></g>'
        )
        y += row
    label = "Theories tested, with the change in PSIS-LOO and verdict: " + "; ".join(
        f"{t['words']} {t['diff']:+,.0f}, {VERDICT_WORDS[t['verdict']]}"
        for t in entries
    )
    return Markup(
        f'<svg class="story-svg trials" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )


# How the served design changed: every switch of the served model, from the
# board's selection milestones.
ERAS = (
    (
        "bayes",
        "Hand-built Bayesian models",
        "one Chelsea model in PyMC, refined fit by fit and chosen by hand",
    ),
    (
        "frontier",
        "A search for the best model",
        "many designs fitted on the same rows and scored by PSIS-LOO, the winner picked by hand",
    ),
    (
        "auto",
        "Chosen automatically",
        "a fixed rule serves a new fit only when it predicts better, or ties and is faster",
    ),
)
# Words for the model terms that only show up in served designs.
TERM_WORDS = {
    "nocurves": "a straight line per feature, no curves",
    "btrend": "each building's own trend",
    "bathfloor": "each building's own price for baths and height",
}
_PR = re.compile(r"\(#(\d+)\)")
_SET_START = re.compile(r"^(nb\d*|unit)")


def design_terms(run: str) -> tuple[list[str], str] | None:
    """A frontier run's model terms and feature set, from its name:
    `m7-nocurves-floorslope-nb3-coded-v2-rows-…` → (["nocurves",
    "floorslope"], "nb3-coded-v2"). None for a name in another form."""
    head = run.split("-rows-")[0]
    tokens = head.split("-")
    if len(tokens) < 2 or not re.fullmatch(r"m\d+\w*", tokens[0]):
        return None
    for i, token in enumerate(tokens[1:], 1):
        if _SET_START.match(token):
            return tokens[1:i], "-".join(tokens[i:])
    return tokens[1:], ""


def _day_label(at: str) -> str:
    from datetime import datetime

    d = datetime.fromisoformat(at)
    return f"{d:%b} {d.day}"


def served_spells(switches: list[dict], word: str) -> list[dict]:
    """Each run of switches whose feature set contains `word`, with the hours
    until the next switch replaced it (None while it is still served)."""
    from datetime import datetime

    out = []
    for i, s in enumerate(switches):
        if word not in (s["feature_set"] or ""):
            continue
        if out and out[-1]["last"] == i - 1:
            out[-1]["last"] = i
        else:
            out.append({"first": i, "last": i, "switch": s})
    for spell in out:
        nxt = spell["last"] + 1
        spell["hours"] = (
            (
                datetime.fromisoformat(switches[nxt]["at"])
                - datetime.fromisoformat(spell["switch"]["at"])
            ).total_seconds()
            / 3600
            if nxt < len(switches)
            else None
        )
        spell["until"] = switches[nxt] if nxt < len(switches) else None
    return out


def term_words(term: str) -> str:
    return PLAIN.get("+" + term) or TERM_WORDS.get(term) or term


def design_history(milestones: list[dict]) -> list[dict]:
    """Every switch of the served model, oldest first, with its era, PR and
    (for frontier fits) model terms and feature set."""
    switches = sorted(
        (m for m in milestones if m.get("kind") == "selection" and m.get("at")),
        key=lambda m: m["at"],
    )
    out, auto = [], False
    for i, m in enumerate(switches):
        title = m.get("title") or ""
        auto = auto or "autoselect" in title or "Automatic selection" in title
        era = (
            "bayes"
            if m.get("family") == "pymc_bayesian"
            else "auto"
            if auto
            else "frontier"
        )
        prs = _PR.findall(title)
        words = _PR.sub("", title)
        words = re.sub(r"^Selection \(autoselect\):\s*", "", words).strip(" ;")
        parsed = design_terms(m.get("model") or "") if era != "bayes" else None
        out.append(
            {
                "seq": i,
                "at": m["at"],
                "date": m["at"][:10],
                "day": _day_label(m["at"]),
                "era": era,
                "words": words[:1].upper() + words[1:],
                "pr": prs[-1] if prs else None,
                "sha": m.get("sha"),
                "terms": parsed[0] if parsed else None,
                "feature_set": parsed[1] if parsed else None,
            }
        )
    return out


def eras(switches: list[dict]) -> list[dict]:
    """Each era that has switches: its name, words, first and last date
    and how many switches it saw."""
    out = []
    for key, name, words in ERAS:
        mine = [s for s in switches if s["era"] == key]
        if mine:
            out.append(
                {
                    "key": key,
                    "name": name,
                    "words": words,
                    "first": mine[0]["date"],
                    "last": mine[-1]["date"],
                    "first_day": mine[0]["day"],
                    "last_day": mine[-1]["day"],
                    "count": len(mine),
                }
            )
    return out


def term_lives(switches: list[dict]) -> list[dict]:
    """Each model term in a served frontier design, in the order it first
    appeared, with the switches it was served in (by seq) and whether the
    design served now still has it."""
    designs = [s for s in switches if s["terms"] is not None]
    if not designs:
        return []
    order, served = [], {}
    for s in designs:
        for t in s["terms"]:
            if t not in served:
                order.append(t)
                served[t] = []
            served[t].append(s["seq"])
    now = set(designs[-1]["terms"])
    return [
        {"term": t, "words": term_words(t), "served": served[t], "now": t in now}
        for t in order
    ]


def _day(at: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(at).timestamp() / 86400


def history_svg(switches: list[dict], lives: list[dict]) -> Markup:
    """The served model's switches on a date axis, in a band for each era,
    and below them a strip for each model term: filled while a served
    design had the term."""
    if not switches:
        return Markup("")
    label_w, top, lane, row = 260, 30, 34, 18
    days = [_day(s["at"]) for s in switches]
    d0, d1 = math.floor(min(days)), math.ceil(max(days)) + 0.5
    plot = WIDTH - label_w - 12

    def x(day):
        return label_w + plot * (day - d0) / (d1 - d0 or 1)

    era_keys = [e[0] for e in ERAS if any(s["era"] == e[0] for s in switches)]
    names = {e[0]: e[1] for e in ERAS}
    strip_top = top + lane * len(era_keys) + 26
    height = strip_top + row * len(lives) + 8
    out = []
    from datetime import date, timedelta

    start = date.fromtimestamp(d0 * 86400)
    for k in range(0, int(d1 - d0) + 1):
        day = start + timedelta(days=k)
        if k % 2:
            continue
        xv = x(d0 + k)
        out.append(
            f'<line class="grid" x1="{xv:.1f}" y1="{top - 6}" x2="{xv:.1f}" y2="{height - 4}"/>'
            f'<text class="tick" x="{xv:.1f}" y="{top - 12}" text-anchor="middle">'
            f"{day.strftime('%b')} {day.day}</text>"
        )
    for i, key in enumerate(era_keys):
        cy = top + lane * i + lane / 2
        out.append(
            f'<text class="eff-label" x="{label_w - 10}" y="{cy + 4:.1f}" '
            f'text-anchor="end">{escape(names[key])}</text>'
        )
        mine = [(s, d) for s, d in zip(switches, days) if s["era"] == key]
        out.append(
            f'<line class="era-line era-{key}" x1="{x(mine[0][1]):.1f}" y1="{cy:.1f}" '
            f'x2="{x(mine[-1][1]):.1f}" y2="{cy:.1f}"/>'
        )
        for s, d in mine:
            out.append(
                f'<circle class="switch era-{key} d{min(s["seq"], 39)}" cx="{x(d):.1f}" '
                f'cy="{cy:.1f}" r="5"><title>{escape(s["date"])}: {escape(s["words"])}'
                "</title></circle>"
            )
    if lives:
        out.append(
            f'<text class="kind-head" x="0" y="{strip_top - 8}">'
            "Model terms in the served design</text>"
        )
        at = {s["seq"]: d for s, d in zip(switches, days)}
        seqs = sorted(at)
        for j, life in enumerate(lives):
            cy = strip_top + row * j + row / 2
            words = (
                life["words"] if len(life["words"]) <= 40 else life["words"][:39] + "…"
            )
            out.append(
                f'<text class="eff-label{"" if life["now"] else " gone"}" '
                f'x="{label_w - 10}" y="{cy + 4:.1f}" text-anchor="end">'
                f"{escape(words)}</text>"
            )
            for seq in life["served"]:
                nxt = next((q for q in seqs if q > seq), None)
                end = at[nxt] if nxt is not None else d1
                out.append(
                    f'<rect class="term-span{" now" if life["now"] else ""}" '
                    f'x="{x(at[seq]):.1f}" y="{cy - 5:.1f}" '
                    f'width="{max(x(end) - x(at[seq]), 1.5):.1f}" height="10">'
                    f"<title>{escape(life['words'])}</title></rect>"
                )
    label = (
        f"The served model changed {len(switches)} times between {switches[0]['date']} "
        f"and {switches[-1]['date']}: "
        + "; ".join(
            f"{e['name']}, {e['count']} switches from {e['first']} to {e['last']}"
            for e in eras(switches)
        )
        + ". Model terms served: "
        + "; ".join(
            f"{life['words']}{'' if life['now'] else ' (since dropped)'}"
            for life in lives
        )
    )
    return Markup(
        f'<svg class="story-svg history" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )
