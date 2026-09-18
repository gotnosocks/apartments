import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "bayesian_comparison", Path(__file__).parents[1] / "models/bayesian_comparison.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def example():
    return pd.DataFrame(
        {
            "unit_id": ["a", "b", "c", "d"],
            "period": ["2025-01-01"] * 4,
            "building": ["one", "one", "two", "three"],
            "asking_rent": [2000, 3000, 4000, 5000],
            "predicted_rent": [2200, 3100, 3600, 4800],
            "log_predictive_density": [0.7, 0.4, 0.5, 0.8],
        }
    )


def test_pairing_ignores_row_order_and_identical_predictions_have_zero_difference():
    candidate = example()
    reference = candidate.iloc[::-1]
    result = m.compare(candidate, reference, draws=100)
    for key in [
        "log_predictive_density_difference",
        "median_absolute_percent_error_difference",
    ]:
        assert result[key] == {"estimate": 0.0, "lower_95": 0.0, "upper_95": 0.0}
    assert result["buildings"] == 3


def test_mismatched_cohorts_or_observed_rents_cannot_be_compared():
    candidate = example()
    reference = example()
    with pytest.raises(ValueError, match="same validation observations"):
        m.compare(candidate, reference.iloc[:3])
    reference.loc[0, "asking_rent"] = 999
    with pytest.raises(ValueError, match="observed rent must agree"):
        m.compare(candidate, reference)
