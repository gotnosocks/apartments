import numpy as np
import pandas as pd
import pytest
from rentfrontier import access


def test_ride_minutes_board_ride_and_alight():
    # Board at A (3 min wait), 2 min to B, 4 more to C.
    edges = {
        "A": [(("A", "1", "0"), 3.0)],
        ("A", "1", "0"): [(("B", "1", "0"), 2.0), ("A", 0.0)],
        ("B", "1", "0"): [(("C", "1", "0"), 4.0), ("B", 0.0)],
        ("C", "1", "0"): [("C", 0.0)],
    }
    ride = access.ride_minutes(edges, ["A", "B", "C"])
    assert ride[0].tolist() == [0.0, 5.0, 9.0]
    assert np.isinf(ride[2, 0])


def test_reach_walks_or_rides():
    at = np.array([[0.0, 0.0], [10_000.0, 0.0]])  # two stations 10 km apart
    ride = np.array([[0.0, 10.0], [np.inf, 0.0]])
    homes = np.array([[0.0, 400.0]])  # 5 minutes' walk from the first
    blocks = np.array(
        [
            [0.0, 2_000.0],  # 20 minutes' walk
            [10_000.0, 800.0],  # 5 + 10 + 10 minutes
            [10_000.0, 1_400.0],  # 5 + 10 + 17.5 minutes: too far
            [10_000.0, 2_000.0],  # beyond the walk from a station
        ]
    )
    np.testing.assert_array_equal(
        access.reach(homes, at, ride, blocks), [[True, True, False, False]]
    )


def test_jobs_year_lags_and_clamps():
    years = range(2002, 2024)
    assert access.jobs_year("2015-06", years) == 2013
    assert access.jobs_year("2003-01", years) == 2002
    assert access.jobs_year("2026-09", years) == 2023


def test_jobs_within_as_of_the_month(monkeypatch):
    now = pd.DataFrame({2012: [10.0, 20.0], 2013: [11.0, 21.0]}, index=["x", "y"])
    before = now - 5.0
    tables = {frozenset(): now, frozenset({"726"}): before}
    monkeypatch.setattr(
        access, "building_jobs", lambda exclude=frozenset(): tables[exclude]
    )
    frame = pd.DataFrame(
        {"building": ["x", "y", "z"], "period": ["2015-08", "2015-10", "2014-03"]}
    )
    out = access.jobs_within(frame)
    assert out[:2].tolist() == pytest.approx([6.0, 21.0])
    assert np.isnan(out[2])
