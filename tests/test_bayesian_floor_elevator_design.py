import json

import numpy as np
import pytest

from models import bayesian_floor_elevator_design as m
from tests.test_bayesian_category_contrasts import training


def data():
    frame = training()
    frame["advertised_floor"] = [2, 3, 4, 5, 8, None] * 40
    frame["elevator"] = ([True] * 6 + [False] * 6 + [None] * 6) * 13 + [True] * 6
    return frame


@pytest.mark.parametrize("mode", m.MODES)
def test_existing_design_columns_priors_and_time_are_preserved(mode):
    frame = data()
    design = m.FeatureDesign(frame, mode=mode)
    base = m.floor.FeatureDesign(frame)
    np.testing.assert_array_equal(
        design.matrix(frame)[:, : len(base.features)], base.matrix(frame)
    )
    np.testing.assert_array_equal(
        design.prior_scales[: len(base.features)], base.prior_scales
    )
    assert design.time.unit_ids == base.time.unit_ids
    np.testing.assert_allclose(
        design.matrix(frame)[:, len(base.features) :].mean(axis=0), 0, atol=1e-15
    )


def test_known_no_yes_symmetric_unknown_separate_and_upper_range_saturates():
    frame = data().iloc[:6].copy()
    frame["advertised_floor"] = [2, 3, 4, 5, 8, None]
    arrays = []
    for value in (False, True, None):
        frame["elevator"] = value
        arrays.append(m.raw_interactions(frame, "separate"))
    np.testing.assert_array_equal(arrays[0], -arrays[1])
    np.testing.assert_array_equal(arrays[2], 0)
    np.testing.assert_array_equal(
        arrays[1],
        np.array(
            [
                [0, 0, 0],
                [0.5, 0, 0],
                [0.5, 0.5, 0],
                [0.5, 0.5, 0.5],
                [0.5, 0.5, 0.5],
                [0, 0, 0],
            ]
        ),
    )


def test_pooled_and_separate_priors_match_full_range_difference_but_not_local_shape():
    frame = data()
    vectors = []
    for mode in m.MODES:
        design = m.FeatureDesign(frame, mode=mode)
        yes = m.floor_contrast_vector(design, frame, 2, 5, True)
        no = m.floor_contrast_vector(design, frame, 2, 5, False)
        diff = yes - no
        np.testing.assert_array_equal(diff[: len(design.base.features)], 0)
        vectors.append(diff)
        assert np.linalg.norm(diff * design.prior_scales) == pytest.approx(
            0.15 * np.sqrt(3)
        )
        # Each access-specific full contrast retains base variance and adds a
        # quarter of the interaction-difference variance. Priors aren't identical
        # to the no-interaction base and that must be reported when fitting.
        assert np.linalg.norm(yes * design.prior_scales) == pytest.approx(
            np.sqrt(3 * 0.15**2 + 3 * 0.15**2 / 4)
        )
        local = m.floor_contrast_vector(
            design, frame, 2, 3, True
        ) - m.floor_contrast_vector(design, frame, 2, 3, False)
        expected = 0.15 / np.sqrt(3) if mode == "pooled" else 0.15
        assert np.linalg.norm(local * design.prior_scales) == pytest.approx(expected)


@pytest.mark.parametrize("mode", m.MODES)
def test_saved_design_round_trip_and_tampered_order_rejection(tmp_path, mode):
    frame = data()
    design = m.FeatureDesign(frame, mode=mode)
    design.save(tmp_path)
    loaded = m.FeatureDesign.load(tmp_path)
    np.testing.assert_array_equal(design.matrix(frame), loaded.matrix(frame))
    path = tmp_path / "interaction-design.json"
    saved = json.loads(path.read_text())
    saved["features"].reverse()
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="feature order"):
        m.FeatureDesign.load(tmp_path)


@pytest.mark.parametrize("bad", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_prior_scales_rejected(bad):
    with pytest.raises(ValueError):
        m.FeatureDesign(data(), interaction_prior_scale=bad)


def test_missing_endpoint_and_unsupported_counterfactual_rejected():
    frame = data()
    with pytest.raises(ValueError, match="endpoints"):
        m.FeatureDesign(frame.loc[frame.advertised_floor != 4])
    with pytest.raises(ValueError, match="both known"):
        m.FeatureDesign(frame.assign(elevator=None))
    design = m.FeatureDesign(frame)
    with pytest.raises(ValueError, match="explicit known"):
        m.floor_contrast_vector(design, frame, 2, 5, None)
    with pytest.raises(ValueError, match="supported"):
        m.floor_contrast_vector(design, frame, 2, 6, True)
    with pytest.raises(ValueError, match="absent from fitted"):
        design.matrix(frame.assign(listed_floor=6))


@pytest.mark.parametrize("mode", m.MODES)
def test_candidate_enters_exact_pymc_reference_and_compressed_graphs(mode):
    from models import bayesian_feature_graph_v3 as compressed

    frame = data()
    design = m.FeatureDesign(frame, mode=mode)
    reference = m.floor.reference.build_model(frame, design)
    compact = compressed.build_model(frame, design)
    assert reference.coords == compact.coords
    a, b = reference.initial_point(), compact.initial_point()
    assert a.keys() == b.keys()
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])
    # Deterministic numerical compatibility test, not a sampler benchmark.
    for target in ("logp", "dlogp"):
        left = getattr(reference, "compile_" + target)(mode="FAST_COMPILE")(a)
        right = getattr(compact, "compile_" + target)(mode="FAST_COMPILE")(b)
        assert np.isfinite(left).all() and np.isfinite(right).all()
        np.testing.assert_allclose(left, right, rtol=1e-10, atol=1e-8)
