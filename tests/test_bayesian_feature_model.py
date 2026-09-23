"""Semantic checks for Bayesian bathroom contrasts and identified design."""

import numpy as np
import pandas as pd
import pytest

from models import bayesian_feature_model as m


@pytest.fixture(scope="module")
def train():
    rng = np.random.default_rng(981)
    n = 300
    full = rng.integers(1, 6, n)
    half = rng.integers(0, 3, n)
    frame = pd.DataFrame(
        {
            "period": pd.date_range("2020-01-01", periods=36, freq="MS").take(
                np.arange(n) % 36
            ),
            "unit_id": ["u" + str(i % 40) for i in range(n)],
            "building": ["b" + str(i % 5) for i in range(n)],
            "bedrooms": rng.integers(0, 6, n).astype(float),
            "bathrooms": full + half / 2,
            "reported_full_bathrooms": full.astype(float),
            "reported_half_bathrooms": half.astype(float),
            "bathroom_count_evidence": [{"flags": []} for _ in range(n)],
            "square_feet": rng.uniform(400, 2400, n),
            "asking_rent": rng.uniform(2000, 14000, n),
            "laundry_type": rng.choice(["in_unit", "in_building", None], n),
        }
    )
    frame.loc[::17, "square_feet"] = np.nan
    frame.loc[::19, "bathroom_count_evidence"] = pd.Series(
        {i: {"flags": ["source_count_disagreement"]} for i in frame.index[::19]}
    )
    return frame


def scenarios(train, bedrooms, full, half):
    count = len(full)
    data = pd.concat([train.iloc[[1]].copy()] * count, ignore_index=True)
    data["bedrooms"] = bedrooms
    data["reported_full_bathrooms"] = full
    data["reported_half_bathrooms"] = half
    data["bathrooms"] = np.array(full) + np.array(half) / 2
    data["bathroom_count_evidence"] = [{"flags": []} for _ in range(count)]
    return data


def raw_dict(design, data):
    matrix, names, _ = design.raw_features(data)
    return {name: matrix[:, i] for i, name in enumerate(names)}


def test_full_half_separates_compositions_that_total_count_collapses(train):
    # One full plus two half baths and two full baths share numeric total=2.
    data = scenarios(train, [2, 2], [1, 2], [2, 0])
    full_half = m.FeatureDesign(train, "full_half")
    columns = raw_dict(full_half, data)
    assert columns["full_bathrooms_gt_1"].tolist() == [0, 1]
    assert columns["half_bathrooms_gt_0"].tolist() == [1, 0]
    assert columns["half_bathrooms_gt_1"].tolist() == [1, 0]
    for spec in ("linear_total", "incremental_total"):
        design = m.FeatureDesign(train, spec)
        np.testing.assert_array_equal(design.matrix(data)[0], design.matrix(data)[1])
    assert not np.array_equal(full_half.matrix(data)[0], full_half.matrix(data)[1])


def test_total_increments_change_exact_half_bath_boundary(train):
    data = scenarios(train, [2] * 5, [1, 1, 2, 2, 3], [0, 1, 0, 1, 0])
    design = m.FeatureDesign(train, "incremental_total")
    columns = raw_dict(design, data)
    expected = np.array(
        [[0, 0, 0, 0], [1, 0, 0, 0], [1, 1, 0, 0], [1, 1, 1, 0], [1, 1, 1, 1]]
    )
    actual = np.column_stack(
        [columns["bathrooms_gt_" + threshold] for threshold in ("1", "1.5", "2", "2.5")]
    )
    np.testing.assert_array_equal(actual, expected)
    linear = raw_dict(m.FeatureDesign(train, "linear_total"), data)
    np.testing.assert_array_equal(linear["bathrooms_above_one"], [0, 0.5, 1, 1.5, 2])


def test_bathroom_shortfall_requires_joint_increment_contrast(train):
    design = m.FeatureDesign(train, "full_half_balance")
    data = scenarios(train, [2, 2, 2], [1, 2, 3], [0, 0, 0])
    columns = raw_dict(design, data)
    np.testing.assert_array_equal(columns["full_bathroom_shortfall"], [1, 0, 0])
    # Net -1 -> 0 gets the second-full-bath increment AND removes a shortfall.
    # Net 0 -> +1 gets only the third-full-bath increment.
    delta = np.diff(design.matrix(data), axis=0)
    expected = np.zeros_like(delta)
    expected[0, design.features.index("full_bathrooms_gt_1")] = 1
    expected[0, design.features.index("full_bathroom_shortfall")] = -1
    expected[1, design.features.index("full_bathrooms_gt_2")] = 1
    np.testing.assert_allclose(delta, expected, atol=1e-14)
    beta = np.zeros(len(design.features))
    beta[design.features.index("full_bathrooms_gt_1")] = 0.15
    beta[design.features.index("full_bathrooms_gt_2")] = 0.07
    beta[design.features.index("full_bathroom_shortfall")] = -0.08
    np.testing.assert_allclose(delta @ beta, [0.23, 0.07])
    # A powder room does not remove a shortage of full bathrooms.
    powder = scenarios(train, [2, 2], [1, 1], [0, 1])
    np.testing.assert_array_equal(
        raw_dict(design, powder)["full_bathroom_shortfall"], [1, 1]
    )


def test_unknown_or_flagged_composition_is_masked_identically_across_specs(train):
    data = scenarios(train, [2] * 6, [2, 2, np.nan, 0, 1.5, 2], [1, 1, 1, 1, 0, -1])
    data.at[1, "bathroom_count_evidence"] = {"flags": ["reported_total_disagrees"]}
    original = data.copy(deep=True)
    full, half, known = m.bathroom_values(data)
    np.testing.assert_array_equal(known, [True, False, False, False, False, False])
    for spec in m.SPECS:
        design = m.FeatureDesign(train, spec)
        columns = raw_dict(design, data)
        np.testing.assert_array_equal(columns["bathroom_composition_unknown"], ~known)
        for name, values in columns.items():
            if (
                "bathroom" in name or "bathrooms" in name
            ) and name != "bathroom_composition_unknown":
                np.testing.assert_array_equal(values[1:], np.zeros(5), err_msg=name)
        assert np.isfinite(design.matrix(data)).all()
    pd.testing.assert_frame_equal(data, original)


def test_category_contrasts_identified_and_unknown_is_not_absence(train):
    design = m.FeatureDesign(train, "full_half_balance")
    meta = design.categories["laundry_type"]
    basis = np.asarray(meta["basis"])
    assert basis.shape == (2, 1)
    np.testing.assert_allclose(basis.sum(axis=0), 0, atol=1e-14)
    np.testing.assert_allclose(basis.T @ basis, np.eye(1), atol=1e-14)
    columns = raw_dict(design, train)
    known = train.laundry_type.notna().to_numpy()
    contrast = columns["laundry_type.contrast_0"]
    assert abs(contrast[known].mean()) < 1e-14
    np.testing.assert_array_equal(contrast[~known], np.zeros((~known).sum()))
    np.testing.assert_array_equal(columns["laundry_type.unknown"], ~known)
    matrix = design.matrix(train)
    assert (
        np.linalg.matrix_rank(np.column_stack([np.ones(len(train)), matrix]))
        == len(design.features) + 1
    )


def test_rank_deficient_feature_design_refuses_silent_arbitrary_coefficients(train):
    data = train.copy(deep=True)
    # The binary category becomes a duplicate of a bedroom threshold.
    data["laundry_type"] = np.where(data.bedrooms > 0, "in_unit", "in_building")
    with pytest.raises(ValueError, match="rank deficient"):
        m.FeatureDesign(data, "full_half_balance")


@pytest.mark.parametrize("spec", m.SPECS)
def test_serialized_design_preserves_training_and_counterfactual_matrix(
    train, tmp_path, spec
):
    design = m.FeatureDesign(train, spec)
    design.save(tmp_path)
    loaded = m.FeatureDesign.load(tmp_path)
    data = scenarios(train, [2, 2], [1, 2], [0, 1])
    data.loc[0, "square_feet"] = np.nan
    data.loc[1, "laundry_type"] = "new_unseen_category"
    for frame in (train, data):
        np.testing.assert_array_equal(loaded.matrix(frame), design.matrix(frame))
    np.testing.assert_array_equal(loaded.time.time_matrix, design.time.time_matrix)
    assert loaded.features == design.features
    assert loaded.support == design.support
    np.testing.assert_array_equal(loaded.prior_scales, design.prior_scales)


@pytest.mark.parametrize("spec", m.SPECS)
def test_pymc_density_is_finite_with_each_bathroom_specification(train, spec):
    design = m.FeatureDesign(train, spec)
    model = m.build_model(train, design)
    assert {
        "beta",
        "building_effect",
        "unit_z",
        "sigma_unit",
        "annual_drift",
        "log_rent",
    } <= set(model.named_vars)
    assert np.isfinite(model.compile_logp()(model.initial_point()))


def test_missing_or_scalar_inconsistent_counts_are_unknown_without_rewriting(train):
    data = scenarios(train, [2] * 6, [2, 2, 2, 2, 2, 2], [1, 1, 1, 1, 1, 1])
    data["bathrooms"] = [2.5, np.nan, 3.0, 2.0, np.inf, 2.5 + 1e-9]
    original = data.copy(deep=True)
    np.testing.assert_array_equal(
        m.bathroom_values(data)[2], [True, False, False, False, False, True]
    )
    for spec in m.SPECS:
        columns = raw_dict(m.FeatureDesign(train, spec), data)
        np.testing.assert_array_equal(
            columns["bathroom_composition_unknown"], [0, 1, 1, 1, 1, 0]
        )
        for name, values in columns.items():
            if "bathroom" in name and name != "bathroom_composition_unknown":
                np.testing.assert_array_equal(values[1:5], np.zeros(4))
    pd.testing.assert_frame_equal(data, original)
