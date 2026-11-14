"""L1 with the stated private outdoor area in the means
(`rentfrontier.drift_building_phase_outdoorsize`)."""

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import drift_building_phase_outdoorsize as M
from rentfrontier.building_zones_kitchen_sink import append


def test_outdoor_columns_mark_the_area_its_log_and_the_uncoded_rows():
    frame = pd.DataFrame(
        {"outdoor_sqft": [500.0, np.nan, 1000.0, 250.0, np.nan, 2000.0]}
    )
    names = [
        "alpha",
        "ad:private_outdoor_terrace",
        "ad:feat_private_outdoor_space",
        "x",
    ]
    x = np.array(
        [
            [1, 1, 0, 5],
            [1, 1, 1, 5],
            [1, 0, 0, 5],
            [1, 0, 1, 5],
            [1, 0, 0, 5],
            [1, 0, 0, 0],
        ],
        float,
    )
    got_names, got = M.outdoor_columns(frame, names, x)
    assert got_names == list(M.COLUMNS)
    np.testing.assert_array_equal(got[:, 0], [1, 0, 1, 1, 0, 1])
    np.testing.assert_allclose(got[:, 1], [0, 0, 1, -1, 0, 2])
    np.testing.assert_array_equal(got[:, 2], [0, 0, 1, 0, 0, 1])


def test_a_frame_without_outdoor_sqft_is_refused():
    frame = pd.DataFrame({"bedrooms": [1, 2]})
    with pytest.raises(ValueError, match="has no outdoor_sqft ") as e:
        M.outdoor_columns(frame, ["alpha"], np.ones((2, 1)))
    assert "rentfrontier.b0outdoorsize" in str(e.value)
    with pytest.raises(ValueError, match="has no outdoor_sqft "):
        M.design(frame)


def test_with_outdoor_appends_the_columns_and_their_unit_means():
    d = td._design(n=400)
    n = len(d.y)
    coded = np.zeros((n, 1))
    coded[1, 0] = 1
    d = append(d, ["ad:private_outdoor_balcony"], coded)
    sqft = np.full(n, np.nan)
    sqft[[0, 1, 2, 5]] = [250.0, 1000.0, 500.0, 2000.0]
    # Rows 0 to 2 are ads of one unit, in date order; the others are units of their own.
    frame = pd.DataFrame(
        {
            "building": ["b"] * 3 + [f"c{i}" for i in range(3, n)],
            "unit_id": ["u"] * 3 + [f"v{i}" for i in range(3, n)],
            "price_at": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "outdoor_sqft": sqft,
        }
    )
    held = np.zeros(n, bool)
    held[1] = True
    out = M.with_outdoor(d, frame, held)
    names = list(out.names)
    assert names[: len(d.names)] == list(d.names)
    new = list(M.COLUMNS) + ["umean:" + c for c in M.COLUMNS]
    assert names[len(d.names) :] == new
    x = out.x[:, [names.index(c) for c in new]]
    np.testing.assert_array_equal(x[:6, 0], [1, 1, 1, 0, 0, 1])
    np.testing.assert_allclose(x[:6, 1], [-1, 1, 0, 0, 0, 2])
    np.testing.assert_array_equal(x[:6, 2], [1, 0, 1, 0, 0, 1])
    # Row 1 is held out: its own mean holds it and row 0, and row 2's leaves it out.
    np.testing.assert_allclose(x[:3, 4], [-1, 0, -0.5])
    np.testing.assert_allclose(x[:3, 5], [1, 0.5, 1])
    np.testing.assert_allclose(x[5:, 3:], x[5:, :3])
    assert out.count["ad:outdoor_sqft_stated"] == 4
