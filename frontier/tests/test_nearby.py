import numpy as np
import pandas as pd
from rentfrontier import features, nearby


def test_nearest_walk_per_kind(tmp_path, monkeypatch):
    registry = tmp_path / "registry.parquet"
    places = tmp_path / "places.parquet"
    pd.DataFrame(
        {
            "building": ["a", "b"],
            "latitude": [40.0, np.nan],
            "longitude": [-74.0, np.nan],
        }
    ).to_parquet(registry)
    pd.DataFrame(
        {
            "kind": ["dog run", "dog run", "hospital"],
            "name": ["Old Run", "New Run", "H"],
            "latitude": [40.0, 40.01, 40.0],
            "longitude": [-74.0, -74.0, -73.99],
        }
    ).to_parquet(places)
    monkeypatch.setattr(features, "lot_registry", lambda: str(registry))
    monkeypatch.setattr(features, "PLACES_FILE", str(places))
    monkeypatch.setattr(
        features,
        "facing_grid",
        lambda: (
            lambda lon, lat: np.stack(
                [np.asarray(lon, float) * 1000, np.asarray(lat, float) * 1000], -1
            )
        ),
    )
    nearby._building_places.cache_clear()
    table = nearby.building_places()
    assert table.loc["a", "dog run"] == 0
    assert np.isclose(table.loc["a", "hospital"], 10)
    assert np.isnan(table.loc["a", "nycha"])
    monkeypatch.setattr(nearby, "OPENED", {"Old Run": "2015-03-01"})
    frame = pd.DataFrame(
        {"building": ["a", "b", "a"], "period": ["2015-03", "2015-03", "2015-02"]}
    )
    t = nearby.terms(frame)
    assert np.isclose(t["dog run"][0], np.log(nearby.FLOOR_M))
    assert np.isnan(t["dog run"][1])
    # Before Old Run opened, the nearest run is New Run, 10 m north.
    assert np.isclose(t["dog run"][2], np.log(nearby.FLOOR_M))
    assert nearby.building_places(frozenset({"Old Run"})).loc["a", "dog run"] == 10
    nearby._building_places.cache_clear()
