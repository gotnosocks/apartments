import numpy as np
import pandas as pd
from rentfrontier import features, retail


def test_storefronts_within_radius_first_year(tmp_path, monkeypatch):
    registry = tmp_path / "registry.parquet"
    shops = tmp_path / "storefronts.parquet"
    pd.DataFrame(
        {"building": ["a", "b"], "latitude": [0.0, np.nan], "longitude": [0.0, np.nan]}
    ).to_parquet(registry)
    pd.DataFrame(
        {
            "reporting_year": [retail.FIRST_YEAR] * 3 + ["2024"],
            "primary_business_activity": [
                "FOOD SERVICES",
                "RETAIL",
                "RETAIL",
                "RETAIL",
            ],
            # Grid metres: 100 m, 140 m (L1 100 + 40) and 300 m away; a later filing.
            "latitude": [0.1, 0.1, 0.3, 0.0],
            "longitude": [0.0, 0.04, 0.0, 0.0],
        }
    ).to_parquet(shops)
    monkeypatch.setattr(features, "lot_registry", lambda: str(registry))
    monkeypatch.setattr(features, "STOREFRONTS_FILE", str(shops))
    monkeypatch.setattr(
        features,
        "facing_grid",
        lambda: (
            lambda lon, lat: np.stack(
                [np.asarray(lon, float) * 1000, np.asarray(lat, float) * 1000], -1
            )
        ),
    )
    retail._building_retail.cache_clear()
    t = retail.building_retail()
    assert t.loc["a", "storefronts"] == 2
    assert t.loc["a", "food"] == 1
    assert np.isnan(t.loc["b", "storefronts"])
    terms = retail.terms(pd.DataFrame({"building": ["a"]}))
    assert np.isclose(terms["storefronts"][0], np.log(3))
    retail._building_retail.cache_clear()
