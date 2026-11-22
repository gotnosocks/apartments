"""Fast screening harness for Modal cloud GPUs (`rentfrontier.screen`).

Builds deterministic, nested, building-stratified subsamples with carried held-out masks
(`--split carried`) so candidate models can be screened in minutes on Modal GPUs and scored
on the exact same held-out buildings as full-data fits. Also scores paired runs, projects
subsample ΔELPD to full-data scale, computes Bayesian GO / KILL / ESCALATE verdicts, and
reports information gain per minute and per dollar.

Subcommands:

    python -m rentfrontier.screen build SOURCE OUT --fraction 0.10 [--split latest|market]
                                        [--seed 20261122] [--stratify size|uniform] [--strata 10]
    python -m rentfrontier.screen compare BASELINE CANDIDATE [--gate 100] [--prior-sd 1500]
                                          [--extra-noise-scale 1.0] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from . import data as data_module
from . import drift_score
from . import run as run_module
from . import splits

DEFAULT_SEED = 20261122
DEFAULT_STRATA = 10
DEFAULT_PRIOR_SD = 1500.0
DEFAULT_GATE_LATEST = 100.0
DEFAULT_GATE_MARKET = 50.0
# Modal list prices (GPU + 2 CPU + 40 GiB RAM), kept in sync with ops/modal/app.py.
MODAL_USD_PER_HOUR = {
    "L4": 1.2133,
    "A100-40GB": 2.5133,
    "A100-80GB": 2.9123,
    "H100": 4.3633,
    "H200": 4.9543,
}
_GPU_NAME_MAP = (
    ("H200", "H200"),
    ("H100", "H100"),
    ("A100-SXM4-80GB", "A100-80GB"),
    ("A100 80GB", "A100-80GB"),
    ("A100-PCIE-40GB", "A100-40GB"),
    ("A100-SXM4-40GB", "A100-40GB"),
    ("A100 40GB", "A100-40GB"),
    ("L4", "L4"),
)


def select_buildings(
    buildings: pd.Series | np.ndarray,
    fraction: float,
    seed: int = DEFAULT_SEED,
    stratify: str = "size",
    strata: int = DEFAULT_STRATA,
) -> np.ndarray:
    """Select an equal-probability building subset of size ~`fraction * B`.

    Within each stratum (or globally for `stratify="uniform"`), buildings are deterministically
    permuted using `seed` so that smaller `fraction` values are strictly nested inside larger
    ones at the same `(seed, stratify, strata)`.

    `stratify="size"` partitions buildings into `strata` equal-count bins ordered by
    `(row_count, building_id)`, reducing row-count and cluster-size variance while preserving
    exact equal inclusion probability across buildings (so `E[delta_sub / f] = delta_full`
    with no Horvitz-Thompson reweighting).
    """
    if not (0.0 < fraction <= 1.0):
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    if stratify not in ("size", "uniform"):
        raise ValueError(f"stratify must be 'size' or 'uniform', got {stratify!r}")
    s = pd.Series(buildings, dtype="string")
    counts = s.value_counts(sort=False)
    order = pd.DataFrame(
        {"building": counts.index.astype(str), "rows": counts.to_numpy(dtype=np.int64)}
    ).sort_values(["rows", "building"], kind="mergesort")
    b_sorted = order["building"].to_numpy(dtype=str)
    n_bld = len(b_sorted)
    if fraction == 1.0:
        return np.sort(b_sorted)
    rng = np.random.default_rng(seed)
    if stratify == "uniform" or strata <= 1 or n_bld < strata:
        perm = rng.permutation(np.sort(b_sorted))
        k = max(1, int(round(fraction * n_bld)))
        return np.sort(perm[:k])
    chosen: list[np.ndarray] = []
    # Equal-count splits in sorted (rows, building) order -> size deciles.
    for bucket in np.array_split(b_sorted, strata):
        if len(bucket) == 0:
            continue
        perm = rng.permutation(bucket)
        k = max(1, int(round(fraction * len(bucket))))
        chosen.append(perm[:k])
    return np.sort(np.concatenate(chosen))


def build_subsample(
    source: Path,
    out: Path,
    fraction: float,
    split: str = "latest",
    seed: int = DEFAULT_SEED,
    stratify: str = "size",
    strata: int = DEFAULT_STRATA,
    overwrite: bool = False,
) -> dict:
    """Create a building-subsampled dataset directory with `carried_heldout` and manifest."""
    source = Path(source)
    out = Path(out)
    if split not in ("latest", "market"):
        raise ValueError(f"split must be 'latest' or 'market', got {split!r}")
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} already exists (pass overwrite=True to replace)")
    frame = pd.read_parquet(source / "rows.parquet")
    held = (
        splits.latest_split(frame) if split == "latest" else splits.market_split(frame)
    )
    buildings = frame["building"].astype(str)
    n_bld_full = int(buildings.nunique())
    picked = select_buildings(
        buildings, fraction=fraction, seed=seed, stratify=stratify, strata=strata
    )
    keep = buildings.isin(set(picked)).to_numpy(bool)
    cut = frame.loc[keep].assign(carried_heldout=held[keep])
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "rows.parquet"
    cut.to_parquet(rows_path, index=False)

    manifest = json.loads((source / "manifest.json").read_text())
    source_sha = manifest.get("rows_sha256")
    n_held_full = int(held.sum())
    n_held_sub = int(cut["carried_heldout"].sum())
    screen_meta = {
        "source": str(source.resolve()),
        "source_rows": int(len(frame)),
        "source_heldout": n_held_full,
        "source_buildings": n_bld_full,
        "source_rows_sha256": source_sha,
        "split": split,
        "stratify": stratify,
        "strata": int(strata) if stratify == "size" else 1,
        "seed": int(seed),
        "fraction": float(fraction),
        "buildings": int(len(picked)),
        "rows": int(len(cut)),
        "carried_heldout": n_held_sub,
        "building_scale_factor": float(n_bld_full / max(1, len(picked))),
        "row_scale_factor": float(len(frame) / max(1, len(cut))),
        "heldout_scale_factor": float(n_held_full / max(1, n_held_sub)),
    }
    manifest |= {
        "rows": int(len(cut)),
        "rows_sha256": data_module.sha256(rows_path),
        "screen": screen_meta,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return screen_meta


def resolve_run_dir(run_ref: str | Path) -> Path:
    """Resolve a run name under `run_module.RUNS` or an explicit directory path."""
    p = Path(run_ref)
    if (p / "result.json").exists() or (p / "posterior.npz").exists():
        return p
    cand = run_module.RUNS / str(run_ref)
    if cand.exists():
        return cand
    raise FileNotFoundError(f"run directory not found: {run_ref}")


def score_or_load(run_dir: Path, force: bool = False) -> dict[str, np.ndarray]:
    """Load cached `pred_scores.npz` inside `run_dir`, or compute it via `drift_score`."""
    cache = run_dir / "pred_scores.npz"
    if cache.exists() and not force:
        with np.load(cache) as z:
            return {k: z[k] for k in z.files}
    scores = drift_score.score_run(run_dir)
    np.savez_compressed(cache, **scores)
    return scores


def paired_cluster_stats(diff: np.ndarray, buildings: np.ndarray) -> dict:
    """Paired sum, building-clustered SE, z-score, and per-row mean on aligned rows."""
    diff = np.asarray(diff, dtype=np.float64)
    bld = np.asarray(buildings, dtype=str)
    n_rows = int(len(diff))
    if n_rows == 0:
        return {
            "n_rows": 0,
            "n_buildings": 0,
            "delta": 0.0,
            "se": float("nan"),
            "z": 0.0,
            "per_row": 0.0,
        }
    _, inv = np.unique(bld, return_inverse=True)
    n_bld = int(inv.max() + 1)
    by_bld = np.bincount(inv, weights=diff, minlength=n_bld)
    delta = float(by_bld.sum())
    if n_bld > 1:
        centered = by_bld - by_bld.mean()
        se = float(math.sqrt(n_bld / (n_bld - 1) * float(np.dot(centered, centered))))
    else:
        se = float("nan")
    z = float(delta / se) if (se and math.isfinite(se) and se > 0.0) else 0.0
    return {
        "n_rows": n_rows,
        "n_buildings": n_bld,
        "delta": delta,
        "se": se,
        "z": z,
        "per_row": float(delta / n_rows),
    }


def _building_half(buildings: np.ndarray) -> np.ndarray:
    """Deterministic 50/50 split of buildings by blake2b hash for internal sign check."""
    uniq, inv = np.unique(np.asarray(buildings, dtype=str), return_inverse=True)
    is_a = np.fromiter(
        (
            (hashlib.blake2b(b.encode(), digest_size=2).digest()[0] & 1) == 0
            for b in uniq
        ),
        dtype=bool,
        count=len(uniq),
    )
    return is_a[inv]


def _binary_entropy(p: float) -> float:
    p = min(max(float(p), 1e-12), 1.0 - 1e-12)
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def _gpu_short_name(gpu_string: str | None) -> str | None:
    if not gpu_string:
        return None
    for needle, short in _GPU_NAME_MAP:
        if needle in gpu_string:
            return short
    return None


def read_run_telemetry(run_dir: Path) -> dict:
    """Extract timing, GPU, cost, convergence, and JAX cache stats from a run directory."""
    info: dict = {
        "run": run_dir.name,
        "model": None,
        "split": None,
        "dataset": None,
        "max_rhat": None,
        "min_ess": None,
        "sweeps": None,
        "chains": None,
        "warmup": None,
        "draws": None,
        "gpu": None,
        "gpu_raw": None,
        "wall_seconds": None,
        "fit_seconds": None,
        "stage_seconds": None,
        "compile_seconds": None,
        "sampling_seconds": None,
        "seconds_per_sweep": None,
        "usd": None,
        "jax_cache": None,
    }
    res_path = run_dir / "result.json"
    if res_path.exists():
        res = json.loads(res_path.read_text())
        info["model"] = (res.get("model") or {}).get("name")
        info["split"] = res.get("split")
        info["dataset"] = res.get("dataset")
        diag = res.get("diagnostics") or {}
        info["max_rhat"] = diag.get("max_rhat")
        info["min_ess"] = diag.get("min_ess")
        gibbs = res.get("gibbs") or {}
        info["sweeps"] = gibbs.get("sweeps")
        ss = res.get("sampler_settings") or {}
        info["chains"] = ss.get("chains")
        info["warmup"] = ss.get("warmup")
        info["draws"] = ss.get("draws")
    modal_path = run_dir / "modal" / "modal.json"
    if modal_path.exists():
        m = json.loads(modal_path.read_text())
        info["gpu_raw"] = m.get("gpu")
        info["gpu"] = _gpu_short_name(m.get("gpu"))
        info["wall_seconds"] = m.get("wall_seconds")
        info["stage_seconds"] = m.get("stage_seconds")
        info["fit_seconds"] = (m.get("stages") or {}).get("fit")
        info["jax_cache"] = m.get("jax_cache")
        if info["gpu"] in MODAL_USD_PER_HOUR and info["wall_seconds"] is not None:
            info["usd"] = round(
                info["wall_seconds"] * MODAL_USD_PER_HOUR[info["gpu"]] / 3600.0, 4
            )
    log_path = run_dir / "modal" / "fit.log"
    if log_path.exists():
        text = log_path.read_text(errors="replace")
        m_comp = re.search(r"first sweep \(compile\)\s+([0-9.]+)s", text)
        if m_comp:
            info["compile_seconds"] = float(m_comp.group(1))
        m_samp = re.search(
            r"sampling\s+([0-9.]+)s,\s+([0-9.]+)s a sweep of\s+(\d+)\s+chains", text
        )
        if m_samp:
            info["sampling_seconds"] = float(m_samp.group(1))
            info["seconds_per_sweep"] = float(m_samp.group(2))
    return info


def bayesian_screen_verdict(
    delta_full_hat: float,
    se_full_hat: float,
    z_sub: float,
    half_a_delta: float,
    half_b_delta: float,
    max_rhat: float | None = None,
    cov80_shift: float = 0.0,
    tail05_cand: float = 0.05,
    prior_sd: float = DEFAULT_PRIOR_SD,
    gate_elpd: float = DEFAULT_GATE_LATEST,
    extra_noise_scale: float = 1.0,
    rhat_limit: float = 1.10,
) -> dict:
    """Compute conjugate Normal posterior, information gain, and GO/KILL/ESCALATE verdict.

    Prior: `Δ_full ~ Normal(0, prior_sd^2)`.
    Observation: `delta_full_hat | Δ_full ~ Normal(Δ_full, sigma_obs^2)`, where
    `sigma_obs = se_full_hat * extra_noise_scale` (with `extra_noise_scale >= 1.0` accounting
    for calibrated small-sample parameter-estimation noise beyond building-sampling SE).
    """
    sigma_obs = max(1e-6, float(se_full_hat) * float(extra_noise_scale))
    prior_var = float(prior_sd) ** 2
    obs_var = sigma_obs**2
    post_var = 1.0 / (1.0 / prior_var + 1.0 / obs_var)
    post_sd = math.sqrt(post_var)
    post_mean = (post_var / obs_var) * float(delta_full_hat)
    p_positive = float(ndtr(post_mean / post_sd))
    p_gt_gate = float(ndtr((post_mean - float(gate_elpd)) / post_sd))
    # Continuous mutual information (bits) of observing delta_full_hat about Δ_full.
    ig_bits = 0.5 * math.log2(1.0 + prior_var / obs_var)
    # Binary decision entropy reduction about sign(Δ_full) from 1.0 bit prior.
    decision_ig_bits = max(0.0, 1.0 - _binary_entropy(p_positive))
    # 80% power MDE at 2-sided alpha=0.05 (z_alpha + z_beta = 1.96 + 0.84 = 2.80).
    mde_80 = 2.80 * sigma_obs

    warnings: list[str] = []
    if max_rhat is not None and max_rhat > rhat_limit:
        warnings.append(f"high R-hat ({max_rhat:.3f} > {rhat_limit:.2f})")
    elif max_rhat is not None and max_rhat > 1.05:
        warnings.append(f"elevated R-hat ({max_rhat:.3f} > 1.05)")
    if abs(cov80_shift) > 0.015:
        warnings.append(f"80% coverage shift {cov80_shift * 100:+.2f} pp")
    if tail05_cand < 0.035 or tail05_cand > 0.065:
        warnings.append(f"<5% tail at {tail05_cand * 100:.2f}% (nominal 5.0%)")

    rhat_ok = max_rhat is None or max_rhat <= rhat_limit
    if z_sub <= -1.5 or (p_gt_gate < 0.05 and z_sub < 1.0 and rhat_ok):
        verdict = "KILL"
    elif (
        z_sub >= 2.0
        and half_a_delta > 0.0
        and half_b_delta > 0.0
        and p_gt_gate >= 0.90
        and rhat_ok
    ):
        verdict = "GO"
    else:
        verdict = "ESCALATE"

    return {
        "verdict": verdict,
        "post_mean": post_mean,
        "post_sd": post_sd,
        "p_positive": p_positive,
        "p_gt_gate": p_gt_gate,
        "ig_bits": ig_bits,
        "decision_ig_bits": decision_ig_bits,
        "mde_80": mde_80,
        "sigma_obs": sigma_obs,
        "warnings": warnings,
    }


def _dataset_screen_meta(run_dir: Path) -> dict | None:
    ds = drift_score.dataset_dir(run_dir)
    if ds is None:
        return None
    manifest_path = ds / "manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text()).get("screen")


def compare_runs(
    baseline_ref: str | Path,
    candidate_ref: str | Path,
    gate_elpd: float | None = None,
    prior_sd: float = DEFAULT_PRIOR_SD,
    extra_noise_scale: float = 1.0,
    force_score: bool = False,
) -> dict:
    """Compare a candidate run against a baseline run on their paired held-out rows."""
    base_dir = resolve_run_dir(baseline_ref)
    cand_dir = resolve_run_dir(candidate_ref)
    sb = score_or_load(base_dir, force=force_score)
    sc = score_or_load(cand_dir, force=force_score)

    if "listing" not in sb or "listing" not in sc:
        raise ValueError(
            "both runs must have dataset metadata (`listing`, `building`, `day`)"
        )
    if np.array_equal(sb["listing"], sc["listing"]):
        elpd_b, elpd_c = sb["elpd"], sc["elpd"]
        cdf_b, cdf_c = sb["cdf"], sc["cdf"]
        bld, day = sb["building"], sb["day"]
    else:
        # Align on intersection of listing_ids in baseline order.
        idx_c = {lid: i for i, lid in enumerate(sc["listing"])}
        keep_b = np.array([lid in idx_c for lid in sb["listing"]], dtype=bool)
        if not keep_b.any():
            raise ValueError("baseline and candidate share no held-out listing_ids")
        take_c = np.array([idx_c[lid] for lid in sb["listing"][keep_b]], dtype=np.int64)
        elpd_b, elpd_c = sb["elpd"][keep_b], sc["elpd"][take_c]
        cdf_b, cdf_c = sb["cdf"][keep_b], sc["cdf"][take_c]
        bld, day = sb["building"][keep_b], sb["day"][keep_b]

    diff = elpd_c - elpd_b
    all_stats = paired_cluster_stats(diff, bld)
    recent_mask = np.asarray(day, dtype=str) >= "2022-01-01"
    recent_stats = paired_cluster_stats(diff[recent_mask], bld[recent_mask])
    half_a_mask = _building_half(bld)
    half_a = paired_cluster_stats(diff[half_a_mask], bld[half_a_mask])
    half_b = paired_cluster_stats(diff[~half_a_mask], bld[~half_a_mask])

    cov80_base = float(((cdf_b >= 0.1) & (cdf_b <= 0.9)).mean())
    cov80_cand = float(((cdf_c >= 0.1) & (cdf_c <= 0.9)).mean())
    tail05_base = float((cdf_b < 0.05).mean())
    tail05_cand = float((cdf_c < 0.05).mean())

    screen_meta = _dataset_screen_meta(cand_dir) or _dataset_screen_meta(base_dir)
    if screen_meta is not None:
        scale = float(screen_meta["source_heldout"] / max(1, all_stats["n_rows"]))
        fraction = float(screen_meta["fraction"])
        split_kind = screen_meta.get("split", "latest")
    else:
        scale = 1.0
        fraction = 1.0
        split_kind = "latest"

    if gate_elpd is None:
        gate_elpd = (
            DEFAULT_GATE_MARKET if split_kind == "market" else DEFAULT_GATE_LATEST
        )

    delta_full_hat = all_stats["delta"] * scale
    se_full_hat = all_stats["se"] * scale

    tb = read_run_telemetry(base_dir)
    tc = read_run_telemetry(cand_dir)
    bayes = bayesian_screen_verdict(
        delta_full_hat=delta_full_hat,
        se_full_hat=se_full_hat,
        z_sub=all_stats["z"],
        half_a_delta=half_a["delta"],
        half_b_delta=half_b["delta"],
        max_rhat=tc["max_rhat"],
        cov80_shift=cov80_cand - cov80_base,
        tail05_cand=tail05_cand,
        prior_sd=prior_sd,
        gate_elpd=gate_elpd,
        extra_noise_scale=extra_noise_scale,
    )

    # Efficiency metrics per marginal candidate screen (baseline is amortized across ideas).
    wall_s = tc["wall_seconds"]
    usd = tc["usd"]
    efficiency = {
        "wall_seconds": wall_s,
        "usd": usd,
        "screens_per_hour": (3600.0 / wall_s) if wall_s else None,
        "screens_per_usd": (1.0 / usd) if usd else None,
        "ig_bits_per_min": (bayes["ig_bits"] / (wall_s / 60.0)) if wall_s else None,
        "ig_bits_per_usd": (bayes["ig_bits"] / usd) if usd else None,
        "decision_ig_bits_per_min": (
            (bayes["decision_ig_bits"] / (wall_s / 60.0)) if wall_s else None
        ),
    }

    return {
        "baseline": tb,
        "candidate": tc,
        "screen": screen_meta,
        "fraction": fraction,
        "scale_factor": scale,
        "gate_elpd": float(gate_elpd),
        "all": all_stats,
        "recent_2022_plus": recent_stats,
        "half_a": half_a,
        "half_b": half_b,
        "projected_full": {
            "delta": delta_full_hat,
            "se": se_full_hat,
        },
        "coverage": {
            "cov80_base": cov80_base,
            "cov80_cand": cov80_cand,
            "cov80_shift": cov80_cand - cov80_base,
            "tail05_base": tail05_base,
            "tail05_cand": tail05_cand,
        },
        "bayesian": bayes,
        "efficiency": efficiency,
    }


def format_report(report: dict) -> str:
    """Human-readable screening report."""
    a = report["all"]
    r22 = report["recent_2022_plus"]
    ha, hb = report["half_a"], report["half_b"]
    pf = report["projected_full"]
    cov = report["coverage"]
    b = report["bayesian"]
    eff = report["efficiency"]
    tc = report["candidate"]
    lines = [
        f"Screen verdict: {b['verdict']}  ({tc['run']} vs {report['baseline']['run']})",
        f"  subsample: f={report['fraction']:.3f} (scale x{report['scale_factor']:.2f}), "
        f"n={a['n_rows']:,} held-out ads across {a['n_buildings']:,} buildings",
        f"  sub ΔELPD: {a['delta']:+.1f} ± {a['se']:.1f} (z={a['z']:+.2f}, {a['per_row']:+.5f}/row)",
        f"  2022+    : {r22['delta']:+.1f} ± {r22['se']:.1f} (z={r22['z']:+.2f}) | "
        f"half A {ha['delta']:+.1f} / half B {hb['delta']:+.1f}",
        f"  projected: {pf['delta']:+.0f} ± {pf['se']:.0f} full-data ΔELPD "
        f"(80% MDE = {b['mde_80']:.0f})",
        f"  posterior: mean {b['post_mean']:+.0f} ± {b['post_sd']:.0f} | "
        f"P(>0)={b['p_positive']:.3f} | P(>{report['gate_elpd']:.0f})={b['p_gt_gate']:.3f} | "
        f"IG={b['ig_bits']:.2f} bits (decision {b['decision_ig_bits']:.2f} bits)",
        f"  coverage : 80% {cov['cov80_base'] * 100:.2f}% -> {cov['cov80_cand'] * 100:.2f}% "
        f"({cov['cov80_shift'] * 100:+.2f} pp) | <5% tail {cov['tail05_base'] * 100:.2f}% -> "
        f"{cov['tail05_cand'] * 100:.2f}%",
    ]
    if tc["max_rhat"] is not None:
        lines.append(
            f"  sampler  : max R-hat {tc['max_rhat']:.4f}, min ESS {tc['min_ess']}, "
            f"GPU {tc['gpu'] or 'local'}"
        )
    if eff["wall_seconds"] is not None:
        usd_s = f"${eff['usd']:.3f}" if eff["usd"] is not None else "n/a"
        ig_usd = (
            f"{eff['ig_bits_per_usd']:.1f} bits/$"
            if eff["ig_bits_per_usd"] is not None
            else "n/a"
        )
        lines.append(
            f"  cost/rate: {eff['wall_seconds']:.1f}s ({usd_s}) | "
            f"{eff['screens_per_hour']:.1f} screens/hr | "
            f"{eff['ig_bits_per_min']:.2f} bits/min | {ig_usd}"
        )
    if b["warnings"]:
        lines.append("  WARNINGS : " + "; ".join(b["warnings"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rentfrontier.screen")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build", help="build a building-stratified screening subsample")
    pb.add_argument("source", type=Path)
    pb.add_argument("out", type=Path)
    grp = pb.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--fraction", type=float, help="fraction of buildings to keep, e.g. 0.10"
    )
    grp.add_argument(
        "--divisor", type=int, help="keep 1 in K buildings, e.g. 10 -> 0.10"
    )
    pb.add_argument("--split", choices=("latest", "market"), default="latest")
    pb.add_argument("--seed", type=int, default=DEFAULT_SEED)
    pb.add_argument("--stratify", choices=("size", "uniform"), default="size")
    pb.add_argument("--strata", type=int, default=DEFAULT_STRATA)
    pb.add_argument("--overwrite", action="store_true")

    pc = sub.add_parser(
        "compare", help="score and compare candidate vs baseline screen runs"
    )
    pc.add_argument("baseline")
    pc.add_argument("candidate")
    pc.add_argument("--gate", type=float, default=None)
    pc.add_argument("--prior-sd", type=float, default=DEFAULT_PRIOR_SD)
    pc.add_argument("--extra-noise-scale", type=float, default=1.0)
    pc.add_argument("--force-score", action="store_true")
    pc.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args(argv)
    if args.cmd == "build":
        frac = args.fraction if args.fraction is not None else 1.0 / args.divisor
        meta = build_subsample(
            source=args.source,
            out=args.out,
            fraction=frac,
            split=args.split,
            seed=args.seed,
            stratify=args.stratify,
            strata=args.strata,
            overwrite=args.overwrite,
        )
        print(json.dumps(meta, indent=2))
        return 0

    report = compare_runs(
        baseline_ref=args.baseline,
        candidate_ref=args.candidate,
        gate_elpd=args.gate,
        prior_sd=args.prior_sd,
        extra_noise_scale=args.extra_noise_scale,
        force_score=args.force_score,
    )
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
