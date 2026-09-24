import numpy as np

from models.bayesian_parameter_audit import inventory, variation
from models.bayesian_feature_model import FeatureDesign
from tests.test_bayesian_feature_model import train


def test_group_variation_distinguishes_between_from_within():
    assert variation([1, 1, 3, 3], ["a", "a", "b", "b"]) == {
        "known_groups": 2,
        "varying_groups": 0,
        "within_ss_fraction": 0.0,
    }
    result = variation([1, 3, 1, 3, np.nan], ["a", "a", "b", "b", "c"])
    assert result == {"known_groups": 2, "varying_groups": 2, "within_ss_fraction": 1.0}
    assert variation([np.nan], ["a"])["within_ss_fraction"] is None


def test_audit_aliases_reporting_and_floor_gaps(train):
    data = train.copy()
    data["listed_floor"] = None
    data["advertised_floor"] = [1, 3, None] * 100
    data["window_exposures"] = [
        {"north": True} if i % 5 == 0 else {} for i in range(len(data))
    ]
    result = inventory(data, FeatureDesign(data))
    floor = result["measurements"]["listed_floor"]
    assert floor["known"]["rows"] == 200
    assert floor["levels"] == [1.0, 3.0]
    assert result["floor_adjacent_observed_levels"][0]["gap"] == 2
    north = result["measurements"]["window_exposures.north"]
    assert north["known"]["rows"] == 60
    assert north["unknown"]["rows"] == 240
    assert north["physical_contrast_observed"] is False
    columns = {r["feature"]: r for r in result["features"]}
    assert "window_exposures.north" not in columns
    assert columns["window_exposures.north.unknown"]["role"] == "reporting_nuisance"
    assert result["measurements"]["physical_floor"]["known"]["rows"] == 0
    assert "physical_floor" not in columns
