"""The base model with a level for ads whose text describes a smaller unit than the coded
count (`rentfrontier.drift_building_bedtext`)."""

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import drift, drift_building, run
from rentfrontier import drift_building_bedtext as M
from rentfrontier import drift_building_phase_unitkn_level_bedtext as L2B


def test_a_frame_without_the_source_columns_is_refused():
    frame = pd.DataFrame({"bedrooms": [1, 2], "bed_flex_at": [True, False]})
    with pytest.raises(ValueError, match="has no bed_text_fewer "):
        M.design(frame)


def test_design_is_the_base_design_with_the_two_flag_columns(monkeypatch):
    d = td._design(n=400)
    n = len(d.y)
    flex = np.zeros(n, bool)
    flex[[0, 5]] = True
    frame = pd.DataFrame(
        {
            "building": ["b"] * 3 + [f"c{i}" for i in range(3, n)],
            "unit_id": ["u"] * 3 + [f"v{i}" for i in range(3, n)],
            "price_at": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "bed_flex_at": flex,
            "bed_text_fewer": np.zeros(n, bool),
        }
    )
    held = np.zeros(n, bool)
    held[2] = True
    seen = {}

    def base(f, start=None, held=None, **kw):
        seen["held"] = held
        return d

    monkeypatch.setattr(drift, "design", base)
    out = M.design(frame, held=held)
    np.testing.assert_array_equal(seen["held"], held)
    k = len(d.names)
    assert list(out.names) == [*d.names, L2B.COLUMN, "umean:" + L2B.COLUMN]
    np.testing.assert_array_equal(out.x[:, :k], d.x)
    np.testing.assert_array_equal(out.x[:6, k], [1, 0, 0, 0, 0, 1])
    # Row 2 is held out and unflagged: its mean is over itself and rows 0 and 1.
    np.testing.assert_allclose(out.x[:3, k + 1], [1, 0.5, 1 / 3])
    rec = M.run_record(out)
    assert rec["bed_text"]["columns"] == [L2B.COLUMN, "umean:" + L2B.COLUMN]
    assert rec["bed_text"]["rows"] == 2


def test_the_sampler_and_settings_are_the_base_models():
    assert M.run is drift_building.run
    assert M.GROUPS == drift_building.GROUPS and M.LEVEL_DOF == drift_building.LEVEL_DOF


def test_run_lists_the_model():
    assert M.NAME == "drift-building-bedtext"
    assert (
        '("drift-building-bedtext", "drift_building_bedtext")'
        in open(run.__file__).read()
    )
