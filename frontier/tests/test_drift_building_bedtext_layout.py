"""The served model with levels for an ad whose coded bedrooms or baths differ from the
apartment's previous ad (`rentfrontier.drift_building_bedtext_layout`)."""

import numpy as np
import pandas as pd
import test_drift as td

from rentfrontier import drift_building_bedtext, run
from rentfrontier import drift_building_bedtext_layout as M


def _frame():
    """Apartment b|u: 1 bed 1 bath, then 2 beds (held out), then 2 beds 1.5 baths, then a
    later piece "u~1" at 4 beds. Apartment b|w has the same unit id in no other building's
    rows; c|u is another building's unit u. The last row has no unit id."""
    rows = [
        ("b", "u", "2024-01-01", 1, 1, 0),
        ("b", "u", "2024-02-01", 2, 1, 0),
        ("b", "u", "2024-03-01", 2, 1, 1),
        ("b", "u~1", "2024-04-01", 4, 1, None),
        ("b", "w", "2024-01-05", 3, 2, 0),
        ("b", "w", "2024-01-05", 2, 2, 0),
        ("b", "w", "2024-02-05", 2, None, 0),
        ("c", "u", "2024-05-01", 0, 1, 0),
        ("c", None, "2024-06-01", 5, 3, 0),
    ]
    f = pd.DataFrame(
        rows,
        columns=[
            "building",
            "unit_id",
            "price_at",
            "bedrooms",
            "full_baths",
            "half_baths",
        ],
    )
    f["price_at"] = pd.to_datetime(f.price_at, utc=True)
    return f


def test_previous_is_the_latest_earlier_training_row_of_the_apartment():
    f = _frame()
    train = np.ones(len(f), bool)
    train[1] = False
    p = M.previous(f, train)
    # Row 2 skips the held-out row 1; row 3 (a later piece) finds row 2; rows 4 and 5
    # share a day and neither is earlier than the other; row 6 takes row 5, the last of
    # that day.
    np.testing.assert_array_equal(
        p.prev_beds.to_numpy(), [np.nan, 1, 1, 2, np.nan, np.nan, 2, np.nan, np.nan]
    )
    np.testing.assert_array_equal(
        p.prev_baths.to_numpy(), [np.nan, 1, 1, 1.5, np.nan, np.nan, 2, np.nan, np.nan]
    )


def test_changes_mark_a_count_above_or_below_the_previous_ad():
    f = _frame()
    train = np.ones(len(f), bool)
    train[1] = False
    x = M.changes(f, train)
    expect = np.zeros((len(f), 4))
    expect[1, 0] = 1  # 2 beds after 1
    expect[2, [0, 2]] = 1  # 2 beds and 1.5 baths after 1 and 1
    expect[3, [0, 3]] = 1  # 4 beds after 2, 1 bath after 1.5
    np.testing.assert_array_equal(x, expect)
    # A fall in the count sets the "down" column.
    g = f.iloc[[2, 0]].assign(
        price_at=pd.to_datetime(["2024-01-01", "2024-02-01"], utc=True)
    )
    np.testing.assert_array_equal(
        M.changes(g.reset_index(drop=True), np.ones(2, bool)),
        [[0, 0, 0, 0], [0, 1, 0, 1]],
    )


def test_design_is_the_served_design_with_the_layout_columns(monkeypatch):
    d = td._design(n=400)
    n = len(d.y)
    frame = pd.DataFrame(
        {
            "building": ["b"] * n,
            "unit_id": ["u"] * 3 + [f"v{i}" for i in range(3, n)],
            "price_at": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "bedrooms": [1, 2, 1] + [1] * (n - 3),
            "full_baths": [1.0] * n,
            "half_baths": [0.0] * n,
        }
    )
    held = np.zeros(n, bool)
    seen = {}

    def served(f, start=None, held=None, **kw):
        seen["held"] = held
        return d

    monkeypatch.setattr(drift_building_bedtext, "design", served)
    out = M.design(frame, held=held)
    np.testing.assert_array_equal(seen["held"], held)
    k = len(d.names)
    # No row's bath count changes, so `append` leaves the bath columns out.
    assert list(out.names) == [*d.names, "ad:beds_up_prev", "ad:beds_down_prev"]
    np.testing.assert_array_equal(out.x[:, :k], d.x)
    np.testing.assert_array_equal(out.x[:4, k:], [[0, 0], [1, 0], [0, 1], [0, 0]])
    rec = M.run_record(out)
    assert rec["layout"]["columns"] == ["ad:beds_up_prev", "ad:beds_down_prev"]
    assert rec["layout"]["rows"] == {
        "ad:beds_up_prev": 1,
        "ad:beds_down_prev": 1,
        "ad:baths_up_prev": 0,
        "ad:baths_down_prev": 0,
    }


def test_the_sampler_and_settings_are_the_served_models():
    assert M.run is drift_building_bedtext.run
    assert M.GROUPS == drift_building_bedtext.GROUPS
    assert M.LEVEL_DOF == drift_building_bedtext.LEVEL_DOF


def test_run_lists_the_model():
    assert M.NAME == "drift-building-bedtext-layout"
    assert (
        '("drift-building-bedtext-layout", "drift_building_bedtext_layout")'
        in open(run.__file__).read()
    )
