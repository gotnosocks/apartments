import json

import numpy as np
import pandas as pd
import pytest
from test_drift_deals import _run

from rentfrontier import drift_estimates
from rentfrontier.b0data import sha256


def _latest(tmp_path, scored=True, **kw):
    """`_run`'s fit, recorded as a run on the latest split."""
    run, ads, reg = _run(tmp_path, **kw)
    result = json.loads((run / "result.json").read_text())
    (run / "result.json").write_text(json.dumps(result | {"split": "latest"}))
    if scored:
        np.savez(
            run / "pred_scores.npz",
            **drift_estimates.drift_score.score_run(run),
        )
    return run, reg


def test_publish_writes_the_held_out_ads_of_both_fits(tmp_path):
    latest, reg = _latest(tmp_path / "l")
    market, _, _ = _run(tmp_path / "m")
    out = tmp_path / "site" / "estimates"
    meta = drift_estimates.publish(latest, out, market, reg)
    assert sorted(p.name for p in out.iterdir()) == ["estimates.parquet", "meta.json"]
    assert meta == json.loads((out / "meta.json").read_text())
    assert meta["estimates_sha256"] == sha256(out / "estimates.parquet")
    assert meta["runs"] == {"latest": "r", "market": "r"}
    assert meta["scoring_day"] == "2026-11-09" and meta["heldout"]["rows"] == 4
    table = pd.read_parquet(out / "estimates.parquet")
    assert table.columns.tolist() == list(drift_estimates.COLUMNS)
    # Both fits held out the same four ads, so each appears once, from the market fit.
    assert meta["ads"] == {"all": 4, "latest": 0, "market": 4}
    assert sorted(table.listing_id) == ["2", "3", "4", "6"]
    assert set(table.source) == {"market"} and set(table.status) == {"ACTIVE"}
    row = table.set_index("listing_id").loc["4"]
    assert row.ask == 3300 and abs(row.model_median - 3000) < 30
    assert row.model_lo95 < row.model_lo80 < row.model_lo50 < row.model_median
    assert row.model_median < row.model_hi50 < row.model_hi80 < row.model_hi95
    assert row.below_share > 0.9 and row.discount_pct < 0
    assert row.address == "1 East 2nd Street"
    # Listing 4's unit u3 has listing 5 in training; listing 2's unit u1 has listing 1.
    assert table.set_index("listing_id").unit_ads.to_dict() == {
        "2": 1,
        "3": 0,
        "4": 1,
        "6": 0,
    }


def test_the_latest_fit_alone_and_without_saved_scores(tmp_path):
    latest, _ = _latest(tmp_path / "l", scored=False)
    frame, meta = drift_estimates.estimates(latest)
    assert meta["ads"] == {"all": 4, "latest": 4, "market": 0}
    assert set(frame.source) == {"latest"}
    assert meta["heldout"]["rows"] == 4 and frame.address.eq("").all()
    assert frame.day.tolist() == ["2026-11-09"] * 4


def test_saved_scores_of_other_ads_are_refused(tmp_path):
    latest, _ = _latest(tmp_path / "l")
    z = dict(np.load(latest / "pred_scores.npz"))
    z["listing"] = z["listing"][::-1]
    np.savez(latest / "pred_scores.npz", **z)
    with pytest.raises(SystemExit, match="does not score"):
        drift_estimates.estimates(latest)


def test_publish_refuses_wrong_splits_models_and_missed_gates(tmp_path):
    latest, _ = _latest(tmp_path / "l")
    market, _, _ = _run(tmp_path / "m")
    other, _, _ = _run(tmp_path / "o", model="drift")
    out = tmp_path / "site" / "estimates"
    with pytest.raises(SystemExit, match="not a run on the latest split"):
        drift_estimates.publish(market, out)
    with pytest.raises(SystemExit, match="not a run on the market split"):
        drift_estimates.publish(latest, out, latest)
    with pytest.raises(SystemExit, match="is a drift fit, not drift-building"):
        drift_estimates.publish(latest, out, other)
    result = json.loads((latest / "result.json").read_text())
    (latest / "result.json").write_text(
        json.dumps(result | {"diagnostics": {"passes": False, "max_rhat": 1.03}})
    )
    with pytest.raises(SystemExit, match="did not pass the convergence gate"):
        drift_estimates.publish(latest, out, market)
    assert not out.exists()


def test_an_ad_held_out_by_both_fits_takes_the_market_fits_row(tmp_path):
    def rename(rows):
        rows.loc[5, "listing_id"] = "60"

    latest, reg = _latest(tmp_path / "l", change=rename)
    market, _, _ = _run(tmp_path / "m")
    frame, meta = drift_estimates.estimates(latest, market, reg)
    assert meta["ads"] == {"all": 5, "latest": 1, "market": 4}
    assert frame.set_index("listing_id").source.to_dict() == {
        "2": "market",
        "3": "market",
        "4": "market",
        "6": "market",
        "60": "latest",
    }
    assert meta["datasets"]["latest"]["dataset"] == "data"


def test_a_backtest_or_a_changed_ads_table_is_not_the_market(tmp_path):
    latest, _ = _latest(tmp_path / "l")
    past, _, _ = _run(tmp_path / "b", backtest=True)
    with pytest.raises(SystemExit, match="not a run on the market split of the market"):
        drift_estimates.estimates(latest, past)
    market, ads, _ = _run(tmp_path / "m")
    frame = pd.read_parquet(ads)
    frame.assign(first_ask=frame.first_ask + 1).to_parquet(ads)
    with pytest.raises(SystemExit, match="changed since the dataset"):
        drift_estimates.estimates(latest, market)


def test_scores_of_another_target_are_refused(tmp_path):
    latest, _ = _latest(tmp_path / "l")
    z = dict(np.load(latest / "pred_scores.npz"))
    z["y"] = z["y"] + 0.1
    np.savez(latest / "pred_scores.npz", **z)
    with pytest.raises(SystemExit, match="not of its held-out asks"):
        drift_estimates.estimates(latest)
