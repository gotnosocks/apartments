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
import posixpath
import re
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
# Ben's fit window (2026-10-01): a full Chelsea + West Village fit within 2
# hours (autoselect's WINDOW_SECONDS); exploratory subset fits within 30
# minutes, never served.
TARGET_MINUTES = 120
SUBSET_MINUTES = 30


def run_of(entry: dict) -> str:
    return ((entry.get("splits") or {}).get("rows") or {}).get("run") or ""


def is_subset(run: str) -> bool:
    """A fit on a tuning subset of the data ("...-nb-tune35"): exploration
    only, never served."""
    return any(part.startswith("tune") for part in run.split("-"))


# A fit's tier (`tier.name`, rentfrontier fit tiers): a full fit, or a short
# exploration fit that counts on the research frontier but is never served.
TIERS = {
    "full": "Full fit",
    "exploration": "Exploration fit",
}


def tier_of(entry: dict) -> str:
    """The fit's tier; entries from before tiers are full fits."""
    name = (entry.get("tier") or {}).get("name")
    return name if name in TIERS else "full"


def subset_fit(entry: dict) -> bool:
    """A fit on a subset of the data (its tier names one, or its run name
    has a tuning part): its accuracy covers fewer listings, so it is shown in
    tables only."""
    return bool((entry.get("tier") or {}).get("subset")) or is_subset(run_of(entry))


def data_rules_of(entry: dict) -> tuple[str, ...]:
    """The data rules a fit used, from its id ("model/features/sampler@commit
    +rule+rule"; none for a fit on all the rows)."""
    after = str(entry.get("id") or "").split(" ")[0].partition("@")[2]
    return tuple(sorted(after.split("+")[1:]))


def draws_of(entry: dict) -> int | None:
    """How many posterior draws the fit kept (its tier's, else the entry's)."""
    draws = (entry.get("tier") or {}).get("draws") or entry.get("draws")
    return draws if isinstance(draws, int) else None


def group_measurements(fits: list[dict]) -> None:
    """A design measured more than once (the same model, features and data
    rules at several draw counts, #126): give each scored fit of it a shared
    `group`, and fade all but the best-measured one (most draws, then the
    newest)."""
    groups: dict[tuple, list[dict]] = {}
    for f in fits:
        f["group"], f["faded"] = None, False
        if f["delta"] is not None:
            key = (design_id(f["entry"]), data_rules_of(f["entry"]))
            groups.setdefault(key, []).append(f)
    members = [g for g in groups.values() if len(g) > 1]
    for i, group in enumerate(members):
        best = max(
            group,
            key=lambda f: (f["draws"] or 0, f["entry"].get("available_at") or ""),
        )
        for f in group:
            f["group"], f["faded"] = i, f is not best


def full_fits_of(data: dict, entry: dict) -> list[dict]:
    """The full fits of an exploration fit's design (same model, features
    and data rules), newest first: where a promising design went next."""
    rules = data_rules_of(entry)
    return sorted(
        (
            e
            for e in data.get("entries", [])
            if tier_of(e) == "full"
            and design_id(e) == design_id(entry)
            and data_rules_of(e) == rules
        ),
        key=lambda e: e.get("available_at") or "",
        reverse=True,
    )


def serve_status(entry: dict) -> tuple[str, str | None]:
    """Whether a fit can be served: ("yes", None), ("no", reason) or
    ("unknown", None). The reason is autoselect's (`why_not_served`, written
    by the dashboard build); without it, a fit that fails the convergence
    checks is still a "no", and anything else is not known yet."""
    if subset_fit(entry):
        return "no", "a subset fit, for exploration only"
    if "why_not_served" in entry:
        reason = entry["why_not_served"]
        return ("no", reason) if reason else ("yes", None)
    if tier_of(entry) == "exploration":
        return "no", "an exploration fit, for tracking the research only"
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
    hidden = 0 if subsets else sum(subset_fit(e) for e in entries)
    fits = []
    for e in entries:
        run = run_of(e)
        subset = subset_fit(e)
        if subset and not subsets:
            continue
        tier = tier_of(e)
        if run and run == served_run and day is None:
            kind = "served"
        elif subset:
            kind = "subset"
        elif e["key"] in frontier:
            kind = "frontier"
        elif not e.get("passes_checks") and tier == "full":
            # The convergence gate applies to full fits; exploration fits are
            # judged on their ranking.
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
                "tier": tier,
                "draws": draws_of(e),
                "best": e["key"] == best,
                "delta": psis.get("delta"),
                "delta_se": psis.get("delta_se"),
                "minutes": e["fit_seconds"] / 60,
                "elegance": elegance_summary(e),
                "serve": serve,
                "why_not": why_not,
            }
        )
    fits.sort(key=lambda f: (f["delta"] is None, -(f["delta"] or 0)))
    group_measurements(fits)
    return {
        "snapshot": snap,
        "fits": fits,
        "frontier": [f for f in fits if f["frontier"] or f["kind"] == "served"],
        "unscored": sum(f["delta"] is None for f in fits),
        "hidden_subsets": hidden,
    }


# Model lines on the board, in plain words.
LINES = {
    "frontier": "Custom samplers (JAX)",
    "numpyro": "NumPyro NUTS",
    "pymc": "PyMC",
}
# The first direction of each board sort: most accurate, fastest, fewest
# effective parameters, newest first.
BOARD_ORDERS = {"delta": "desc", "time": "asc", "params": "asc", "landed": "desc"}
BOARD_SORTS = {
    "delta": lambda e: (e.get("psis") or {}).get("delta"),
    "time": lambda e: e.get("fit_seconds"),
    "params": lambda e: (e.get("psis") or {}).get("p_loo"),
    "landed": lambda e: e.get("available_at"),
}


# The judge agents' pairwise elegance judgements, as rentfrontier writes them
# (Ben, 2026-10-01: elegance replaces renter simplicity; every pair is judged
# again under the elegance brief, so the old simplicity verdicts are not shown).
VERDICTS_FIELD = "elegance"
JUDGEMENTS_FIELD = "elegance_judgements"

# A fit's verdict against another design, in words.
ELEGANCE_WORDS = {
    "more elegant": "more elegant than",
    "equal": "as elegant as",
    "less elegant": "less elegant than",
}
# The same verdict as a table cell ("this design is ...").
ELEGANCE_CELLS = {
    "more elegant": "more elegant",
    "equal": "about as elegant",
    "less elegant": "less elegant",
}


def design_id(entry: dict) -> str:
    """ "model/feature set", the design the judges compare
    (rentfrontier.elegance.design_id)."""
    if entry.get("design") and entry.get("feature_set"):
        return f"{entry['design']}/{entry['feature_set']}"
    return str(entry.get("id") or entry.get("key"))


def verdicts(entry: dict) -> list[dict]:
    """A fit's judged pairs: [{vs, verdict, reason}]."""
    return list(entry.get(VERDICTS_FIELD) or ())


def judgements(data: dict) -> list[dict]:
    return list(data.get(JUDGEMENTS_FIELD) or ())


def elegance_summary(entry: dict) -> str | None:
    """A fit's judged pairs counted in words ("more elegant than 2, less
    elegant than 1"), or None when its design has no judgement."""
    counts: dict[str, int] = {}
    for j in verdicts(entry):
        word = ELEGANCE_WORDS.get(j.get("verdict"))
        if word:
            counts[word] = counts.get(word, 0) + 1
    order = ["more elegant than", "as elegant as", "less elegant than"]
    return ", ".join(f"{w} {counts[w]}" for w in order if w in counts) or None


def elegance_pairs(data: dict) -> list[dict]:
    """Every recorded judgement, newest first, with the board fits of each
    design and whether the two judges agreed."""
    fits: dict[str, list[str]] = {}
    p_loo: dict[str, float] = {}
    newest = sorted(data.get("entries", []), key=lambda e: e.get("available_at") or "")
    for e in newest:
        fits.setdefault(design_id(e), []).append(e["key"])
        value = (e.get("psis") or {}).get("p_loo")
        if isinstance(value, (int, float)):
            p_loo[design_id(e)] = value  # the newest fit's
    for keys in fits.values():
        keys.reverse()  # newest first: a design links to its latest fit
    out = []
    for j in judgements(data):
        designs = list(j.get("designs") or ())
        if len(designs) != 2:
            continue
        said = [x.get("verdict") for x in j.get("judges") or ()]
        out.append(
            {
                "designs": [
                    {"id": d, "fits": fits.get(d, []), "p_loo": p_loo.get(d)}
                    for d in designs
                ],
                "verdict": j.get("verdict"),
                "reason": j.get("reason"),
                "date": j.get("date"),
                "judges": j.get("judges") or [],
                "agreed": len(said) > 1 and len(set(said)) == 1,
            }
        )
    out.sort(key=lambda p: p["date"] or "", reverse=True)
    return out


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
    tier: str | None = None,
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
        and (not servable or serve_status(e)[0] == "yes")
        and (subsets or not subset_fit(e))
        and (tier is None or tier_of(e) == tier)
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


def _ranks(values: list[float]) -> list[float]:
    """Ranks from 1, ties sharing their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation, or None for fewer than three pairs or no
    spread."""
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if not sxx or not syy:
        return None
    return sxy / (sxx * syy) ** 0.5


def validation_pairs(data: dict, hardware: str | None) -> list[dict]:
    """Fits with both their PSIS-LOO score and a genuine held-out score (the
    row split's held-out listings), on one hardware class or all."""
    out = []
    for e in data.get("entries", []):
        if hardware and e["hardware_class"] != hardware:
            continue
        if subset_fit(e):
            continue
        psis = (e.get("psis") or {}).get("delta")
        rows = (e.get("splits") or {}).get("rows") or {}
        if psis is None or rows.get("delta") is None:
            continue
        out.append(
            {
                "entry": e,
                "psis": psis,
                "heldout": rows["delta"],
                "heldout_se": rows.get("delta_se"),
            }
        )
    return out


def implementations(data: dict) -> list[dict]:
    """Designs fit by more than one sampler on the same hardware: the same
    model, different implementations."""
    groups: dict[tuple, list] = {}
    for e in data.get("entries", []):
        groups.setdefault((e.get("structure"), e["hardware_class"]), []).append(e)
    out = []
    for (structure, hardware), entries in sorted(
        groups.items(), key=lambda kv: (kv[0][1], kv[0][0] or "")
    ):
        if len({e.get("sampler") for e in entries}) > 1:
            out.append(
                {
                    "structure": structure,
                    "hardware": hardware,
                    "entries": sorted(entries, key=lambda e: e["fit_seconds"]),
                }
            )
    return out


# The research plan, read from the dashboard's checkout, which follows master
# every ten minutes, so the page is current between site deploys.
PLAN = Path(
    os.environ.get(
        "RESEARCH_PLAN", "/data1/apartments/serve/master/docs/research-plan.md"
    )
)
REPO_PLAN = Path(__file__).resolve().parents[3] / "docs" / "research-plan.md"
GITHUB = "https://github.com/gotnosocks/apartments/blob/master/"


def doc_link(href: str, base: str = "docs") -> str:
    """A link in a document under docs/, made absolute: other repository
    files open on GitHub; web links and in-page anchors are kept."""
    if not href or href.startswith("#"):
        return href
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href):
        return href  # any scheme (https:, mailto:, ...) is left as written
    if href.startswith("/"):
        href = href.lstrip("/")
        base = ""
    path, _, fragment = href.partition("#")
    resolved = posixpath.normpath(posixpath.join(base, path))
    if resolved.startswith(".."):
        return "#"  # outside the repository: no link
    return GITHUB + resolved + (f"#{fragment}" if fragment else "")


def _slug(text: str, seen: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    slug, n = base, 2
    while slug in seen:
        slug, n = f"{base}-{n}", n + 1
    seen.add(slug)
    return slug


def render_markdown(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Markdown to HTML (raw HTML in the source is escaped, not rendered),
    with headings one level down (the page has its own h1), ids on them for a
    contents list, and repository links pointing at GitHub."""
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = md.parse(text)
    toc, seen = [], set()
    for i, token in enumerate(tokens):
        if token.type in ("heading_open", "heading_close"):
            level = min(int(token.tag[1]) + 1, 6)
            token.tag = f"h{level}"
            if token.type == "heading_open":
                inline = tokens[i + 1]
                title = (
                    "".join(
                        c.content
                        for c in inline.children or []
                        if c.type in ("text", "code_inline")
                    )
                    or inline.content
                )
                slug = _slug(title, seen)
                token.attrSet("id", slug)
                if level <= 3:
                    toc.append((level, title, slug))
        if token.type == "inline":
            for child in token.children or []:
                if child.type == "link_open":
                    child.attrSet("href", doc_link(child.attrGet("href") or ""))
                elif child.type == "image":
                    child.attrSet(
                        "src",
                        doc_link(child.attrGet("src") or "").replace("/blob/", "/raw/"),
                    )
    return md.renderer.render(tokens, md.options, {}), toc


class Plan:
    """The rendered research plan, kept until the file changes."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else PLAN
        self._key = None
        self._value = None
        self._lock = threading.Lock()

    def load(self) -> dict | None:
        source = next(
            (p for p in (self.path, REPO_PLAN) if p.is_file()),
            None,
        )
        if source is None:
            return None
        stat = source.stat()
        key = (str(source.resolve()), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key != self._key:
                html, toc = render_markdown(source.read_text())
                self._key = key
                self._value = {
                    "html": html,
                    "toc": toc,
                    "source": str(source),
                    "fallback": source != self.path,
                    "modified": stat.st_mtime,
                }
            return self._value


def designs(data: dict | None, served_run: str | None) -> tuple[list[dict], list[str]]:
    """Every model design on the board with a recorded structure, best first:
    [{name, anatomy, best (the entry with the highest PSIS-LOO, else the
    latest), fits, served, differences (from the served design)}], and the
    names of designs whose records hold no structure (the old PyMC screens)."""
    from .anatomy import describe, differences

    if not data:
        return [], []
    served = entry_for_run(data, served_run)
    served_design = served.get("design") if served else None
    by_design: dict[str, list[dict]] = {}
    for e in data.get("entries", []):
        by_design.setdefault(e.get("design") or "", []).append(e)
    rows, unrecorded = [], []
    for name, entries in by_design.items():
        # Fits of one design name by another backend (the PyMC ladder) record
        # no structure: take the design from the fits that do.
        recorded = [e for e in entries if describe(e.get("model")) is not None]
        if not recorded:
            unrecorded.append(name)
            continue
        scored = [e for e in recorded if _delta(e) is not None]
        best = max(scored, key=_delta) if scored else recorded[-1]
        own = served if name == served_design else best
        a = describe(own.get("model"), own.get("sizes"))
        rows.append(
            {
                "name": name,
                "anatomy": a,
                "best": best,
                "fits": len(entries),
                "served": name == served_design,
            }
        )
    base = next((r["anatomy"] for r in rows if r["served"]), None)
    for r in rows:
        r["differences"] = (
            differences(r["anatomy"], base) if base and not r["served"] else []
        )
    rows.sort(
        key=lambda r: (
            not r["served"],
            _delta(r["best"]) is None,
            -(_delta(r["best"]) or 0.0),
        )
    )
    return rows, sorted(unrecorded)


def _delta(entry: dict) -> float | None:
    d = (entry.get("psis") or {}).get("delta")
    return d if isinstance(d, (int, float)) else None
