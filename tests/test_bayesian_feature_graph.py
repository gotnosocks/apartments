"""Exact compressed graph preserves the reference posterior and gradients."""
import numpy as np
import pandas as pd
import pytest

from models import bayesian_feature_graph as compressed
from models import bayesian_feature_model as reference


def graph_data():
    rng = np.random.default_rng(174)
    n = 90
    full, half = rng.integers(1, 6, n), rng.integers(0, 3, n)
    rows = pd.DataFrame({
        'period': pd.date_range('2020-01-01', periods=36, freq='MS').take(np.arange(n) % 36),
        'unit_id': ['u' + str(i) for i in range(n)], 'building': ['b' + str(i % 5) for i in range(n)],
        'bedrooms': rng.integers(0, 6, n).astype(float), 'bathrooms': full + half / 2,
        'reported_full_bathrooms': full.astype(float), 'reported_half_bathrooms': half.astype(float),
        'bathroom_count_evidence': [{'flags': []} for _ in range(n)],
        'square_feet': rng.uniform(400, 2400, n), 'asking_rent': rng.uniform(2000, 15000, n),
        'laundry_type': rng.choice(['in_unit', 'in_building', None], n)})
    # Repeated feature rows retain different observations and likelihood terms.
    duplicate = rows.copy(deep=True)
    duplicate['asking_rent'] = rows.asking_rent.to_numpy() * 1.07
    return pd.concat([rows, duplicate], ignore_index=True)


def parameter_points(model):
    initial = model.initial_point()
    rng = np.random.default_rng(391)
    return [initial, *[{key: np.asarray(value) + rng.normal(0, scale, np.shape(value))
                       for key, value in initial.items()} for scale in (.025, .13)]]


def test_compression_is_exact_even_for_adjacent_floating_point_values():
    near = np.nextafter(1., 2.)
    matrix = np.array([[1., 2.], [near, 2.], [1., 2.], [-3., 4.], [near, 2.]])
    unique, inverse = compressed.compress(matrix)
    assert len(unique) == 3
    assert inverse[0] == inverse[2]
    assert inverse[0] != inverse[1]
    np.testing.assert_array_equal(unique[inverse], matrix)
    with pytest.raises(ValueError, match='Finite two-dimensional'):
        compressed.compress(np.array([1., 2.]))
    with pytest.raises(ValueError, match='Finite two-dimensional'):
        compressed.compress(np.array([[1., np.nan]]))


@pytest.mark.parametrize('spec', reference.SPECS)
def test_reference_and_compressed_posterior_density_gradient_and_priors_match(spec):
    data = graph_data()
    design = reference.FeatureDesign(data, spec)
    old = reference.build_model(data, design, prior_multiplier=1.3)
    new = compressed.build_model(data, design, prior_multiplier=1.3)
    assert old.coords == new.coords
    assert old.named_vars_to_dims == new.named_vars_to_dims
    assert [rv.name for rv in old.free_RVs] == [rv.name for rv in new.free_RVs]
    assert [str(rv.owner.op) for rv in old.free_RVs] == [str(rv.owner.op) for rv in new.free_RVs]
    assert [v.name for v in old.value_vars] == [v.name for v in new.value_vars]
    for key, value in old.initial_point().items():
        np.testing.assert_array_equal(value, new.initial_point()[key])
    assert new.compression_summary['observations'] == 180
    assert new.compression_summary['unique_feature_rows'] == 90
    # FAST_COMPILE avoids requiring a C++ compiler or writable external cache.
    old_logp = old.compile_logp(mode='FAST_COMPILE')
    new_logp = new.compile_logp(mode='FAST_COMPILE')
    old_grad = old.compile_dlogp(mode='FAST_COMPILE')
    new_grad = new.compile_dlogp(mode='FAST_COMPILE')
    old_prior = old.compile_logp(vars=old.free_RVs, sum=False, mode='FAST_COMPILE')
    new_prior = new.compile_logp(vars=new.free_RVs, sum=False, mode='FAST_COMPILE')
    for point in parameter_points(old):
        a, b = float(old_logp(point)), float(new_logp(point))
        assert np.isfinite([a, b]).all()
        assert a == pytest.approx(b, rel=1e-12, abs=1e-9)
        ga, gb = old_grad(point), new_grad(point)
        assert np.isfinite(ga).all() and np.isfinite(gb).all()
        np.testing.assert_allclose(ga, gb, rtol=1e-11, atol=1e-9)
        # Individual free-RV contributions check priors, transforms and Jacobians,
        # not merely cancellation in the total density.
        for pa, pb in zip(old_prior(point), new_prior(point)):
            np.testing.assert_array_equal(pa, pb)
