import numpy as np
import pandas as pd
import pytest

from rentfrontier import features, sizefill


def test_earlier_sum_counts_only_earlier_days_with_the_key():
    day = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-02", "2020-01-03"])
    s, n = sizefill.earlier_sum(
        pd.Series(["a", "a", None, "b"]),
        pd.Series(day),
        pd.Series(["a", "a", "b"]),
        pd.Series(pd.to_datetime(["2020-01-01", "2019-12-01", "2020-01-02"])),
        pd.Series([1.0, 2.0, 5.0]),
    )
    # The same-day event (2020-01-01, 1.0) does not count for the first query.
    assert s.tolist() == [2.0, 3.0, 0.0, 5.0]
    assert n.tolist() == [1, 2, 0, 1]


def _frame():
    return pd.DataFrame(
        {
            "unit_id": ["u1", "u1", "u2", "u3", "u4", "u5"],
            "building": ["b"] * 6,
            "canonical_unit_url": [
                "x/building/b/2a",
                "x/building/b/2a",
                "x/building/b/3a",
                "x/building/b/5a",
                "x/building/b/4c",
                "x/building/b/7c",
            ],
            "bedrooms": [1, 1, 1, 1, 1, 2],
            "full_baths": [1, 1, 1, 1, 1, 1],
            "square_feet": [700.0, np.nan, 800.0, np.nan, np.nan, np.nan],
            "price_at": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-03-01",
                    "2020-02-01",
                    "2020-04-01",
                    "2020-01-15",
                    "2020-05-01",
                ],
                utc=True,
            ),
        }
    )


def test_asof_size_fills_unit_then_line_then_building_from_earlier_days():
    got = sizefill.asof_size(_frame())
    assert got.source.tolist() == ["own", "unit", "own", "line", "building", "none"]
    # u3 (line A, 1 bed): u1 from Jan 1 and u2 from Feb 1, geometric mean.
    assert got.sqft[3] == pytest.approx(np.sqrt(700 * 800))
    # u4 (line C) on Jan 15: only u1 had stated a size in the building.
    assert got.sqft[4] == pytest.approx(700)
    assert got.sqft[1] == pytest.approx(700)
    assert np.isnan(got.sqft[5])


def test_a_units_own_size_does_not_fill_it_as_another_unit():
    f = _frame().iloc[[0, 1]].reset_index(drop=True)
    f.loc[1, "unit_id"] = "u1"
    got = sizefill.asof_size(f.assign(unit_id=["u1", "u1"]))
    assert got.source.tolist() == ["own", "unit"]
    lone = sizefill.asof_size(f.iloc[[0]])
    assert lone.source.tolist() == ["own"]


def test_sizefill_v1_replaces_size_columns_and_adds_sources(monkeypatch):
    frame = _frame()
    names = ["log_sqft_vs_bedroom_median", "sqft_unknown", "x"]
    base = features.Features(
        "b", names, ["size", "size", "x"], np.ones((6, 3)), np.ones(3)
    )
    monkeypatch.setitem(features.FEATURE_SETS, "toy", lambda f, t: base)
    got = features.sizefill_v1(frame, np.ones(6, bool), id="t", base="toy")
    cols = dict(zip(got.names, got.values.T.tolist()))
    assert cols["sqft_unknown"] == [0, 0, 0, 0, 0, 1]
    assert cols["x"] == [1] * 6
    assert cols["size from the line"] == [0, 0, 0, 1, 0, 0]
    assert cols["size from the building"] == [0, 0, 0, 0, 1, 0]
    dev = cols["log_sqft_vs_bedroom_median"]
    assert dev[5] == 0.0
    assert dev[3] == pytest.approx(0.0)  # the 1-bed median of 700 and 800
    assert got.groups[-2:] == ["size", "size"]


def test_sizefill_set_is_registered_on_the_nb6_base():
    f = features.FEATURE_SETS["nb6-nostuy-sizefill-v1"]
    assert f.func is features.sizefill_v1
    assert f.keywords == {"id": "nb6-nostuy-sizefill-v1", "base": "nb6-nostuy-v1"}
    assert features.NB6_SETS["nb6-nostuy-sizefill-v1"] == "nb5-plutoasof-v3"
