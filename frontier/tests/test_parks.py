import json

import numpy as np
import pandas as pd
import pytest
from rentfrontier import features, parks


def _square(lon, lat, d=0.001):
    ring = [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]
    return json.dumps({"type": "MultiPolygon", "coordinates": [[ring]]})


def test_outline_adds_points_along_long_edges():
    points = parks.outline(json.loads(_square(-74.0, 40.74)), step=20.0)
    # Sides of about 84 m (5 steps) and 111 m (6 steps), and the closing point.
    assert len(points) == 2 * (5 + 6) + 1
    assert np.allclose(points[0], [-74.0, 40.74])
    gaps = np.abs(np.diff(points, axis=0)).max(1)
    assert gaps.max() < 0.0003


def _table(names, acres, acquired, geometries):
    return pd.DataFrame(
        {
            "name": names,
            "acres": acres,
            "acquired": pd.to_datetime(acquired),
            "geometry": geometries,
        }
    )


def test_places_keep_large_parks_and_split_the_high_line():
    line = [[-74.005, 40.740], [-74.004, 40.750], [-74.003, 40.752], [-74.004, 40.740]]
    spur = [
        [-74.0012, 40.7518],
        [-74.0007, 40.7518],
        [-74.0007, 40.7523],
        [-74.0012, 40.7518],
    ]
    high_line = {"type": "MultiPolygon", "coordinates": [[line], [spur]]}
    table = _table(
        ["Big", "Small", parks.HIGH_LINE],
        [2.0, 0.3, 6.7],
        ["1900-01-01", "1900-01-01", "2006-02-24"],
        [_square(-74.0, 40.74), _square(-74.01, 40.74), json.dumps(high_line)],
    )
    out = parks.places(table)
    assert out.name.tolist()[0] == "Big"
    line = out[out.kind == "high line"]
    assert line.opened.dt.year.tolist() == [2009, 2011, 2019]
    north = [p[:, 1].max() for p in line.points[:2]]
    assert north[0] < 40.7462 <= north[1]
    assert (line.points.iloc[2][:, 0] >= -74.0016).all()


def test_places_refuse_recent_or_undated_large_parks():
    for acquired in ["2015-08-14", None]:
        table = _table(["New"], [2.0], [acquired], [_square(-74.0, 40.74)])
        with pytest.raises(ValueError, match="add SECTIONS"):
            parks.places(table)


def test_park_terms_count_only_places_open_by_the_month(monkeypatch):
    minutes = pd.DataFrame([[3.0, 9.0, 2.0], [12.0, 8.0, 30.0]], index=["b1", "b2"])
    table = pd.DataFrame(
        {
            "kind": ["park", "park", "high line"],
            "opened": pd.to_datetime(["1900-01-01", None, "2009-06-08"]),
        }
    )
    monkeypatch.setattr(parks, "building_minutes", lambda: (minutes, table))
    frame = pd.DataFrame(
        {
            "building": ["b1", "b1", "b2", "b9"],
            "period": ["2009-06", "2009-07", "2009-07", "2009-07"],
        }
    )
    out = parks.park_terms(frame)
    assert out.park_min.tolist()[:3] == [3.0, 2.0, 8.0]
    assert out.high_line.tolist()[:3] == [0.0, 1.0, 0.0]
    assert np.isnan(out.park_min.iloc[3]) and np.isnan(out.high_line.iloc[3])


def test_parks_v1_adds_centred_walk_and_high_line(monkeypatch):
    terms = pd.DataFrame(
        {"park_min": [1.0, np.e**2, np.nan], "high_line": [1.0, 0.0, np.nan]}
    )
    monkeypatch.setattr(parks, "park_terms", lambda f: terms)
    base = features.Features("base", ["x"], ["unit"], np.ones((3, 1)), np.ones(1))
    monkeypatch.setitem(features.FEATURE_SETS, "base", lambda f, t: base)
    frame = pd.DataFrame({"building": ["b1", "b2", "b3"]})
    out = features.parks_v1(frame, np.ones(3, bool), id="t", base="base")
    assert out.names == ["x", "log walk min to a park", "High Line within 5 min"]
    assert np.allclose(out.values[:, 1], [-1.0, 1.0, 0.0])
    assert out.values[:, 2].tolist() == [1.0, 0.0, 0.0]
