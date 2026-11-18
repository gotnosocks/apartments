"""The layout model with levels for an ad whose coded counts are above the lowest or below
the highest of the apartment's earlier ads
(`rentfrontier.drift_building_bedtext_layout_range`)."""

import numpy as np
import pandas as pd
import test_drift as td
from test_drift_building_bedtext_layout import _frame

from rentfrontier import drift_building_bedtext_layout, run
from rentfrontier import drift_building_bedtext_layout_range as M


def _unit(rows):
    f = pd.DataFrame(rows, columns=["price_at", "bedrooms", "full_baths"])
    f["price_at"] = pd.to_datetime(f.price_at, utc=True)
    return f.assign(building="b", unit_id="u", half_baths=0.0)


def test_earlier_range_is_the_lowest_and_highest_of_earlier_training_rows():
    f = _frame()
    train = np.ones(len(f), bool)
    train[1] = False
    r = M.earlier_range(f, train)
    nan = np.nan
    # Row 3 (a later piece of b|u) reads rows 0 and 2 and skips the held-out row 1. Rows 4
    # and 5 share a day, so neither is earlier than the other, and row 6 reads both.
    np.testing.assert_array_equal(r.low_beds, [nan, 1, 1, 1, nan, nan, 2, nan, nan])
    np.testing.assert_array_equal(r.high_beds, [nan, 1, 1, 2, nan, nan, 3, nan, nan])
    np.testing.assert_array_equal(r.low_baths, [nan, 1, 1, 1, nan, nan, 2, nan, nan])
    np.testing.assert_array_equal(r.high_baths, [nan, 1, 1, 1.5, nan, nan, 2, nan, nan])


def test_marks_compare_a_row_with_its_earlier_range():
    f = _frame()
    train = np.ones(len(f), bool)
    train[1] = False
    expect = np.zeros((len(f), 4))
    expect[1, 0] = 1  # 2 beds, 1 before
    expect[2, [0, 2]] = 1  # 2 beds and 1.5 baths, 1 and 1 before
    expect[3, [0, 3]] = 1  # 4 beds above 1; 1 bath below 1.5
    expect[6, 1] = 1  # 2 beds below 3; its bath count is missing
    np.testing.assert_array_equal(M.marks(f, train), expect)


def test_a_later_ad_at_the_changed_count_keeps_the_range_mark():
    f = _unit(
        [
            ("2024-01-01", 1, 1),
            ("2024-02-01", 2, 1),
            ("2024-03-01", 2, 1),
            ("2024-04-01", 1, 1),
        ]
    )
    train = np.ones(4, bool)
    np.testing.assert_array_equal(
        drift_building_bedtext_layout.changes(f, train)[:, :2],
        [[0, 0], [1, 0], [0, 0], [0, 1]],
    )
    np.testing.assert_array_equal(
        M.marks(f, train)[:, :2], [[0, 0], [1, 0], [1, 0], [0, 1]]
    )


def test_a_day_with_a_missing_count_carries_the_earlier_range():
    f = _unit(
        [
            ("2024-01-01", 1, 1),
            ("2024-02-01", 1, None),
            ("2024-03-01", 1, 2),
            ("2024-04-01", 1, 2),
        ]
    )
    r = M.earlier_range(f, np.ones(4, bool))
    np.testing.assert_array_equal(r.low_baths, [np.nan, 1, 1, 1])
    np.testing.assert_array_equal(r.high_baths, [np.nan, 1, 1, 2])
    np.testing.assert_array_equal(M.marks(f, np.ones(4, bool))[:, 2], [0, 0, 1, 1])


def test_design_is_the_layout_design_with_the_range_columns(monkeypatch):
    d = td._design(n=400)
    n = len(d.y)
    frame = pd.DataFrame(
        {
            "building": ["b"] * n,
            "unit_id": ["u"] * 3 + [f"v{i}" for i in range(3, n)],
            "price_at": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "bedrooms": [1, 2, 2] + [1] * (n - 3),
            "full_baths": [1.0] * n,
            "half_baths": [0.0] * n,
        }
    )
    held = np.zeros(n, bool)
    seen = {}

    def layout(f, start=None, held=None, **kw):
        seen["held"] = held
        return d

    monkeypatch.setattr(drift_building_bedtext_layout, "design", layout)
    out = M.design(frame, held=held)
    np.testing.assert_array_equal(seen["held"], held)
    k = len(d.names)
    # Only the first range column has a row set, so `append` leaves the others out.
    assert list(out.names) == [*d.names, "ad:beds_above_low"]
    np.testing.assert_array_equal(out.x[:, :k], d.x)
    np.testing.assert_array_equal(out.x[:4, k], [0, 1, 1, 0])
    rec = M.run_record(out)
    assert rec["layout_range"]["columns"] == ["ad:beds_above_low"]
    assert rec["layout_range"]["rows"] == {
        "ad:beds_above_low": 2,
        "ad:beds_below_high": 0,
        "ad:baths_above_low": 0,
        "ad:baths_below_high": 0,
    }


def test_the_sampler_and_settings_are_the_layout_models():
    assert M.run is drift_building_bedtext_layout.run
    assert M.GROUPS == drift_building_bedtext_layout.GROUPS
    assert M.LEVEL_DOF == drift_building_bedtext_layout.LEVEL_DOF


def test_run_lists_the_model():
    assert M.NAME == "drift-building-bedtext-layout-range"
    assert '"drift_building_bedtext_layout_range"' in open(run.__file__).read()
