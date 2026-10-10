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
import statistics
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
            # the median over draws; records from before it was kept carry only the mean
            central = share.get("median", share["mean"])
            mid = max(central, 0.0)
            lo = max(share.get("lower_90", central), 0.0)
            hi = max(share.get("upper_90", central), 0.0)
            cy = y + box_h / 2
            out.append(
                f'<rect class="share" x="{bar_x}" y="{cy - 9:.1f}" '
                f'width="{max(scale * mid, 1.5):.1f}" height="18" rx="3"/>'
                f'<line class="share-ci" x1="{bar_x + scale * lo:.1f}" y1="{cy:.1f}" '
                f'x2="{bar_x + scale * hi:.1f}" y2="{cy:.1f}"/>'
                f'<text class="share-label" x="{bar_x + scale * max(hi, mid) + 6:.1f}" '
                f'y="{cy + 4:.1f}">{100 * central:.0f}%</text>'
            )
        out.append("</g>")
    if has_share:
        out.insert(
            0,
            f'<text class="axis-title" x="{bar_x}" y="-14">share of the spread in asks</text>'
            f'<text class="axis-title" x="{bar_x}" y="0">between listings, not of the rent</text>',
        )
    names = "; ".join(
        r["name"]
        + (f" ({100 * r['share']['mean']:.0f}% of the spread)" if r["share"] else "")
        for r in rows
    )
    label = f"An ask is built from {len(rows)} parts, added on the log scale: {names}."
    return Markup(
        f'<svg class="story-svg compose" viewBox="0 -28 {WIDTH} {height + 28}" '
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
        return summary.hood_name(feature)
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
                "is_area": group == "neighbourhood",
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
        # a neighbourhood's baseline is not one a reader can guess
        vs = (
            f'<tspan class="vs"> vs {escape(e["against"])}</tspan>'
            if e.get("is_area") and e["against"]
            else ""
        )
        out.append(
            f'<text class="eff-label" x="{label_w - 10}" y="{y + 4:.1f}" '
            f'text-anchor="end">{escape(e["words"])}{vs}</text>'
            f'<line class="ci {side}" x1="{x(e["lower"]):.1f}" y1="{y:.1f}" '
            f'x2="{x(e["upper"]):.1f}" y2="{y:.1f}"/>'
            f'<circle class="dot {side}" cx="{x(e["pct"]):.1f}" cy="{y:.1f}" r="4.5"/>'
        )
    label = "Feature effects on the typical ask, with 95% intervals: " + "; ".join(
        f"{e['words']}{' vs ' + e['against'] if e.get('is_area') and e['against'] else ''} "
        f"{pct(e['pct'], digits=1)}"
        for e in effects
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


def _median_miss(rows) -> float:
    """The median gap between ask and estimate, as a percentage of the estimate."""
    gaps = sorted(abs(r["ask"] - r["estimate"]) / r["estimate"] for r in rows)
    mid = len(gaps) // 2
    return 100 * (gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2)


def borders(
    db, reach: float = 600, step: float = 75, near_min: int = 5, bin_min: int = 5
) -> list[dict]:
    """Does a neighbourhood's name carry its premium, or only where it is?
    Every building's total premium, its neighbourhood's label term times its
    own level, by signed distance to the nearest building with the other
    label (negative on the first side), as medians in `step`-metre bins out
    to `reach`. Pairs with under `near_min` buildings within one step of the
    line on either side don't share a border; bins under `bin_min` are not
    drawn. Each side is summed up by its buildings within one step of the
    line and those from half of `reach` to `reach` in: how a side moves
    toward the line, and the gap across it. A no-fit look at the served
    terms, not a test."""
    labels = {
        r["feature"]: r["pct"]
        for r in db.execute(
            "SELECT feature, pct FROM coefficients WHERE feature_group = 'neighbourhood'"
        )
    }
    if not labels:
        return []
    rows = db.execute(
        "SELECT neighbourhood, latitude, longitude, level_pct FROM buildings "
        "WHERE latitude IS NOT NULL AND level_pct IS NOT NULL AND fit_rows > 0 "
        "AND neighbourhood IS NOT NULL"
    ).fetchall()
    if not rows:
        return []
    # metres on a flat projection about one latitude; fine at this scale
    east = (
        math.cos(math.radians(statistics.mean(r["latitude"] for r in rows))) * 111_320
    )
    by = {}
    for r in rows:
        label = labels.get(r["neighbourhood"], 0.0)
        by.setdefault(r["neighbourhood"], []).append(
            (
                r["longitude"] * east,
                r["latitude"] * 110_540,
                100 * ((1 + label / 100) * (1 + r["level_pct"] / 100) - 1),
            )
        )

    def grid(points):
        cells = {}
        for p in points:
            cells.setdefault((int(p[0] // reach), int(p[1] // reach)), []).append(p)
        return cells

    def nearest(p, cells):
        cx, cy = int(p[0] // reach), int(p[1] // reach)
        best_d = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in cells.get((cx + dx, cy + dy), ()):
                    d = math.hypot(p[0] - q[0], p[1] - q[1])
                    best_d = d if best_d is None or d < best_d else best_d
        return best_d

    def median(v):
        return statistics.median(v) if v else None

    out = []
    names = sorted(by)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pts = []
            for side, own, other in ((-1, by[a], grid(by[b])), (1, by[b], grid(by[a]))):
                for p in own:
                    d = nearest(p, other)
                    if d is not None and d < reach:
                        pts.append((side * d, p[2]))
            near_a = [t for d, t in pts if -step <= d < 0]
            near_b = [t for d, t in pts if 0 <= d < step]
            if len(near_a) < near_min or len(near_b) < near_min:
                continue
            bins = []
            k = int(reach // step)
            for j in range(-k, k):
                v = [t for d, t in pts if j * step <= d < (j + 1) * step]
                if len(v) >= bin_min:
                    bins.append(
                        {"mid": (j + 0.5) * step, "median": median(v), "n": len(v)}
                    )
            in_a = [t for d, t in pts if d <= -reach / 2]
            in_b = [t for d, t in pts if d >= reach / 2]
            in_a = median(in_a) if len(in_a) >= bin_min else None
            in_b = median(in_b) if len(in_b) >= bin_min else None
            out.append(
                {
                    "a": a,
                    "b": b,
                    "label_a": labels.get(a, 0.0),
                    "label_b": labels.get(b, 0.0),
                    "gap": labels.get(b, 0.0) - labels.get(a, 0.0),
                    "buildings": len(pts),
                    "in_a": in_a,
                    "near_a": median(near_a),
                    "near_b": median(near_b),
                    "in_b": in_b,
                    # the gap across the line, and each side's move toward it
                    "near": median(near_b) - median(near_a),
                    "near_n": min(len(near_a), len(near_b)),
                    "toward_a": None if in_a is None else median(near_a) - in_a,
                    "toward_b": None if in_b is None else median(near_b) - in_b,
                    "bins": bins,
                }
            )
    return out


def border_tests(trials: list[dict]) -> dict:
    """The ledger's latest tests of a smooth location surface added to the
    neighbourhood names ("-loc-v1") and in place of them ("-locnolabel-v1")."""
    out = {}
    for key, suffix in (("surface", "-loc-v1"), ("nolabel", "-locnolabel-v1")):
        found = [t for t in trials if t["change"].endswith(suffix)]
        out[key] = max(found, key=lambda t: t["date"]) if found else None
    return out


def borders_svg(pairs: list[dict], reach: float = 600) -> Markup:
    """Small multiples, one per border: dots at the median total premium of
    the buildings in each distance bin, and a dashed step at the two label
    terms alone. Dots that follow the step: the name carries the premium;
    dots that climb across the line: the buildings' own levels carry it."""
    if not pairs:
        return Markup("")
    cols, gap, top, ph, axis_h = 2, 70, 34, 150, 32
    pw = (WIDTH - 66 - gap * (cols - 1)) / cols
    values = [b["median"] for p in pairs for b in p["bins"]]
    values += [v for p in pairs for v in (p["label_a"], p["label_b"])]
    ticks = nice_ticks(min(values + [0]), max(values + [0]), 5)
    lo, hi = ticks[0], ticks[-1]
    rows = math.ceil(len(pairs) / cols)
    height = rows * (top + ph + axis_h)
    out = []
    for i, p in enumerate(pairs):
        ox = 44 + (i % cols) * (pw + gap)
        oy = (i // cols) * (top + ph + axis_h) + top

        def x(d):
            return ox + pw * (d + reach) / (2 * reach)

        def y(v):
            return oy + ph * (hi - v) / (hi - lo)

        out.append(
            f'<text class="eff-label strong" x="{ox:.1f}" y="{oy - 18}">'
            f"{escape(p['a'])} → {escape(p['b'])}</text>"
        )
        for t in ticks:
            out.append(
                f'<line class="grid" x1="{ox:.1f}" y1="{y(t):.1f}" x2="{ox + pw:.1f}" '
                f'y2="{y(t):.1f}"/><text class="tick" x="{ox - 6:.1f}" y="{y(t) + 4:.1f}" '
                f'text-anchor="end">{signed(t)}%</text>'
            )
        for d in (-reach, -reach / 2, 0, reach / 2, reach):
            out.append(
                f'<text class="tick" x="{x(d):.1f}" y="{oy + ph + 18:.1f}" '
                f'text-anchor="middle">{abs(d):.0f} m</text>'
            )
        out.append(
            f'<line class="zero" x1="{x(0):.1f}" y1="{oy - 6:.1f}" x2="{x(0):.1f}" '
            f'y2="{oy + ph:.1f}"/>'
            f'<polyline class="target" fill="none" points="{x(-reach):.1f},{y(p["label_a"]):.1f} '
            f"{x(0):.1f},{y(p['label_a']):.1f} {x(0):.1f},{y(p['label_b']):.1f} "
            f'{x(reach):.1f},{y(p["label_b"]):.1f}"/>'
        )
        for b in p["bins"]:
            out.append(
                f'<circle class="cov80" cx="{x(b["mid"]):.1f}" cy="{y(b["median"]):.1f}" '
                f'r="{min(7, 2.5 + math.sqrt(b["n"]) / 2):.1f}"><title>{b["n"]} buildings, '
                f"{signed(round(b['median'], 1))}%</title></circle>"
            )
    label = "Total building premium by distance to each border: " + "; ".join(
        f"{p['a']} to {p['b']}: names alone {signed(round(p['gap']))} points, "
        f"buildings within 75 m of the line {signed(round(p['near']))}"
        for p in pairs
    )
    return Markup(
        f'<svg class="story-svg borders" viewBox="0 0 {WIDTH} {height:.0f}" '
        f'role="img" aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )


def accuracy(db, small: int = 30) -> dict | None:
    """How close the estimates come on the held-out asks, which no fit saw:
    the median miss, for apartments the fit saw in other listings ("seen") and
    for ones it never saw ("new", reported only with at least `small` asks),
    and the share of asks inside their likely ask range (the middle 80%).
    `groups` are the same shares, and the 95% range's, by neighbourhood, by
    estimate fifth and for seen and new apartments: where the ranges hold."""
    rows = db.execute(
        "SELECT ask, estimate, pit, unit_fit_rows, neighbourhood FROM listings "
        "WHERE method = 'heldout' AND ask > 0 AND estimate > 0"
    ).fetchall()
    if not rows:
        return None
    seen = [r for r in rows if r["unit_fit_rows"] > 0]
    new = [r for r in rows if r["unit_fit_rows"] == 0]
    return {
        "n": len(rows),
        "median": _median_miss(rows),
        # the median ask, to $100, to put the miss in dollars
        "typical": round(statistics.median(r["ask"] for r in rows), -2),
        "seen": {"n": len(seen), "median": _median_miss(seen), **_inside(seen)}
        if seen
        else None,
        "new": {"n": len(new), "median": _median_miss(new), **_inside(new)}
        if len(new) >= small
        else None,
        "likely": _inside(rows)["likely"],
        "groups": _coverage_groups(rows, small),
    }


def _inside(rows) -> dict:
    """The share of asks inside their 80% and their 95% ranges, in percent."""
    n = len(rows)
    return {
        "likely": 100 * sum(0.1 <= r["pit"] <= 0.9 for r in rows) / n,
        "wide": 100 * sum(0.025 <= r["pit"] <= 0.975 for r in rows) / n,
    }


def _coverage_groups(rows, small: int) -> list[dict]:
    """Coverage by neighbourhood, by fifth of the estimate (cheapest first)
    and by whether the fit saw the apartment; groups under `small` asks out."""
    out = []

    def add(kind, name, part):
        if len(part) >= small:
            out.append({"kind": kind, "name": name, "n": len(part), **_inside(part)})

    for area in sorted({r["neighbourhood"] or "" for r in rows} - {""}):
        add("Neighbourhood", area, [r for r in rows if r["neighbourhood"] == area])
    ranked = sorted(rows, key=lambda r: r["estimate"])
    for i, name in enumerate(
        ("Cheapest fifth", "", "Middle fifth", "", "Priciest fifth")
    ):
        part = ranked[i * len(ranked) // 5 : (i + 1) * len(ranked) // 5]
        if part:
            add("Estimate", name or f"Fifth {i + 1}", part)
    add("Apartment", "Listed before", [r for r in rows if r["unit_fit_rows"] > 0])
    add("Apartment", "New to the data", [r for r in rows if r["unit_fit_rows"] == 0])
    return out


def coverage_svg(groups: list[dict]) -> Markup:
    """Where the ranges hold: per group, a dot at the share of held-out asks
    inside the 80% range and a ring at the share inside the 95% range, with
    dashed lines at the 80% and 95% an honest range would hold."""
    if not groups:
        return Markup("")
    row, head, top, label_w = 22, 22, 30, 200
    lo = min(50, 5 * math.floor(min(g["likely"] for g in groups) / 5))
    plot = WIDTH - label_w - 24

    def x(v):
        return label_w + plot * (v - lo) / (100 - lo)

    out, y, kind = [], top, None
    for g in groups:
        if g["kind"] != kind:
            kind = g["kind"]
            y += head if len(out) else head - 8
            out.append(
                f'<text class="eff-label strong" x="{label_w - 10}" y="{y - 4:.1f}" '
                f'text-anchor="end">{escape(kind)}</text>'
            )
        y += row
        cy = y - row / 2
        out.append(
            f'<text class="eff-label" x="{label_w - 10}" y="{cy + 4:.1f}" '
            f'text-anchor="end">{escape(g["name"])}</text>'
            f'<line class="link" x1="{x(g["likely"]):.1f}" y1="{cy:.1f}" '
            f'x2="{x(g["wide"]):.1f}" y2="{cy:.1f}"/>'
            f'<circle class="cov80" cx="{x(g["likely"]):.1f}" cy="{cy:.1f}" r="5"/>'
            f'<circle class="cov95" cx="{x(g["wide"]):.1f}" cy="{cy:.1f}" r="4.5"/>'
        )
    height = y + 10
    axis = [
        f'<line class="grid" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" '
        f'y2="{height - 4}"/><text class="tick" x="{x(t):.1f}" y="{top - 10}" '
        f'text-anchor="middle">{t}%</text>'
        for t in range(lo, 101, 10)
        if t not in (80,)
    ] + [
        f'<line class="target" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" '
        f'y2="{height - 4}"/><text class="tick" x="{x(t):.1f}" y="{top - 10}" '
        f'text-anchor="middle">{t}%</text>'
        for t in (80, 95)
    ]
    label = "Share of held-out asks inside their 80% and 95% ranges: " + "; ".join(
        f"{g['name']} {g['likely']:.0f}% and {g['wide']:.0f}%" for g in groups
    )
    return Markup(
        f'<svg class="story-svg coverage" viewBox="0 0 {WIDTH} {height:.0f}" '
        f'role="img" aria-label="{escape(label)}">' + "".join(axis + out) + "</svg>"
    )


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
    "nb-prevprice-v1": "how the unit's previous listing was repriced",
    "nb3-prevprice-v2": "the same repricing idea, retested once Greenwich Village joined",
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
                "retest": row.get("Retest", ""),
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
            retest=last.get("retest", ""),
            words=PLAIN.get(t["change"]) or t["about"] or t["change"].lstrip("+"),
        )
        t["clear_gain"] = t["diff"] > 2 * t["se"]
        # The ledger marks a test "due" when it ran on an older dataset.
        t["due"] = t["retest"].startswith("due")
        # The ledger's words for the table, without its own asides.
        t["note"] = re.sub(r"\s*\([^()]*\)", "", t["about"]).strip()
        out.append(t)
    order = {k[0]: i for i, k in enumerate(KINDS)}
    out.sort(key=lambda t: (order.get(t["kind"], 9), -t["diff"]))
    # The order the theories were first tried, for the playback.
    for i, t in enumerate(sorted(out, key=lambda t: (t["first"], t["change"]))):
        t["seq"] = i
    return out


class _Cached:
    """A file read from the checkout that follows master (or the repo's own
    copy), parsed again only when it changes."""

    default: Path
    repo: Path
    empty = None

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else self.default
        self._key = None
        self._value = None
        self._lock = threading.Lock()

    def parse(self, text: str):
        raise NotImplementedError

    def load(self):
        source = next((p for p in (self.path, self.repo) if p.is_file()), None)
        if source is None:
            return self.empty
        stat = source.stat()
        key = (str(source.resolve()), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key != self._key:
                self._key, self._value = key, self.parse(source.read_text())
            return self._value


class Ledger(_Cached):
    default, repo, empty = LEDGER, REPO_LEDGER, []

    def parse(self, text: str) -> list[dict]:
        return parse_ledger(text)


def _signed_sqrt(v: float) -> float:
    return math.copysign(math.sqrt(abs(v)), v)


def label_lines(words: str, width: int = 46, lines: int = 2) -> list[str]:
    """`words` wrapped at spaces into at most `lines` lines of `width`
    characters, the last cut with an ellipsis if the words still run on."""
    out, rest = [], words
    while rest and len(out) < lines - 1 and len(rest) > width:
        cut = rest.rfind(" ", 0, width + 1)
        cut = cut if cut > 0 else width
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if len(rest) > width:
        rest = rest[: width - 1].rstrip() + "…"
    return out + [rest]


def theories_svg(entries: list[dict]) -> Markup:
    """Every theory as a row: a dot for each time it was tested, a band of
    two standard errors around the latest test, coloured by its verdict, on
    a square-root axis so +2,000 and +20 both read. Rows appear in the order
    the theories were first tried."""
    if not entries:
        return Markup("")
    row, top, label_w, head, line = 20, 26, 300, 22, 13
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
    wrapped = [label_lines(t["words"], lines=4) for t in entries]
    extra = sum(line * (len(w) - 1) for w in wrapped)
    height = top + row * len(entries) + extra + head * len(kinds) + 8
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
    for t, lines in zip(entries, wrapped):
        if t["kind"] != kind:
            kind = t["kind"]
            out.append(
                f'<text class="kind-head" x="0" y="{y + head - 6}">'
                f"{escape(names.get(kind, kind))}</text>"
            )
            y += head
        tall = row + line * (len(lines) - 1)
        cy = y + tall / 2
        first = cy + 4 - line * (len(lines) - 1) / 2
        # a space leading each later line keeps the words apart when the text is copied or
        # read out; the lines are right-aligned, so it doesn't move them
        text = "".join(
            f'<tspan x="{label_w - 10}" y="{first + line * i:.1f}">'
            f"{' ' if i else ''}{escape(part)}</tspan>"
            for i, part in enumerate(lines)
        )
        lo2, hi2 = t["diff"] - 2 * t["se"], t["diff"] + 2 * t["se"]
        out.append(
            f'<g class="trial v-{t["verdict"]} d{min(t["seq"], 39)}">'
            f"<title>{escape(t['words'])}: {t['diff']:+,.0f} ± {t['se']:,.0f}, "
            f"{VERDICT_WORDS[t['verdict']]}</title>"
            f'<text class="eff-label" text-anchor="end">{text}</text>'
            f'<line class="ci" x1="{x(lo2):.1f}" y1="{cy:.1f}" x2="{x(hi2):.1f}" y2="{cy:.1f}"/>'
            + "".join(
                f'<circle class="rep" cx="{x(r["diff"]):.1f}" cy="{cy:.1f}" r="2.5"/>'
                for r in t["tests"][:-1]
            )
            + f'<circle class="dot" cx="{x(t["diff"]):.1f}" cy="{cy:.1f}" r="4.5"/></g>'
        )
        y += tall
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
    "nosizeslope": "the same price for size in every building",
    "sizeunkslope": "each building's own price for an apartment of unstated size",
}
# Words for the feature sets of served designs: the area prefix (the
# neighbourhood each step took in, in order) and the body (what the features
# read; an unknown body shows as its name).
AREA_WORDS = {
    "unit": "Chelsea",
    "nb": "West Village",
    "nb3": "Greenwich Village",
    "nb5": "Flatiron and Gramercy Park",
    "nb6": "Stuyvesant Town/PCV",
    "nb7": "NoMad",
    "nb8": "East Village",
}
SET_WORDS = {
    "unitdesc": "words from the ads",
    "unitdescpluto": "words from the ads and city building records",
    "unitfacing": "which way each apartment faces",
    "facing": "which way each apartment faces",
    "bedtext": "bedroom details from the ads",
    "relist": "each apartment's relisting history",
    "coded": "the listings' coded fields",
    "prevprice": "how the unit's previous listing was repriced",
    # nb6 on: the coded fields with city building records as of each
    # listing's day, and no Stuyvesant Town/PCV indicator
    "nostuy": "the coded fields with building records as of each listing's day",
}
# What a test set adds to its base (`nb8-nostuy-sizefill-v1`: "sizefill" on
# "nostuy"), said after the base's words.
EXTRA_WORDS = {
    "sizefill": "each apartment's size as of the listing's day",
    "elevfill": "the elevator as of the listing's day",
    "nta": "the city's neighbourhood tabulation areas",
    "lister": "who listed the ad",
    "lines": "the subway lines within an 8-minute walk",
    "riverparks": "the parks nearby, Hudson River Park and its new piers",
    "retail": "the shops, restaurants and bars nearby",
    "noise": "the noise complaints around the building",
    "trees": "the street trees nearby",
    "crime": "the felonies reported nearby in the past year",
    "hpd": "the hazardous housing-code violations found in the building in the past year",
}


def set_words(body: str) -> str:
    """A feature set's body in words: "coded" → "the listings' coded fields";
    "nostuy-lister" → its base's words plus "who listed the ad"."""
    if body in SET_WORDS:
        return SET_WORDS[body]
    base, _, extra = body.partition("-")
    if extra and base in SET_WORDS:
        return f"{SET_WORDS[base]}, plus {EXTRA_WORDS.get(extra, extra)}"
    return body


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


def _iso(at):
    """The milestone's time, or None when it isn't an ISO timestamp with a zone."""
    from datetime import datetime

    try:
        d = datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else None


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


def _set_parts(feature_set: str) -> tuple[str, str, str]:
    """`nb3-coded-v2` → ("nb3", "coded", "v2"); `unitfacing-v5` → ("unit",
    "unitfacing", "v5")."""
    m = re.fullmatch(r"(nb\d*)?-?([a-z][a-z-]*?)(?:-(v\d+))?", feature_set or "")
    if not m:
        return "", feature_set or "", ""
    area = m.group(1) or ("unit" if m.group(2).startswith("unit") else "")
    return area, m.group(2), m.group(3) or ""


def change_words(before: dict | None, after: dict, seen=()) -> str | None:
    """What a frontier switch changed from the design before it, in plain
    words (`seen`: the feature words of the designs served before it); None
    for a design whose name doesn't parse."""
    if after["terms"] is None:
        return None
    area, body, version = _set_parts(after["feature_set"])
    what = set_words(body)
    if before is None or before["terms"] is None:
        terms = [term_words(t) for t in after["terms"]]
        return f"The first searched design: {'; '.join(terms)}. Features: {what}"
    parts = []
    added = [term_words(t) for t in after["terms"] if t not in before["terms"]]
    dropped = [term_words(t) for t in before["terms"] if t not in after["terms"]]
    if added:
        parts.append("Added " + "; ".join(added))
    if dropped:
        parts.append("Dropped " + "; ".join(dropped))
    was_area, was_body, was_version = _set_parts(before["feature_set"])
    order = list(AREA_WORDS)
    if area in order and was_area in order and area != was_area:
        a, b = order.index(was_area), order.index(area)
        # every area between the two steps, as a switch can skip some
        steps = [AREA_WORDS[k] for k in order[min(a, b) + 1 : max(a, b) + 1]]
        names = (
            steps[0] if len(steps) == 1 else ", ".join(steps[:-1]) + " and " + steps[-1]
        )
        parts.append(f"{'Took in' if b > a else 'Left out'} {names}")
    if what != set_words(was_body):
        back = what in seen
        parts.append(f"Features {'back to' if back else 'now include'} {what}")
    elif version != was_version and area == was_area:
        parts.append(f"A revised version of {what}")
    if parts:
        return ". ".join(parts)
    if after.get("rows") != before.get("rows"):
        return "The same design, refitted on the current data rules"
    return "The same design, refitted"


def design_history(milestones: list[dict]) -> list[dict]:
    """Every switch of the served model, oldest first, with its era, PR and
    (for frontier fits) model terms and feature set."""
    switches = sorted(
        (
            m
            for m in milestones or []
            if isinstance(m, dict)
            and m.get("kind") == "selection"
            and _iso(m.get("at"))
        ),
        key=lambda m: _iso(m["at"]),
    )
    out, auto = [], False
    for i, m in enumerate(switches):
        title = str(m.get("title") or "")
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
        parsed = design_terms(str(m.get("model") or "")) if era != "bayes" else None
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
                "rows": str(m.get("model") or "").partition("-rows-")[2].split("-")[0],
            }
        )
    seen = []
    for i, s in enumerate(out):
        s["change"] = change_words(out[i - 1] if i else None, s, seen) or s["words"]
        if s["feature_set"] is not None:
            body = _set_parts(s["feature_set"])[1]
            seen.append(set_words(body))
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
    from datetime import datetime, timedelta, timezone

    start = datetime.fromtimestamp(d0 * 86400, timezone.utc).date()
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
                f'cy="{cy:.1f}" r="5"><title>{escape(s["date"])}: {escape(s["change"])}'
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


# --- Cleaning the record ----------------------------------------------------------

# What the served fit's data rules do to its rows, one rule at a time
# (rentfrontier.cleaning), read like the ledger.
CLEANING = Path(
    os.environ.get(
        "CLEANING_STEPS", "/data1/apartments/serve/master/docs/model/cleaning.json"
    )
)
REPO_CLEANING = Path(__file__).resolve().parents[3] / "docs/model/cleaning.json"
FIELD_WORDS = {
    "bedrooms": "bedroom counts",
    "full_baths": "full baths",
    "half_baths": "half baths",
    "square_feet": "floor areas",
    "listed_floor": "floors",
}
FAMILY_WORDS = {
    "correct": "corrects fields from the ad",
    "drop": "sets rows aside",
    "join": "joins units listed under two names",
    "split": "splits a unit's history",
}
CHECKS = (
    ("bed_changes", "next listing has another bedroom count"),
    ("big_jumps", "rent moves by more than 40%"),
)


class Cleaning(_Cached):
    default, repo = CLEANING, REPO_CLEANING

    def parse(self, text: str) -> dict | None:
        try:
            doc = json.loads(text)
        except ValueError:
            return None
        return doc if isinstance(doc, dict) else None


# Consecutive listings of one unit (the same price basis), as the cleaning
# checks pair them, with the years between them (a bare "YYYY-MM" period counts
# from the first of the month); a jump moves the ask by more
# than 40% either way.
_PAIRS = """
WITH s AS (
  SELECT unit_id, unit_label, building_id, ask, COALESCE(price_at, period) AS at,
    LAG(ask) OVER w AS prev_ask, LAG(COALESCE(price_at, period)) OVER w AS prev_at
  FROM listings
  WINDOW w AS (PARTITION BY unit_id, price_basis ORDER BY COALESCE(price_at, period), id))
SELECT s.*, b.address,
  (julianday(CASE WHEN length(at) = 7 THEN at || '-01' ELSE substr(at, 1, 10) END)
   - julianday(CASE WHEN length(prev_at) = 7 THEN prev_at || '-01' ELSE substr(prev_at, 1, 10) END))
   / 365.25 AS years,
  (ask > 1.4 * prev_ask OR prev_ask > 1.4 * ask) AS jump
FROM s JOIN buildings b ON b.id = s.building_id
WHERE prev_ask > 0 AND ask > 0
"""
GAPS = (
    (0, 1, "within a year"),
    (1, 2, "one to two years apart"),
    (2, None, "two or more years apart"),
)


def _iso_day(at: str) -> str:
    """An ISO date from a listing time or a bare "YYYY-MM" period."""
    return f"{at}-01" if len(at) == 7 else at[:10]


NUMBER_WORDS = ("one", "two", "three", "four", "five", "six")


def bed_phrase(bedrooms) -> str:
    """'a studio', 'a one-bedroom', 'a 7-bedroom'; 'an apartment' when unknown."""
    if bedrooms is None:
        return "an apartment"
    n = max(0, round(bedrooms))
    if n == 0:
        return "a studio"
    word = NUMBER_WORDS[n - 1] if n <= len(NUMBER_WORDS) else str(n)
    return f"{'an' if word in ('8', '11', '18') else 'a'} {word}-bedroom"


def rent_jumps(db) -> dict | None:
    """The jumps between a unit's consecutive listings, by the years between
    them, and the median-sized one as an example."""
    rows = [r for r in db.execute(_PAIRS).fetchall() if r["years"] is not None]
    jumps = [r for r in rows if r["jump"]]
    if not jumps:
        return None
    gaps = []
    for lo, hi, words in GAPS:
        group = [
            r for r in rows if r["years"] >= lo and (hi is None or r["years"] < hi)
        ]
        if group:
            n = sum(r["jump"] for r in group)
            gaps.append(
                {
                    "words": words,
                    "pairs": len(group),
                    "jumps": n,
                    "share": 100 * n / len(group),
                }
            )
    jumps.sort(
        key=lambda r: (abs(math.log(r["ask"] / r["prev_ask"])), r["unit_id"], r["at"])
    )
    e = jumps[(len(jumps) - 1) // 2]
    return {
        "pairs": len(rows),
        "jumps": len(jumps),
        "late": 100 * sum(r["years"] >= 2 for r in jumps) / len(jumps),
        "gaps": gaps,
        "example": {
            "unit_id": e["unit_id"],
            "label": e["unit_label"],
            "address": e["address"],
            "before": e["prev_ask"],
            "after": e["ask"],
            "from": _iso_day(e["prev_at"]),
            "to": _iso_day(e["at"]),
            "years": e["years"],
            "change": 100 * (e["ask"] / e["prev_ask"] - 1),
        },
    }


# A unit's listings in order, with its building's address. The split rule
# names the later pieces of a unit's history "<unit_id>~1", "~2", ...
_UNIT_ROWS = """
SELECT l.unit_id, l.unit_label, l.bedrooms, l.ask, COALESCE(l.price_at, l.period) AS at,
  b.address, substr(l.unit_id, 1, instr(l.unit_id || '~', '~') - 1) AS base
FROM listings l JOIN buildings b ON b.id = l.building_id
ORDER BY base, at, l.id
"""


def unit_examples(db) -> dict:
    """One real unit for each identity rule: the joined unit whose ads spell
    its name the most ways, and a clean split: the unit with the most pieces
    whose bedroom count and ask both rise from piece to piece, three pieces
    preferred so the example stays short."""
    units: dict = {}
    for r in db.execute(_UNIT_ROWS):
        units.setdefault(r["base"], []).append(r)
    joined = split = None
    for base, rows in units.items():
        labels = list(dict.fromkeys(r["unit_label"] for r in rows if r["unit_label"]))
        ids = list(dict.fromkeys(r["unit_id"] for r in rows))
        if len(ids) == 1 and len(labels) > 1:
            key = (len(labels), len(rows), base)
            if joined is None or key > joined[0]:
                joined = (key, rows, labels)
        if len(ids) > 1:
            pieces = [next(r for r in rows if r["unit_id"] == i) for i in ids]
            beds = [r["bedrooms"] for r in pieces]
            asks = [r["ask"] for r in pieces]
            if None not in beds and all(
                b1 < b2 and a1 < a2
                for b1, b2, a1, a2 in zip(beds, beds[1:], asks, asks[1:])
            ):
                key = (len(pieces) == 3, len(pieces), len(rows), base)
                if split is None or key > split[0]:
                    split = (key, pieces)
    out = {}
    if joined:
        _, rows, labels = joined
        out["joined"] = {
            "unit_id": rows[0]["unit_id"],
            "address": rows[0]["address"],
            "labels": labels,
            "listings": len(rows),
        }
    if split:
        pieces = split[1]
        out["split"] = {
            "address": pieces[0]["address"],
            "label": pieces[0]["unit_label"],
            "count": NUMBER_WORDS[len(pieces) - 1]
            if len(pieces) <= len(NUMBER_WORDS)
            else str(len(pieces)),
            "pieces": [
                {
                    "unit_id": r["unit_id"],
                    "words": bed_phrase(r["bedrooms"]),
                    "ask": r["ask"],
                    "at": _iso_day(r["at"]),
                }
                for r in pieces
            ],
        }
    return out


def _step_words(step: dict, before: dict) -> str:
    family = step.get("family")
    if family == "correct":
        changed = step.get("changed") or {}
        if not changed:
            return "no change (it reverts an earlier rule)"
        return ", ".join(
            f"{n:,} {FIELD_WORDS.get(f, f.replace('_', ' '))}"
            for f, n in changed.items()
        )
    if family == "drop":
        return f"{step['dropped']:,} rows set aside"
    if family == "join":
        return f"{before['units'] - step['units']:,} unit names joined"
    if family == "split":
        return f"{step['units'] - before['units']:,} more units"
    return ""


def _count(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(value)
    return int(value)


def _share(value) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok and math.isfinite(value) else None


def _clean_step(step: dict) -> dict:
    changed = step.get("changed") or {}
    if not isinstance(changed, dict):
        raise ValueError(changed)
    return {
        "rule": str(step.get("rule", "")),
        "family": step.get("family"),
        "dropped": _count(step.get("dropped", 0)),
        "changed": {str(f): _count(n) for f, n in changed.items()},
        **{k: _count(step[k]) for k in ("rows", "units", "buildings")},
        **{k: _share(step.get(k)) for k, _ in CHECKS},
    }


def cleaning(doc: dict | None, served_run: str | None = None) -> dict | None:
    """The cleaning chapter's numbers: the rows before and after the served
    fit's data rules, each rule's effect, and the two history checks. None
    when the file is missing or malformed."""
    try:
        start = _clean_step(doc["start"])
        steps = [_clean_step(s) for s in doc["steps"]]
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not steps:
        return None
    rows, before = [], start
    for s in steps:
        rows.append(
            {
                "rule": s["rule"],
                "family": s["family"] or "",
                "does": FAMILY_WORDS.get(s["family"], ""),
                "words": _step_words(s, before),
                **{k: s[k] for k in ("rows", "units", "buildings")},
            }
        )
        before = s
    end = steps[-1]

    def total(family, fn):
        out, prev = 0, start
        for s in steps:
            if s.get("family") == family:
                out += fn(s, prev)
            prev = s
        return out

    checks = []
    for key, name in CHECKS:
        a, b = start[key], end[key]
        if a is not None and b is not None:
            checks.append(
                {"key": key, "name": name, "before": 100 * a, "after": 100 * b}
            )
    return {
        "run": doc.get("run"),
        "current": served_run is None or doc.get("run") == served_run,
        "start": start,
        "end": end,
        "steps": rows,
        "corrected": total(
            "correct", lambda s, p: sum((s.get("changed") or {}).values())
        ),
        "dropped": total("drop", lambda s, p: s["dropped"]),
        "dropped_buildings": total(
            "drop", lambda s, p: p["buildings"] - s["buildings"]
        ),
        "joined": total("join", lambda s, p: p["units"] - s["units"]),
        "split": total("split", lambda s, p: s["units"] - p["units"]),
        "checks": checks,
    }


def cleaning_svg(c: dict | None) -> Markup:
    """Each history check before and after the rules: a hollow dot at the raw
    rows, a filled one after the rules, and a line between them."""
    if not c or not c["checks"]:
        return Markup("")
    row, top, label_w = 40, 26, 300
    hi = max(max(k["before"], k["after"]) for k in c["checks"])
    ticks = nice_ticks(0, hi, 5)
    hi = max(hi, ticks[-1]) or 1
    plot = WIDTH - label_w - 24

    def x(v):
        return label_w + plot * v / hi

    height = top + row * len(c["checks"]) + 8
    out = [
        f'<line class="grid" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" '
        f'y2="{height - 4}"/><text class="tick" x="{x(t):.1f}" y="{top - 10}" '
        f'text-anchor="middle">{t:g}%</text>'
        for t in ticks
    ]
    for i, k in enumerate(c["checks"]):
        y = top + row * i + row / 2
        out.append(
            f'<g class="fix r{i}"><text class="eff-label" x="{label_w - 10}" '
            f'y="{y + 4:.1f}" text-anchor="end">{escape(k["name"])}</text>'
            f'<line class="shift" pathLength="1" x1="{x(k["before"]):.1f}" y1="{y:.1f}" '
            f'x2="{x(k["after"]):.1f}" y2="{y:.1f}"/>'
            f'<circle class="raw" cx="{x(k["before"]):.1f}" cy="{y:.1f}" r="5"/>'
            f'<circle class="clean" cx="{x(k["after"]):.1f}" cy="{y:.1f}" r="5"/>'
            f'<text class="tick" x="{x(k["after"]):.1f}" y="{y - 9:.1f}" '
            f'text-anchor="middle">{k["after"]:.1f}%</text>'
            f'<text class="tick" x="{x(k["before"]):.1f}" y="{y + 18:.1f}" '
            f'text-anchor="middle">{k["before"]:.1f}%</text></g>'
        )
    label = "Share of a unit's consecutive listings where the " + "; ".join(
        f"{k['name']}: {k['before']:.1f}% in the raw rows, {k['after']:.1f}% after the rules"
        for k in c["checks"]
    )
    return Markup(
        f'<svg class="story-svg cleaning" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )


# --- Inside two grouped tests ------------------------------------------------------

# The items of two ideas the ledger tested as one group each
# (rentfrontier.groupitems): how common each is on the served fit's rows, and
# a raw rent difference with only bedrooms held fixed. No model effects.
GROUP_ITEMS = Path(
    os.environ.get(
        "GROUP_ITEMS", "/data1/apartments/serve/master/docs/model/group-items.json"
    )
)
REPO_GROUP_ITEMS = Path(__file__).resolve().parents[3] / "docs/model/group-items.json"

ATTRIBUTE_WORDS = {
    "walk_in_closet": ("Walk-in closet", "“walk-in closet”"),
    "live_in_super": (
        "Live-in super",
        "“live-in super”, “on-site super”, “resident super”, “live-in manager”",
    ),
    "utilities_included": (
        "Utilities included",
        "“utilities included”, “heat and hot water included”, “includes heat”",
    ),
    "windowed_kitchen": (
        "Windowed kitchen",
        "“windowed kitchen”, “kitchen with a window”",
    ),
    "windowed_bath": ("Windowed bath", "“windowed bath”, “bathroom with a window”"),
    "tree_lined": ("Tree-lined street", "“tree-lined”"),
    "skylight": ("Skylight", "“skylight”"),
    "video_intercom": ("Video intercom", "“video intercom”, “virtual doorman”"),
    "corner_unit": (
        "Corner unit",
        "“corner unit”, “corner apartment”, “corner one-bedroom”",
    ),
    "separate_kitchen": ("Separate kitchen", "“separate kitchen”"),
    "floor_to_ceiling_windows": (
        "Floor-to-ceiling windows",
        "“floor-to-ceiling windows” or “glass”",
    ),
    "marble_bath": ("Marble bath", "“marble bath”"),
    "hardwood": (
        "Hardwood floors",
        "“hardwood”, “wood floors”, “wide-plank”, “oak floors”, “parquet”",
    ),
    "stainless": ("Stainless steel", "“stainless”"),
    "prewar_text": ("Pre-war", "“pre-war” in the ad"),
}
PLACE_WORDS = {
    "dog run": ("Dog run", "a dog run or off-leash area"),
    "hospital": ("Hospital", "a hospital"),
    "ambulance station": ("EMS station", "an ambulance or EMS station (sirens)"),
    "drop-in center": ("Drop-in center", "a homeless drop-in center"),
    "nycha": ("NYCHA housing", "a NYCHA public-housing lot"),
    "arena": ("Madison Square Garden", "Madison Square Garden"),
}
GROUP_TESTS = {"attributes": "nb3-attrs-v1", "places": "nb3-nearby-v1"}


class GroupItems(_Cached):
    default, repo = GROUP_ITEMS, REPO_GROUP_ITEMS

    def parse(self, text: str) -> dict | None:
        try:
            doc = json.loads(text)
        except ValueError:
            return None
        return doc if isinstance(doc, dict) else None


def group_items(
    doc: dict | None, trials: list[dict], served_run: str | None, served=frozenset()
) -> dict | None:
    """The two grouped tests' items, in words, with the group's own ledger
    result. None unless the file is for the served run, and None once the served
    model has a term for any item (`served`, its coefficient names): the page
    says the served model has no estimate for them."""
    if not doc or doc.get("run") != served_run:
        return None
    terms = {f"text:{i.get('item')}" for i in doc.get("attributes") or []}
    terms |= {f"log m to {i.get('words')}" for i in doc.get("places") or []}
    if terms & set(served):
        return None
    tests = {t["change"]: t for t in trials}
    out = {"rows": doc.get("rows"), "rows_with_text": doc.get("rows_with_text")}
    out["near_m"] = doc.get("near_m")
    for key, words in (("attributes", ATTRIBUTE_WORDS), ("places", PLACE_WORDS)):
        items = []
        for item in doc.get(key) or []:
            name, what = words.get(item.get("item"), (item.get("item"), ""))
            share = item.get("share", item.get("near_share"))
            raw = item.get("raw_pct", item.get("raw_pct_per_doubling"))
            if share is None:
                continue
            items.append(
                {
                    **item,
                    "name": name,
                    "what": what,
                    "pct_share": 100 * share,
                    "raw": raw,
                }
            )
        items.sort(key=lambda i: -i["pct_share"])
        out[key] = {"items": items, "test": tests.get(GROUP_TESTS[key])}
    if not out["attributes"]["items"] and not out["places"]["items"]:
        return None
    return out


def group_items_svg(items: list[dict], noun: str) -> Markup:
    """Bars: each item's share of listings, with the share written at the end."""
    if not items:
        return Markup("")
    row, top, label_w = 24, 22, 200
    hi = max(max(i["pct_share"] for i in items), 1)
    ticks = nice_ticks(0, hi, 5)
    hi = max(hi, ticks[-1])
    plot = WIDTH - label_w - 60

    def x(v):
        return label_w + plot * v / hi

    height = top + row * len(items) + 8
    out = [
        f'<line class="grid" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" '
        f'y2="{height - 4}"/><text class="tick" x="{x(t):.1f}" y="{top - 10}" '
        f'text-anchor="middle">{t:g}%</text>'
        for t in ticks
    ]
    for n, i in enumerate(items):
        y = top + row * n
        out.append(
            f'<text class="eff-label" x="{label_w - 10}" y="{y + row / 2 + 4:.1f}" '
            f'text-anchor="end">{escape(i["name"])}</text>'
            f'<rect class="item-bar" x="{label_w}" y="{y + 5}" '
            f'width="{max(x(i["pct_share"]) - label_w, 1):.1f}" height="{row - 10}"/>'
            f'<text class="share-label" x="{x(i["pct_share"]) + 6:.1f}" '
            f'y="{y + row / 2 + 4:.1f}">{i["pct_share"]:.1f}%</text>'
        )
    label = f"Share of listings {noun}: " + "; ".join(
        f"{i['name']} {i['pct_share']:.1f}%" for i in items
    )
    return Markup(
        f'<svg class="story-svg items" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )


# --- What the building premium is made of -----------------------------------


def explained(entry: dict | None) -> list[dict]:
    """The fit's own explained-share screens (rentfrontier.explained): for each
    family of building features, the share of the spread in the fit's building
    premiums it predicts out of fold, beside the 95th percentile of the same
    share with the features shuffled across buildings. A family beats chance
    when its share is above zero and above that percentile. Largest excess
    first; empty when the fit has no screens."""
    rows = []
    for cs, r in sorted(((entry or {}).get("explained") or {}).items()):
        for family, f in (r.get("families") or {}).items():
            if not all(
                isinstance(f.get(k), (int, float)) for k in ("explained", "null_95")
            ):
                continue
            rows.append(
                {
                    "name": family,
                    "set": cs,
                    "buildings": r.get("buildings"),
                    "explained": f["explained"],
                    "null_mean": f.get("null_mean"),
                    "null_95": f["null_95"],
                    "excess": f.get("excess"),
                    "beats": f["explained"] > max(0.0, f["null_95"]),
                }
            )
    rows.sort(
        key=lambda r: -(r["excess"] if r["excess"] is not None else r["explained"])
    )
    return rows


def _pct1(v: float) -> str:
    """A percentage to one decimal, without a minus sign on a value that rounds to zero."""
    return f"{v:.1f}%" if round(v, 1) else "0.0%"


def explained_svg(rows: list[dict]) -> Markup:
    """Bars: each family's out-of-fold share of the building premium, with a
    dashed mark where shuffled features reach 95% of the time; families that
    don't beat chance are drawn faint."""
    if not rows:
        return Markup("")
    row, top, label_w = 26, 22, 200
    vals = [100 * v for r in rows for v in (r["explained"], r["null_95"])]
    ticks = nice_ticks(min(0.0, *vals), max(0.5, *vals), 5)
    lo, hi = ticks[0], ticks[-1]
    plot = WIDTH - label_w - 70

    def x(v):
        return label_w + plot * (v - lo) / (hi - lo)

    height = top + row * len(rows) + 8
    out = [
        f'<line class="grid" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" '
        f'y2="{height - 4}"/><text class="tick" x="{x(t):.1f}" y="{top - 10}" '
        f'text-anchor="middle">{t:g}%</text>'
        for t in ticks
    ]
    out.append(
        f'<line class="zero" x1="{x(0):.1f}" y1="{top - 6}" x2="{x(0):.1f}" y2="{height - 4}"/>'
    )
    for n, r in enumerate(rows):
        y = top + row * n
        v, c = 100 * r["explained"], 100 * r["null_95"]
        left, right = sorted((x(0), x(v)))
        out.append(
            f'<text class="eff-label" x="{label_w - 10}" y="{y + row / 2 + 4:.1f}" '
            f'text-anchor="end">{escape(r["name"].capitalize())}</text>'
            f'<rect class="item-bar{"" if r["beats"] else " faint"}" x="{left:.1f}" y="{y + 6}" '
            f'width="{max(right - left, 1):.1f}" height="{row - 12}"/>'
            f'<line class="target" x1="{x(c):.1f}" y1="{y + 2}" x2="{x(c):.1f}" y2="{y + row - 2}"/>'
            f'<text class="share-label" x="{max(x(v), x(0), x(c)) + 6:.1f}" '
            f'y="{y + row / 2 + 4:.1f}">{_pct1(v)}</text>'
        )
    label = (
        "Share of the building premium each family of features predicts: "
        + "; ".join(
            f"{r['name']} {_pct1(100 * r['explained'])} against {_pct1(100 * r['null_95'])} by chance"
            + (", beats chance" if r["beats"] else ", no better than chance")
            for r in rows
        )
    )
    return Markup(
        f'<svg class="story-svg items" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}">' + "".join(out) + "</svg>"
    )
