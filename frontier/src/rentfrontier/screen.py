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
from . import drift_score, splits
from . import run as run_module

DEFAULT_SEED = 20261122
DEFAULT_STRATA = 10
DEFAULT_PRIOR_SD = 1500.0
DEFAULT_GATE_LATEST = 100.0
DEFAULT_GATE_MARKET = 50.0
DEFAULT_TOL_LATEST = 50.0
DEFAULT_TOL_MARKET = 15.0
DEFAULT_RHAT_LIMIT = 1.15
MODAL_LEDGER = Path("/data1/apartments/modal/ledger.jsonl")
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
    # Preserve point-in-time snapshot pins (e.g. asof-* market datasets) so screening fits
    # never fall back to newer default external tables.
    inputs_json = source / "inputs.json"
    if inputs_json.exists():
        (out / "inputs.json").write_bytes(inputs_json.read_bytes())

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


def window_dataset(
    source: Path,
    out: Path,
    min_year: int,
    *,
    tail_anchor: bool = False,
    overwrite: bool = False,
) -> dict:
    """Create a temporally windowed dataset keeping ALL held-out rows plus training rows with
    `price_at.year >= min_year` (and optionally the single most recent earlier training row
    per unit that has no training row `>= min_year`). Preserves `inputs.json` and `manifest.json`."""
    src = Path(source)
    dst = Path(out)
    if dst.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {dst} (pass --overwrite)")
    dst.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(src / "rows.parquet")
    if "carried_heldout" in frame.columns:
        held = frame["carried_heldout"].to_numpy(bool)
    elif "open" in frame.columns:
        held = frame["open"].eq(True).to_numpy(bool)
    else:
        raise ValueError(f"source dataset has neither carried_heldout nor open: {src}")
    dt = pd.to_datetime(frame["price_at"], utc=True)
    yr = dt.dt.year.to_numpy(int)
    keep = held | (yr >= int(min_year))
    n_tail = 0
    if tail_anchor:
        has_uid = frame["unit_id"].notna().to_numpy(bool)
        ukey = (
            frame["building"].astype(str)
            + "\x1f"
            + frame["unit_id"].fillna("").astype(str)
        ).to_numpy()
        recent_tr_units = set(ukey[keep & (~held) & has_uid])
        older_idx = np.flatnonzero((~held) & (yr < int(min_year)) & has_uid)
        if len(older_idx) > 0:
            older_df = pd.DataFrame(
                {
                    "idx": older_idx,
                    "ukey": ukey[older_idx],
                    "ts": dt.iloc[older_idx].astype("int64").to_numpy(),
                }
            )
            older_df = older_df[~older_df["ukey"].isin(recent_tr_units)]
            if len(older_df) > 0:
                latest_idx = (
                    older_df.sort_values(["ts", "idx"], kind="stable")
                    .groupby("ukey", sort=False)["idx"]
                    .last()
                    .to_numpy(int)
                )
                keep[latest_idx] = True
                n_tail = int(len(latest_idx))
    cut = frame.loc[keep].reset_index(drop=True)
    rows_path = dst / "rows.parquet"
    cut.to_parquet(rows_path, index=False)
    manifest = {}
    if (src / "manifest.json").exists():
        manifest = json.loads((src / "manifest.json").read_text())
    if (src / "inputs.json").exists():
        (dst / "inputs.json").write_text((src / "inputs.json").read_text())
    win_meta = {
        "source": str(src),
        "min_year": int(min_year),
        "tail_anchor": bool(tail_anchor),
        "n_tail_anchors": int(n_tail),
        "source_rows": int(len(frame)),
        "rows": int(len(cut)),
        "heldout_rows": int(held.sum()),
        "row_fraction": float(len(cut) / max(1, len(frame))),
    }
    manifest |= {
        "rows": int(len(cut)),
        "rows_sha256": data_module.sha256(rows_path),
        "window": win_meta,
    }
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return win_meta


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


def _settled_usd_from_ledger(
    run_name: str, ledger: Path = MODAL_LEDGER
) -> float | None:
    """Return the exact billed USD from Modal's settle ledger when available.

    Modal sometimes fulfills an `A100-40GB` request on a physical `A100-SXM4-80GB` card while
    billing the requested `A100-40GB` rate, so the settle ledger is authoritative over nvidia-smi.
    """
    if not ledger.exists():
        return None
    settled = None
    try:
        for line in ledger.read_text().splitlines():
            if run_name not in line:
                continue
            row = json.loads(line)
            if row.get("kind") == "settle" and row.get("name") == run_name:
                settled = float(row["usd"])
    except (OSError, ValueError, KeyError):
        return None
    return settled


def _gpu_short_name(gpu_string: str | None) -> str | None:
    if not gpu_string:
        return None
    for needle, short in _GPU_NAME_MAP:
        if needle in gpu_string:
            return short
    return None


def read_run_telemetry(run_dir: Path) -> dict:
    """Extract timing, GPU, cost, convergence, model complexity, and JAX cache stats."""
    info: dict = {
        "run": run_dir.name,
        "model": None,
        "variant": None,
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
        "prepare_seconds": None,
        "warmup_seconds": None,
        "compile_seconds": None,
        "sampling_seconds": None,
        "seconds_per_sweep": None,
        "usd": None,
        "jax_cache": None,
        "n_beta": None,
        "n_weeks": None,
        "n_phase_factors": None,
        "n_sigma": None,
        "n_gp": None,
        "G_dim": None,
        "K_scale": None,
        "explicit_params": None,
        "walk_stride": 1,
        "scale_passes": 1,
        "has_bld_ar": None,
        "ess_per_min": None,
    }
    res_path = run_dir / "result.json"
    if res_path.exists():
        res = json.loads(res_path.read_text())
        info["model"] = (res.get("model") or {}).get("name")
        info["variant"] = res.get("ablate_variant")
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
        secs = res.get("seconds") or {}
        if isinstance(secs, dict):
            info["prepare_seconds"] = secs.get("prepare")
            info["warmup_seconds"] = secs.get("warmup")
            if info["compile_seconds"] is None:
                info["compile_seconds"] = secs.get("compile")
            if info["sampling_seconds"] is None:
                info["sampling_seconds"] = secs.get("sampling")
        sizes = res.get("sizes") or {}
        n_beta = sizes.get("coefficients")
        n_weeks = sizes.get("weeks")
        info["n_beta"] = int(n_beta) if n_beta is not None else None
        info["n_weeks"] = int(n_weeks) if n_weeks is not None else None
        ph = res.get("phase") or {}
        n_pf = ph.get("n_free_factors")
        if n_pf is None and isinstance(ph.get("free_factors"), list):
            n_pf = len(ph["free_factors"])
        info["n_phase_factors"] = int(n_pf) if n_pf is not None else 0
        n_sigma = gibbs.get("n_sigma", 4)
        info["n_sigma"] = int(n_sigma)
        info["walk_stride"] = int(gibbs.get("walk_stride", 1))
        info["scale_passes"] = int(gibbs.get("scale_passes", 1))
        info["has_bld_ar"] = gibbs.get("has_bld_ar", True)
        n_gp = gibbs.get("n_gp")
        if n_gp is None:
            # Fallback for older runs before gibbs.n_gp existed.
            has_seg = isinstance(res.get("segments"), dict) or (
                isinstance(info["variant"], list) and "seg" in info["variant"]
            )
            n_gp = 9 if has_seg else 2
        info["n_gp"] = int(n_gp)
        if gibbs.get("G_dim") is not None:
            info["G_dim"] = int(gibbs["G_dim"])
        # Scale-step slice dimension: 3 unit hyp + n_sigma + free phase factors (+1 if nu free).
        nu_free = 0 if res.get("row_dof_fixed") is not None else 1
        info["K_scale"] = int(3 + info["n_sigma"] + info["n_phase_factors"] + nu_free)
        if info["n_beta"] is not None:
            # Explicit global parameters: beta + scale-step dims + 2*n_gp hypers.
            info["explicit_params"] = int(
                info["n_beta"] + info["K_scale"] + 2 * info["n_gp"]
            )
    modal_path = run_dir / "modal" / "modal.json"
    if modal_path.exists():
        m = json.loads(modal_path.read_text())
        info["gpu_raw"] = m.get("gpu")
        info["gpu"] = _gpu_short_name(m.get("gpu"))
        info["wall_seconds"] = m.get("wall_seconds")
        info["stage_seconds"] = m.get("stage_seconds")
        info["fit_seconds"] = (m.get("stages") or {}).get("fit")
        info["jax_cache"] = m.get("jax_cache")
        settled = _settled_usd_from_ledger(run_dir.name)
        if settled is not None:
            info["usd"] = round(settled, 4)
        elif info["gpu"] in MODAL_USD_PER_HOUR and info["wall_seconds"] is not None:
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
    if info["min_ess"] is not None and info["wall_seconds"]:
        info["ess_per_min"] = round(
            float(info["min_ess"]) / (float(info["wall_seconds"]) / 60.0), 3
        )
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
    rhat_limit: float = DEFAULT_RHAT_LIMIT,
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


def bayesian_simplify_verdict(
    delta_full_hat: float,
    se_full_hat: float,
    z_sub: float,
    max_rhat: float | None = None,
    cov80_shift: float = 0.0,
    tail05_cand: float = 0.05,
    prior_sd: float = DEFAULT_PRIOR_SD,
    tol_elpd: float = DEFAULT_TOL_LATEST,
    extra_noise_scale: float = 1.0,
    rhat_limit: float = DEFAULT_RHAT_LIMIT,
) -> dict:
    """Bayesian non-inferiority & parsimony verdict for model-simplification ablations.

    Tests whether removing or compressing parameters preserves predictive performance within
    `tol_elpd` (`Δ_full > -tol_elpd`):
    - `SIMPLIFY_KEEP`: high posterior probability `P(Δ_full > -tol_elpd) >= 0.90` (or
      `delta_full_hat >= 0` with `P > 0.85`), clean mixing, and no severe coverage drop.
    - `KEEP_COMPLEX`: `P(Δ_full < -tol_elpd) >= 0.90` (the ablated parameters earn their keep).
    - `ESCALATE`: uncertain — needs more draws/chains or dual-split verification.
    """
    sigma_obs = max(1e-6, float(se_full_hat) * float(extra_noise_scale))
    prior_var = float(prior_sd) ** 2
    obs_var = sigma_obs**2
    post_var = 1.0 / (1.0 / prior_var + 1.0 / obs_var)
    post_sd = math.sqrt(post_var)
    post_mean = (post_var / obs_var) * float(delta_full_hat)
    p_positive = float(ndtr(post_mean / post_sd))
    p_non_inferior = float(ndtr((post_mean + float(tol_elpd)) / post_sd))
    p_worse_than_tol = 1.0 - p_non_inferior
    ig_bits = 0.5 * math.log2(1.0 + prior_var / obs_var)
    prior_p_ni = float(ndtr(float(tol_elpd) / float(prior_sd)))
    decision_ig_bits = max(
        0.0, _binary_entropy(prior_p_ni) - _binary_entropy(p_non_inferior)
    )
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
    cov_ok = cov80_shift >= -0.015
    if p_worse_than_tol >= 0.90 or (z_sub <= -2.5 and delta_full_hat < -tol_elpd):
        verdict = "KEEP_COMPLEX"
    elif (
        rhat_ok
        and cov_ok
        and (
            p_non_inferior >= 0.90 or (delta_full_hat >= 0.0 and p_non_inferior >= 0.85)
        )
    ):
        verdict = "SIMPLIFY_KEEP"
    else:
        verdict = "ESCALATE"

    return {
        "verdict": verdict,
        "post_mean": post_mean,
        "post_sd": post_sd,
        "p_positive": p_positive,
        "p_gt_gate": p_non_inferior,
        "p_non_inferior": p_non_inferior,
        "tol_elpd": float(tol_elpd),
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
    mode: str = "forward",
    tol_elpd: float | None = None,
) -> dict:
    """Compare a candidate run against a baseline run on their paired held-out rows."""
    if mode not in ("forward", "simplify"):
        raise ValueError(f"mode must be 'forward' or 'simplify', got {mode!r}")
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
    if tol_elpd is None:
        tol_elpd = DEFAULT_TOL_MARKET if split_kind == "market" else DEFAULT_TOL_LATEST

    delta_full_hat = all_stats["delta"] * scale
    se_full_hat = all_stats["se"] * scale

    tb = read_run_telemetry(base_dir)
    tc = read_run_telemetry(cand_dir)
    if mode == "simplify":
        bayes = bayesian_simplify_verdict(
            delta_full_hat=delta_full_hat,
            se_full_hat=se_full_hat,
            z_sub=all_stats["z"],
            max_rhat=tc["max_rhat"],
            cov80_shift=cov80_cand - cov80_base,
            tail05_cand=tail05_cand,
            prior_sd=prior_sd,
            tol_elpd=tol_elpd,
            extra_noise_scale=extra_noise_scale,
        )
    else:
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

    # Efficiency & parsimony metrics per marginal candidate screen.
    wall_s = tc["wall_seconds"]
    usd = tc["usd"]
    delta_beta = (
        tc["n_beta"] - tb["n_beta"]
        if tc["n_beta"] is not None and tb["n_beta"] is not None
        else None
    )
    delta_pf = (
        tc["n_phase_factors"] - tb["n_phase_factors"]
        if tc["n_phase_factors"] is not None and tb["n_phase_factors"] is not None
        else None
    )
    delta_kscale = (
        tc["K_scale"] - tb["K_scale"]
        if tc["K_scale"] is not None and tb["K_scale"] is not None
        else None
    )
    delta_params = (
        tc["explicit_params"] - tb["explicit_params"]
        if tc["explicit_params"] is not None and tb["explicit_params"] is not None
        else None
    )
    params_removed = (
        -delta_params if delta_params is not None and delta_params < 0 else None
    )
    elpd_per_param_removed = (
        (-delta_full_hat / params_removed) if params_removed else None
    )
    wall_speedup = (
        (tb["wall_seconds"] / wall_s) if tb["wall_seconds"] and wall_s else None
    )
    sweep_speedup = (
        (tb["seconds_per_sweep"] / tc["seconds_per_sweep"])
        if tb["seconds_per_sweep"] and tc["seconds_per_sweep"]
        else None
    )
    usd_savings_pct = (
        100.0 * (1.0 - usd / tb["usd"]) if tb["usd"] and usd is not None else None
    )
    complexity = {
        "base_beta": tb["n_beta"],
        "cand_beta": tc["n_beta"],
        "delta_beta": delta_beta,
        "base_phase_factors": tb["n_phase_factors"],
        "cand_phase_factors": tc["n_phase_factors"],
        "delta_phase_factors": delta_pf,
        "base_K_scale": tb["K_scale"],
        "cand_K_scale": tc["K_scale"],
        "delta_K_scale": delta_kscale,
        "base_explicit_params": tb["explicit_params"],
        "cand_explicit_params": tc["explicit_params"],
        "delta_explicit_params": delta_params,
        "elpd_value_per_removed_param": elpd_per_param_removed,
        "wall_speedup": wall_speedup,
        "sweep_speedup": sweep_speedup,
        "usd_savings_pct": usd_savings_pct,
    }
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
        "mode": mode,
        "baseline": tb,
        "candidate": tc,
        "screen": screen_meta,
        "fraction": fraction,
        "scale_factor": scale,
        "gate_elpd": float(gate_elpd),
        "tol_elpd": float(tol_elpd),
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
        "complexity": complexity,
        "bayesian": bayes,
        "efficiency": efficiency,
    }


def pareto_frontier(
    baseline_ref: str | Path,
    candidate_refs: list[str | Path],
    *,
    mode: str = "simplify",
    tol_elpd: float | None = None,
    prior_sd: float = DEFAULT_PRIOR_SD,
    extra_noise_scale: float = 1.0,
) -> dict:
    """Batch-score candidates vs `baseline_ref` and identify the Pareto frontier over
    `(projected ΔELPD high, explicit_params low, seconds_per_sweep low)`."""
    reports = [
        compare_runs(
            baseline_ref=baseline_ref,
            candidate_ref=c,
            prior_sd=prior_sd,
            extra_noise_scale=extra_noise_scale,
            mode=mode,
            tol_elpd=tol_elpd,
        )
        for c in candidate_refs
    ]
    rows = []
    for r in reports:
        tc = r["candidate"]
        cx = r["complexity"]
        eff = r["efficiency"]
        b = r["bayesian"]
        rows.append(
            {
                "run": tc["run"],
                "variant": ",".join(tc["variant"]) if tc["variant"] else "",
                "verdict": b["verdict"],
                "proj_delta": r["projected_full"]["delta"],
                "proj_se": r["projected_full"]["se"],
                "z": r["all"]["z"],
                "p_non_inferior": b.get("p_non_inferior", b["p_gt_gate"]),
                "cov80": r["coverage"]["cov80_cand"],
                "cov80_shift": r["coverage"]["cov80_shift"],
                "n_beta": tc["n_beta"],
                "n_pf": tc["n_phase_factors"],
                "explicit_params": tc["explicit_params"],
                "delta_params": cx["delta_explicit_params"],
                "elpd_per_removed_param": cx["elpd_value_per_removed_param"],
                "s_per_sweep": tc["seconds_per_sweep"],
                "sweep_speedup": cx["sweep_speedup"],
                "wall_s": eff["wall_seconds"],
                "wall_speedup": cx["wall_speedup"],
                "usd": eff["usd"],
                "max_rhat": tc["max_rhat"],
                "min_ess": tc["min_ess"],
                "ess_per_min": tc["ess_per_min"],
                "ig_bits": b["ig_bits"],
                "ig_bits_per_min": eff["ig_bits_per_min"],
                "ig_bits_per_usd": eff["ig_bits_per_usd"],
            }
        )
    # Mark Pareto-optimal rows (non-dominated in maximizing proj_delta & minimizing explicit_params).
    for i, a in enumerate(rows):
        dom = False
        ap = a["explicit_params"] if a["explicit_params"] is not None else 10**9
        for j, b in enumerate(rows):
            if i == j:
                continue
            bp = b["explicit_params"] if b["explicit_params"] is not None else 10**9
            if (
                b["proj_delta"] >= a["proj_delta"]
                and bp <= ap
                and (b["proj_delta"] > a["proj_delta"] or bp < ap)
            ):
                dom = True
                break
        a["pareto"] = not dom
    tot_bits = sum(r["ig_bits"] for r in rows)
    tot_wall = sum(r["wall_s"] or 0.0 for r in rows)
    tot_usd = sum(r["usd"] or 0.0 for r in rows)
    return {
        "baseline": reports[0]["baseline"] if reports else None,
        "mode": mode,
        "count": len(rows),
        "total_ig_bits": tot_bits,
        "total_wall_seconds": tot_wall,
        "total_usd": round(tot_usd, 4),
        "aggregate_bits_per_min": (tot_bits / (tot_wall / 60.0)) if tot_wall else None,
        "aggregate_bits_per_usd": (tot_bits / tot_usd) if tot_usd else None,
        "rows": rows,
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
    prob_label = (
        f"P(>-{report['tol_elpd']:.0f})={b['p_gt_gate']:.3f}"
        if report.get("mode") == "simplify"
        else f"P(>{report['gate_elpd']:.0f})={b['p_gt_gate']:.3f}"
    )
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
        f"P(>0)={b['p_positive']:.3f} | {prob_label} | "
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
    cx = report.get("complexity") or {}
    if cx.get("cand_explicit_params") is not None:
        dp = cx.get("delta_explicit_params")
        dp_s = f"{dp:+d}" if dp is not None else "n/a"
        sp_s = (
            f"{cx['sweep_speedup']:.2f}x sweep"
            if cx.get("sweep_speedup") is not None
            else "n/a"
        )
        ep_s = (
            f" | {cx['elpd_value_per_removed_param']:+.2f} ELPD/param"
            if cx.get("elpd_value_per_removed_param") is not None
            else ""
        )
        lines.append(
            f"  parsimony: {cx['base_explicit_params']} -> {cx['cand_explicit_params']} "
            f"params ({dp_s}; beta={cx['cand_beta']}, pf={cx['cand_phase_factors']}, "
            f"K_scale={cx['cand_K_scale']}) | {sp_s}{ep_s}"
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


def format_pareto(summary: dict) -> str:
    """Compact table of Pareto-frontier & parameter-value results."""
    lines = [
        f"Pareto / Discovery Summary ({summary['count']} candidates, mode={summary['mode']})",
        f"  Total IG: {summary['total_ig_bits']:.1f} bits | "
        f"Wall: {summary['total_wall_seconds'] / 60:.1f} min | "
        f"USD: ${summary['total_usd']:.2f} | "
        f"Rate: {summary['aggregate_bits_per_min'] or 0:.2f} bits/min, "
        f"{summary['aggregate_bits_per_usd'] or 0:.1f} bits/$",
        "",
        f"{'Run':34s} {'Verdict':13s} {'ΔELPD±SE':14s} {'Params(Δ)':12s} {'s/sw':6s} {'R-hat':6s} {'bits/m':6s} {'P*'}",
    ]
    for r in sorted(summary["rows"], key=lambda x: -x["proj_delta"]):
        dp = f"{r['delta_params']:+d}" if r["delta_params"] is not None else "n/a"
        ep = (
            f"{r['explicit_params']}({dp})"
            if r["explicit_params"] is not None
            else "n/a"
        )
        sw = f"{r['s_per_sweep']:.3f}" if r["s_per_sweep"] is not None else "  n/a"
        rh = f"{r['max_rhat']:.3f}" if r["max_rhat"] is not None else "  n/a"
        bm = (
            f"{r['ig_bits_per_min']:.2f}"
            if r["ig_bits_per_min"] is not None
            else " n/a"
        )
        mark = "*" if r["pareto"] else ""
        lines.append(
            f"{r['run'][-34:]:34s} {r['verdict']:13s} "
            f"{r['proj_delta']:+6.0f}±{r['proj_se']:<5.0f} "
            f"{ep:12s} {sw:6s} {rh:6s} {bm:6s} {mark}"
        )
    return "\n".join(lines)


def sprint_budget(
    *,
    filter_substring: str | None = None,
    cap_usd: float | None = None,
    ledger_path: Path = MODAL_LEDGER,
) -> dict:
    """Summarize settled Modal spend and open estimates from `ledger.jsonl`."""
    if not ledger_path.exists():
        return {
            "settled_usd": 0.0,
            "open_estimate_usd": 0.0,
            "settled_runs": 0,
            "open_runs": 0,
            "remaining_usd": cap_usd,
        }
    settled_ids: set[str] = set()
    settled_usd = 0.0
    settled_runs = 0
    open_entries: dict[str, float] = {}
    for line in ledger_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = str(rec.get("name", ""))
        if filter_substring and filter_substring not in name:
            continue
        rid = str(rec.get("id", name))
        if rec.get("kind") == "settle":
            settled_ids.add(rid)
            settled_usd += float(rec.get("usd", 0.0))
            settled_runs += 1
        elif rec.get("usd_estimate") is not None:
            open_entries[rid] = float(rec["usd_estimate"])
    open_usd = sum(v for k, v in open_entries.items() if k not in settled_ids)
    open_runs = sum(1 for k in open_entries if k not in settled_ids)
    out = {
        "filter": filter_substring,
        "settled_usd": round(settled_usd, 4),
        "open_estimate_usd": round(open_usd, 4),
        "settled_runs": settled_runs,
        "open_runs": open_runs,
        "projected_total_usd": round(settled_usd + open_usd, 4),
    }
    if cap_usd is not None:
        out["cap_usd"] = float(cap_usd)
        out["remaining_usd"] = round(float(cap_usd) - settled_usd - open_usd, 4)
    return out


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

    pw = sub.add_parser(
        "window", help="build a temporally windowed dataset keeping all held-out rows"
    )
    pw.add_argument("source", type=Path)
    pw.add_argument("out", type=Path)
    pw.add_argument("--min-year", type=int, required=True)
    pw.add_argument("--tail-anchor", action="store_true")
    pw.add_argument("--overwrite", action="store_true")

    pc = sub.add_parser(
        "compare", help="score and compare candidate vs baseline screen runs"
    )
    pc.add_argument("baseline")
    pc.add_argument("candidate")
    pc.add_argument("--gate", type=float, default=None)
    pc.add_argument("--tol", type=float, default=None)
    pc.add_argument("--mode", choices=("forward", "simplify"), default="forward")
    pc.add_argument("--prior-sd", type=float, default=DEFAULT_PRIOR_SD)
    pc.add_argument("--extra-noise-scale", type=float, default=1.0)
    pc.add_argument("--force-score", action="store_true")
    pc.add_argument("--json", action="store_true", dest="as_json")

    pp = sub.add_parser(
        "pareto", help="score a batch of candidates and report the Pareto frontier"
    )
    pp.add_argument("baseline")
    pp.add_argument("candidates", nargs="+")
    pp.add_argument("--tol", type=float, default=None)
    pp.add_argument("--mode", choices=("forward", "simplify"), default="simplify")
    pp.add_argument("--prior-sd", type=float, default=DEFAULT_PRIOR_SD)
    pp.add_argument("--extra-noise-scale", type=float, default=1.0)
    pp.add_argument("--json", action="store_true", dest="as_json")

    pbud = sub.add_parser(
        "budget", help="summarize Modal sprint spend and remaining budget"
    )
    pbud.add_argument("--filter", default=None, help="substring match on run name")
    pbud.add_argument("--cap", type=float, default=None, help="budget ceiling in USD")
    pbud.add_argument("--json", action="store_true", dest="as_json")

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

    if args.cmd == "window":
        meta = window_dataset(
            source=args.source,
            out=args.out,
            min_year=args.min_year,
            tail_anchor=args.tail_anchor,
            overwrite=args.overwrite,
        )
        print(json.dumps(meta, indent=2))
        return 0

    if args.cmd == "budget":
        b = sprint_budget(filter_substring=args.filter, cap_usd=args.cap)
        if args.as_json:
            print(json.dumps(b, indent=2))
        else:
            rem = (
                f" | remaining: ${b['remaining_usd']:.2f} of ${b['cap_usd']:.2f}"
                if "remaining_usd" in b
                else ""
            )
            print(
                f"Modal budget ({b['filter'] or 'all'}): "
                f"${b['settled_usd']:.2f} settled ({b['settled_runs']} runs) + "
                f"${b['open_estimate_usd']:.2f} open est ({b['open_runs']} runs){rem}"
            )
        return 0

    if args.cmd == "pareto":
        summary = pareto_frontier(
            baseline_ref=args.baseline,
            candidate_refs=args.candidates,
            mode=args.mode,
            tol_elpd=args.tol,
            prior_sd=args.prior_sd,
            extra_noise_scale=args.extra_noise_scale,
        )
        if args.as_json:
            print(json.dumps(summary, indent=2))
        else:
            print(format_pareto(summary))
        return 0

    report = compare_runs(
        baseline_ref=args.baseline,
        candidate_ref=args.candidate,
        gate_elpd=args.gate,
        prior_sd=args.prior_sd,
        extra_noise_scale=args.extra_noise_scale,
        force_score=args.force_score,
        mode=args.mode,
        tol_elpd=args.tol,
    )
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
