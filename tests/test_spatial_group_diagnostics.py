import hashlib
import itertools

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from apartments.corrections import canonical
from models.spatial_group_diagnostics import (
    check_lineage, distinct_locations, moran_draws, neighbor_graph, posterior_statistics,
)


def chain_weights(n=5):
    return csr_matrix(np.eye(n, k=1)+np.eye(n, k=-1))


def test_blocked_sparse_statistic_matches_direct_quadratic_form():
    rng = np.random.default_rng(123)
    values = rng.normal(size=(4, 17, 5))
    weights = chain_weights()
    z = values-values.mean(axis=-1, keepdims=True)
    expected = np.einsum('...i,ij,...j->...', z, weights.toarray(), z)/np.sum(z*z, axis=-1)*5/8
    np.testing.assert_allclose(moran_draws(values, weights, block_size=7), expected)
    np.testing.assert_allclose(moran_draws(3*values+11, weights), expected)


def test_joint_dependence_is_preserved_instead_of_using_marginal_medians():
    values = np.array([[-2., -1., 0., 1., 2.], [2., 1., 0., -1., -2.]])
    np.testing.assert_allclose(moran_draws(values, chain_weights()), [.5, .5])
    with pytest.raises(ValueError, match='constant'):
        moran_draws(np.median(values, axis=0)[None, :], chain_weights())


def test_exhaustive_randomization_has_known_expectation():
    values = np.array(list(itertools.permutations([1., 2., 3., 4., 5.])))
    assert moran_draws(values, chain_weights()).mean() == pytest.approx(-1/4)
    clustered = [[-2., -1., 0., 1., 2.]]
    alternating = [[1., -1., 1., -1., 1.]]
    assert moran_draws(clustered, chain_weights())[0] > 0
    assert moran_draws(alternating, chain_weights())[0] < 0


def test_neighbor_graph_is_order_invariant_including_coincident_ties():
    labels = ['d', 'b', 'a', 'c', 'e', 'f']
    coordinates = np.array([[40., -74.], [40., -74.], [40., -74.],
                            [40.01, -74.], [41., -74.], [41.01, -74.]])
    w, meta = neighbor_graph(labels, coordinates, 1)
    order = [3, 2, 5, 0, 4, 1]
    other, _ = neighbor_graph([labels[i] for i in order], coordinates[order], 1)
    np.testing.assert_array_equal(w.toarray()[np.ix_(order, order)], other.toarray())
    assert meta['coincident_coordinate_pairs'] == 3
    assert meta['connected_components'] == 2
    assert w[0, 2] == w[2, 0] == 1  # 'a' wins the exact zero-distance tie.
    assert np.all(w.diagonal() == 0)


def test_coincident_sensitivity_excludes_every_group_member_not_an_arbitrary_representative():
    buildings = [{'building': name, 'latitude': lat, 'longitude': -74.} for name, lat in
                 [('a', 40.), ('b', 40.), ('c', 40.1), ('d', 40.2), ('e', 40.2), ('f', 40.3)]]
    assert [b['building'] for b in distinct_locations(buildings)] == ['c', 'f']
    assert len(buildings) == 6


@pytest.mark.parametrize('fault', ['constant', 'nan', 'diagonal', 'negative', 'empty', 'shape'])
def test_invalid_statistics_refused(fault):
    values = np.array([[1., 2., 3., 4., 5.]])
    w = chain_weights().toarray()
    if fault == 'constant': values[:] = 1
    elif fault == 'nan': values[0, 0] = np.nan
    elif fault == 'diagonal': w[0, 0] = 1
    elif fault == 'negative': w[0, 1] = -1
    elif fault == 'empty': w[:] = 0
    elif fault == 'shape': values = values[:, :4]
    with pytest.raises(ValueError): moran_draws(values, w)


@pytest.mark.parametrize('fault', ['duplicate', 'nan', 'latitude', 'k'])
def test_invalid_locations_refused(fault):
    labels, coordinates, k = ['a', 'b', 'c'], [[40., -74.], [41., -74.], [42., -74.]], 1
    if fault == 'duplicate': labels[1] = 'a'
    elif fault == 'nan': coordinates[0][0] = np.nan
    elif fault == 'latitude': coordinates[0][0] = 91
    elif fault == 'k': k = 3
    with pytest.raises(ValueError): neighbor_graph(labels, coordinates, k)


def test_location_revision_must_bind_selected_source_and_exact_buildings():
    selected = {'files': {'observations.jsonl': 'source'}}
    candidate = {'source_manifest': selected,
                 'source_manifest_sha256': hashlib.sha256((canonical(selected)+'\n').encode()).hexdigest()}
    spatial = {'version': 'cohort-building-spatial-candidates-v1'}
    rows = [{'building': 'a'}, {'building': 'b'}]
    buildings = [{'building': name, 'status': 'source_bound'} for name in ['a', 'b']]
    assert check_lineage(selected, candidate, spatial, rows, buildings) == 'direct_source_revision'
    with pytest.raises(ValueError): check_lineage(selected, candidate, spatial, rows, buildings[:1])
    candidate['source_manifest_sha256'] = 'different'
    with pytest.raises(ValueError): check_lineage(selected, candidate, spatial, rows, buildings)


def test_refitted_posterior_uses_exact_same_location_cohort_without_requiring_another_revision():
    selected = {'files': {'observations.jsonl': 'refitted-source'}, 'version': 'reviewed-source'}
    spatial = {'version': 'cohort-building-spatial-candidates-v1'}
    rows = [{'building': 'a'}, {'building': 'b'}]
    buildings = [{'building': name, 'status': 'source_bound'} for name in ['a', 'b']]
    assert check_lineage(selected, dict(selected), spatial, rows, buildings) == 'same_source'
    with pytest.raises(ValueError):
        check_lineage(selected, {**selected, 'files': {'observations.jsonl': 'other'}}, spatial, rows, buildings)
    with pytest.raises(ValueError): check_lineage(selected, selected, spatial, rows, buildings[:1])
    with pytest.raises(ValueError): check_lineage(selected, selected, {'version': 'unknown'}, rows, buildings)


def write_posterior(path, fault=None):
    import xarray as xr
    rng = np.random.default_rng(400)
    labels = ['a', 'b', 'c', 'd', 'e', 'f']
    values = rng.normal(size=(4, 1200, 6))
    if fault == 'unmixed':
        # Each chain has a different spatial pattern but individually moves.
        values[0] = 5*np.array([-3, -2, -1, 1, 2, 3])+values[0]*.01
    posterior = xr.Dataset({'building_effect': (('chain', 'draw', 'building'), values)},
                           coords={'building': labels, 'chain': range(4), 'draw': range(1200)})
    stats = xr.Dataset({'energy': (('chain', 'draw'), rng.normal(size=(4, 1200))),
        'diverging': (('chain', 'draw'), np.zeros((4, 1200), dtype=bool)),
        'maxdepth_reached': (('chain', 'draw'), np.zeros((4, 1200), dtype=bool))},
        coords={'chain': range(4), 'draw': range(1200)})
    if fault == 'depth': stats['maxdepth_reached'][0, 0] = True
    if fault == 'coordinates': stats = stats.assign_coords(draw=range(1, 1201))
    xr.DataTree.from_dict({'posterior': posterior, 'sample_stats': stats}).to_netcdf(path, engine='h5netcdf')
    return labels, values


def test_real_netcdf_uses_all_joint_draws_with_ordered_subset_and_fresh_diagnostics(tmp_path):
    p = tmp_path/'posterior.nc'
    labels, values = write_posterior(p)
    subset = ['f', 'c', 'a', 'b', 'e']
    w = chain_weights()
    results, diag, table, buildings = posterior_statistics(p, {'chains': 4, 'draws': 1200}, labels, subset, [w, w])
    assert results.shape == (4, 1200, 2)
    expected = values[:, :, [labels.index(k) for k in subset]]
    np.testing.assert_allclose(results[:, :, 0], moran_draws(expected, w))
    assert diag['acceptable'] and len(table) == 2
    assert [b['building'] for b in buildings] == subset
    expected -= expected.mean(axis=-1, keepdims=True)
    assert buildings[0]['centered_log_effect']['median'] == pytest.approx(np.median(expected[:, :, 0]))


@pytest.mark.parametrize('fault', ['unmixed', 'depth', 'coordinates', 'dimensions', 'labels'])
def test_posterior_with_failed_gates_or_wrong_identity_cannot_publish(tmp_path, fault):
    p = tmp_path/'posterior.nc'
    labels, _ = write_posterior(p, fault)
    protocol = {'chains': 4, 'draws': 1200 if fault != 'dimensions' else 1199}
    if fault == 'labels': labels[-1] = 'unknown'
    with pytest.raises(ValueError):
        posterior_statistics(p, protocol, labels, labels[:5], [chain_weights(), chain_weights()])
