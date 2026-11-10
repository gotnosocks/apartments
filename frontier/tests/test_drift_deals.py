import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from rentfrontier import drift_deals
from rentfrontier.b0data import sha256


def _run(tmp_path, backtest=False, model="drift-building"):
    """A run directory with four held-out ads among six rows, predicted at log 3000 with
    little spread, and its dataset (a market dataset, or a backtest), ads and registry."""
    tmp_path.mkdir(exist_ok=True)
    data = tmp_path / "data"
    data.mkdir()
    rows = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5", "6"],
            "building": ["a", "a", "b", "b", "b", "c"],
            "unit_id": ["u1", "u1", "u2", "u3", "u3", "u4"],
            "neighbourhood": ["Chelsea"] * 6,
            "bedrooms": [1.0] * 6,
            "full_baths": [1.0] * 6,
            "half_baths": [0.0] * 6,
            "latest_ask": [3000.0, 2700, 3000, 3300, 3000, 3000],
            "latest_day": [date(2026, 11, 9)] * 6,
            "final_day": [date(2026, 11, 20)] * 6,
            "status": ["RENTED", "ACTIVE", "ACTIVE", "ACTIVE", "RENTED", "ACTIVE"],
        }
    )
    rows.to_parquet(data / "rows.parquet", index=False)
    run = tmp_path / "runs" / "r"
    run.mkdir(parents=True)
    held = np.array([False, True, True, True, False, True])
    shape = (2, 50, 4)
    rng = np.random.default_rng(0)
    np.savez(
        run / "posterior.npz",
        heldout=held,
        **{
            "kept/pred_loc": np.log(3000) + 0.001 * rng.standard_normal(shape),
            "kept/pred_unit_sd": np.full(shape, 0.03),
            "kept/sigma": np.full((2, 50, 4), 0.05),
            "kept/nu": np.full((2, 50), 5.0),
            "kept/pred_y": np.log(rows.latest_ask.to_numpy()[held]),
            "kept/pred_group": np.ones(4, int),
        },
    )
    ads = pd.DataFrame(
        {
            "listing_id": [2, 3, 4, 6],
            "page": [
                f"https://streeteasy.com/building/x/{u}"
                for u in ("2a", "3b", "ph1", "4d")
            ],
            "square_feet": [700.0, np.nan, 800, 650],
            "months_free": [0.0, 1, 0, 0],
            "days_on_market": [3, 10, 40, 20],
            "first_day": [
                date(2026, 11, 1),
                date(2026, 10, 30),
                date(2026, 10, 1),
                date(2026, 10, 20),
            ],
            "first_ask": [2700.0, 3000, 3600, 3000],
            "status": ["ACTIVE"] * 4,
            "off_day": [
                date(2026, 11, 5),
                date(2026, 11, 20),
                date(2026, 11, 20),
                None,
            ],
        }
    )
    ads.to_parquet(tmp_path / "ads.parquet", index=False)
    manifest = {
        "rows_sha256": sha256(data / "rows.parquet"),
        "market": {
            "ads": str(tmp_path / "ads.parquet"),
            "ads_sha256": sha256(tmp_path / "ads.parquet"),
            "scoring_day": "2025-11-10" if backtest else "2026-11-09",
            "backtest": backtest,
        },
    }
    (data / "manifest.json").write_text(json.dumps(manifest))
    result = {
        "dataset": str(data),
        "dataset_observations_sha256": manifest["rows_sha256"],
        "split": "market",
        "model": {"name": model},
        "sampler_settings": {"chains": 4},
        "diagnostics": {"passes": True, "max_rhat": 1.004, "min_ess": 612.0},
    }
    (run / "result.json").write_text(json.dumps(result))
    reg = pd.DataFrame(
        {
            "building": ["a", "b", "c"],
            "label": [
                "134 WEST 23 STREET, New York, NY, USA",
                "1 EAST 2 STREET, New York",
                None,
            ],
            "latitude": [40.7, 40.71, 40.72],
            "longitude": [-74.0, -74.01, -74.02],
        }
    )
    reg.to_parquet(tmp_path / "registry.parquet", index=False)
    return run, tmp_path / "ads.parquet", tmp_path / "registry.parquet"


def test_deals_ranks_the_lowest_asks_first(tmp_path):
    run, ads, reg = _run(tmp_path)
    t = drift_deals.deals(run, ads, reg)
    assert t.listing_id.tolist()[0] == "2" and t.listing_id.tolist()[-1] == "4"
    assert (np.diff(t.below_share) >= 0).all()
    first = t.iloc[0]
    assert first.unit == "2A" and first.address == "134 West 23rd Street"
    assert first.url == "https://streeteasy.com/rental/2"
    # Listing 2 asks 2700 against a median near 3000: about 11% under, low in the range.
    assert 9 < first.discount_pct < 13 and first.below_share < 0.1
    assert 2950 < first.model_median < 3050
    assert first.model_lo80 < first.model_lo50 < first.model_median < first.model_hi50
    # Unit u1 has one training ad, u2 and u4 none.
    assert t.set_index("listing_id").unit_ads.to_dict() == {
        "2": 1,
        "3": 0,
        "4": 1,
        "6": 0,
    }
    mid = t.set_index("listing_id").loc["3"]
    assert 0.4 < mid.below_share < 0.6 and abs(mid.discount_pct) < 1


def test_validate_tabulates_outcomes_by_the_first_asks_place(tmp_path):
    run, ads, _ = _run(tmp_path)
    out = drift_deals.validate(run, ads, bins=2)
    assert out["ads_with_first_ask"] == 4
    low, high = out["by_first_ask_place"]
    # First asks 2700 and 3000 (twice, at the median) fall in the low or middle; 3600 is high.
    assert low["ads"] + high["ads"] == 4 and high["ads"] >= 1
    assert low["median_days_on_market"] < high["median_days_on_market"]
    assert high["share_cut"] > 0 and low["share_cut"] == 0
    assert out["final_ask_scores"]["rows"] == 4


def test_title_address_and_unit_label():
    assert drift_deals.title_address("1 EAST 2 STREET, New York") == "1 East 2nd Street"
    assert drift_deals.title_address("12 WEST 113 STREET") == "12 West 113th Street"
    assert drift_deals.title_address(None) == ""
    assert drift_deals.unit_label("https://streeteasy.com/building/x/6b?y=1") == "6B"
    assert drift_deals.unit_label(None) == ""


def _scored(tmp_path, **kw):
    run, ads, reg = _run(tmp_path, **kw)
    np.savez(run / "pred_scores.npz", **drift_deals.drift_score.score_run(run))
    return run, ads, reg


def test_publish_writes_the_sites_folder_from_the_runs_manifests(tmp_path, monkeypatch):
    run, _, reg = _scored(tmp_path / "m")
    past, _, _ = _scored(tmp_path / "b", backtest=True)
    out = tmp_path / "site" / "deals"
    meta = drift_deals.publish(run, out, reg, backtest=past, heldout=run)
    assert sorted(p.name for p in out.iterdir()) == [
        "deals.json",
        "meta.json",
        "validation.json",
    ]
    assert meta == json.loads((out / "meta.json").read_text())
    assert (meta["model"], meta["run"], meta["scoring_day"], meta["ads"]) == (
        "drift-building",
        "r",
        "2026-11-09",
        4,
    )
    assert meta["heldout"]["rows"] == 4 and meta["heldout"]["run"] == "r"
    assert meta["backtest_run"] == "r"
    passed = {"passes": True, "max_rhat": 1.004, "min_ess": 612.0, "chains": 4}
    assert meta["gate"] == {"market": passed, "heldout": passed, "backtest": passed}
    assert meta["deals_sha256"] == sha256(out / "deals.json")
    assert meta["validation_sha256"] == sha256(out / "validation.json")
    rows = json.loads((out / "deals.json").read_text())
    assert [r["listing_id"] for r in rows][0] == "2" and rows[0]["address"]
    check = json.loads((out / "validation.json").read_text())
    assert check["as_of"] == "2025-11-10" and check["ads_with_first_ask"] == 4
    # Without a backtest, the earlier publish's backtest goes.
    meta = drift_deals.publish(run, out)
    assert not (out / "validation.json").exists() and "validation_sha256" not in meta
    assert "address" not in json.loads((out / "deals.json").read_text())[0]
    # A fit that ran elsewhere names a path this machine lacks: the dataset of the same
    # name in this machine's datasets folder is used, when its rows are the run's.
    (tmp_path / "datasets").mkdir()
    (tmp_path / "m" / "data").rename(tmp_path / "datasets" / "data")
    monkeypatch.setattr(drift_deals.run_module, "RUNS", tmp_path / "runs")
    assert drift_deals.publish(run, out)["ads"] == 4
    manifest = tmp_path / "datasets" / "data" / "manifest.json"
    manifest.write_text(
        json.dumps(json.loads(manifest.read_text()) | {"rows_sha256": "0"})
    )
    with pytest.raises(SystemExit, match="not on this machine"):
        drift_deals.publish(run, out)


def test_publish_refuses_runs_in_the_wrong_places(tmp_path):
    run, _, _ = _scored(tmp_path / "m")
    past, _, _ = _scored(tmp_path / "b", backtest=True)
    other, _, _ = _scored(tmp_path / "o", backtest=True, model="drift")
    out = tmp_path / "site" / "deals"
    for kw, words in (
        (dict(run_dir=past), "not a run on the market split of the market"),
        (
            dict(run_dir=run, backtest=run),
            "not a run on the market split of a backtest",
        ),
        (dict(run_dir=run, backtest=other), "is a drift fit, not drift-building"),
        (dict(run_dir=run, heldout=other), "is a drift fit, not drift-building"),
    ):
        with pytest.raises(SystemExit, match=words):
            drift_deals.publish(out=out, **kw)
    # A latest-split run is not a market run, and a changed ads table is refused.
    result = json.loads((run / "result.json").read_text())
    (run / "result.json").write_text(json.dumps(result | {"split": "latest"}))
    with pytest.raises(SystemExit, match="not a run on the market split"):
        drift_deals.publish(run, out)
    (run / "result.json").write_text(json.dumps(result))
    ads = pd.read_parquet(tmp_path / "m" / "ads.parquet")
    ads.assign(first_ask=ads.first_ask + 1).to_parquet(tmp_path / "m" / "ads.parquet")
    with pytest.raises(SystemExit, match="changed since the dataset"):
        drift_deals.publish(run, out)
    assert not out.exists()


def test_publish_refuses_a_market_fit_that_missed_the_gate(tmp_path):
    run, _, reg = _scored(tmp_path / "m")
    past, _, _ = _scored(tmp_path / "b", backtest=True)
    out = tmp_path / "site" / "deals"
    missed = {"passes": False, "max_rhat": 1.03, "min_ess": 188.0}
    result = json.loads((run / "result.json").read_text())
    for diagnostics in (missed, None):
        (run / "result.json").write_text(
            json.dumps(result | {"diagnostics": diagnostics})
        )
        with pytest.raises(SystemExit, match="did not pass the convergence gate"):
            drift_deals.publish(run, out, reg, backtest=past)
        assert not out.exists()
    # A backtest that missed it is published with the market fit and marked.
    (run / "result.json").write_text(json.dumps(result))
    record = json.loads((past / "result.json").read_text())
    (past / "result.json").write_text(json.dumps(record | {"diagnostics": missed}))
    meta = drift_deals.publish(run, out, reg, backtest=past)
    assert meta["gate"]["market"]["passes"] and not meta["gate"]["backtest"]["passes"]
    assert meta["gate"]["backtest"]["max_rhat"] == 1.03
