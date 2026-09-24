"""Build the leaderboard from recorded runs.

    python -m rentfrontier.leaderboard

Reads every reportable run under /data1/apartments/frontier/runs, groups the
row-split and unit-split runs of the same design (commit, model, feature set,
sampler), and writes docs/model/gpu-frontier/leaderboard.{json,md}.

Ranking rule. Entries must pass the convergence gate and the
interpretability requirement. They are ranked by row-split dELPD against the
promoted model. When two entries' paired row-split difference is within two
standard errors, the unit split decides: it scores every listing of unseen
units, so it tests whether the named feature terms carry over rather than
being absorbed by unit effects, which is what an interpretable coefficient
claims. If neither split separates them, the faster entry ranks first.

Frontier. An entry is on the frontier if no other entry is at least as good
on row-split dELPD, unit-split dELPD, fit time and cost, and strictly better
on one.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import data
from .run import REFERENCES

RUNS = data.OUTPUT_ROOT / "runs"
DOCS = Path(__file__).resolve().parents[3] / "docs" / "model" / "gpu-frontier"

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


def design_key(r):
    return (
        r["commit"],
        r["model"]["name"],
        r["feature_set"],
        r["sampler"],
        json.dumps(r["sampler_settings"], sort_keys=True),
    )


def paired(a_dir: Path, b_dir: Path):
    """Paired sum and SE of lpd differences a - b on shared held-out rows."""
    a = np.load(a_dir / "heldout.npz", allow_pickle=True)
    b = np.load(b_dir / "heldout.npz", allow_pickle=True)
    bl = dict(zip(b["audit_id"].tolist(), b["lpd"]))
    d = np.array(
        [x - bl[k] for k, x in zip(a["audit_id"].tolist(), a["lpd"]) if k in bl]
    )
    return float(d.sum()), float(d.std(ddof=1) * math.sqrt(len(d)))


def build():
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
            passes &= r["diagnostics"]["passes"]
            fit_seconds.append(r["seconds"]["fit_total"])
            cost.append(r.get("cost_usd") or 0.0)
        e["passes_checks"] = passes
        e["fit_seconds"] = max(fit_seconds)
        e["cost_usd"] = max(cost)
        entries.append(e)

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
        # Quality on both splits (a missing split counts as worst), speed, cost.
        unit = e["splits"].get("units", {}).get("delta")
        return (
            e["splits"]["rows"]["delta"],
            unit if unit is not None else -np.inf,
            -e["fit_seconds"],
            -e["cost_usd"],
        )

    candidates = [e for e in entries if e["passes_checks"] and "rows" in e["splits"]]
    ref_point = (0.0, 0.0, -PROMOTED["fit_seconds"], -PROMOTED["cost_usd"])
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
        if best is not None and e is not best and "rows" in e["splits"]:
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
    for e in entries:
        for s in e["splits"].values():
            s.pop("_dir", None)
    return {
        "promoted": PROMOTED,
        "entries": entries,
        "current_best": best["id"] if best else None,
    }


def fmt(x, digits=1):
    return "—" if x is None else f"{x:,.{digits}f}"


def markdown(board) -> str:
    lines = [
        "# GPU-frontier leaderboard",
        "",
        "Generated by `python -m rentfrontier.leaderboard` from recorded runs; machine-readable copy in `leaderboard.json`.",
        "ΔELPD is paired against the promoted model on identical held-out rows (log-rent density), with its standard error.",
        "",
        "**Ranking.** Only entries that pass the convergence gate (max split R-hat < 1.01, min bulk ESS > 400) and the",
        "interpretability requirement are eligible. Rank by row-split ΔELPD. When two entries differ by less than two paired",
        "standard errors on the row split, the unit split decides, because it tests whether named feature terms carry over to",
        "unseen units instead of being absorbed by unit effects. **Frontier** = not beaten on row-split ΔELPD, unit-split ΔELPD, fit time and cost at once.",
        "",
        "| Entry | Design | Features | Rows ΔELPD | Units ΔELPD | Units ELPD | R-hat / ESS | Fit time | Cost | Hardware | Checks | Interp. | Best | Frontier | Note |",
        "|---|---|---|---:|---:|---:|---|---:|---:|---|---|---|---|---|---|",
    ]
    p = PROMOTED
    lines.append(
        f"| promoted (reference) | {p['description']} | own | 0 (ELPD {fmt(p['rows']['elpd'])}) | 0 | {fmt(p['units']['elpd'])} | passes | {fmt(p['fit_seconds'] / 60, 0)} min* | ${p['cost_usd']:.2f}* | {p['hardware']} | yes | yes | — | reference | |"
    )
    for e in sorted(
        board["entries"],
        key=lambda e: -(e["splits"].get("rows", {}).get("delta") or -1e9),
    ):
        r = e["splits"].get("rows", {})
        u = e["splits"].get("units", {})
        diag = "; ".join(
            f"{k}: {v['max_rhat']:.3f} / {v['min_ess']:.0f}"
            for k, v in e["splits"].items()
        )
        lines.append(
            f"| `{e['id']}` | {e['model']['name']} | {e['feature_set']} | {fmt(r.get('delta'))} ± {fmt(r.get('delta_se'))} | "
            f"{fmt(u.get('delta'))}{' ± ' + fmt(u.get('delta_se')) if u.get('delta') is not None else ''} | {fmt(u.get('elpd'))} | {diag} | "
            f"{fmt(e['fit_seconds'], 0)} s | ${e['cost_usd']:.2f} | {e['hardware']} | {'pass' if e['passes_checks'] else 'fail'} | "
            f"{'yes' if e['interpretable'] else 'no'} | {'**best**' if e['current_best'] else ''} | {'yes' if e['frontier'] else ''} | {e['note']} |"
        )
    lines += [
        "",
        f"\\* {p['fit_seconds_note']}; cost is {p['cost_note']}.",
        "",
        "Fit time is the sampler wall time (warmup + draws, including JIT compilation); cost is the Modal list price over the client-side container lifetime.",
        "Runs named `dev-*` or `canary-*` are pipeline checks and are not listed.",
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
