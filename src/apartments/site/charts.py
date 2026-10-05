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


def _days(period: str) -> float:
    """Days since year 1 of a date, or of a timestamp with its time of day."""
    if len(period) > 10:
        t = dt.datetime.fromisoformat(period)
        return t.toordinal() + (t.hour * 3600 + t.minute * 60 + t.second) / 86400
    return dt.date.fromisoformat(period).toordinal()


class Frame:
    """Linear scales from data to the plot area of a WIDTH x HEIGHT viewBox."""

    def __init__(self, periods, values, *, zero=False, clamp_zero=False, height=HEIGHT):
        """zero: the y range includes zero. clamp_zero: the measure is never
        negative (or never positive), so the axis stops at zero."""
        self.height = height
        self.timestamped = any(len(p) > 10 for p in periods)
        days = [_days(p) for p in periods]
        self.x0, self.x1 = min(days), max(days)
        if self.x1 == self.x0:
            self.x0, self.x1 = self.x0 - 180, self.x1 + 180
        lo, hi = min(values), max(values)
        if zero:
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        pad = (hi - lo) * 0.05 or abs(hi) * 0.05 or 1.0
        # A measure that is never negative (or never positive) stops at zero.
        low_pad = 0.0 if clamp_zero and lo >= 0.0 else pad
        high_pad = 0.0 if clamp_zero and hi <= 0.0 else pad
        if clamp_zero:
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        self.ticks = nice_ticks(lo - low_pad, hi + high_pad)
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
        """Tick labels along time: years for long spans, months or days for
        short ones (the research history spans weeks)."""
        span = self.x1 - self.x0
        start, end = math.ceil(self.x0), math.floor(self.x1)
        if span < 75 and self.timestamped:
            step = max(1, math.ceil(span / 8))
            days = range(start, end + 1, step)
            return [
                (
                    self.x(dt.date.fromordinal(d).isoformat()),
                    dt.date.fromordinal(d).strftime("%b %-d"),
                )
                for d in days
            ]
        if span < 700:
            out, d = [], dt.date.fromordinal(start).replace(day=1)
            months = []
            while d.toordinal() <= self.x1:
                if d.toordinal() >= self.x0:
                    months.append(d)
                d = (d + dt.timedelta(days=32)).replace(day=1)
            every = max(1, math.ceil(len(months) / 8))
            for m in months[::every]:
                out.append((self.x(m.isoformat()), m.strftime("%b %Y")))
            return out
        first = dt.date.fromordinal(start).year
        last = dt.date.fromordinal(end).year
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
                    [
                        "Typical rent, 95% range",
                        f"{usd(r['lower'])} – {usd(r['upper'])}",
                    ],
                ],
                "href": r.get("href"),
            }
        )
    legend = (
        '<div class="legend">'
        '<span class="key"><span class="key-tick s1"></span>Estimate, with the 95% range of the typical rent</span>'
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


XY_PAD = {"left": 64, "right": 16, "top": 28, "bottom": 46}


class XYFrame:
    """Linear scales for two measures (a scatter), in a WIDTH x HEIGHT viewBox.
    `y_floor` cuts the y range from below; points under it are drawn at the
    floor and say so in their tooltip."""

    def __init__(self, xs, ys, *, y_floor=None, x_zero=True, height=HEIGHT):
        self.height = height
        xlo, xhi = min(xs), max(xs)
        if x_zero:
            xlo = min(xlo, 0.0)
        xpad = (xhi - xlo) * 0.04 or 1.0
        self.xticks = nice_ticks(xlo, xhi + xpad, count=6)
        self.x0, self.x1 = self.xticks[0], self.xticks[-1]
        shown = [y for y in ys if y_floor is None or y >= y_floor]
        ylo, yhi = min(shown or ys), max(shown or ys)
        ypad = (yhi - ylo) * 0.06 or abs(yhi) * 0.05 or 1.0
        self.yticks = nice_ticks(ylo - ypad, yhi + ypad)
        self.y0, self.y1 = self.yticks[0], self.yticks[-1]
        self.left, self.right = XY_PAD["left"], WIDTH - XY_PAD["right"]
        self.top, self.bottom = XY_PAD["top"], height - XY_PAD["bottom"]

    def x(self, value: float) -> float:
        span = self.x1 - self.x0
        return self.left + (value - self.x0) / span * (self.right - self.left)

    def y(self, value: float) -> float:
        value = max(value, self.y0)
        span = self.y1 - self.y0
        return self.bottom - (value - self.y0) / span * (self.bottom - self.top)


# Marks of a fit on the research charts, drawn in this order (the served
# fit last, on top). Text labels say the same in the legend and tooltip.
FIT_KINDS = {
    "subset": "Subset fit (exploration only)",
    "failing": "Fails the convergence checks",
    "other": "Other fit",
    "frontier": "On the frontier",
    "served": "Served model",
}


def _fit_mark(p, x: float, y: float) -> str:
    """A fit's mark: a circle for a full fit, a diamond of about the same area
    for an exploration fit (so the tier is not colour alone)."""
    radius = 5.5 if p["kind"] == "served" else 4
    cls = f"fit {p['kind']}" + (" faded" if p.get("faded") else "")
    if p.get("tier") == "exploration":
        r = radius * 1.25
        return (
            f'<path class="{cls}" d="M{x:.1f} {y - r:.1f}'
            f"L{x + r:.1f} {y:.1f}L{x:.1f} {y + r:.1f}L{x - r:.1f} {y:.1f}Z"
            '"/>'
        )
    return f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{radius}"/>'


def _fit_label(p) -> str:
    """The tooltip's first line: the fit's kind, and its tier when it is an
    exploration fit."""
    label = FIT_KINDS[p["kind"]]
    return label + " · exploration fit" if p.get("tier") == "exploration" else label


def _fit_legend(points) -> str:
    """The kinds present, and the two shapes when any fit is an exploration
    fit."""
    present = [k for k in FIT_KINDS if any(p["kind"] == k for p in points)]
    shapes = ""
    if any(p.get("tier") == "exploration" for p in points):
        shapes = (
            '<span class="key"><span class="key-shape circle"></span>Full fit</span>'
            '<span class="key"><span class="key-shape diamond"></span>'
            "Exploration fit</span>"
        )
    return (
        '<div class="legend">'
        + "".join(
            f'<span class="key"><span class="key-fit {k}"></span>'
            f"{escape(FIT_KINDS[k])}</span>"
            for k in reversed(present)
        )
        + shapes
        + "</div>"
    )


def fit_scatter(
    points,
    *,
    label: str,
    x_title: str,
    y_title: str,
    x_format,
    y_format,
    y_floor=None,
    x_line=None,
    x_zero=True,
) -> Markup:
    """One dot per fit on two measures. points: [{"x", "y", "kind" (a
    FIT_KINDS key), "title", "rows", "href", "tier" (optional: "exploration"
    draws a diamond instead of a circle, so the tier is not colour alone)}].
    x_line: (value, label) draws a reference line, such as a time target."""
    if not points:
        return Markup("")
    # A reference line is drawn where the data reach it; it does not stretch
    # the axis (a 2-hour limit would squash fits of a few minutes).
    xs = [p["x"] for p in points]
    frame = XYFrame(xs, [p["y"] for p in points], y_floor=y_floor, x_zero=x_zero)
    parts = []
    for tick in frame.yticks:
        y = frame.y(tick)
        parts.append(
            f'<line class="grid" x1="{frame.left}" x2="{frame.right}" '
            f'y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{frame.left - 8}" y="{y + 4:.1f}" '
            f'text-anchor="end">{escape(y_format(tick))}</text>'
        )
    for tick in frame.xticks:
        x = frame.x(tick)
        parts.append(
            f'<text class="tick" x="{x:.1f}" y="{frame.bottom + 16}" '
            f'text-anchor="middle">{escape(x_format(tick))}</text>'
        )
    parts.append(
        f'<line class="axis" x1="{frame.left}" x2="{frame.right}" '
        f'y1="{frame.bottom}" y2="{frame.bottom}"/>'
        f'<text class="axis-title" x="{(frame.left + frame.right) / 2:.1f}" '
        f'y="{frame.height - 6}" text-anchor="middle">{escape(x_title)}</text>'
        f'<text class="axis-title" x="{frame.left - 56}" y="14">{escape(y_title)}</text>'
    )
    if x_line and frame.x0 <= x_line[0] <= frame.x1:
        x = frame.x(x_line[0])
        parts.append(
            f'<line class="ref" x1="{x:.1f}" x2="{x:.1f}" y1="{frame.top}" '
            f'y2="{frame.bottom}"/><text class="ref-label" x="{x - 4:.1f}" '
            f'y="{frame.bottom - 6}" text-anchor="end">{escape(x_line[1])}</text>'
        )
    # One design measured at several draw counts: its points joined in draw
    # order, under the marks.
    groups: dict = {}
    for p in points:
        if p.get("group") is not None:
            groups.setdefault(p["group"], []).append(p)
    for group in groups.values():
        group.sort(key=lambda p: p.get("draws") or 0)
        line = " ".join(f"{frame.x(p['x']):.1f},{frame.y(p['y']):.1f}" for p in group)
        parts.append(f'<polyline class="measured" points="{line}"/>')
    order = {k: i for i, k in enumerate(FIT_KINDS)}
    hover = []
    for p in sorted(points, key=lambda p: (not p.get("faded"), order[p["kind"]])):
        x, y = frame.x(p["x"]), frame.y(p["y"])
        parts.append(_fit_mark(p, x, y))
        rows = list(p.get("rows", []))
        if p["y"] < frame.y0:
            rows.append(["Note", "below the chart's range, drawn at its floor"])
        hover.append(
            {
                "x": round(x, 1),
                "y": round(y, 1),
                "title": p["title"],
                "rows": [["", _fit_label(p)], *rows],
                "href": p.get("href"),
            }
        )
    legend = _fit_legend(points)
    if groups:
        legend = legend.replace(
            "</div>",
            '<span class="key"><span class="key-measured"></span>One design at '
            "several draw counts, joined; the faded points have fewer draws</span></div>",
        )
    return _figure("points", _svg(parts, label, frame), hover, legend)


def _y_title(frame, title):
    return (
        f'<text class="axis-title" x="{frame.left - 56}" y="10">{escape(title)}</text>'
    )


def lines_over_time(
    series, *, label: str, y_title: str, y_format, clamp_zero=False, zero=True
) -> Markup:
    """Up to four series over time, one categorical colour each (fixed order,
    slots s1-s4), with a legend; `step` series hold their value until the
    next point (a running best). series: [{"name", "points": [(iso time,
    value)], "step": bool}]."""
    series = [s for s in series if s["points"]][:4]
    if not series:
        return Markup("")
    periods = [p[0] for s in series for p in s["points"]]
    values = [p[1] for s in series for p in s["points"]]
    frame = Frame(periods, values, zero=zero, clamp_zero=clamp_zero)
    frame.top = max(frame.top, 20)
    parts = _axes(frame, y_format)
    parts.append(_y_title(frame, y_title))
    hover = []
    for i, s in enumerate(series, start=1):
        xy = [(frame.x(t), frame.y(v)) for t, v in s["points"]]
        if s.get("step"):
            stepped = []
            for (x, y), nxt in zip(xy, xy[1:] + [None]):
                stepped.append((x, y))
                if nxt:
                    stepped.append((nxt[0], y))
            xy_path = stepped
        else:
            xy_path = xy
        parts.append(f'<path class="line s{i}" d="{_path(xy_path)}"/>')
        for (x, y), (t, v) in zip(xy, s["points"]):
            hover.append(
                {
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "title": t[:10],
                    "rows": [[s["name"], y_format(v)]],
                }
            )
    legend = (
        '<div class="legend">'
        + "".join(
            f'<span class="key"><span class="key-line s{i}"></span>'
            f"{escape(s['name'])}</span>"
            for i, s in enumerate(series, start=1)
        )
        + "</div>"
    )
    return _figure("points", _svg(parts, label, frame), hover, legend)


def dated_points(
    points, *, label: str, y_title: str, y_format, clamp_zero=False
) -> Markup:
    """One dot per item over time. points: [{"at", "y", "kind" (a FIT_KINDS
    key), "title", "rows", "href"}]."""
    if not points:
        return Markup("")
    frame = Frame(
        [p["at"] for p in points],
        [p["y"] for p in points],
        zero=True,
        clamp_zero=clamp_zero,
    )
    frame.top = max(frame.top, 20)
    parts = _axes(frame, y_format)
    parts.append(_y_title(frame, y_title))
    order = {k: i for i, k in enumerate(FIT_KINDS)}
    hover = []
    for p in sorted(points, key=lambda p: order[p["kind"]]):
        x, y = frame.x(p["at"]), frame.y(p["y"])
        parts.append(_fit_mark(p, x, y))
        hover.append(
            {
                "x": round(x, 1),
                "y": round(y, 1),
                "title": p["title"],
                "rows": [["", _fit_label(p)], *p.get("rows", [])],
                "href": p.get("href"),
            }
        )
    legend = _fit_legend(points)
    return _figure("points", _svg(parts, label, frame), hover, legend)
