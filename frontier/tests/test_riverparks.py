import json

import numpy as np
import pandas as pd

from rentfrontier import features, riverparks, run


def _square(x0, y0, x1, y1):
    ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def _tables():
    nyc = pd.DataFrame(
        {
            "name": ["Old Park", "Andrew Haswell Green Park", "Tiny"],
            "typecategory": ["Park"] * 3,
            "acres": [2.0, 2.0, 0.1],
            "acquired": pd.to_datetime(["1950-01-01", "2007-08-02", "1950-01-01"]),
            "geometry": [
                _square(-74.000, 40.740, -73.999, 40.741),
                _square(-73.960, 40.760, -73.959, 40.761),
                _square(-74.001, 40.740, -74.0005, 40.7405),
            ],
        }
    )
    river = pd.DataFrame(
        {
            "name": ["Hudson River Park esplanade", "Little Island"],
            "opened": pd.to_datetime(["2003-05-30", "2021-05-21"]),
            "source": ["jr73-mxkz", "osm"],
            "key": ["x", "W1"],
            "geometry": [
                _square(-74.011, 40.730, -74.010, 40.750),
                _square(-74.0125, 40.7415, -74.0115, 40.7425),
            ],
        }
    )
    return nyc, river


def test_places_dates_opened_parks_and_marks_the_new_piers():
    nyc, river = _tables()
    got = riverparks.places(nyc, river).set_index("name")
    # Without OPENED, parks.places refuses a park acquired after 2000.
    assert got.loc["Andrew Haswell Green Park", "opened"] == pd.Timestamp("2023-12-19")
    assert got.loc["Little Island", "kind"] == "river pier"
    assert got.loc["Hudson River Park esplanade", "kind"] == "park"
    assert "Tiny" not in got.index


def test_terms_count_places_open_before_the_month(monkeypatch, tmp_path):
    nyc, river = _tables()
    nyc.to_parquet(tmp_path / "parks.parquet")
    river.to_parquet(tmp_path / "river.parquet")
    pd.DataFrame(
        {
            "building": ["near", "far"],
            "latitude": [40.742, 40.742],
            "longitude": [-74.0105, -73.9995],
        }
    ).to_parquet(tmp_path / "registry.parquet")
    monkeypatch.setattr(
        features, "lot_registry", lambda: str(tmp_path / "registry.parquet")
    )
    frame = pd.DataFrame(
        {
            "building": ["near", "near", "far", "nowhere"],
            "period": ["2021-05", "2021-06", "2021-06", "2021-06"],
        }
    )
    got = riverparks.terms(
        frame, str(tmp_path / "parks.parquet"), str(tmp_path / "river.parquet")
    )
    # Little Island counts from the month after it opened, near the river only.
    assert got.pier.tolist()[:3] == [0.0, 1.0, 0.0]
    assert np.isnan(got.pier[3]) and np.isnan(got.park_min[3])
    # The esplanade is the nearest park for the river building.
    assert got.park_min[0] < 2.0
    assert got.park_min[2] < 2.0
    assert got.high_line.tolist()[:3] == [0.0, 0.0, 0.0]


def test_riverparks_set_is_registered_and_recorded(monkeypatch):
    f = features.FEATURE_SETS["nb6-nostuy-riverparks-v1"]
    assert f.func is features.riverparks_v1
    assert f.keywords == {"id": "nb6-nostuy-riverparks-v1", "base": "nb6-nostuy-v1"}
    assert features.NB6_SETS["nb6-nostuy-riverparks-v1"] == "nb5-plutoasof-v3"
    assert (
        features.PARKS_SNAPSHOTS["nb6-nostuy-riverparks-v1"] == features.NB6_PARKS_FILE
    )
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    sources = run.feature_sources("nb6-nostuy-riverparks-v1")
    assert sources["riverparks"]["path"] == features.RIVERPARKS_FILE
    assert sources["parks"]["path"] == features.NB6_PARKS_FILE
    assert "riverparks" not in run.feature_sources("nb6-nostuy-v1")
