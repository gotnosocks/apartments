import json

import numpy as np
import pandas as pd
import pytest

from rentfrontier import market, splits
from rentfrontier.b0data import sha256


def _dataset(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    rows = pd.DataFrame(
        {"listing_id": ["1", "2", "3", "4"], "latest_ask": [3000, 3100, 3200, 3300]}
    )
    rows.to_parquet(src / "rows.parquet", index=False)
    (src / "manifest.json").write_text(
        json.dumps({"rows": 4, "rows_sha256": sha256(src / "rows.parquet")})
    )
    ads = pd.DataFrame(
        {
            "listing_id": [4, 3, 2, 2, 9],
            "status": [
                "ACTIVE",
                "RENTED",
                "TEMPORARILY_OFF_MARKET",
                "DELISTED",
                "ACTIVE",
            ],
            "first_day": pd.to_datetime(["2026-11-01"] * 5),
            "first_ask": [3400, 3200, 3150, 1, 1],
            "off_day": pd.to_datetime([None, "2026-10-20", None, None, None]),
        }
    )
    ads.to_parquet(tmp_path / "ads.parquet", index=False)
    return src, tmp_path / "ads.parquet"


def test_with_status_joins_the_ads_and_the_market_split_holds_out_open_ads(tmp_path):
    src, ads = _dataset(tmp_path)
    out = tmp_path / "out"
    inputs = {"rentfrontier.market.INPUTS": "/x/inputs.json"}
    manifest = market.with_status(src, out, ads, inputs)
    frame = pd.read_parquet(out / "rows.parquet")
    assert frame.listing_id.tolist() == ["1", "2", "3", "4"]
    # Listing 1 has no ad; listing 2 keeps its first ad row.
    assert frame.status.fillna("none").tolist() == [
        "none",
        "TEMPORARILY_OFF_MARKET",
        "RENTED",
        "ACTIVE",
    ]
    assert frame.first_ask.tolist()[1:] == [3150, 3200, 3400]
    np.testing.assert_array_equal(
        splits.SPLITS["market"](frame), [False, True, False, True]
    )
    assert manifest["market"]["open"] == 2
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert json.loads((out / "inputs.json").read_text()) == inputs
    with pytest.raises(ValueError, match="rentfrontier.market"):
        splits.market_split(frame.drop(columns="status"))


def test_apply_inputs_points_the_named_constants_at_the_datasets_paths(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(market, "COLUMNS", market.COLUMNS)
    (tmp_path / "inputs.json").write_text(
        json.dumps({"rentfrontier.market.COLUMNS": "/data/x.parquet"})
    )
    assert market.apply_inputs(tmp_path) == {
        "rentfrontier.market.COLUMNS": "/data/x.parquet"
    }
    assert str(market.COLUMNS) == "/data/x.parquet"
    assert market.apply_inputs(tmp_path / "none") == {}
    assert market.apply_inputs(None) == {}
    (tmp_path / "inputs.json").write_text(
        json.dumps({"rentfrontier.market.NOPE": "/x"})
    )
    with pytest.raises(AttributeError, match="NOPE"):
        market.apply_inputs(tmp_path)
