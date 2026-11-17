"""L2 with a level for ads whose text describes a smaller unit than the coded count
(`rentfrontier.drift_building_phase_unitkn_level_bedtext`)."""

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import drift_building_phase_unitkn_level_bedtext as M
from rentfrontier import run


def test_flag_is_set_by_either_source_column():
    frame = pd.DataFrame(
        {
            "bed_flex_at": [True, False, False, None],
            "bed_text_fewer": [False, True, False, None],
        }
    )
    np.testing.assert_array_equal(M.flag(frame), [1, 1, 0, 0])


def test_a_frame_without_the_source_columns_is_refused():
    frame = pd.DataFrame({"bedrooms": [1, 2], "bed_flex_at": [True, False]})
    with pytest.raises(ValueError, match="has no bed_text_fewer ") as e:
        M.flag(frame)
    assert "rentfrontier.b0bedtext" in str(e.value)
    with pytest.raises(ValueError, match="has no bed_text_fewer "):
        M.design(frame)


def test_with_flag_appends_the_column_and_its_unit_mean():
    d = td._design(n=400)
    n = len(d.y)
    flex = np.zeros(n, bool)
    flex[[0, 5]] = True
    fewer = np.zeros(n, bool)
    fewer[1] = True
    # Rows 0 to 2 are ads of one unit, in date order; the others are units of their own.
    frame = pd.DataFrame(
        {
            "building": ["b"] * 3 + [f"c{i}" for i in range(3, n)],
            "unit_id": ["u"] * 3 + [f"v{i}" for i in range(3, n)],
            "price_at": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "bed_flex_at": flex,
            "bed_text_fewer": fewer,
        }
    )
    held = np.zeros(n, bool)
    held[1] = True
    out = M.with_flag(d, frame, held)
    names = list(out.names)
    assert names[: len(d.names)] == list(d.names)
    assert names[len(d.names) :] == [M.COLUMN, "umean:" + M.COLUMN]
    x = out.x[:, len(d.names) :]
    np.testing.assert_array_equal(x[:6, 0], [1, 1, 0, 0, 0, 1])
    # Row 1 is held out: its own mean holds it and row 0, and row 2's leaves it out.
    np.testing.assert_allclose(x[:3, 1], [1, 1, 0.5])
    np.testing.assert_allclose(x[5:, 1], x[5:, 0])
    assert out.count[M.COLUMN] == 3


def test_run_lists_the_model():
    assert M.NAME == "drift-building-phase-unitkn-level-bedtext"
    assert M.NAME in open(run.__file__).read()
