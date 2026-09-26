"""Run one fit on one held-out split and record everything needed to report it.

    python -m rentfrontier.run --split rows --features base-v1 --model m0-base \
        --sampler gibbs --name <run-name>

Refuses to start on a dirty working tree unless --dev is given; dev runs are
marked not reportable. Outputs go to /data1/apartments/frontier/runs/<name>/:

- result.json   provenance, settings, hardware, timings, diagnostics, scores
- heldout.npz   audit_id, per-row lpd (pooled and per chain)
- posterior.npz posterior means/sds of named effects, kept joint draws, traces
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import time
from pathlib import Path

import numpy as np

from . import data, features, splits

RUNS = data.OUTPUT_ROOT / "runs"
REFERENCE_ROOT = Path(
    os.environ.get(
        "FRONTIER_REFERENCE_ROOT",
        "/home/ben/code/apartments/data/model/feature-screen-20260923",
    )
)
REFERENCES = {
    "rows": REFERENCE_ROOT / "nuts-hwalk/heldout.npz",
    "units": REFERENCE_ROOT / "nuts-hwalk-units/heldout.npz",
}


def git(*args) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def cpu_clock():
    """(machine busy CPU seconds, this process's CPU seconds, wall seconds) now."""
    with open("/proc/stat") as f:
        user, nice, system, _idle, _iowait, irq, softirq, steal = (
            int(x) for x in f.readline().split()[1:9]
        )
    busy = (user + nice + system + irq + softirq + steal) / os.sysconf("SC_CLK_TCK")
    t = os.times()
    own = t.user + t.system + t.children_user + t.children_system
    return busy, own, time.perf_counter()


def contention(start) -> dict:
    """What else used the machine while a fit ran, since `start = cpu_clock()`.

    other_cores is the mean number of cores busy with other processes over the
    fit's wall time; a timing is clean when it is near zero. GPU compute
    processes other than this one are listed as seen at the end.
    """
    busy0, own0, wall0 = start
    busy1, own1, wall1 = cpu_clock()
    wall = wall1 - wall0
    other = max(0.0, (busy1 - busy0) - (own1 - own0))
    out = {
        "wall_seconds": wall,
        "own_cpu_seconds": own1 - own0,
        "other_cpu_seconds": other,
        "other_cores": other / wall if wall > 0 else 0.0,
        "cpus": os.cpu_count(),
    }
    try:
        pids = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        out["gpu_other_pids"] = [int(p) for p in pids if int(p) != os.getpid()]
    except (OSError, ValueError):
        pass
    return out


def hardware() -> dict:
    import jax

    info = {
        "platform": platform.platform(),
        "jax_devices": [str(d) for d in jax.devices()],
    }
    try:
        with open("/proc/cpuinfo") as f:
            info["cpu"] = next(
                line.split(":", 1)[1].strip()
                for line in f
                if line.startswith("model name")
            )
    except (OSError, StopIteration):
        pass
    try:
        info["gpu"] = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        pass
    return info


def split_rhat(x):
    """Split R-hat over axis 1 (draws) for x of shape (chains, draws)."""
    _, n = x.shape
    half = n // 2
    x = np.concatenate([x[:, :half], x[:, half : 2 * half]], axis=0)
    _, n = x.shape
    means = x.mean(axis=1)
    within = x.var(axis=1, ddof=1).mean()
    between = n * means.var(ddof=1)
    var = (n - 1) / n * within + between / n
    return float(np.sqrt(var / within)) if within > 0 else float("nan")


def ess(x):
    """Bulk ESS (Geyer initial monotone sequence, pooled over chains)."""
    import blackjax

    return float(blackjax.ess(np.asarray(x), chain_axis=0, sample_axis=1))


GROUP_RHAT_GATE = 1.05  # max over every element of every effect (tens of thousands)


def diagnostics(trace, names_beta, rhat_all=None) -> dict:
    from .collect import SCALARS

    quantities = {}
    for i, n in enumerate(SCALARS):
        quantities[n] = trace["scalars"][..., i]
    for i, n in enumerate(names_beta):
        quantities[f"beta[{n}]"] = trace["beta"][..., i]
    for i in range(trace["trend"].shape[-1]):
        quantities[f"trend[{12 * i}]"] = trace["trend"][..., i]
    for i in range(trace["fslope_scales"].shape[-1]):
        quantities[f"fslope_scale[{i}]"] = trace["fslope_scales"][..., i]
    for key in ("building", "unit"):
        for i in range(trace[key].shape[-1]):
            quantities[f"{key}[trace {i}]"] = trace[key][..., i]
    rows = {}
    for n, x in quantities.items():
        if np.ptp(x) == 0:
            continue
        rows[n] = {"rhat": split_rhat(x), "ess": ess(x)}
    worst_rhat = max(rows.items(), key=lambda kv: kv[1]["rhat"])
    worst_ess = min(rows.items(), key=lambda kv: kv[1]["ess"])
    return {
        "quantities": len(rows),
        "max_rhat": worst_rhat[1]["rhat"],
        "max_rhat_name": worst_rhat[0],
        "min_ess": worst_ess[1]["ess"],
        "min_ess_name": worst_ess[0],
        "scalars": {n: rows[n] for n in SCALARS if n in rows},
        "group_rhat": rhat_all,
        "group_rhat_max": max(
            (v["max"] for v in (rhat_all or {}).values()), default=None
        ),
        "passes": bool(
            worst_rhat[1]["rhat"] < 1.01
            and worst_ess[1]["ess"] > 400
            and all(v["max"] < GROUP_RHAT_GATE for v in (rhat_all or {}).values())
        ),
        "gate": "max split R-hat < 1.01 and min bulk ESS > 400 over scalars, coefficients, sampled trend points and 32+32 traced group effects; and max R-hat < 1.05 over every element of every effect (all buildings, walks, slopes, units)",
    }


def score(
    split: str, audit_id: np.ndarray, lpd: np.ndarray, lpd_chain: np.ndarray
) -> dict:
    n_chains = lpd_chain.shape[0]
    chain_elpd = lpd_chain.sum(axis=1)
    if len(lpd) == 0:
        return {"rows": 0, "note": "analysis fit on all rows; no held-out score"}
    out = {
        "rows": len(lpd),
        "elpd": float(lpd.sum()),
        "elpd_se": float(lpd.std(ddof=1) * math.sqrt(len(lpd))),
        # Monte Carlo error of the pooled ELPD from the spread of per-chain estimates.
        "elpd_mcse": float(chain_elpd.std(ddof=1) / math.sqrt(n_chains)),
    }
    ref_path = REFERENCES[split]
    if ref_path.exists():
        ref = np.load(ref_path, allow_pickle=True)
        ref_lpd = dict(zip(ref["audit_id"].tolist(), ref["lpd"]))
        mine = dict(zip(audit_id.tolist(), lpd))
        common = sorted(set(ref_lpd) & set(mine))
        d = np.array([mine[a] - ref_lpd[a] for a in common])
        out["vs_promoted"] = {
            "reference": str(ref_path),
            "paired_rows": len(common),
            "rows_only_here": len(mine) - len(common),
            "rows_only_reference": len(ref_lpd) - len(common),
            "delta_elpd": float(d.sum()),
            "delta_elpd_se": float(d.std(ddof=1) * math.sqrt(len(d))),
            "reference_elpd_on_paired_rows": float(sum(ref_lpd[a] for a in common)),
        }
    else:
        out["vs_promoted"] = {
            "reference": str(ref_path),
            "status": "reference not available yet",
        }
    return out


def feature_sources(feature_set: str) -> dict:
    """Input files behind a feature set, beyond the analytical dataset."""
    out = {}
    if feature_set.startswith("desc"):
        from . import descriptions

        out["descriptions"] = {
            "path": str(descriptions.SOURCE),
            "sha256": data.sha256(descriptions.SOURCE),
        }
    if feature_set in features.EXTERNAL:
        # Hash the files the features read, not the provenance's record of them.
        for name, path in (
            ("registry", features.REGISTRY_FILE),
            ("pluto", features.PLUTO_FILE),
        ):
            out[name] = {"path": path, "sha256": data.sha256(Path(path))}
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--split", choices=sorted(splits.SPLITS), required=True)
    parser.add_argument(
        "--features", default="base-v1", choices=sorted(features.FEATURE_SETS)
    )
    parser.add_argument(
        "--data-rules",
        help="comma-separated data rules (data.DATA_RULES), applied after the split",
    )
    parser.add_argument("--model", default="m0-base")
    parser.add_argument(
        "--sampler",
        choices=("nuts", "gibbs"),
        default="nuts",
        help="nuts: NumPyro NUTS; gibbs: the custom Gibbs sampler (deprecated)",
    )
    parser.add_argument(
        "--reproduce-deprecated",
        action="store_true",
        help="allow --sampler gibbs, only to reproduce an existing run record",
    )
    parser.add_argument("--chains", type=int)
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--draws", type=int)
    parser.add_argument("--keep-every", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--chain-batch", type=int, help="vectorise this many chains at a time"
    )
    parser.add_argument(
        "--solo-scales",
        help="Gibbs: comma-separated scales given 1-D collapsed updates ('none' for no solo updates)",
    )
    parser.add_argument(
        "--dense-globals",
        action="store_true",
        help="nuts: dense mass matrix over the global sites (NumPyro structured mass)",
    )
    parser.add_argument(
        "--float32", action="store_true", help="nuts: float32 arithmetic (GPU)"
    )
    parser.add_argument(
        "--init-radius",
        type=float,
        help="nuts: chains start uniformly within this radius (unconstrained; default 2)",
    )
    parser.add_argument(
        "--svi-steps",
        type=int,
        help="nuts: warm start (starting points and initial metric) from this many "
        "steps of NumPyro SVI with a mean-field normal guide",
    )
    parser.add_argument(
        "--svi-lr", type=float, help="nuts: Adam step size for --svi-steps"
    )
    parser.add_argument(
        "--coordinates",
        help="nuts: comma-separated sampling coordinates (trend_levels, season_zerosum, building_zerosum, building_totals, unit_totals, unit_partial, walk_levels, slope_totals)",
    )
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--dev", action="store_true", help="allow a dirty tree; run is not reportable"
    )
    args = parser.parse_args(argv)
    if args.sampler == "gibbs" and not args.reproduce_deprecated:
        raise SystemExit(
            "The custom Gibbs sampler is deprecated (2026-09-25) and not for new work; "
            "use --sampler nuts (--reproduce-deprecated only to reproduce an old run)."
        )

    # Remote workers get a clean export of a commit and no .git; the local
    # submitter checks the tree and passes the commit in FRONTIER_COMMIT.
    commit = os.environ.get("FRONTIER_COMMIT")
    dirty = "" if commit else git("status", "--porcelain")
    commit = commit or git("rev-parse", "HEAD")
    if dirty and not args.dev:
        raise SystemExit(
            f"Refusing to run on a dirty working tree (use --dev for unreportable runs):\n{dirty}"
        )
    out_dir = RUNS / args.name
    if (out_dir / "result.json").exists():
        raise SystemExit(f"{out_dir} already has a result; choose a new --name")

    import jax

    # Gibbs always runs in float64; NUTS too unless --float32.
    jax.config.update("jax_enable_x64", not (args.sampler == "nuts" and args.float32))
    from . import gibbs, model, nuts

    config = model.MODELS[args.model]
    started = time.time()
    t0 = time.perf_counter()
    frame = data.load()
    heldout = splits.SPLITS[args.split](frame)
    rules = tuple(args.data_rules.split(",")) if args.data_rules else ()
    frame = data.apply_rules(frame, rules)  # after the split: scored rows are fixed
    feats = features.build(args.features, frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    prep_seconds = time.perf_counter() - t0

    overrides = {
        k: v
        for k, v in {
            "chains": args.chains,
            "warmup": args.warmup,
            "draws": args.draws,
            "keep_every": args.keep_every,
            "seed": args.seed,
            "chain_batch": args.chain_batch,
            "dense_globals": True if args.dense_globals else None,
            "coordinates": tuple(args.coordinates.split(","))
            if args.coordinates
            else None,
            "float32": True if args.float32 else None,
            "init_radius": args.init_radius,
            "svi_steps": args.svi_steps,
            "svi_lr": args.svi_lr,
            "solo_scales": (
                () if args.solo_scales == "none" else tuple(args.solo_scales.split(","))
            )
            if args.solo_scales
            else None,
        }.items()
        if v is not None
    }
    module = gibbs if args.sampler == "gibbs" else nuts
    settings = module.Settings(**overrides)
    log_lines = []

    def log(msg):
        print(msg, flush=True)
        log_lines.append(msg)

    log(f"{args.name}: {args.split} split, {prep.sizes}")
    t0 = time.perf_counter()
    clock = cpu_clock()
    out = module.run(prep, config, settings, log=log)
    fit_seconds = time.perf_counter() - t0
    load = contention(clock)

    diag = diagnostics(out["trace"], feats.names, out.get("rhat_all"))
    if "divergent" in out["trace"]:  # NUTS: the gate also needs no divergences
        diag["divergences"] = int(np.asarray(out["trace"]["divergent"]).sum())
        diag["passes"] = diag["passes"] and diag["divergences"] == 0
    scores = score(args.split, prep.test_audit_id, out["lpd"], out["lpd_chain"])
    log(
        f"diagnostics: max R-hat {diag['max_rhat']:.4f} ({diag['max_rhat_name']}), min ESS {diag['min_ess']:.0f} ({diag['min_ess_name']})"
    )
    log(f"score: {json.dumps(scores)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / "heldout.npz",
        audit_id=prep.test_audit_id,
        lpd=out["lpd"],
        lpd_chain=out["lpd_chain"].astype(np.float32),
    )
    flat = {}
    for group in ("mean", "sd"):
        for k, v in out[group].items():
            flat[f"{group}/{k}"] = np.asarray(v)
    for k, v in out["kept"].items():
        flat[f"kept/{k}"] = np.asarray(v, np.float32)
    for k, v in out["trace"].items():
        flat[f"trace/{k}"] = np.asarray(v)
    flat["buildings"] = prep.buildings
    flat["units"] = prep.units
    flat["feature_names"] = np.asarray(feats.names)
    flat["feature_groups"] = np.asarray(feats.groups)
    np.savez_compressed(out_dir / "posterior.npz", **flat)

    result = {
        "name": args.name,
        "reportable": not dirty,
        "commit": commit,
        "dirty": bool(dirty),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "dataset": frame.attrs["dataset"],
        "dataset_observations_sha256": frame.attrs["source_sha256"],
        "split": args.split,
        "split_seed": splits.SEED,
        "feature_set": args.features,
        "data_rules": list(rules),
        "feature_sources": feature_sources(args.features),
        "model": config.to_dict(),
        "sampler": args.sampler,
        "line": "frontier" if args.sampler == "gibbs" else "numpyro",
        "deprecated_sampler": args.sampler == "gibbs",
        "sampler_settings": settings.to_dict(),
        "dtype": out.get("dtype"),
        "adapted": {
            k: out.get(k)
            for k in (
                "collapsed_proposal_sd",
                "noise_step_sd",
                "solo_proposal_sd",
                "noncentered",
                "step_size",
                "mean_tree_steps",
                "dense_sites",
                "svi",
            )
            if k in out
        },
        "sizes": prep.sizes,
        "hardware": hardware(),
        "seconds": {
            "prepare": prep_seconds,
            "fit_total": fit_seconds,
            **out["seconds"],
        },
        "contention": load,
        "cost_usd": None,  # filled in by the Modal submitter; local runs cost nothing
        "diagnostics": diag,
        "score": scores,
        "interpretability": {
            "named_additive_contributions": True,
            "per_apartment_residuals": True,
            "uncertainty": "posterior draws kept for joint contribution intervals",
        },
        "log": log_lines,
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
