import json

import numpy as np
import pytest

from models.bayesian_feature_model import FeatureDesign as Previous
from models.bayesian_floor_spline_design import FeatureDesign, knot_specification
from tests.test_bayesian_floor_increment_design import train, cases


@pytest.fixture
def spline_train(train):
    data = train.copy()
    data["listed_floor"] = np.resize(np.r_[np.arange(1.0, 53.0), np.nan], len(data))
    return data


@pytest.mark.parametrize(
    "spec", ["linear_total", "incremental_total", "full_half", "full_half_balance"]
)
def test_nonfloor_values_centering_priors_and_time_unchanged(spline_train, spec):
    previous = Previous(spline_train, spec)
    design = FeatureDesign(spline_train, spec)
    old, old_names, old_scales = previous.raw_features(spline_train)
    new, new_names, new_scales = design.raw_features(spline_train)
    for index, name in enumerate(old_names):
        if name in ("listed_floor", "listed_floor.unknown"):
            continue
        column = new_names.index(name)
        np.testing.assert_array_equal(old[:, index], new[:, column])
        assert old_scales[index] == new_scales[column]
        if name in previous.features:
            np.testing.assert_array_equal(
                previous.matrix(spline_train)[:, previous.features.index(name)],
                design.matrix(spline_train)[:, design.features.index(name)],
            )
    np.testing.assert_array_equal(previous.time.time_matrix, design.time.time_matrix)
    assert previous.time.unit_ids == design.time.unit_ids
    assert previous.time.buildings == design.time.buildings


def test_full_floor_coverage_unknown_separation_and_floor_two_anchor(spline_train):
    design = FeatureDesign(spline_train)
    assert design.floor_levels == list(np.arange(1.0, 53.0))
    assert design.floor_knots == [1.0, 5.0, 10.0, 20.0, 35.0, 52.0]
    assert design.floor_reference == 2
    matrix, names, _ = design.raw_features(cases(spline_train, [1, 2, 10, 52, None]))
    columns = [names.index(f"listed_floor_spline_{i}") for i in range(5)]
    np.testing.assert_array_equal(matrix[[1, 4]][:, columns], np.zeros((2, 5)))
    np.testing.assert_array_equal(
        matrix[:, names.index("listed_floor.unknown")], [0, 0, 0, 0, 1]
    )
    assert np.isfinite(design.matrix(spline_train)).all()
    assert (
        sum(row["rows"] for row in design.floor_support["levels"])
        == spline_train.listed_floor.notna().sum()
    )
    assert not any(name.startswith("listed_floor_gt_") for name in design.features)
    assert not any(
        "physical" in name for name in names if name.startswith("listed_floor")
    )


def test_spline_is_twice_continuous_and_natural_at_boundaries(spline_train):
    design = FeatureDesign(spline_train)
    h = 1e-3
    for knot in design.floor_knots[1:-1]:
        values = design.floor_coordinates(knot + h * np.arange(-3, 4))
        # Separate one-sided derivative estimates must agree at a knot.
        left_first = (3 * values[3] - 4 * values[2] + values[1]) / (2 * h)
        right_first = (-3 * values[3] + 4 * values[4] - values[5]) / (2 * h)
        np.testing.assert_allclose(left_first, right_first, atol=2e-7)
        left_second = (2 * values[3] - 5 * values[2] + 4 * values[1] - values[0]) / h**2
        right_second = (
            2 * values[3] - 5 * values[4] + 4 * values[5] - values[6]
        ) / h**2
        np.testing.assert_allclose(left_second, right_second, atol=5e-8)
    for endpoint, direction in [
        (design.floor_knots[0], 1),
        (design.floor_knots[-1], -1),
    ]:
        values = design.floor_coordinates(endpoint + direction * h * np.arange(4))
        second = (2 * values[0] - 5 * values[1] + 4 * values[2] - values[3]) / h**2
        np.testing.assert_allclose(second, 0, atol=5e-8)


@pytest.mark.parametrize("high", [3, 8, 15, 28, 52])
def test_knot_to_knot_prior_is_independent_of_number_of_knots(train, high):
    data = train.copy()
    data["listed_floor"] = np.resize(np.r_[np.arange(1.0, high + 1), np.nan], len(data))
    design = FeatureDesign(data, floor_prior_scale=0.1)
    for low, upper in zip(design.floor_knots[:-1], design.floor_knots[1:]):
        direction = design.contrast_vector(low, upper)
        assert np.linalg.norm(direction * design.prior_scales) == pytest.approx(
            np.sqrt(2) * 0.1
        )
    direction = design.contrast_vector(1, high)
    assert np.linalg.norm(direction * design.prior_scales) == pytest.approx(
        np.sqrt(2) * 0.1
    )
    np.testing.assert_array_equal(
        design.contrast_vector(2, 2), np.zeros(len(design.features))
    )
    np.testing.assert_allclose(design.contrast_vector(high, 1), -direction)


def test_unobserved_interior_floor_can_interpolate_but_cannot_extrapolate(train):
    data = train.copy()
    data["listed_floor"] = np.resize([1.0, 3.0, 5.0, 10.0, np.nan], len(data))
    design = FeatureDesign(data)
    assert 2 not in design.floor_levels
    assert np.isfinite(design.matrix(cases(data, [2.0, 4.0, 7.5]))).all()
    for value in [0.0, 10.001, np.inf, -np.inf]:
        with pytest.raises(ValueError, match="extrapolation"):
            design.floor_coordinates([value])
        with pytest.raises(ValueError):
            design.contrast_vector(1, value)


def test_advertised_alias_preserves_canonical_priority(spline_train):
    data = spline_train.copy()
    data["advertised_floor"] = data["listed_floor"]
    data["listed_floor"] = None
    alias = FeatureDesign(data)
    canonical = FeatureDesign(spline_train)
    np.testing.assert_array_equal(alias.matrix(data), canonical.matrix(spline_train))
    data["physical_floor"] = 999
    coordinates = alias.floor_coordinates([1, 2])
    data.loc[0, "listed_floor"] = 2
    data.loc[0, "advertised_floor"] = 1
    raw, names, _ = alias.raw_features(data.iloc[[0]])
    np.testing.assert_array_equal(
        raw[:, [names.index(f"listed_floor_spline_{i}") for i in range(5)]],
        coordinates[[1]],
    )


def test_saved_design_reconstructs_identical_features_and_contrasts(
    spline_train, tmp_path
):
    design = FeatureDesign(spline_train, floor_prior_scale=0.08)
    design.save(tmp_path)
    restored = FeatureDesign.load(tmp_path)
    np.testing.assert_array_equal(
        restored.matrix(spline_train), design.matrix(spline_train)
    )
    np.testing.assert_array_equal(restored.prior_scales, design.prior_scales)
    np.testing.assert_array_equal(
        restored.contrast_vector(2, 52), design.contrast_vector(2, 52)
    )
    assert restored.floor_support == design.floor_support


@pytest.mark.parametrize(
    "fault",
    [
        "knots",
        "anchor",
        "basis",
        "policy",
        "features",
        "numeric_order",
        "category_order",
        "raw_order",
        "priors",
        "active",
        "version",
        "means",
    ],
)
def test_corrupt_saved_design_rejected(spline_train, tmp_path, fault):
    design = FeatureDesign(spline_train)
    design.save(tmp_path)
    path = tmp_path / "feature-design.json"
    metadata = json.loads(path.read_text())
    if fault == "knots":
        metadata["floor_knots"][1] += 1
    elif fault == "anchor":
        metadata["floor_reference"] = 1
    elif fault == "basis":
        metadata["floor_basis"][0][0] += 0.01
    elif fault == "policy":
        metadata["floor_policy"]["unknown"] = "zero means ground floor"
    elif fault == "features":
        metadata["features"].reverse()
    elif fault == "numeric_order":
        metadata["numeric_order"].reverse()
    elif fault == "category_order":
        metadata["category_order"].reverse()
    elif fault == "raw_order":
        metadata["raw_feature_names"].reverse()
    elif fault == "priors":
        metadata["floor_prior_scale"] = 0.4
    elif fault == "active":
        metadata["active"] = [int(value) for value in metadata["active"]]
    elif fault == "version":
        metadata["version"] = "unsupported"
    elif fault == "means":
        metadata["means"] = metadata["means"][:-1]
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        FeatureDesign.load(tmp_path)


@pytest.mark.parametrize(
    "levels", [[], [1.0], [2.0, 1.0], [1.0, 1.0], [1.0, np.nan], [1.0, np.inf]]
)
def test_degenerate_or_unordered_support_is_not_fabricated(levels):
    with pytest.raises(ValueError):
        knot_specification(levels)


@pytest.mark.parametrize("scale", [0, -1, np.nan, np.inf, True])
def test_invalid_prior_rejected(spline_train, scale):
    with pytest.raises(ValueError, match="prior scale"):
        FeatureDesign(spline_train, floor_prior_scale=scale)


def test_anchor_outside_floor_two_range_uses_observed_minimum(train):
    data = train.copy()
    data["listed_floor"] = np.resize([6.0, 8.0, 10.0, 20.0, np.nan], len(data))
    design = FeatureDesign(data)
    assert design.floor_reference == 6
    np.testing.assert_array_equal(design.floor_coordinates([6]), np.zeros((1, 2)))
