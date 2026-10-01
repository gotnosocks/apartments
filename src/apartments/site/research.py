"""Research data for the site's Research section.

`rentfrontier.dashboard` (frontier environment, every 10 minutes under the
heavy-job lock) writes the board's data to the `site` build of
/data1/apartments/dashboard: entries, as-of snapshots, milestones and the
data-quality card. The site reads that file read-only and keeps the parsed
copy until the file behind the symlink changes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DEFAULT = Path(
    os.environ.get("RESEARCH_DATA", "/data1/apartments/dashboard/site/data.json")
)


class Research:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or DEFAULT)
        self._key = None
        self._data = None
        self._lock = threading.Lock()

    def load(self) -> dict | None:
        """The board data, or None when no build is readable."""
        try:
            real = self.path.resolve(strict=True)
            stat = real.stat()
        except OSError:
            return None
        key = (str(real), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key != self._key:
                try:
                    data = json.loads(real.read_text())
                except (OSError, ValueError):
                    return self._data  # a build mid-swap: keep the last good copy
                self._key, self._data = key, data
            return self._data


def entry_for_run(data: dict | None, run: str | None) -> dict | None:
    """The board entry whose row-split fit is `run`."""
    if not data or not run:
        return None
    for entry in data.get("entries", []):
        rows = (entry.get("splits") or {}).get("rows") or {}
        if rows.get("run") == run:
            return entry
    return None


def latest_milestones(data: dict | None, n: int = 6) -> list[dict]:
    if not data:
        return []
    # Newest first; a model switch before the merge that carries it (same time).
    milestones = sorted(
        data.get("milestones", []),
        key=lambda m: (m.get("at", ""), m.get("kind") == "selection"),
        reverse=True,
    )
    return milestones[:n]


# The hardware the served model is chosen on (rentfrontier.autoselect).
TARGET_HARDWARE = "thelio RTX 2060 SUPER"
# Ben's target: a full Chelsea + West Village fit within 30 minutes.
TARGET_MINUTES = 30


def run_of(entry: dict) -> str:
    return ((entry.get("splits") or {}).get("rows") or {}).get("run") or ""


def is_subset(run: str) -> bool:
    """A fit on a tuning subset of the data ("...-nb-tune35"): exploration
    only, never served."""
    return any(part.startswith("tune") for part in run.split("-"))


def serve_status(entry: dict) -> tuple[str, str | None]:
    """Whether a fit can be served: ("yes", None), ("no", reason) or
    ("unknown", None). The reason is autoselect's (`why_not_served`, written
    by the dashboard build); without it, a fit that fails the convergence
    checks is still a "no", and anything else is not known yet."""
    if is_subset(run_of(entry)):
        return "no", "a subset fit, for exploration only"
    if "why_not_served" in entry:
        reason = entry["why_not_served"]
        return ("no", reason) if reason else ("yes", None)
    if not entry.get("passes_checks"):
        return "no", "it fails the convergence gate"
    return "unknown", None


def hardware_classes(data: dict) -> list[str]:
    """Hardware classes on the board, the target first, then by entry count."""
    counts: dict[str, int] = {}
    for e in data.get("entries", []):
        counts[e["hardware_class"]] = counts.get(e["hardware_class"], 0) + 1
    return sorted(counts, key=lambda c: (c != TARGET_HARDWARE, -counts[c], c))


def snapshot_days(data: dict) -> list[str]:
    """Days (UTC) on which board results landed, newest first."""
    return sorted({s["at"][:10] for s in data.get("snapshots", [])}, reverse=True)


def snapshot_on(data: dict, day: str | None) -> dict | None:
    """The board as it stood at the end of `day` (the newest when None)."""
    snaps = sorted(data.get("snapshots", []), key=lambda s: s["at"])
    if day:
        snaps = [s for s in snaps if s["at"][:10] <= day]
    return snaps[-1] if snaps else None


def outlier_floor(deltas: list[float]) -> float | None:
    """A y-axis floor that leaves out fits far below the rest (the mean-only
    baselines sit tens of thousands below every structured model), so the
    differences that matter stay visible; None when nothing is that far."""
    if len(deltas) < 4:
        return None
    ordered = sorted(deltas)
    q1, q3 = ordered[len(ordered) // 4], ordered[(3 * len(ordered)) // 4]
    cut = q1 - 3 * max(q3 - q1, 1.0)
    kept = [d for d in ordered if d >= cut]
    return min(kept) if len(kept) < len(ordered) else None


def frontier_view(
    data: dict,
    hardware: str,
    day: str | None,
    served_run: str | None,
    subsets: bool = False,
) -> dict:
    """The fits of one hardware class as the board stood on `day`: their marks
    (served, subset, frontier, failing, other), and the frontier and best.
    The served mark is today's, so a past day shows none."""
    snap = snapshot_on(data, day)
    cut = snap["at"] if snap else None
    group = (snap or {}).get("by_class", {}).get(hardware, {})
    frontier, best = set(group.get("frontier", [])), group.get("best")
    entries = [
        e
        for e in data.get("entries", [])
        if e["hardware_class"] == hardware
        and e.get("available_at")
        and (cut is None or e["available_at"] <= cut)
    ]
    hidden = 0 if subsets else sum(is_subset(run_of(e)) for e in entries)
    fits = []
    for e in entries:
        run = run_of(e)
        if is_subset(run) and not subsets:
            continue
        if run and run == served_run and day is None:
            kind = "served"
        elif is_subset(run):
            kind = "subset"
        elif e["key"] in frontier:
            kind = "frontier"
        elif not e.get("passes_checks"):
            kind = "failing"
        else:
            kind = "other"
        psis = e.get("psis") or {}
        serve, why_not = serve_status(e)
        fits.append(
            {
                "entry": e,
                "run": run,
                "kind": kind,
                "frontier": e["key"] in frontier,
                "best": e["key"] == best,
                "delta": psis.get("delta"),
                "delta_se": psis.get("delta_se"),
                "minutes": e["fit_seconds"] / 60,
                "complexity": e.get("complexity"),
                "serve": serve,
                "why_not": why_not,
            }
        )
    fits.sort(key=lambda f: (f["delta"] is None, -(f["delta"] or 0)))
    return {
        "snapshot": snap,
        "fits": fits,
        "frontier": [f for f in fits if f["frontier"] or f["kind"] == "served"],
        "unscored": sum(f["delta"] is None for f in fits),
        "unrated": sum(f["complexity"] is None for f in fits if f["delta"] is not None),
        "hidden_subsets": hidden,
    }


# Model lines on the board, in plain words.
LINES = {
    "frontier": "Custom samplers (JAX)",
    "numpyro": "NumPyro NUTS",
    "pymc": "PyMC",
}
BOARD_SORTS = {
    "delta": lambda e: (e.get("psis") or {}).get("delta"),
    "time": lambda e: e.get("fit_seconds"),
    "complexity": lambda e: e.get("complexity"),
    "landed": lambda e: e.get("available_at"),
}


def entry_by_key(data: dict | None, key: str) -> dict | None:
    if not data:
        return None
    return next((e for e in data.get("entries", []) if e.get("key") == key), None)


def board_rows(
    data: dict,
    *,
    hardware: str | None = None,
    line: str | None = None,
    q: str = "",
    servable: bool = False,
    subsets: bool = False,
    sort: str = "delta",
    descending: bool = True,
) -> list[dict]:
    """Board entries filtered and sorted; entries without the sort value last."""
    q = q.lower()
    rows = [
        e
        for e in data.get("entries", [])
        if (hardware is None or e["hardware_class"] == hardware)
        and (line is None or e.get("line") == line)
        and (
            not q or q in e["key"].lower() or q in (e.get("design_text") or "").lower()
        )
        and (not servable or not e.get("why_not_served"))
        and (subsets or not is_subset(run_of(e)))
    ]
    value = BOARD_SORTS.get(sort, BOARD_SORTS["delta"])
    present = [e for e in rows if value(e) is not None]
    missing = [e for e in rows if value(e) is None]
    present.sort(key=value, reverse=descending)
    return present + missing


def best_over_time(data: dict, hardware: str) -> list[tuple[str, float]]:
    """The best fit's PSIS-LOO ΔELPD each time a result landed (the board's
    own replay), for one hardware class."""
    out = []
    for snap in sorted(data.get("snapshots", []), key=lambda s: s["at"]):
        best = snap.get("by_class", {}).get(hardware, {}).get("best_delta")
        if best is not None:
            out.append((snap["at"], best))
    return out


def compute_by_line(data: dict) -> list[dict]:
    """Cumulative fit hours by model line, one point per finished split."""
    splits = sorted(
        (
            s["completed_at"],
            e.get("line") or "frontier",
            s.get("fit_seconds") or 0.0,
        )
        for e in data.get("entries", [])
        for s in (e.get("splits") or {}).values()
        if s.get("completed_at")
    )
    totals: dict[str, float] = {}
    series: dict[str, list] = {}
    for at, line, seconds in splits:
        totals[line] = totals.get(line, 0.0) + seconds / 3600
        series.setdefault(line, []).append((at, totals[line]))
    order = [k for k in LINES if k in series] + [k for k in series if k not in LINES]
    return [{"name": LINES.get(k, k), "points": series[k], "line": k} for k in order]
