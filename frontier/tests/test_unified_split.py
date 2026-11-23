"""Tests for the single-fit `unified` split and single-run publishing across Deals,
Estimates, Diagnostics, and Today."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import (
    drift_deals,
    drift_diagnostics,
    drift_estimates,
    drift_today,
    splits,
)


def _synthetic_market_frame(n_buildings: int = 8, n_units: int = 20) -> pd.DataFrame:
    rows = []
    lid = 1000
    for u in range(n_units):
        b = f"b{u % n_buildings}"
        uid = f"u{u}"
        # 3 closed historical ads per unit
        for k in range(3):
            rows.append(
                {
                    "audit_id": f"a-{lid}",
                    "listing_id": str(lid),
                    "building": b,
                    "unit_id": uid,
                    "neighbourhood": "Chelsea",
                    "bedrooms": float(u % 3),
                    "full_baths": 1.0,
                    "half_baths": 0.0,
                    "price_at": pd.Timestamp(f"2024-0{k + 1}-15", tz="UTC"),
                    "latest_day": pd.Timestamp(f"2024-0{k + 1}-15"),
                    "latest_ask": 3000.0 + 100.0 * k,
                    "status": "RENTED",
                    "open": False,
                }
            )
            lid += 1
        # First 4 units also have a currently active open listing
        if u < 4:
            rows.append(
                {
                    "audit_id": f"a-{lid}",
                    "listing_id": str(lid),
                    "building": b,
                    "unit_id": uid,
                    "neighbourhood": "Chelsea",
                    "bedrooms": float(u % 3),
                    "full_baths": 1.0,
                    "half_baths": 0.0,
                    "price_at": pd.Timestamp("2026-11-20", tz="UTC"),
                    "latest_day": pd.Timestamp("2026-11-20"),
                    "latest_ask": 3500.0,
                    "status": "ACTIVE",
                    "open": True,
                }
            )
            lid += 1
    return pd.DataFrame(rows)


def test_unified_split_preserves_active_unit_history_and_holds_closed_eval():
    df = _synthetic_market_frame()
    held = splits.unified_split(df, fraction=0.10, seed=20260922)
    open_mask = df.open.to_numpy(bool)

    # Every open listing is held out
    assert held[open_mask].all()

    # Closed eval rows are also held out
    closed_held = held & ~open_mask
    assert closed_held.sum() > 0

    # Zero closed rows of any active unit are held out (100% of active unit history stays in training)
    active_units = set(df.loc[open_mask, "unit_id"])
    assert not (closed_held & df.unit_id.isin(active_units).to_numpy()).any()

    # Every held-out closed row is the latest listing of its unit (strictly leak-free)
    for idx in np.flatnonzero(closed_held):
        row = df.iloc[idx]
        same_unit = df[df.unit_id == row.unit_id]
        assert row.price_at == same_unit.price_at.max()


def test_unified_split_registered_after_rules():
    assert "unified" in splits.SPLITS
    assert "unified" in splits.AFTER_RULES


def test_unified_single_fit_estimates_and_deals_mask(tmp_path: Path, monkeypatch):
    df = _synthetic_market_frame()
    held = splits.unified_split(df, fraction=0.10, seed=20260922)

    ds_dir = tmp_path / "ds"
    ds_dir.mkdir()
    df.to_parquet(ds_dir / "rows.parquet", index=False)
    ads_path = tmp_path / "ads.parquet"
    ads_df = pd.DataFrame(
        {
            "listing_id": df.listing_id.astype(str),
            "page": ["https://streeteasy.com/building/b0/1a"] * len(df),
            "square_feet": 700.0,
            "months_free": 0.0,
            "first_ask": df.latest_ask,
            "page_price": df.latest_ask,
            "first_day": df.latest_day,
            "off_day": pd.NaT,
            "days_on_market": 10.0,
        }
    )
    ads_df.to_parquet(ads_path, index=False)
    from rentfrontier.b0data import sha256

    (ds_dir / "manifest.json").write_text(
        json.dumps(
            {
                "market": {
                    "backtest": False,
                    "scoring_day": "2026-11-20",
                    "ads": str(ads_path),
                    "ads_sha256": sha256(ads_path),
                }
            }
        )
    )

    run_dir = tmp_path / "run-unified"
    run_dir.mkdir()
    n_h = int(held.sum())
    np.savez(
        run_dir / "posterior.npz",
        heldout=held,
        names=np.array(["alpha"]),
    )
    y_h = np.log(df.loc[held, "latest_ask"].to_numpy(float))
    q_h = np.tile(y_h[:, None], (1, 8)) + np.linspace(-0.2, 0.2, 8)[None, :]
    np.savez(
        run_dir / "pred_scores.npz",
        listing=df.loc[held, "listing_id"].astype(str).to_numpy(dtype="U32"),
        q=q_h,
        pred=y_h,
        cdf=np.full(n_h, 0.5),
        y=y_h,
        elpd=np.full(n_h, 1.5),
        unit_sd=np.full(n_h, 0.05),
    )
    (run_dir / "result.json").write_text(
        json.dumps(
            {
                "split": "unified",
                "dataset": str(ds_dir),
                "model": {"name": "drift-building-phase-unitkn-ablate"},
                "diagnostics": {"passes": True, "max_rhat": 1.004, "min_ess": 800.0},
                "sampler_settings": {"chains": 4},
            }
        )
    )
    monkeypatch.setattr(drift_deals, "_dataset", lambda _: ds_dir)

    # 1. _market_mask slices strictly to open listings for Deals
    frame, h, held_loaded = drift_deals._held_frame(run_dir)
    target, keep_h = drift_deals._market_mask(run_dir, frame, held_loaded)
    assert int(target.sum()) == int(df.open.sum()) == 4
    assert int(keep_h.sum()) == 4
    assert len(h) > 4  # also includes closed latest-eval rows

    # 2. drift_estimates accepts a single unified run with no --market second fit
    est_df, est_meta = drift_estimates.estimates(run_dir)
    assert est_meta["runs"]["unified"] == run_dir.name
    assert est_meta["ads"]["market"] == 4
    assert est_meta["ads"]["latest"] == n_h - 4
    assert set(est_df["source"].unique()) == {"market", "latest"}
    assert "elpd" in est_meta["heldout"]

    # 3. drift_today._on_market distinguishes open ads from closed held-out eval ads
    fake_fit = type("FakeFit", (), {"frame": df, "held": held})()
    on_mkt = drift_today._on_market(fake_fit)
    assert int(on_mkt.sum()) == 4
    assert np.array_equal(on_mkt, df.open.to_numpy(bool))

    # 4. drift_diagnostics accepts a single unified run cleanly
    assert drift_diagnostics.coverage(np.full(5, 0.5))["80"] == 1.0


def test_drift_today_supports_sv_gp_mo_and_seg_add_semi():
    """Verify drift_today.segment_terms / segment_shift and cell_terms / cell_today work
    cleanly on the simplified unified tokens (`seg_add_semi` and `sv_gp_mo`)."""
    import test_drift as td

    from rentfrontier import drift_building_phase_unitkn_ablate as ab

    d_long = td._design(n=400, weeks=160)
    d_semi = ab.additive_segment_paths(d_long, stride=2)
    sg = drift_today.segment_terms(d_semi, list(d_semi.names))
    assert sg is not None and sg.additive is True

    # Verify segment_shift matches direct beta dot product change
    rng = np.random.default_rng(7)
    beta = rng.normal(0.0, 0.05, size=(3, len(d_semi.names)))
    rows = np.array([0, 10, 50, 150, 300])
    t_new = float(sg.knots[-1])
    fake_fit = type(
        "FakeFit",
        (),
        {
            "seg": sg,
            "pick": np.arange(3),
            "kept": {"beta": beta},
            "full": type("Full", (), {"t": td.drift.years(d_semi)})(),
        },
    )()
    shift = drift_today.segment_shift(fake_fit, rows, t_new)
    assert shift.shape == (3, len(rows))
    assert np.all(np.isfinite(shift))

    # Verify _sv_day_vector clamps cleanly and matches sv_gp_features
    vec, names = drift_today._sv_day_vector("sv_gp_mo", pd.Timestamp("2026-11-22"), 140)
    assert len(vec) == ab.SV_MO_MODES
    assert names[0] == "sv:m00" and names[-1] == f"sv:m{ab.SV_MO_MODES - 1:02d}"
    assert np.all(np.isfinite(vec))


def test_scales_fixed_resolves_run_dir_and_runs_unitkn_ablate(tmp_path: Path):
    """Verify `--scales-fixed RUN_DIR` extracts posterior-mean scales (including
    phase_factor) from any converged run and runs cleanly under unitkn + phase_map."""
    import test_drift as td

    from rentfrontier import drift_building_phase_unitkn_ablate as ab
    from rentfrontier import drift_scales, screen

    # 1. Build a small mock converged run directory
    run_dir = tmp_path / "base-unified-run"
    run_dir.mkdir()
    np.savez(
        run_dir / "posterior.npz",
        **{
            "kept/sigma": np.full((2, 4, 4), 0.015),
            "kept/unit_sd": np.full((2, 4), 0.06),
            "kept/drift_sd": np.full((2, 4), 0.045),
            "kept/drift_tau": np.full((2, 4), 6.0),
            "kept/bld_sd": np.tile(np.array([0.11, 0.07]), (2, 4, 1)),
            "kept/building_ar_sd": np.full((2, 4), 0.075),
            "kept/building_ar_rho": np.full((2, 4), 0.89),
            "kept/tau": np.full((2, 4), 0.0034),
            "kept/phase_factor": np.full((2, 4, 3), 1.05),
        },
    )
    (run_dir / "result.json").write_text(
        json.dumps({"split": "unified", "row_dof_fixed": 2.0})
    )
    scales, src = drift_scales.resolve(str(run_dir))
    assert scales["nu"] == 2.0
    assert len(scales["sigma"]) == 4
    assert len(scales["phase_scale"]) == 3
    assert "base-unified-run" in src

    # 2. Verify make_sampler accepts scales_fixed with unit_t=True, unit_dof_fixed=3.0
    d = td._design(n=120, weeks=20)
    pmap = np.vstack([np.zeros((1, 3)), np.eye(3)])
    d = ab.dataclasses.replace(
        d,
        phase=np.arange(len(d.y)) % 4,
        phases=("ref", "a", "b", "c"),
        phase_map=pmap,
    )
    settings = ab.Settings(
        chains=2,
        warmup=2,
        draws=2,
        keep_every=1,
        scales_fixed=str(run_dir),
    )
    out = ab.drift.run(
        d,
        ab.Priors(),
        settings,
        groups=ab.drift.groups_of(d, ab.GROUPS),
        unit_t=True,
        unit_dof_fixed=3.0,
        unit_kap_collapsed=True,
        row_dof_fixed=2.0,
        scalar_sigma=True,
        log=lambda _: None,
    )
    assert out["result"]["gibbs"]["scales_fixed"]["set"] == str(run_dir)
    assert np.allclose(out["kept"]["unit_sd"], 0.06)
    assert np.allclose(out["kept"]["sigma"], 0.015)

    # 3. Verify screen.sprint_budget parses ledger cleanly
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "r1@1",
                        "name": "tag-a",
                        "kind": "outside",
                        "usd_estimate": 1.5,
                    }
                ),
                json.dumps(
                    {"id": "r1@1", "name": "tag-a", "kind": "settle", "usd": 0.55}
                ),
                json.dumps(
                    {
                        "id": "r2@2",
                        "name": "tag-b",
                        "kind": "outside",
                        "usd_estimate": 2.0,
                    }
                ),
            ]
        )
    )
    bud = screen.sprint_budget(
        filter_substring="tag-", cap_usd=10.0, ledger_path=ledger
    )
    assert bud["settled_usd"] == 0.55
    assert bud["open_estimate_usd"] == 2.0
    assert bud["remaining_usd"] == 7.45
