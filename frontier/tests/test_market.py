import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rentfrontier import building_attrs, market, splits
from rentfrontier.b0data import sha256


def _dataset(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    rows = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5"],
            "latest_ask": [3000.0, 3100, 3200, 3300, 3400],
            "latest_day": [
                date(2026, 1, 5),
                date(2026, 10, 1),
                date(2026, 10, 20),
                date(2026, 11, 2),
                date(2025, 6, 1),
            ],
            "price_at": pd.to_datetime(
                ["2026-01-01", "2026-09-20", "2026-10-01", "2026-10-30", "2025-05-01"],
                utc=True,
            ),
        }
    )
    rows.to_parquet(src / "rows.parquet", index=False)
    (src / "manifest.json").write_text(
        json.dumps({"rows": 5, "rows_sha256": sha256(src / "rows.parquet")})
    )
    ads = pd.DataFrame(
        {
            "listing_id": [4, 3, 2, 2, 9, 5],
            "status": [
                "ACTIVE",
                "RENTED",
                "TEMPORARILY_OFF_MARKET",
                "TEMPORARILY_OFF_MARKET",
                "ACTIVE",
                "RENTED",
            ],
            "first_day": [
                date(2026, 10, 30),
                date(2026, 10, 1),
                date(2026, 9, 20),
                date(2026, 9, 20),
                date(2026, 1, 1),
                date(2025, 5, 1),
            ],
            "first_ask": [3400.0, 3200, 3150, 3150, 1, 3500],
            "off_day": [None, date(2026, 10, 21), None, None, None, date(2025, 6, 3)],
        }
    )
    ads.to_parquet(tmp_path / "ads.parquet", index=False)
    return src, tmp_path / "ads.parquet"


def test_with_status_marks_the_open_ads_and_moves_them_to_the_scoring_day(tmp_path):
    src, ads = _dataset(tmp_path)
    out = tmp_path / "out"
    inputs = {"rentfrontier.market.INPUTS": "/x/inputs.json"}
    manifest = market.with_status(src, out, ads, inputs)
    frame = pd.read_parquet(out / "rows.parquet")
    assert frame.listing_id.tolist() == ["1", "2", "3", "4", "5"]
    # Listing 1 has no ad; listing 2's two ad rows are the same.
    assert frame.status.fillna("none").tolist() == [
        "none",
        "TEMPORARILY_OFF_MARKET",
        "RENTED",
        "ACTIVE",
        "RENTED",
    ]
    assert frame.first_ask.tolist()[1:] == [3150, 3200, 3400, 3500]
    held = splits.SPLITS["market"](frame)
    np.testing.assert_array_equal(held, [False, True, False, True, False])
    # The open rows sit on the newest day in the source; the others keep their days.
    days = pd.to_datetime(frame.latest_day).dt.date.tolist()
    assert days == [
        date(2026, 1, 5),
        date(2026, 11, 2),
        date(2026, 10, 20),
        date(2026, 11, 2),
        date(2025, 6, 1),
    ]
    assert pd.to_datetime(frame.final_day).dt.date.tolist()[1] == date(2026, 10, 1)
    at = pd.to_datetime(frame.price_at)
    assert str(at.dt.tz) == "UTC"
    assert at[1] == pd.Timestamp("2026-11-02", tz="UTC") and at[2] == pd.Timestamp(
        "2026-10-01", tz="UTC"
    )
    assert (
        manifest["market"]["open"] == 2
        and manifest["market"]["scoring_day"] == "2026-11-02"
    )
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert json.loads((out / "inputs.json").read_text()) == inputs
    with pytest.raises(ValueError, match="rentfrontier.market"):
        splits.market_split(frame.drop(columns="open"))


def test_as_of_builds_a_backtest_with_final_asks(tmp_path):
    src, ads = _dataset(tmp_path)
    out = tmp_path / "out"
    manifest = market.with_status(src, out, ads, as_of="2026-10-10")
    frame = pd.read_parquet(out / "rows.parquet")
    # Listing 1 has no ad, so its first day is its price_at day. Listing 3 was listed
    # before the day and closed after it. Listings 2 and 4 are still on the market, and
    # listing 5 closed before the day.
    assert frame.listing_id.tolist() == ["1", "3", "5"]
    assert frame.open.tolist() == [False, True, False]
    assert pd.to_datetime(frame.latest_day).dt.date.tolist()[1] == date(2026, 10, 10)
    assert pd.to_datetime(frame.final_day).dt.date.tolist()[1] == date(2026, 10, 20)
    assert frame.latest_ask.tolist() == [3000, 3200, 3400]
    aside = pd.read_parquet(out / "set_aside.parquet")
    assert aside.listing_id.tolist() == ["2", "4"]
    assert manifest["market"]["backtest"] and manifest["market"]["set_aside"] == 2
    assert manifest["rows"] == 3


def test_apply_inputs_points_the_named_constants_at_the_datasets_paths(
    tmp_path, monkeypatch
):

    monkeypatch.setattr(building_attrs, "REGISTRY", building_attrs.REGISTRY)
    name = "rentfrontier.building_attrs.REGISTRY"
    (tmp_path / "inputs.json").write_text(json.dumps({name: "/data/x"}))
    assert market.apply_inputs(tmp_path) == {name: "/data/x"}
    assert building_attrs.REGISTRY == Path("/data/x")
    assert market.apply_inputs(tmp_path / "none") == {}
    assert market.apply_inputs(None) == {}
    # Nothing but a path constant of a rentfrontier module can be named, and a file with one
    # bad entry changes nothing.
    for key, value in (
        ("rentfrontier.market.NOPE", "/x"),
        ("rentfrontier.market.INPUTS", "/x"),
        ("os.sep", "/x"),
        ("rentfrontier.building_attrs.PLUTO", 3),
    ):
        (tmp_path / "inputs.json").write_text(json.dumps({name: "/data/y", key: value}))
        with pytest.raises(ValueError, match=key.rsplit(".", 1)[1]):
            market.apply_inputs(tmp_path)
        assert building_attrs.REGISTRY == Path("/data/x")


def test_with_status_refuses_ad_rows_that_disagree(tmp_path):
    src, ads = _dataset(tmp_path)
    a = pd.read_parquet(ads)
    a.loc[3, "status"] = "DELISTED"
    a.to_parquet(ads, index=False)
    with pytest.raises(SystemExit, match="disagree"):
        market.with_status(src, tmp_path / "out", ads)


def test_backtest_sets_aside_a_closed_ad_whose_last_ask_is_later(tmp_path):
    """Listing 3 went off the market on 2026-10-21. With a last ask dated 2026-11-05 (a
    relisting), a backtest as of 2026-10-25 must not train on that ask."""
    src, ads = _dataset(tmp_path)
    rows = pd.read_parquet(src / "rows.parquet")
    at = rows.listing_id.astype(str) == "3"
    assert pd.Timestamp(rows.latest_day[at].iloc[0]) < pd.Timestamp("2026-10-25")
    market.with_status(src, tmp_path / "plain", ads, as_of="2026-10-25")
    plain = pd.read_parquet(tmp_path / "plain" / "rows.parquet")
    assert not plain.open[plain.listing_id.astype(str) == "3"].iloc[0]
    rows.loc[at, "latest_day"] = date(2026, 11, 5)
    rows.to_parquet(src / "rows.parquet", index=False)
    market.with_status(src, tmp_path / "late", ads, as_of="2026-10-25")
    late = pd.read_parquet(tmp_path / "late" / "rows.parquet")
    assert late.open[late.listing_id.astype(str) == "3"].iloc[0]
