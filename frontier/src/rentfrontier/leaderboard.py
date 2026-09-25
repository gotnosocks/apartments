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

Primary score (since 2026-09-24): integrated PSIS-LOO over the row split's
47,374 training rows (`rentfrontier.loo`), paired row by row against the
baseline entry (BASELINE). Its uncertainty combines the paired standard error
with both runs' Monte Carlo errors. Held-out dELPD against the promoted PyMC
model (5,264 row-split held-out rows) and the unit split are validation and
secondary columns.

Ranking rule. Eligible entries pass the convergence gate, are
interpretable and have a PSIS-LOO score. The top entry has the highest
PSIS-LOO dELPD; every eligible entry within two combined standard errors of
it ties, and the fastest tied entry is the current best (Ben's axes are
accuracy and fit time). PyMC screens that fail the gate are screen-grade:
shown, never best or on the frontier; screens without saved draws have no
PSIS-LOO score.

Frontier. An entry is on the frontier if no other eligible entry is at
least as good on PSIS-LOO dELPD and fit time and strictly better on one.
Fit time is the scored (row-split) fit's wall time; unit-split fits are
optional and not counted.
"""

from __future__ import annotations

import functools
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from . import data
from .run import REFERENCES, git

RUNS = data.OUTPUT_ROOT / "runs"
RESCORES = data.OUTPUT_ROOT / "rescores"
LOO_ROOT = data.OUTPUT_ROOT / "loo"
VARIANCE_ROOT = data.OUTPUT_ROOT / "variance"
# PSIS-LOO dELPD is paired against this entry (the plainest gate-passing design).
BASELINE = "m0-base/base-v1/gibbs@5cc0809"
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


@functools.cache
def commit_time(commit: str) -> int:
    """Committer time of a scoring commit; 0 when this repository lacks it."""
    if not commit:
        return 0
    try:
        return int(git("show", "-s", "--format=%ct", commit))
    except (subprocess.CalledProcessError, ValueError):
        return 0


def latest_records(root: Path) -> dict:
    """The newest reportable record per source run under root/*/result.json.

    Newest means scored by the most recent commit (committer time), then the
    newest file. A re-score with older code, or a copy that loses file times,
    does not displace a record from newer code.
    """
    rows = []
    for path in root.glob("*/result.json"):
        r = json.loads(path.read_text())
        if not r.get("dirty"):
            r["_dir"] = str(path.parent)
            rows.append((commit_time(r.get("commit", "")), path.stat().st_mtime, r))
    return {r["source_run"]: r for *_, r in sorted(rows, key=lambda t: t[:2])}


def load_loo():
    """Latest reportable PSIS-LOO record per source run name."""
    return latest_records(LOO_ROOT)


def load_variance():
    """Latest reportable variance decomposition per source run name."""
    return latest_records(VARIANCE_ROOT)


def paired_loo(a_dir, b_dir):
    """Paired PSIS-LOO difference a - b on identical training rows:
    (sum, SE, combined Monte Carlo error)."""
    a = np.load(Path(a_dir) / "pointwise.npz", allow_pickle=True)
    b = np.load(Path(b_dir) / "pointwise.npz", allow_pickle=True)
    for x, folder in ((a, a_dir), (b, b_dir)):
        if len(set(x["audit_id"].tolist())) != len(x["audit_id"]):
            raise ValueError(f"Duplicate training audit IDs in {Path(folder).name}")
    ai = dict(zip(a["audit_id"].tolist(), range(len(a["audit_id"]))))
    bi = dict(zip(b["audit_id"].tolist(), range(len(b["audit_id"]))))
    if ai.keys() != bi.keys():
        raise ValueError(
            f"Training rows differ: {Path(a_dir).name} ({len(ai)}) vs {Path(b_dir).name} ({len(bi)})"
        )
    keys = list(ai)
    ia = np.array([ai[k] for k in keys])
    ib = np.array([bi[k] for k in keys])
    d = a["elpd_loo"][ia] - b["elpd_loo"][ib]
    mc = math.sqrt(float(np.sum(a["mcse"] ** 2) + np.sum(b["mcse"] ** 2)))
    return float(d.sum()), float(d.std(ddof=1) * math.sqrt(len(d))), mc


def tie_tolerance(se, mcse):
    return 2.0 * math.hypot(se, mcse)


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


def hardware_class(r) -> str:
    """Where a frontier run's fit actually ran: the JAX device, not just the host's GPU."""
    remote = r.get("remote") or {}
    hw = r.get("hardware") or {}
    on_gpu = any("cuda" in d or "gpu" in d for d in hw.get("jax_devices", []))
    if remote:
        gpu = (remote.get("gpu_reported") or hw.get("gpu") or "").split(",")[0]
        return "Modal " + short_gpu(gpu) if on_gpu else "Modal CPU"
    if on_gpu:
        return "thelio " + short_gpu(hw.get("gpu") or "GPU")
    return "thelio CPU (" + short_cpu(hw.get("cpu") or "CPU") + ")"


def short_gpu(name: str) -> str:
    for token in ("H100", "H200", "A100", "L4", "T4", "RTX 2060 SUPER"):
        if token in name:
            return token
    return name.replace("NVIDIA ", "").replace("GeForce ", "")


def short_cpu(name: str) -> str:
    return name.replace("AMD ", "").replace(" 6-Core Processor", "").strip()


# Local PyMC screens record no hardware; they ran on thelio's CPU.
THELIO_CPU = "thelio CPU (Ryzen 5 3600X)"


def design_key(r):
    return (
        hardware_class(r),
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
                else THELIO_CPU
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
        rows_split = by_split.get("rows")
        e["fit_seconds"] = rows_split[1]["seconds"] if rows_split else max(seconds)
        e["fit_seconds_all_splits"] = sum(seconds)
        e["cost_usd"] = max(cost)
        entries.append(e)
    return entries


def scored_raw(e):
    return bool(e.get("psis"))


def scored(e):
    return (e.get("psis") or {}).get("delta") is not None


def choose_best(entries, paired=paired_loo):
    """The fastest eligible entry tied (within two combined SE) with the top
    PSIS-LOO dELPD. Entries need ``psis["_dir"]``; ``paired`` can be a cached
    equivalent of `paired_loo`."""
    eligible = [
        e for e in entries if e["passes_checks"] and e["interpretable"] and scored(e)
    ]
    if not eligible:
        return None
    top = max(eligible, key=lambda e: e["psis"]["delta"])
    tied = []
    for e in eligible:
        if e is top:
            tied.append(e)
            continue
        d, se, mc = paired(e["psis"]["_dir"], top["psis"]["_dir"])
        if abs(d) <= tie_tolerance(se, mc):
            tied.append(e)
    return min(tied, key=lambda e: (e["fit_seconds"], -e["psis"]["delta"]))


def on_frontier(entries):
    """Per entry: not dominated on (PSIS-LOO dELPD, fit time) by another
    eligible entry."""

    def point(e):
        return (e["psis"]["delta"], -e["fit_seconds"])

    candidates = [
        e for e in entries if e["passes_checks"] and e["interpretable"] and scored(e)
    ]
    flags = []
    for e in entries:
        if not any(e is c for c in candidates):
            flags.append(False)
            continue
        p = point(e)
        others = [point(o) for o in candidates if o is not e]
        flags.append(
            not any(all(o[i] >= p[i] for i in range(len(p))) and o != p for o in others)
        )
    return flags


def group_runs(runs):
    """A design's split runs as one entry, keyed by design_key.

    The row split (the scored fit) sets the entry's hardware; a secondary
    split that ran on other hardware joins the same design's row-split entry
    instead of forming an entry of its own."""
    groups = {}
    for r in runs:
        if r["split"] == "rows":
            groups.setdefault(design_key(r), {})["rows"] = r
    for r in runs:
        if r["split"] == "rows":
            continue
        key = design_key(r)
        if key not in groups:
            same = [k for k in groups if k[1:] == key[1:]]
            key = same[0] if same else key
        groups.setdefault(key, {})[r["split"]] = r
    return groups


def build(keep_dirs=False):
    rescores = load_rescores()
    loos = load_loo()
    variances = load_variance()
    annotations = load_annotations()
    groups = group_runs(load_runs())
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
            "hardware": hardware_class(any_run),
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
                # NUTS runs count divergences; Gibbs has none.
                "divergences": r["diagnostics"].get("divergences"),
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
        e["split_hardware"] = {k: hardware_class(r) for k, r in by_split.items()}
        # Run records carry their sampler's line (numpyro for NUTS, and the
        # removed PyMC ladder's pymc); older Gibbs records have none.
        e["line"] = any_run.get("line", "frontier")
        e["grade"] = "full" if passes else "failed"
        # Fit time is the scored (row-split) fit's; unit-split fits are optional.
        rows_run = by_split.get("rows")
        e["fit_seconds"] = (
            rows_run["seconds"]["fit_total"] if rows_run else max(fit_seconds)
        )
        e["fit_seconds_all_splits"] = sum(fit_seconds)
        e["cost_usd"] = max(cost)
        # Other processes' mean busy cores during the scored fit (recorded
        # from 3c26c4a on); None when not measured.
        e["contention"] = (rows_run or {}).get("contention")
        if rows_run and rows_run["name"] in variances:
            vr = variances[rows_run["name"]]
            e["variance"] = {
                "commit": vr["commit"],
                "shares": {k: v["mean"] for k, v in vr["shares"].items()},
                "intervals": vr["shares"],
            }
        if rows_run and rows_run["name"] in loos:
            lr = loos[rows_run["name"]]
            e["psis"] = {
                "run": rows_run["name"],
                "commit": lr["commit"],
                "rows": lr["rows"],
                "draws": lr["draws"],
                "elpd": lr["elpd_loo"],
                "elpd_se": lr["elpd_loo_se"],
                "mcse": lr["elpd_loo_mcse"],
                "pareto_k": lr["pareto_k"],
                "validation": lr["validation"],
                "integrated": lr["integrated"],
                "_dir": lr["_dir"],
            }
        entries.append(e)
    entries += screen_entries()
    base = next((e for e in entries if e["id"] == BASELINE and scored_raw(e)), None)
    for e in entries:
        if e.get("psis") and base is not None:
            if e is base:
                d, se, mc = 0.0, 0.0, 0.0
            else:
                d, se, mc = paired_loo(e["psis"]["_dir"], base["psis"]["_dir"])
            e["psis"].update(delta=d, delta_se=se, delta_mcse=mc, baseline=BASELINE)

    # The frontier and the best are per hardware class: a fit time only
    # competes with fit times on the same hardware.
    for e in entries:
        e.setdefault("hardware_class", e["hardware"])
    best_by_class = {}
    for cls in sorted({e["hardware_class"] for e in entries}):
        group = [e for e in entries if e["hardware_class"] == cls]
        best_by_class[cls] = choose_best(group)
        for e, on in zip(group, on_frontier(group)):
            e["frontier"] = on
    for e in entries:
        e["current_best"] = e is best_by_class[e["hardware_class"]]
    # What supersedes each entry: the current best (if it beats it on the
    # paired row split), otherwise a later run of the same design that passes.
    for e in entries:
        best = best_by_class[e["hardware_class"]]
        note = ""
        if e.get("grade") == "screen":
            worst = max(s["max_rhat"] for s in e["splits"].values())
            note = f"screen-grade (max R-hat {worst:.3f}); not eligible for best or frontier"
            if any(s["delta"] is None for s in e["splits"].values()):
                note += "; held-out rows differ from the reference, so not paired"
        elif not scored(e) and e["line"] != "pymc" and "rows" in e["splits"]:
            note = "no PSIS-LOO score yet"
        elif best is not None and e is not best and scored(e):
            d, se, mc = paired_loo(best["psis"]["_dir"], e["psis"]["_dir"])
            if d > tie_tolerance(se, mc):
                note = f"beaten on {e['hardware_class']} by {best['id']} ({d:+.1f} ± {math.hypot(se, mc):.1f} PSIS-LOO)"
            elif not e["passes_checks"]:
                same = [
                    o
                    for o in entries
                    if o is not e
                    and o["passes_checks"]
                    and o["model"]["name"] == e["model"]["name"]
                    and o["feature_set"] == e["feature_set"]
                    and o["sampler"] == e["sampler"]
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
        if e.get("grade") == "screen" or (e["line"] == "pymc" and not scored(e)):
            e["note"] = "; ".join(
                x for x in (e["note"], "no saved draws, so no PSIS-LOO score") if x
            )
        for s in e["splits"].values():
            if not keep_dirs:
                s.pop("_dir", None)
        if e.get("psis") and not keep_dirs:
            e["psis"].pop("_dir", None)
    return {
        "promoted": PROMOTED,
        "baseline": BASELINE,
        "footer": annotations["footer"],
        "entries": entries,
        "current_best": {c: (b["id"] if b else None) for c, b in best_by_class.items()},
    }


def fmt(x, digits=1):
    return "—" if x is None else f"{x:,.{digits}f}"


def row(e, marks) -> str:
    r = e["splits"].get("rows", {})
    u = e["splits"].get("units", {})
    ps = e.get("psis") or {}
    if ps.get("delta") is not None:
        psis = (
            f"{fmt(ps['delta'])} ± {fmt(math.hypot(ps['delta_se'], ps['delta_mcse']))}"
        )
        kshare = f"{100 * ps['pareto_k']['share_over_threshold']:.1f}%"
    else:
        psis, kshare = "—", "—"
    var = e.get("variance")
    shares = (
        " / ".join(
            f"{100 * var['shares'][g]:.0f}%"
            for g in ("features", "building", "unit", "residual")
        )
        if var
        else "—"
    )
    diag = "; ".join(
        f"{k}: {v['max_rhat']:.3f} / {v['min_ess']:.0f} / all-effects {v['group_rhat_max']:.2f}"
        + (
            f" / {v['divergences']} divergence{'s' if v['divergences'] > 1 else ''}"
            if v.get("divergences")
            else ""
        )
        for k, v in e["splits"].items()
    )
    note = "; ".join(
        x
        for x in (e["note"], ("see " + marks[e["id"]]) if e["id"] in marks else "")
        if x
    )
    return (
        f"| `{e['id']}` | {e['line']} | {e['model']['name']} | {e['feature_set']} | {psis} | {kshare} | "
        f"{fmt(r.get('delta'))}{' ± ' + fmt(r.get('delta_se')) if r.get('delta') is not None else ''} | "
        f"{fmt(u.get('delta'))}{' ± ' + fmt(u.get('delta_se')) if u.get('delta') is not None else ''} | {shares} | {diag} | "
        f"{fmt(e['fit_seconds'], 0)} s | {e['grade']} | "
        f"{'**best**' if e['current_best'] else ''} | {'yes' if e['frontier'] else ''} | {note} |"
    )


def markdown(board) -> str:
    base = board.get("baseline", BASELINE)
    lines = [
        "# Model leaderboard (both lines)",
        "",
        "Generated by `python -m rentfrontier.leaderboard` from recorded frontier runs and PyMC NUTS screens; machine-readable copy in `leaderboard.json`.",
        "The plan behind it is [docs/research-plan.md](../../research-plan.md).",
        "",
        f"**Primary score: PSIS-LOO ΔELPD** over the row split's 47,374 training rows (log-rent density, unit effects integrated exactly per row; `rentfrontier.loo`), paired row by row against `{base}`.",
        "± is the paired standard error combined with both runs' Monte Carlo errors. *k* is the share of rows whose Pareto k exceeds the draw-count threshold (reliability).",
        "**Held-out** ΔELPD (5,264 row-split held-out rows, vs the promoted PyMC model) is the independent validation; the unit split is secondary.",
        "",
        "**Ranking.** Eligible entries pass the convergence gate (max split R-hat < 1.01 and min bulk ESS > 400; frontier runs also need",
        "R-hat < 1.05 over every group effect, 1.1 when recomputed from older runs' kept draws; NUTS runs also need no divergences), are interpretable and have a PSIS-LOO score.",
        "Every eligible entry within two combined SE of the top PSIS-LOO ΔELPD ties with it; the **best** is the fastest tied entry.",
        "**Frontier** = not beaten on PSIS-LOO ΔELPD and fit time at once. Fit time is the scored (row-split) fit's sampler wall time.",
        "**Per hardware.** The frontier and the best are computed separately for each hardware class (where the fit actually ran):",
        "a fit time only competes with fit times on the same hardware.",
        "**Variance** = share of the variation in log rent over the training rows attributed to features / building level / unit effects / residual",
        "(covariance attribution per draw, `rentfrontier.variance`; market and time, building-over-time and building-slope shares are in `leaderboard.json`).",
        "",
    ]
    p = PROMOTED

    def key(e):
        ps = e.get("psis") or {}
        if ps.get("delta") is not None:
            return (0, -ps["delta"])
        return (1, -(e["splits"].get("rows", {}).get("delta") or -1e9))

    marks = {}
    for e in sorted(board["entries"], key=key):
        if e.get("annotations"):
            marks[e["id"]] = f"[{len(marks) + 1}]"
    ordered = []

    def cls_of(e):
        return e.get("hardware_class", e["hardware"])

    classes = sorted({cls_of(e) for e in board["entries"]})
    for cls in classes:
        group = sorted([e for e in board["entries"] if cls_of(e) == cls], key=key)
        ordered += group
        lines += [
            "",
            f"### {cls}",
            "",
            "| Entry | Line | Design | Features | PSIS-LOO ΔELPD | k | Held-out ΔELPD | Units ΔELPD | Variance: features / building / unit / residual | R-hat / ESS | Fit time | Grade | Best | Frontier | Note |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---|---|---|---|",
        ]
        for e in group:
            lines.append(row(e, marks))
    lines += [
        "",
        "### Validation reference",
        "",
        f"`promoted`: {p['description']}. Held-out ΔELPD 0 by definition (rows ELPD {fmt(p['rows']['elpd'])}); full production fit {fmt(p['fit_seconds'] / 60, 0)} min* on {p['hardware']}. No saved row-split draws, so no PSIS-LOO score yet.",
    ]
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
        "Fit time is the sampler wall time of the scored fit (frontier: warmup + draws, including JIT compilation; PyMC screens: the screen's recorded seconds)",
        "on the hardware in its column; times compare well within a line and hardware, only roughly across them.",
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
