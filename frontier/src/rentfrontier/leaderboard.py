"""Build the single leaderboard for both model lines from recorded runs.

    python -m rentfrontier.leaderboard

Two sources, scored against the same pinned per-row references:

* frontier runs: every reportable run under /data1/apartments/frontier/runs,
  grouping the row-split and unit-split runs of the same design (commit,
  model, feature set, sampler);
* PyMC screens: every NUTS screen under data/model/feature-screen-*/<name>/
  (``result.json`` plus per-row ``heldout.npz``), grouping ``<stem>-rows`` and
  ``<stem>-units``.

Writes docs/model/leaderboard/leaderboard.{json,md}.

Annotations. docs/model/leaderboard/annotations.json holds hand-written
context for entries (hardware, what a record does and does not show, which
fit the app serves), keyed by entry id, plus footer lines. Kept-draw
rescores under /data1/apartments/frontier/rescores (`rentfrontier.rescore`)
are attached to the split they rescore and summarised as annotations. Neither
changes a score, the ranking or the frontier: those use the recorded runs.

Ranking rule. Entries must pass the convergence gate and the
interpretability requirement. They are ranked by row-split dELPD against the
promoted model: Ben's use fits data that includes the listing's own unit, and
a held-out row of an in-fit unit is the matching test. When two entries'
paired row-split difference is within two standard errors, the unit split
decides; if neither split separates them, the faster entry ranks first.
PyMC screens that fail the gate are listed as screen-grade: shown, but never
current best or on the frontier.

Frontier. An entry is on the frontier if no other entry is at least as good
on row-split dELPD and fit time (Ben's accuracy-vs-complexity axes) and
strictly better on one. Unit-split dELPD, cost and hardware are columns.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import data
from .run import REFERENCES

RUNS = data.OUTPUT_ROOT / "runs"
RESCORES = data.OUTPUT_ROOT / "rescores"
DOCS = Path(__file__).resolve().parents[3] / "docs" / "model" / "leaderboard"
ANNOTATIONS = DOCS / "annotations.json"
# PyMC screens live beside the pinned references (feature-screen-20260923).
SCREENS = REFERENCES["rows"].parent.parent.parent
REFERENCE_SCREENS = {"nuts-hwalk", "nuts-hwalk-units"}
GATE_RHAT, GATE_ESS = 1.01, 400

PROMOTED = {
    "id": "promoted",
    "description": "Promoted PyMC model (bedroom-group time curves + per-building half-year random walk), NUTS 4x1000/1000; screen fits on each split's training rows",
    "fit": "data/model/chelsea-bayesian-product-scope-structure-20260923",
    "feature_set": "promoted model's own design (bayesian_structure_graph_v2 defaults + building walk)",
    "rows": {"elpd": 5863.6954937789105, "elpd_se": 75.62662539814482, "delta": 0.0},
    "units": {
        "elpd": 3822.15,
        "delta": 0.0,
        "note": "nuts-hwalk-units, unit effect integrated by 200 MC draws",
    },
    "fit_seconds": 22200.0,
    "fit_seconds_note": "full production fit of the promoted structure model: ~6.2 h local wall time (protocol 22:28 -> posterior 04:38, 4 chains x 4000 tune + 6000 draws, shared machine); its row-split held-out screen took 9,697 s",
    "cost_usd": 1.97,
    "cost_note": "estimate: 6.2 h at the Modal 4-core CPU rate ($0.32/h); the older spline model's measured Modal fit was 55 min, $0.38",
    "hardware": "CPU (nutpie/Numba)",
    "passes_checks": True,
    "interpretable": True,
}


def load_runs():
    runs = []
    for path in sorted(RUNS.glob("*/result.json")):
        r = json.loads(path.read_text())
        # Smoke tests and canaries check the pipeline; they are not reported runs.
        if (
            not r.get("reportable")
            or r["name"].startswith(("dev-", "canary-"))
            or r["split"] not in ("rows", "units")
        ):
            continue
        r["_dir"] = path.parent
        runs.append(r)
    return runs


def load_rescores():
    """Latest reportable kept-draw rescore per source run name."""
    out = {}
    for path in sorted(RESCORES.glob("*/result.json"), key=lambda p: p.stat().st_mtime):
        r = json.loads(path.read_text())
        if not r.get("dirty"):
            out[r["source_run"]] = r
    return out


def load_annotations():
    if not ANNOTATIONS.exists():
        return {"entries": {}, "footer": []}
    a = json.loads(ANNOTATIONS.read_text())
    return {"entries": a.get("entries", {}), "footer": a.get("footer", [])}


def rescore_text(split, rs):
    d = rs["exact_minus_approximate"]
    draws = rs["draws"]["chains"] * rs["draws"]["per_chain"]
    return (
        f"{split} split rescored from {draws} kept draws with the exact unseen-unit "
        f"quadrature (rentfrontier.rescore @{rs['commit'][:7]}): exact - recorded "
        f"approximation = {d['elpd']:+.1f} ± {d['se']:.1f} on the same draws "
        f"({rs['unseen_unit_rows']:,} unseen-unit rows), so the recorded "
        f"{rs['recorded']['delta_elpd']:+.1f} is about "
        f"{rs['exact_recorded_equivalent']['delta_elpd']:+.1f} under exact scoring."
    )


def group_gate(r) -> tuple[float | None, bool, str]:
    """Max R-hat over every group effect, and whether it passes.

    New runs record it from exact per-chain moments (threshold 1.05). For
    older runs it is recomputed from the saved kept joint draws (20-30 per
    chain, so a looser 1.1 threshold), which still exposes chains stuck in
    different modes for a single building.
    """
    recorded = r["diagnostics"].get("group_rhat_max")
    if recorded is not None:
        return recorded, recorded < 1.05, "per-chain moments, all effects"
    post = np.load(r["_dir"] / "posterior.npz", allow_pickle=True)
    worst = 1.0
    for key in ("building", "bedroom_slope", "fslope", "walk", "unit"):
        name = f"kept/{key}"
        if name not in post.files:
            continue
        x = post[name].astype(np.float64)  # (chains, kept, ...)
        if x.ndim < 3 or x.shape[2] <= 1:
            continue
        n = x.shape[1]
        w = x.var(axis=1, ddof=1).mean(axis=0)
        b = n * x.mean(axis=1).var(axis=0, ddof=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            rh = np.sqrt(((n - 1) / n * w + b / n) / w)
        worst = max(worst, float(np.nanmax(np.where(w > 0, rh, 1.0))))
    return worst, worst < 1.1, "kept joint draws, all group effects"


def design_key(r):
    return (
        r["commit"],
        r["model"]["name"],
        r["feature_set"],
        r["sampler"],
        json.dumps(r["sampler_settings"], sort_keys=True),
    )


def paired(a_dir: Path, b_dir: Path):
    """Paired sum and SE of lpd differences a - b on identical held-out rows.

    Refuses differing row sets: a comparison on a silently shrunken subset is
    not the same test."""
    a = np.load(a_dir / "heldout.npz", allow_pickle=True)
    b = np.load(b_dir / "heldout.npz", allow_pickle=True)
    for x, folder in ((a, a_dir), (b, b_dir)):
        if len(set(x["audit_id"].tolist())) != len(x["audit_id"]):
            raise ValueError(f"Duplicate held-out audit IDs in {folder.name}")
    al = dict(zip(a["audit_id"].tolist(), a["lpd"]))
    bl = dict(zip(b["audit_id"].tolist(), b["lpd"]))
    if al.keys() != bl.keys():
        raise ValueError(
            f"Held-out rows differ: {a_dir.name} ({len(al)}) vs {b_dir.name} ({len(bl)})"
        )
    d = np.array([al[k] - bl[k] for k in al])
    return float(d.sum()), float(d.std(ddof=1) * math.sqrt(len(d)))


def screen_entries():
    """PyMC NUTS screens as board entries, grouped by ``<stem>-rows/-units``.

    Commit, cost and hardware come from the remote-run record when the screen
    ran through models.modal_remote_fit; local screens record neither."""
    groups = {}
    for path in sorted(SCREENS.glob("feature-screen-*/*/result.json")):
        name = path.parent.name
        r = json.loads(path.read_text())
        if (
            name in REFERENCE_SCREENS
            or r.get("method") != "nuts"
            or r.get("split", "rows") not in ("rows", "units")
            or not (path.parent / "heldout.npz").exists()
        ):
            continue
        split = r.get("split", "rows")
        stem = name.removesuffix(f"-{split}")
        groups.setdefault(stem, {})[split] = (path.parent, r)
    entries = []
    for stem, by_split in sorted(groups.items()):
        # Each split is its own run: read its own remote record.
        remotes = {
            split: (
                json.loads((folder / "remote-run.json").read_text())
                if (folder / "remote-run.json").exists()
                else {}
            )
            for split, (folder, _) in by_split.items()
        }
        commits = set()
        for remote in remotes.values():
            git = remote.get("request_git") or {}
            commits.add(git.get("head") if git and not git.get("dirty_paths") else None)
        commits_differ = len(commits) > 1
        commit = None if commits_differ else commits.pop()
        cpus = {(rem.get("resources") or {}).get("cpu") for rem in remotes.values()}
        cpus.discard(None)
        e = {
            "id": f"pymc/{stem}" + (f"@{commit[:7]}" if commit else ""),
            "line": "pymc",
            "commit": commit,
            "commits_differ": commits_differ,
            "model": {"name": stem},
            "feature_set": "pymc design",
            "sampler": "nuts",
            "sampler_settings": {
                "draws": "structure_screen defaults (4 chains x 1,000 tune / 1,000 draws)",
                "train_rows": {
                    s: r.get("train_rows") for s, (_, r) in by_split.items()
                },
                "runner_args": {
                    s: rem.get("runner_args") for s, rem in remotes.items() if rem
                },
            },
            "hardware": (
                "Modal CPU (" + "/".join(f"{c:g}" for c in sorted(cpus)) + " cores)"
                if cpus
                else "thelio CPU"
            ),
            "interpretable": True,
            "splits": {},
        }
        passes, seconds, cost = True, [], []
        for split, (folder, r) in by_split.items():
            remote = remotes[split]
            diag, held = r["diagnostics"], r["heldout"]
            try:
                delta, delta_se = paired(folder, REFERENCES[split].parent)
            except ValueError:
                delta = delta_se = None
            ok = (
                diag["max_rhat"] < GATE_RHAT
                and diag["min_ess_bulk"] > GATE_ESS
                and not diag.get("divergences")
                and delta is not None
            )
            e["splits"][split] = {
                "run": folder.name,
                "elpd": held["elpd"],
                "elpd_se": held.get("elpd_se"),
                "delta": delta,
                "delta_se": delta_se,
                "max_rhat": diag["max_rhat"],
                "min_ess": diag["min_ess_bulk"],
                # Screens report R-hat over every parameter, group effects included.
                "group_rhat_max": diag["max_rhat"],
                "passes": bool(ok),
                "fit_seconds": r["seconds"],
                "coverage_95": held.get("coverage_95"),
                "_dir": str(folder),
            }
            passes &= bool(ok)
            seconds.append(r["seconds"])
            cost.append(remote.get("estimated_worker_usd") or 0.0)
        e["passes_checks"] = passes
        e["grade"] = "full" if passes else "screen"
        e["fit_seconds"] = max(seconds)
        e["cost_usd"] = max(cost)
        entries.append(e)
    return entries


def build():
    rescores = load_rescores()
    annotations = load_annotations()
    groups = {}
    for r in load_runs():
        groups.setdefault(design_key(r), {})[r["split"]] = r
    entries = []
    for by_split in groups.values():
        any_run = next(iter(by_split.values()))
        e = {
            "id": f"{any_run['model']['name']}/{any_run['feature_set']}/{any_run['sampler']}@{any_run['commit'][:7]}",
            "commit": any_run["commit"],
            "model": any_run["model"],
            "feature_set": any_run["feature_set"],
            "sampler": any_run["sampler"],
            "sampler_settings": any_run["sampler_settings"],
            "hardware": ((any_run.get("remote") or {}).get("gpu_reported") or "").split(
                ","
            )[0]
            or any_run["hardware"].get("gpu")
            or "local",
            "interpretable": bool(
                any_run["interpretability"]["named_additive_contributions"]
            ),
            "splits": {},
        }
        passes = True
        fit_seconds, cost = [], []
        for split, r in by_split.items():
            s = r["score"]
            vp = dict(s.get("vs_promoted", {}))
            if (
                vp.get("delta_elpd") is None
                and REFERENCES.get(split, Path("/nonexistent")).exists()
            ):
                # Reference landed after the run was scored: pair it here.
                d_, se_ = paired(r["_dir"], REFERENCES[split].parent)
                vp.update(
                    delta_elpd=d_, delta_elpd_se=se_, reference=str(REFERENCES[split])
                )
            e["splits"][split] = {
                "run": r["name"],
                "elpd": s["elpd"],
                "elpd_se": s["elpd_se"],
                "elpd_mcse": s["elpd_mcse"],
                "delta": vp.get("delta_elpd"),
                "delta_se": vp.get("delta_elpd_se"),
                "paired_rows": vp.get("paired_rows"),
                "max_rhat": r["diagnostics"]["max_rhat"],
                "min_ess": r["diagnostics"]["min_ess"],
                "passes": r["diagnostics"]["passes"],
                "fit_seconds": r["seconds"]["fit_total"],
                "sampling_seconds": r["seconds"].get("sampling"),
                "cost_usd": r.get("cost_usd"),
                "_dir": str(r["_dir"]),
            }
            if r["name"] in rescores:
                rs = rescores[r["name"]]
                e["splits"][split]["rescore"] = {
                    "commit": rs["commit"],
                    "draws": rs["draws"],
                    "exact_minus_approximate": rs["exact_minus_approximate"],
                    "exact_recorded_equivalent": rs["exact_recorded_equivalent"][
                        "delta_elpd"
                    ],
                    "exact_kept_draws": rs["exact"].get("vs_promoted", {}),
                }
            g_max, g_pass, g_method = group_gate(r)
            e["splits"][split]["group_rhat_max"] = g_max
            e["splits"][split]["group_rhat_method"] = g_method
            e["splits"][split]["passes"] = bool(r["diagnostics"]["passes"] and g_pass)
            passes &= e["splits"][split]["passes"]
            fit_seconds.append(r["seconds"]["fit_total"])
            cost.append(r.get("cost_usd") or 0.0)
        e["passes_checks"] = passes
        e["line"] = "frontier"
        e["grade"] = "full" if passes else "failed"
        e["fit_seconds"] = max(fit_seconds)
        e["cost_usd"] = max(cost)
        entries.append(e)
    entries += screen_entries()

    eligible = [
        e
        for e in entries
        if e["passes_checks"] and e["interpretable"] and "rows" in e["splits"]
    ]
    eligible.sort(key=lambda e: -e["splits"]["rows"]["delta"])
    best = None
    for e in eligible:
        if best is None:
            best = e
            continue
        d, se = paired(
            Path(e["splits"]["rows"]["_dir"]), Path(best["splits"]["rows"]["_dir"])
        )
        if d > 2 * se:
            best = e
        elif abs(d) <= 2 * se and "units" in e["splits"] and "units" in best["splits"]:
            du, seu = paired(
                Path(e["splits"]["units"]["_dir"]),
                Path(best["splits"]["units"]["_dir"]),
            )
            if du > 2 * seu or (
                abs(du) <= 2 * seu and e["fit_seconds"] < best["fit_seconds"]
            ):
                best = e

    def point(e):
        # Ben's axes: accuracy (row-split dELPD) against fit time.
        return (e["splits"]["rows"]["delta"], -e["fit_seconds"])

    candidates = [e for e in entries if e["passes_checks"] and "rows" in e["splits"]]
    ref_point = (0.0, -PROMOTED["fit_seconds"])
    for e in entries:
        e["current_best"] = e is best
        if e not in candidates:
            e["frontier"] = False
            continue
        p = point(e)
        others = [point(o) for o in candidates if o is not e] + [ref_point]
        e["frontier"] = not any(
            all(o[i] >= p[i] for i in range(len(p))) and o != p for o in others
        )
    # What supersedes each entry: the current best (if it beats it on the
    # paired row split), otherwise a later run of the same design that passes.
    for e in entries:
        note = ""
        if e.get("grade") == "screen":
            worst = max(s["max_rhat"] for s in e["splits"].values())
            note = f"screen-grade (max R-hat {worst:.3f}); not eligible for best or frontier"
            if any(s["delta"] is None for s in e["splits"].values()):
                note += "; held-out rows differ from the reference, so not paired"
        elif best is not None and e is not best and "rows" in e["splits"]:
            d, se = paired(
                Path(best["splits"]["rows"]["_dir"]), Path(e["splits"]["rows"]["_dir"])
            )
            if d > 2 * se:
                note = f"beaten by {best['id']} ({d:+.1f} ± {se:.1f} rows)"
            elif not e["passes_checks"]:
                same = [
                    o
                    for o in entries
                    if o is not e
                    and o["passes_checks"]
                    and o["model"]["name"] == e["model"]["name"]
                    and o["feature_set"] == e["feature_set"]
                ]
                note = (
                    f"superseded by passing rerun {same[0]['id']}"
                    if same
                    else "fails the convergence gate"
                )
        e["note"] = note
        e["annotations"] = list(annotations["entries"].get(e["id"], []))
        for split, sp in e["splits"].items():
            if "rescore" in sp:
                rs = rescores[sp["run"]]
                e["annotations"].append(rescore_text(split, rs))
    for e in entries:
        for s in e["splits"].values():
            s.pop("_dir", None)
    return {
        "promoted": PROMOTED,
        "footer": annotations["footer"],
        "entries": entries,
        "current_best": best["id"] if best else None,
    }


def fmt(x, digits=1):
    return "—" if x is None else f"{x:,.{digits}f}"


def markdown(board) -> str:
    lines = [
        "# Model leaderboard (both lines)",
        "",
        "Generated by `python -m rentfrontier.leaderboard` from recorded frontier runs and PyMC NUTS screens; machine-readable copy in `leaderboard.json`.",
        "ΔELPD is paired against the promoted model on identical held-out rows (log-rent density), with its standard error; differing row sets are refused.",
        "",
        "**Ranking.** Only entries that pass the convergence gate (max split R-hat < 1.01 and min bulk ESS > 400; frontier runs also need",
        "max R-hat < 1.05 over every building, walk, slope and unit effect, or 1.1 when recomputed from older runs' kept draws; PyMC screens",
        "report R-hat over every parameter) and the interpretability requirement are eligible. Rank by row-split ΔELPD. When two entries",
        "differ by less than two paired standard errors on the row split, the unit split decides. **Frontier** = not beaten on row-split",
        "ΔELPD and fit time at once (accuracy against complexity). PyMC screens that fail the gate are **screen-grade**: shown for",
        "comparison, never best or on the frontier.",
        "",
        "| Entry | Line | Design | Features | Rows ΔELPD | Units ΔELPD | Units ELPD | R-hat / ESS | Fit time | Cost | Hardware | Grade | Interp. | Best | Frontier | Note |",
        "|---|---|---|---|---:|---:|---:|---|---:|---:|---|---|---|---|---|---|",
    ]
    p = PROMOTED
    lines.append(
        f"| promoted (reference) | pymc | {p['description']} | own | 0 (ELPD {fmt(p['rows']['elpd'])}) | 0 | {fmt(p['units']['elpd'])} | passes | {fmt(p['fit_seconds'] / 60, 0)} min* | ${p['cost_usd']:.2f}* | {p['hardware']} | reference | yes | — | reference | |"
    )
    ordered = sorted(
        board["entries"],
        key=lambda e: -(e["splits"].get("rows", {}).get("delta") or -1e9),
    )
    marks = {}
    for e in ordered:
        if e.get("annotations"):
            marks[e["id"]] = f"[{len(marks) + 1}]"
    for e in ordered:
        r = e["splits"].get("rows", {})
        u = e["splits"].get("units", {})
        diag = "; ".join(
            f"{k}: {v['max_rhat']:.3f} / {v['min_ess']:.0f} / all-effects {v['group_rhat_max']:.2f}"
            for k, v in e["splits"].items()
        )
        lines.append(
            f"| `{e['id']}` | {e['line']} | {e['model']['name']} | {e['feature_set']} | {fmt(r.get('delta'))} ± {fmt(r.get('delta_se'))} | "
            f"{fmt(u.get('delta'))}{' ± ' + fmt(u.get('delta_se')) if u.get('delta') is not None else ''} | {fmt(u.get('elpd'))} | {diag} | "
            f"{fmt(e['fit_seconds'], 0)} s | ${e['cost_usd']:.2f} | {e['hardware']} | {e['grade']} | "
            f"{'yes' if e['interpretable'] else 'no'} | {'**best**' if e['current_best'] else ''} | {'yes' if e['frontier'] else ''} | {'; '.join(x for x in (e['note'], ('see ' + marks[e['id']]) if e['id'] in marks else '') if x)} |"
        )
    if marks:
        lines += [
            "",
            "**Annotations** (context only; scores, ranking and frontier use the recorded runs):",
            "",
        ]
        for e in ordered:
            if e["id"] in marks:
                lines.append(f"- {marks[e['id']]} `{e['id']}`:")
                lines += [f"  - {t}" for t in e["annotations"]]
    lines += [
        "",
        f"\\* {p['fit_seconds_note']}; cost is {p['cost_note']}.",
        "",
        "Fit time is the sampler wall time (frontier: warmup + draws, including JIT compilation; PyMC screens: the screen's recorded seconds).",
        "Fit times compare well within a line but only roughly across lines: PyMC screens are 4 chains x 1,000/1,000 on 90% of rows,",
        "while frontier runs are production-length (e.g. 16 chains x 2,000). Cost is per fit (the larger of a design's two split runs).",
        "The current best can sit off the frontier: the unit split breaks row-split ties for best, but the frontier uses row ΔELPD and time only.",
        "Cost is the Modal list-price estimate for runs made there (Modal use stopped on 2026-09-24; local runs record $0).",
        "Runs named `dev-*` or `canary-*` are pipeline checks and are not listed.",
        *board.get("footer", []),
        "",
    ]
    return "\n".join(lines)


def main():
    board = build()
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "leaderboard.json").write_text(json.dumps(board, indent=2, default=str))
    (DOCS / "leaderboard.md").write_text(markdown(board))
    print(markdown(board))


if __name__ == "__main__":
    main()
