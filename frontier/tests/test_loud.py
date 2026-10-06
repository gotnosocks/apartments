import numpy as np
import pandas as pd
from rentfrontier import features, loud, quiet


def test_street_kind_splits_busy_from_quiet():
    assert (
        loud.street_kind("HUDSON ST", {"rw_type": "1", "streetwidth": "60"}) == "busy"
    )
    assert (
        loud.street_kind("BARROW ST", {"rw_type": "1", "streetwidth": "30"}) == "quiet"
    )
    assert loud.street_kind("8 AVE", {"rw_type": "1", "streetwidth": "40"}) == "busy"
    assert loud.street_kind("W  4 ST", {"rw_type": "1"}) == "quiet"
    assert loud.street_kind("HIGH LINE", {"rw_type": "13", "streetwidth": "80"}) is None


def test_busy_share():
    sides = pd.DataFrame(
        {
            "north": ["busy", "busy", "none", np.nan],
            "south": ["quiet", "none", "none", np.nan],
            "east": ["none", "no facade", "none", np.nan],
            "west": ["none", "none", "none", np.nan],
        }
    )
    assert loud.busy_share(sides).tolist() == [0.25, 1 / 3, 0.0, 0.0]
    assert loud.busy_share(sides, street_only=True).tolist() == [0.5, 1.0, 0.0, 0.0]


def test_unit_terms(monkeypatch):
    # Building b: north busy, south quiet, east and west no street.
    sides = pd.DataFrame(
        {"north": ["busy"], "south": ["quiet"], "east": ["none"], "west": ["none"]},
        index=["b"],
    )
    monkeypatch.setattr(loud, "building_street_sides", lambda: sides)
    monkeypatch.setattr(
        quiet,
        "building_streets",
        lambda: pd.DataFrame({"on_busy": [True]}, index=["b"]),
    )
    units = ["north", "north", "front", "back", "rear-line", "street-line", "unknown"]
    frame = pd.DataFrame({"unit_id": units, "building": "b"})
    for d in features.GRID_DIRECTIONS:
        frame[f"window_{d}"] = "unknown"
    frame.loc[0, "window_north"] = "yes"  # the second listing of "north" shows nothing
    front = np.array([False, False, True, False, False, False, False])
    rear = np.array([False, False, False, True, False, False, False])
    monkeypatch.setattr(features, "front_rear", lambda f: (front, rear))
    line = ["", "", "", "", "rear", "street", ""]
    monkeypatch.setattr(features, "line_orientation", lambda f: pd.Series(line))
    t = loud.unit_terms(frame)
    assert t["looks"].tolist() == [True, True, True, False, False, False, False]
    # Shown sides get no chance; the line narrows it; otherwise 1 of 4 facades.
    assert t["chance"].tolist() == [0, 0, 0, 0, 0, 0.5, 0.25]
