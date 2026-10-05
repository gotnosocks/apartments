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
    # A unit whose two latest listings share a date is never held out.
    tied = frame.copy()
    tied.loc[len(tied)] = ["t1", "uT", pd.Timestamp("2025-01-01", tz="UTC")]
    tied.loc[len(tied)] = ["t2", "uT", pd.Timestamp("2025-01-01", tz="UTC")]
    assert not splits.latest_split(tied, fraction=0.9)[-2:].any()
    np.testing.assert_array_equal(held, splits.latest_split(frame))
    assert "latest" in splits.AFTER_RULES


def test_split_and_rules_draws_latest_after_the_rules(monkeypatch):
    import numpy as np
    import pandas as pd

    from rentfrontier import data, splits

    frame = pd.DataFrame(
        {
            "audit_id": ["a", "b", "c", "d"],
            "unit_id": ["u1", "u1b", "u2", "u2"],
            "building": ["b1", "b1", "b2", "b2"],
            "price_at": pd.to_datetime(
                ["2020-01-01", "2021-01-01", "2020-01-01", "2021-01-01"], utc=True
            ),
        }
    )
    # A rule that merges u1b into u1: only then is u1 a re-listed unit.
    monkeypatch.setitem(
        data.DATA_RULES, "merge-test", lambda f: f.assign(unit_id=f.unit_id.str[:2])
    )
    from functools import partial

    monkeypatch.setitem(
        splits.SPLITS, "latest", partial(splits.latest_split, fraction=0.5)
    )
    out, held = data.split_and_rules(frame, "latest", ["merge-test"])
    assert set(out.audit_id[held]) == {"b", "d"}
    # Other splits keep the old order: drawn first, rules after.
    a, ha = data.split_and_rules(frame, "all", ["merge-test"])
    assert not ha.any() and len(a) == 4
