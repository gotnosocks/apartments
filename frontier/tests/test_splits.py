

def test_latest_split_holds_out_only_each_units_last_listing():
    import numpy as np
    import pandas as pd

    from rentfrontier import splits

    rng = np.random.default_rng(1)
    n = 400
    frame = pd.DataFrame(
        {
            "audit_id": [f"a{i}" for i in range(n)],
            "unit_id": [f"u{i}" for i in rng.integers(0, 120, n)],
            "price_at": pd.to_datetime("2020-01-01", utc=True)
            + pd.to_timedelta(rng.integers(0, 2000, n), unit="D"),
        }
    )
    held = splits.latest_split(frame)
    assert held.sum() == round(0.1 * n)
    counts = frame.unit_id.value_counts()
    for row in frame[held].itertuples():
        same = frame[frame.unit_id == row.unit_id]
        assert counts[row.unit_id] >= 2
        # Nothing in its unit comes later, so no training row can read its ask.
        assert (same.price_at <= row.price_at).all()
    assert frame[held].unit_id.is_unique
    np.testing.assert_array_equal(held, splits.latest_split(frame))
    assert "latest" in splits.AFTER_RULES
