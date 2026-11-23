import numpy as np
import pandas as pd
import pytest

from rentfrontier import splits


def frame():
    # Four units of two ads each; unit 2 has an open ad; unit 3's ads are recent.
    days = ["2023-01-01", "2023-06-01"] * 3 + ["2025-03-01", "2025-06-01"]
    return pd.DataFrame(
        {
            "audit_id": range(8),
            "building": [1] * 8,
            "unit_id": [0, 0, 1, 1, 2, 2, 3, 3],
            "price_at": pd.to_datetime(days[:5] + ["2025-06-01"] + days[6:], utc=True),
            "open": [False] * 5 + [True] + [False] * 2,
        }
    )


def test_holds_open_ads_and_old_latest_rows_of_units_with_no_open_ad():
    held = splits.one_fit_split(frame(), fraction=1.0)
    # Units 0 and 1: latest rows, over a year old. Unit 2: only its open ad. Unit 3: its
    # latest row is too recent, so it stays in training.
    assert held.tolist() == [False, True, False, True, False, True, False, False]
    assert splits.SPLITS["onefit"] is splits.one_fit_split
    assert "onefit" in splits.AFTER_RULES


def test_min_age_zero_is_the_plain_union():
    held = splits.one_fit_split(frame(), fraction=1.0, min_age_days=0)
    assert np.flatnonzero(held).tolist() == [1, 3, 5, 7]


def test_needs_a_market_dataset():
    with pytest.raises(ValueError, match="market"):
        splits.one_fit_split(frame().drop(columns="open"))
