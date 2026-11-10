import json
from datetime import date

import numpy as np
import pandas as pd

from rentfrontier import drift_deals


def _run(tmp_path, backtest=False):
    """A run directory with four held-out ads among six rows, predicted at log 3000 with
    little spread, and its dataset, ads and registry."""
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
    (run / "result.json").write_text(json.dumps({"dataset": str(data)}))
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
