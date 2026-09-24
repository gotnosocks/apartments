from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from models.bayesian_floor_spline_design import FeatureDesign
from tests.test_bayesian_floor_increment_design import train
from tests.test_bayesian_floor_spline_design import spline_train

spec = importlib.util.spec_from_file_location(
    "scope_readers",
    Path(__file__).parents[1]
    / "docs/analysis/scripts/verify_residual_scope_readers.py",
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_identical_design_is_explicit(spline_train):
    design = FeatureDesign(spline_train)
    result = m.compare_designs([design, deepcopy(design)], [spline_train, spline_train])
    assert result["design_ranks"] == result["feature_counts"]
    assert result["numeric_normalization_equal"]
    assert result["size_reference_equal"]
    assert result["centering_changes"] == []
    assert result["floor_knots"] == [1.0, 5.0, 10.0, 20.0, 35.0, 52.0]


@pytest.mark.parametrize("fault", ["prior", "knots", "basis", "category", "rank"])
def test_design_drift_rejected(spline_train, fault):
    a = FeatureDesign(spline_train)
    b = deepcopy(a)
    if fault == "prior":
        b.prior_scales[0] *= 2
    elif fault == "knots":
        b.floor_knots[-1] += 1
    elif fault == "basis":
        b.floor_basis[0][0] += 0.1
    elif fault == "category":
        next(iter(b.categories.values()))["basis"][0][0] += 0.1
    elif fault == "rank":
        b.matrix = lambda frame: a.matrix(frame) * 0
    with pytest.raises(ValueError):
        m.compare_designs([a, b], [spline_train, spline_train])


def test_empirical_changes_reported_not_hidden(spline_train):
    a = FeatureDesign(spline_train)
    b = deepcopy(a)
    b.means[0] += 0.01
    name = next(n for n in b.numeric if n in b.features)
    b.numeric[name]["scale"] *= 2
    b.time.size_default += 1
    result = m.compare_designs([a, b], [spline_train, spline_train])
    assert len(result["centering_changes"]) == 1
    assert not result["numeric_normalization_equal"]
    assert not result["size_reference_equal"]
    assert (
        result["numeric_normalization_changes"][0]["raw_unit_prior_sd_relative_change"]
        == -0.5
    )
