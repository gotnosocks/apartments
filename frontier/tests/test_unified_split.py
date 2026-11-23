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
