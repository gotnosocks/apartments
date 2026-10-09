import numpy as np
import pandas as pd

from rentfrontier import features, nta, run


def _square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def test_inside_uses_even_odd_so_holes_are_outside():
    ring = {
        "type": "Polygon",
        "coordinates": [_square(0, 0, 4, 4), _square(1, 1, 2, 2)],
    }
    lon = np.array([0.5, 1.5, 3.0, 5.0])
    lat = np.array([0.5, 1.5, 3.0, 1.0])
    assert nta.inside(lon, lat, ring).tolist() == [True, False, True, False]
    multi = {
        "type": "MultiPolygon",
        "coordinates": [[_square(0, 0, 1, 1)], [_square(2, 0, 3, 1)]],
    }
    lon, lat = np.array([0.5, 1.5, 2.5]), np.array([0.5, 0.5, 0.5])
    assert nta.inside(lon, lat, multi).tolist() == [True, False, True]


def test_assign_names_each_building_and_leaves_out_points_in_none():
    areas = [
        {
            "geometry": {"type": "Polygon", "coordinates": [_square(0, 0, 1, 1)]},
            "properties": {"nta2020": "MN01", "ntaname": "A", "cdta2020": "MN04"},
        },
        {
            "geometry": {"type": "Polygon", "coordinates": [_square(1, 0, 2, 1)]},
            "properties": {"nta2020": "MN02", "ntaname": "B", "cdta2020": "MN04"},
        },
    ]
    buildings = pd.DataFrame(
        {
            "building": ["x", "y", "z", "w"],
            "latitude": [0.5, 0.5, 5.0, np.nan],
            "longitude": [0.5, 1.5, 5.0, 0.5],
        }
    )
    got = nta.assign(buildings, areas)
    assert got.building.tolist() == ["x", "y"]
    assert got.ntaname.tolist() == ["A", "B"]
    assert got.nta2020.tolist() == ["MN01", "MN02"]


def test_nta_v1_adds_areas_against_chelsea(monkeypatch, tmp_path):
    path = tmp_path / "nta.parquet"
    pd.DataFrame(
        {
            "building": ["a", "b"],
            "ntaname": ["Chelsea-Hudson Yards", "Gramercy"],
        }
    ).to_parquet(path)
    monkeypatch.setattr(features, "NTA_FILE", str(path))
    frame = pd.DataFrame({"building": ["a", "b", "c"]})
    base = features.Features("b", [], [], np.zeros((3, 0)), np.zeros(0))
    monkeypatch.setitem(features.FEATURE_SETS, "toy", lambda f, t: base)
    got = features.nta_v1(frame, np.ones(3, bool), id="t", base="toy")
    cols = dict(zip(got.names, got.values.T.tolist()))
    assert cols == {"nta=Gramercy": [0, 1, 0], "nta=unknown": [0, 0, 1]}
    assert got.groups == ["nta", "nta"]


def test_nta_set_is_registered_and_recorded(monkeypatch):
    f = features.FEATURE_SETS["nb6-nostuy-nta-v1"]
    assert f.func is features.nta_v1
    assert f.keywords == {"id": "nb6-nostuy-nta-v1", "base": "nb6-nostuy-v1"}
    assert features.NB6_SETS["nb6-nostuy-nta-v1"] == "nb5-plutoasof-v3"
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    assert run.feature_sources("nb6-nostuy-nta-v1")["nta"]["path"] == features.NTA_FILE
    assert "nta" not in run.feature_sources("nb6-nostuy-v1")
