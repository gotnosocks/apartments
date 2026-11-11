"""Server-rendered SVG charts and number formatters for the listings site.

Every chart is plain SVG (no inline style, so the site's CSP holds) with its
hover data in a JSON block that static/site.js reads for the crosshair or
nearest-point tooltip. Colors come from CSS classes (static/site.css), so
light and dark themes swap in one place.
"""

from __future__ import annotations

import datetime as dt
import json
import math

from markupsafe import Markup, escape


def usd(value, signed=False) -> str:
    if value is None:
        return "—"
    text = f"${abs(value):,.0f}"
    if text == "$0":
        return text
    if signed:
        return ("+" if value > 0 else "−" if value < 0 else "") + text
    return ("−" if value < 0 else "") + text


def pct(value, signed=True, digits=0) -> str:
    if value is None:
        return "—"
    text = f"{abs(value):.{digits}f}%"
    if float(text[:-1]) == 0:
        return text
    if signed:
        return ("+" if value > 0 else "−" if value < 0 else "") + text
    return text


def signed(value: float) -> str:
    """An axis value with its sign ("+1,000", "−500", "0")."""
    if not value:
        return "0"
    return ("+" if value > 0 else "−") + f"{abs(value):,.0f}"


def month_label(period: str) -> str:
    return dt.date.fromisoformat(period).strftime("%b %Y")


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Round tick values covering [lo, hi]."""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(lo / step) * step
    ticks = []
    value = start
    while value <= hi + step * 1e-9:
        ticks.append(round(value, 10))
        value += step
    if ticks[-1] < hi:
        ticks.append(ticks[-1] + step)
    return ticks


def _json(value) -> str:
    # No "<" at all inside a script data block ("</script>", "<!--").
    return json.dumps(value, separators=(",", ":")).replace("<", "\\u003c")


def _figure(kind: str, svg: str, points: list[dict], legend: str = "") -> Markup:
    """A chart's figure: its SVG, the hover card and the hover data (static/site.js)."""
    return Markup(
        f'<figure class="chart" data-chart="{kind}" tabindex="0">'
        f"{legend}{svg}"
        f'<div class="chart-tip" hidden></div>'
        f'<script type="application/json" class="chart-data">{_json(points)}</script>'
        f"</figure>"
    )


def interval_strip(ask, median, intervals) -> Markup:
    """One ad's predictive intervals as nested horizontal bands, the widest palest,
    with the median as a tick and the ask as a dot. intervals: [(level, lower, upper)],
    narrowest first. The page states every value in words beside it."""
    width, height = 560, 64
    left, right, top, band = 16, 16, 10, 22
    values = [v for _, lo, hi in intervals for v in (lo, hi)] + [ask, median]
    lo_all, hi_all = min(values), max(values)
    span = (hi_all - lo_all) or 1.0
    lo_all, hi_all = lo_all - 0.05 * span, hi_all + 0.05 * span

    def at(v):
        return left + (v - lo_all) / (hi_all - lo_all) * (width - left - right)

    parts = []
    for level, lo, hi in sorted(intervals, key=lambda i: -i[0]):
        parts.append(
            f'<rect class="band band-{int(level)}" x="{at(lo):.1f}" y="{top}" '
            f'width="{max(at(hi) - at(lo), 1):.1f}" height="{band}" rx="3"/>'
        )
    m, a = at(median), at(ask)
    parts.append(
        f'<line class="median" x1="{m:.1f}" x2="{m:.1f}" y1="{top - 4}" '
        f'y2="{top + band + 4}"/>'
    )
    parts.append(f'<circle class="ask" cx="{a:.1f}" cy="{top + band / 2}" r="6"/>')
    for tick in nice_ticks(lo_all, hi_all, 5):
        if lo_all <= tick <= hi_all:
            parts.append(
                f'<text class="tick" x="{at(tick):.1f}" y="{height - 6}" '
                f'text-anchor="middle">{escape(usd(tick))}</text>'
            )
    return Markup(
        f'<svg class="istrip" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="The ask at {escape(usd(ask))} against the model\'s ranges">'
        + "".join(parts)
        + "</svg>"
    )
