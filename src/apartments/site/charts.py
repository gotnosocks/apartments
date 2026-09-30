"""Server-rendered SVG charts for the listings site.

Every chart is plain SVG (no inline style, so the site's CSP holds) with its
hover data in a JSON block that static/site.js reads for the crosshair or
nearest-point tooltip. Colors come from CSS classes (static/site.css), so
light and dark themes swap in one place. Every chart has a table view in
the page (or the page's own table) with the same values.
"""

from __future__ import annotations

import datetime as dt
import json
import math

from markupsafe import Markup, escape

WIDTH, HEIGHT = 720, 260
PAD = {"left": 64, "right": 16, "top": 12, "bottom": 28}


def usd(value, signed=False) -> str:
    if value is None:
        return "—"
    text = f"${abs(value):,.0f}"
    if signed:
        return ("+" if value > 0 else "−" if value < 0 else "") + text
    return ("−" if value < 0 else "") + text


def pct(value, signed=True, digits=0) -> str:
    if value is None:
        return "—"
    text = f"{abs(value):.{digits}f}%"
    if signed:
        return ("+" if value > 0 else "−" if value < 0 else "") + text
    return text


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


def _days(period: str) -> int:
    return dt.date.fromisoformat(period[:10]).toordinal()


class Frame:
    """Linear scales from data to the plot area of a WIDTH x HEIGHT viewBox."""

    def __init__(self, periods, values, *, zero=False, height=HEIGHT):
        self.height = height
        days = [_days(p) for p in periods]
        self.x0, self.x1 = min(days), max(days)
        if self.x1 == self.x0:
            self.x0, self.x1 = self.x0 - 180, self.x1 + 180
        lo, hi = min(values), max(values)
        if zero:
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        pad = (hi - lo) * 0.05 or abs(hi) * 0.05 or 1.0
        self.ticks = nice_ticks(lo - pad, hi + pad)
        self.y0, self.y1 = self.ticks[0], self.ticks[-1]
        self.left, self.right = PAD["left"], WIDTH - PAD["right"]
        self.top, self.bottom = PAD["top"], height - PAD["bottom"]

    def x(self, period: str) -> float:
        span = self.x1 - self.x0
        return self.left + (_days(period) - self.x0) / span * (self.right - self.left)

    def y(self, value: float) -> float:
        span = self.y1 - self.y0
        return self.bottom - (value - self.y0) / span * (self.bottom - self.top)

    def year_ticks(self) -> list[tuple[float, str]]:
        first = dt.date.fromordinal(self.x0).year
        last = dt.date.fromordinal(self.x1).year
        years = list(range(first + 1, last + 1)) or [first]
        step = max(1, math.ceil(len(years) / 8))
        out = []
        for year in years[::step]:
            day = dt.date(year, 1, 1).toordinal()
            if self.x0 <= day <= self.x1:
                out.append((self.x(dt.date(year, 1, 1).isoformat()), str(year)))
        return out


def _axes(frame: Frame, y_format) -> list[str]:
    parts = []
    for tick in frame.ticks:
        y = frame.y(tick)
        parts.append(
            f'<line class="grid" x1="{frame.left}" x2="{frame.right}" '
            f'y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{frame.left - 8}" y="{y + 4:.1f}" '
            f'text-anchor="end">{escape(y_format(tick))}</text>'
        )
    for x, label in frame.year_ticks():
        parts.append(
            f'<text class="tick" x="{x:.1f}" y="{frame.bottom + 18}" '
            f'text-anchor="middle">{label}</text>'
        )
    parts.append(
        f'<line class="axis" x1="{frame.left}" x2="{frame.right}" '
        f'y1="{frame.bottom}" y2="{frame.bottom}"/>'
    )
    return parts


def _svg(parts, label: str, frame: Frame) -> str:
    return (
        f'<svg viewBox="0 0 {WIDTH} {frame.height}" role="img" '
        f'aria-label="{escape(label)}" preserveAspectRatio="xMidYMid meet">'
        + "".join(parts)
        + "</svg>"
    )


def _figure(kind: str, svg: str, points: list[dict], legend: str = "") -> Markup:
    # No "<" at all inside the script data block ("</script>", "<!--").
    data = json.dumps(points, separators=(",", ":")).replace("<", "\\u003c")
    return Markup(
        f'<figure class="chart" data-chart="{kind}" tabindex="0">'
        f"{legend}{svg}"
        f'<div class="chart-tip" hidden></div>'
        f'<script type="application/json" class="chart-data">{data}</script>'
        f"</figure>"
    )


def _path(points) -> str:
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in points)


def band_line(series, *, label: str, value_label="Estimate") -> Markup:
    """A line with its 95% band over time (a monthly series).

    series: [{"period", "value", "lower", "upper"}]."""
    if not series:
        return Markup("")
    values = [s["lower"] for s in series] + [s["upper"] for s in series]
    frame = Frame([s["period"] for s in series], values)
    parts = _axes(frame, lambda v: usd(v))
    upper = [(frame.x(s["period"]), frame.y(s["upper"])) for s in series]
    lower = [(frame.x(s["period"]), frame.y(s["lower"])) for s in series]
    parts.append(f'<path class="band s1" d="{_path(upper + lower[::-1])}Z"/>')
    line = [(frame.x(s["period"]), frame.y(s["value"])) for s in series]
    parts.append(f'<path class="line s1" d="{_path(line)}"/>')
    points = [
        {
            "x": round(x, 1),
            "y": round(y, 1),
            "title": month_label(s["period"]),
            "rows": [
                [value_label, usd(s["value"])],
                ["95% interval", f"{usd(s['lower'])} – {usd(s['upper'])}"],
            ],
        }
        for (x, y), s in zip(line, series)
    ]
    return _figure("line", _svg(parts, label, frame), points)


def asks_and_estimates(rows, *, label: str) -> Markup:
    """Per listing: the estimate as a tick with its 95% whisker, and the ask
    as a dot, at the listing's month. Listings are separate points in time
    (with their own features), so nothing is drawn between them.

    rows: [{"period", "ask", "estimate", "lower", "upper", "title", "href"}]."""
    if not rows:
        return Markup("")
    values = [r["lower"] for r in rows] + [r["upper"] for r in rows]
    values += [r["ask"] for r in rows]
    frame = Frame([r["period"] for r in rows], values)
    parts = _axes(frame, lambda v: usd(v))
    points = []
    for r in rows:
        x = frame.x(r["period"])
        top, bottom = frame.y(r["upper"]), frame.y(r["lower"])
        mid, ask = frame.y(r["estimate"]), frame.y(r["ask"])
        parts.append(
            f'<line class="whisker s1" x1="{x:.1f}" x2="{x:.1f}" '
            f'y1="{top:.1f}" y2="{bottom:.1f}"/>'
            f'<line class="tick-mark s1" x1="{x - 6:.1f}" x2="{x + 6:.1f}" '
            f'y1="{mid:.1f}" y2="{mid:.1f}"/>'
            f'<circle class="dot s2" cx="{x:.1f}" cy="{ask:.1f}" r="4.5"/>'
        )
        points.append(
            {
                "x": round(x, 1),
                "y": round(min(mid, ask), 1),
                "title": r["title"],
                "rows": [
                    ["Ask", usd(r["ask"])],
                    ["Estimate", usd(r["estimate"])],
                    ["95% range", f"{usd(r['lower'])} – {usd(r['upper'])}"],
                ],
                "href": r.get("href"),
            }
        )
    legend = (
        '<div class="legend">'
        '<span class="key"><span class="key-tick s1"></span>Estimate, with its 95% range</span>'
        '<span class="key"><span class="key-dot s2"></span>Ask</span></div>'
    )
    return _figure("line", _svg(parts, label, frame), points, legend)


def residual_scatter(rows, *, label: str) -> Markup:
    """Ask vs leave-own-row-out estimate (percent) per listing over time.

    rows: [{"period", "residual_pct" (fraction), "title", "rows"}]."""
    if not rows:
        return Markup("")
    values = [100 * r["residual_pct"] for r in rows]
    frame = Frame([r["period"] for r in rows], values, zero=True)
    parts = _axes(frame, lambda v: pct(v))
    zero = frame.y(0.0)
    parts.append(
        f'<line class="zero" x1="{frame.left}" x2="{frame.right}" '
        f'y1="{zero:.1f}" y2="{zero:.1f}"/>'
    )
    points = []
    radius = 4 if len(rows) <= 300 else 3  # dense buildings: smaller marks
    for r, v in zip(rows, values):
        x, y = frame.x(r["period"]), frame.y(v)
        parts.append(f'<circle class="dot s1" cx="{x:.1f}" cy="{y:.1f}" r="{radius}"/>')
        points.append(
            {
                "x": round(x, 1),
                "y": round(y, 1),
                "title": r["title"],
                "rows": [["Ask vs estimate", pct(v)]] + r.get("rows", []),
                "href": r.get("href"),
            }
        )
    return _figure("points", _svg(parts, label, frame), points)


def contribution_bar(value, lower, upper, scale) -> Markup:
    """A diverging bar from a center line for one dollar contribution, with
    its 95% interval as a whisker; scale is the largest |value| on the page."""
    width, height, mid = 220, 18, 110
    scale = scale or 1.0

    def at(v):
        return mid + max(-1.0, min(1.0, v / scale)) * (mid - 4)

    x = at(value)
    lo, hi = sorted((at(lower), at(upper)))
    cls = "up" if value > 0 else "down"
    left, bar = min(mid, x), abs(x - mid)
    rect = (
        f'<rect class="bar {cls}" x="{left:.1f}" y="4" width="{max(bar, 1):.1f}" '
        f'height="10" rx="2"/>'
    )
    return Markup(
        f'<svg class="cbar" viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<line class="zero" x1="{mid}" x2="{mid}" y1="0" y2="{height}"/>'
        f"{rect}"
        f'<line class="whisker" x1="{lo:.1f}" x2="{hi:.1f}" y1="9" y2="9"/>'
        "</svg>"
    )
