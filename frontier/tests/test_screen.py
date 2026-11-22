"""Tests for `rentfrontier.screen` (fast screening harness)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rentfrontier import screen


def _synthetic_dataset(tmp_path: Path, n_buildings: int = 40, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    rows = []
    aid = 0
    for b in range(n_buildings):
        # Skewed building sizes from 2 to 25 units, 2 listings per unit.
        n_units = int(2 + (b % 10) * 2)
        for u in range(n_units):
            uid = f"b{b:03d}-u{u:02d}"
            for rep, day in enumerate(("2021-06-01", "2024-06-01")):
                aid += 1
                rows.append(
                    {
                        "audit_id": f"a{aid:06d}",
                        "listing_id": f"l{aid:06d}",
                        "building": f"b{b:03d}",
                        "unit_id": uid,
                        "price_at": f"{day}T12:00:00Z",
                        "latest_day": day,
                        "latest_ask": float(2500 + 50 * u + rng.normal(0, 100)),
                        "open": rep == 1 and (u % 4 == 0),
                    }
                )
    ds = tmp_path / "src_ds"
    ds.mkdir()
    frame = pd.DataFrame(rows)
    frame.to_parquet(ds / "rows.parquet", index=False)
    (ds / "manifest.json").write_text(
        json.dumps({"rows": len(frame), "rows_sha256": "deadbeef"}) + "\n"
    )
    return ds


def test_select_buildings_is_deterministic_and_nested():
    buildings = np.repeat([f"b{i:03d}" for i in range(200)], np.arange(1, 201))
    b05 = set(screen.select_buildings(buildings, 0.05, seed=42, stratify="size"))
    b10 = set(screen.select_buildings(buildings, 0.10, seed=42, stratify="size"))
    b20 = set(screen.select_buildings(buildings, 0.20, seed=42, stratify="size"))
    assert len(b05) == 10
    assert len(b10) == 20
    assert len(b20) == 40
    assert b05 < b10 < b20
    # Deterministic across repeated calls.
    assert b10 == set(
        screen.select_buildings(buildings, 0.10, seed=42, stratify="size")
    )
    # Different seed produces a different draw.
    assert b10 != set(
        screen.select_buildings(buildings, 0.10, seed=99, stratify="size")
    )
    # Uniform mode is also nested.
    u10 = set(screen.select_buildings(buildings, 0.10, seed=42, stratify="uniform"))
    u20 = set(screen.select_buildings(buildings, 0.20, seed=42, stratify="uniform"))
    assert u10 < u20


def test_build_subsample_carries_exact_full_split_and_updates_manifest(tmp_path):
    src = _synthetic_dataset(tmp_path, n_buildings=40)
    full = pd.read_parquet(src / "rows.parquet")

    out_latest = tmp_path / "sub_latest"
    meta = screen.build_subsample(
        src, out_latest, fraction=0.25, split="latest", seed=7
    )
    sub = pd.read_parquet(out_latest / "rows.parquet")
    manifest = json.loads((out_latest / "manifest.json").read_text())

    assert meta["buildings"] == 10
    assert meta["rows"] == len(sub)
    assert manifest["rows"] == len(sub)
    assert manifest["rows_sha256"] != "deadbeef"
    assert manifest["screen"]["split"] == "latest"
    assert "carried_heldout" in sub.columns
    # Exact match with full latest_split on the kept rows (zero leakage / no re-splitting).
    from rentfrontier import splits

    full_held = pd.Series(splits.latest_split(full), index=full["audit_id"])
    assert np.array_equal(
        sub["carried_heldout"].to_numpy(bool),
        full_held.loc[sub["audit_id"]].to_numpy(bool),
    )

    # Market split carries `open` as `carried_heldout`.
    out_mkt = tmp_path / "sub_market"
    meta_mkt = screen.build_subsample(
        src, out_mkt, fraction=0.25, split="market", seed=7
    )
    sub_mkt = pd.read_parquet(out_mkt / "rows.parquet")
    assert meta_mkt["carried_heldout"] == int(sub_mkt["open"].sum())
    assert np.array_equal(
        sub_mkt["carried_heldout"].to_numpy(bool), sub_mkt["open"].to_numpy(bool)
    )


def test_paired_cluster_stats_and_bayesian_verdicts():
    # 20 buildings, 5 rows each: +1.0 per row in every building -> zero variance across equal-size clusters
    # Add slight building-level heterogeneity so SE > 0.
    rng = np.random.default_rng(1)
    bld = np.repeat([f"b{i}" for i in range(40)], 5)
    b_eff = np.repeat(rng.normal(0.5, 0.2, size=40), 5)
    st = screen.paired_cluster_stats(b_eff, bld)
    assert st["n_rows"] == 200
    assert st["n_buildings"] == 40
    assert st["delta"] == pytest.approx(b_eff.sum())
    assert st["se"] > 0
    assert st["z"] > 5.0

    # Clear GO
    go = screen.bayesian_screen_verdict(
        delta_full_hat=2500.0,
        se_full_hat=300.0,
        z_sub=8.3,
        half_a_delta=120.0,
        half_b_delta=130.0,
        max_rhat=1.02,
    )
    assert go["verdict"] == "GO"
    assert go["p_gt_gate"] > 0.99
    assert go["ig_bits"] > 2.0
    assert go["decision_ig_bits"] > 0.9

    # Clear KILL
    kill = screen.bayesian_screen_verdict(
        delta_full_hat=-300.0,
        se_full_hat=150.0,
        z_sub=-2.0,
        half_a_delta=-15.0,
        half_b_delta=-15.0,
        max_rhat=1.01,
    )
    assert kill["verdict"] == "KILL"

    # Ambiguous -> ESCALATE
    esc = screen.bayesian_screen_verdict(
        delta_full_hat=180.0,
        se_full_hat=150.0,
        z_sub=1.2,
        half_a_delta=12.0,
        half_b_delta=6.0,
        max_rhat=1.02,
    )
    assert esc["verdict"] == "ESCALATE"

    # High R-hat prevents GO even when z is large, and emits a warning.
    bad_rhat = screen.bayesian_screen_verdict(
        delta_full_hat=2500.0,
        se_full_hat=300.0,
        z_sub=8.3,
        half_a_delta=120.0,
        half_b_delta=130.0,
        max_rhat=1.25,
        cov80_shift=-0.025,
        tail05_cand=0.072,
    )
    assert bad_rhat["verdict"] == "ESCALATE"
    assert len(bad_rhat["warnings"]) == 3


def test_compare_runs_end_to_end_with_cached_scores(tmp_path):
    ds = tmp_path / "sub_ds"
    ds.mkdir()
    (ds / "rows.parquet").write_bytes(b"")
    (ds / "manifest.json").write_text(
        json.dumps(
            {
                "rows": 2000,
                "rows_sha256": "abc123",
                "screen": {
                    "source_heldout": 2000,
                    "fraction": 0.10,
                    "split": "latest",
                },
            }
        )
    )
    n = 200
    listings = np.array([f"L{i:04d}" for i in range(n)])
    buildings = np.array([f"B{i // 4:03d}" for i in range(n)])
    days = np.where(np.arange(n) % 2 == 0, "2020-05-01", "2024-05-01")
    rng = np.random.default_rng(123)
    elpd_b = rng.normal(0.0, 0.5, size=n)
    elpd_c = elpd_b + rng.normal(0.25, 0.10, size=n)
    cdf_b = np.linspace(0.01, 0.99, n)
    cdf_c = np.linspace(0.01, 0.99, n)

    def make_run(name: str, elpd: np.ndarray, cdf: np.ndarray) -> Path:
        r = tmp_path / name
        (r / "modal").mkdir(parents=True)
        (r / "result.json").write_text(
            json.dumps(
                {
                    "dataset": str(ds),
                    "dataset_observations_sha256": "abc123",
                    "split": "carried",
                    "model": {"name": name},
                    "diagnostics": {"max_rhat": 1.015, "min_ess": 420},
                    "gibbs": {"sweeps": 650},
                    "sampler_settings": {"chains": 2, "warmup": 250, "draws": 400},
                }
            )
        )
        (r / "modal" / "modal.json").write_text(
            json.dumps(
                {
                    "gpu": "NVIDIA A100-SXM4-40GB, 40960 MiB, 550.54",
                    "wall_seconds": 180.0,
                    "stage_seconds": 12.0,
                    "stages": {"fit": 160.0},
                    "jax_cache": {"before": 3, "after": 3},
                }
            )
        )
        (r / "modal" / "fit.log").write_text(
            "first sweep (compile) 14.2s\nsampling 120.0s, 0.185s a sweep of 2 chains\n"
        )
        np.savez_compressed(
            r / "pred_scores.npz",
            elpd=elpd,
            cdf=cdf,
            listing=listings,
            building=buildings,
            day=days,
        )
        return r

    r_base = make_run("base", elpd_b, cdf_b)
    r_cand = make_run("cand", elpd_c, cdf_c)
    rep = screen.compare_runs(r_base, r_cand)
    assert rep["scale_factor"] == pytest.approx(10.0)
    assert rep["projected_full"]["delta"] == pytest.approx(rep["all"]["delta"] * 10.0)
    assert rep["bayesian"]["verdict"] == "GO"
    assert rep["candidate"]["compile_seconds"] == pytest.approx(14.2)
    assert rep["candidate"]["seconds_per_sweep"] == pytest.approx(0.185)
    assert rep["efficiency"]["screens_per_hour"] == pytest.approx(20.0)
    assert math.isfinite(rep["efficiency"]["ig_bits_per_min"])
    txt = screen.format_report(rep)
    assert "Screen verdict: GO" in txt
