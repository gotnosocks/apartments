from copy import deepcopy
import json

import numpy as np
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import quarantine_fit_comparison as m, reviewed_cohort_projection as projection
from tests.test_laundry_floor_fit_comparison import protocols as laundry_protocols, residual_fixture
from tests.test_reviewed_cohort_quarantine import fixture, CLOCK


def protocols():
    a, b = laundry_protocols()
    b['source_version'] = m.quarantine.VERSION
    for value in (a, b):
        value.update(execution_version=m.disk.VERSION, storage_policy=deepcopy(m.disk.POLICY),
                     storage_versions=dict.fromkeys(('zarr', 'obstore', 'xarray', 'h5py'), '1.0'))
        value['implementation_sha256'].update(dict.fromkeys(m.disk.CODE, 'same'))
    b['implementation_sha256']['reviewed_cohort_quarantine.py'] = 'new'
    return a, b


def test_source_and_loader_revision_preserves_sampling_and_math():
    a, b = protocols()
    b.update(rows=10, buildings=2, units=3, source_observations_sha256='new')
    assert m.check_protocols(a, b) == ['bayesian_feature_experiment_v3.py', 'reviewed_source_lineage.py']


@pytest.mark.parametrize('fault', ['math', 'inventory', 'removed_code', 'missing_helper', 'storage',
    'adaptation', 'draws', 'floor', 'prior', 'noise', 'environment'])
def test_source_comparison_rejects_conflated_experiments(fault):
    a, b = protocols()
    if fault == 'math': b['implementation_sha256']['math.py'] = 'changed'
    elif fault == 'inventory': b['implementation_sha256']['extra.py'] = 'new'
    elif fault == 'removed_code': del b['implementation_sha256']['math.py']
    elif fault == 'missing_helper': del b['implementation_sha256']['reviewed_cohort_quarantine.py']
    elif fault == 'storage': b['storage_policy']['all_retained_draws'] = False
    elif fault == 'adaptation': b['adaptation'] = 'low_rank'
    elif fault == 'draws': b['draws'] = 50
    elif fault == 'floor': b['floor_levels'].append(9)
    elif fault == 'prior': b['building_prior_scale'] *= 2
    elif fault == 'noise': b['residual_scale'] = 'bedroom'
    elif fault == 'environment': b['versions'] = {'numpy': 'different'}
    with pytest.raises(ValueError): m.check_protocols(a, b)


def test_published_source_revision_restores_exact_reference(tmp_path):
    rows, decisions, *_ = fixture()
    parent, decision_path, candidate = [tmp_path/name for name in ('parent', 'decisions', 'candidate')]
    publish_bundle(parent, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows),
        'current-source-evidence.jsonl': '{}\n'}, {'version': m.quarantine.PARENT})
    manifest = json.loads((parent/'complete.json').read_text())
    publish_bundle(decision_path, {'decisions.jsonl': ''.join(canonical(d)+'\n' for d in decisions)},
        {'version': m.quarantine.DECISION_VERSION, 'reviewed_at': CLOCK,
         'source_manifest_sha256': digest(parent/'complete.json'),
         'source_observations_sha256': manifest['files']['observations.jsonl']})
    projection.run(parent, decision_path, candidate)
    original, kept, excluded = m.verify_revision(parent, candidate)
    assert original == rows and kept == [rows[1], rows[3]]
    assert [r['observation'] for r in excluded] == [rows[0], rows[2]]
    wrong = tmp_path/'wrong'
    publish_bundle(wrong, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                   {'version': m.quarantine.PARENT})
    with pytest.raises(ValueError, match='exact reference'): m.verify_revision(wrong, candidate)


def test_residual_summary_uses_common_rows_and_keeps_excluded_separate():
    a, b, rows = residual_fixture()
    a[1]['residual_log'] = 50.0
    movements, summary = m.compare_residuals(a[::-1], b[:1], rows, rows[:1])
    assert len(movements) == 1 and movements[0]['fitted_rent_change'] == 50
    assert summary['common_rows']['reference_median_absolute_log_residual'] == .1
    assert summary['current_rows']['rows'] == 1
    assert summary['excluded_reference_rows'] == [a[1]]


@pytest.mark.parametrize('fault', ['price', 'ad', 'missing', 'duplicate'])
def test_residual_source_membership_and_target_are_bound(fault):
    a, b, rows = residual_fixture()
    if fault == 'price': b[0]['asking_rent'] += 1
    elif fault == 'ad': b[0]['source_listing_id'] = 'other'
    elif fault == 'missing': b.pop()
    elif fault == 'duplicate': b.append(deepcopy(b[0]))
    with pytest.raises(ValueError): m.compare_residuals(a, b, rows, rows)


def interval(x):
    return {'median': x, 'lower_95': x-.1, 'upper_95': x+.1, 'probability_positive': .5}


def test_group_comparison_reports_removed_buildings_and_units():
    rows = [{'building': 'a', 'unit_id': 'a1'}, {'building': 'b', 'unit_id': 'b1'}]
    a = [{'kind': kind, 'id': identity, 'log_effect': interval(0)}
         for kind, identity in [('building', 'a'), ('building', 'b'), ('unit', 'a1'), ('unit', 'b1')]]
    b = [deepcopy(a[0]), deepcopy(a[2])]
    b[1]['log_effect'] = interval(.2)
    changed, removed = m.compare_groups(a, b, rows, rows[:1])
    assert changed[0]['id'] == 'a1' and changed[0]['log_effect']['median_change'] == .2
    assert {(r['kind'], r['id']) for r in removed} == {('building', 'b'), ('unit', 'b1')}
    for bad in (b[:1], b+[b[0]]):
        with pytest.raises(ValueError, match='membership'): m.compare_groups(a, bad, rows, rows[:1])


def test_common_building_contrasts_remove_draw_specific_reference_shift():
    rng = np.random.default_rng(17)
    values = rng.normal(size=(4, 100, 3))
    # The candidate lost a building, reversed coordinates and gained a random
    # draw-specific common offset. The surviving pairwise effects did not move.
    offset = rng.normal(size=(4, 100, 1))*100
    candidate = values[:, :, [1, 0]]+offset
    a = m.common_building_draws(values, ['a', 'b', 'removed'], ['a', 'b'])
    b = m.common_building_draws(candidate, ['b', 'a'], ['a', 'b'])
    np.testing.assert_allclose(a, b, atol=1e-13)
    np.testing.assert_allclose(a.sum(axis=-1), 0, atol=1e-15)
    np.testing.assert_allclose(a[:, :, 0], (values[:, :, 0]-values[:, :, 1])/2)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'single', 'nan', 'shape', 'labels'])
def test_invalid_common_reference_is_rejected(fault):
    values, labels, shared = np.zeros((4, 100, 3)), ['a', 'b', 'c'], ['a', 'b']
    if fault == 'missing': shared = ['a', 'other']
    elif fault == 'duplicate': shared = ['a', 'a']
    elif fault == 'single': shared = ['a']
    elif fault == 'nan': values[0, 0, 0] = np.nan
    elif fault == 'shape': values = values[0]
    elif fault == 'labels': labels = ['a', 'a', 'b']
    with pytest.raises(ValueError): m.common_building_draws(values, labels, shared)


@pytest.mark.parametrize('fault', [None, 'unmixed_chains', 'draw_count', 'coordinates'])
def test_joint_building_analysis_reads_all_draws_and_enforces_convergence(tmp_path, fault):
    from types import SimpleNamespace
    import xarray as xr

    rng = np.random.default_rng(402)
    values = rng.normal(size=(4, 1000, 3))
    if fault == 'unmixed_chains': values[:, :, 0] += np.arange(4)[:, None]*10
    labels = ['a', 'b', 'removed']
    posterior = xr.Dataset({'building_effect': (('chain', 'draw', 'building'), values)},
                           coords={'building': labels})
    stats = xr.Dataset({
        'energy': (('chain', 'draw'), rng.normal(size=(4, 1000))),
        'diverging': (('chain', 'draw'), np.zeros((4, 1000), dtype=bool)),
        'maxdepth_reached': (('chain', 'draw'), np.zeros((4, 1000), dtype=bool))})
    (tmp_path/'fit').mkdir()
    posterior.to_netcdf(tmp_path/'fit/posterior.nc', group='posterior', engine='h5netcdf')
    stats.to_netcdf(tmp_path/'fit/posterior.nc', group='sample_stats', mode='a', engine='h5netcdf')
    fit = {'root': tmp_path, 'protocol': {'chains': 4, 'draws': 1000},
           'data': SimpleNamespace(building=labels)}
    if fault == 'draw_count': fit['protocol']['draws'] = 50
    elif fault == 'coordinates': fit['data'].building = ['a', 'b', 'wrong']
    if fault:
        with pytest.raises(ValueError): m.building_contrasts(fit, ['a', 'b'])
    else:
        result = m.building_contrasts(fit, ['a', 'b'])
        assert result['diagnostics']['acceptable']
        expected = np.quantile((values[:, :, 0]-values[:, :, 1])/2, [.025, .5, .975])
        effect = result['contrasts'][0]['log_effect']
        np.testing.assert_allclose([effect[k] for k in ('lower_95', 'median', 'upper_95')], expected)


def test_floor_comparison_aligns_physical_endpoints():
    a = {'contrasts': [{'lower_floor': low, 'upper_floor': high, 'percent_effect': interval(1)}
                       for low, high in [(1, 2), (2, 4)]]}
    b = deepcopy(a)
    b['contrasts'].reverse()
    assert all(r['percent_effect']['median_change'] == 0 for r in m.compare_floors(a, b))
    b['contrasts'][0]['upper_floor'] = 5
    with pytest.raises(ValueError, match='endpoints'): m.compare_floors(a, b)


@pytest.mark.parametrize('fault', [None, 'membership', 'duplicate', 'direction', 'vector', 'vector_shape', 'nonfinite'])
def test_category_comparison_preserves_physical_scenario(fault):
    a = {'contrasts': [{'id': 'laundry', 'field': 'laundry_type', 'before': 'in_building',
        'after': 'in_unit', 'design_vector': [0, 1], 'percent_effect': interval(2)}]}
    b = deepcopy(a)
    b['contrasts'][0]['percent_effect'] = interval(3)
    if fault == 'membership': b['contrasts'].clear()
    elif fault == 'duplicate': b['contrasts'] *= 2
    elif fault == 'direction': b['contrasts'][0]['after'] = 'on_floor'
    elif fault == 'vector': b['contrasts'][0]['design_vector'] = [1, 0]
    elif fault == 'vector_shape': b['contrasts'][0]['design_vector'] = [1]
    elif fault == 'nonfinite': b['contrasts'][0]['design_vector'] = [0, np.nan]
    if fault:
        with pytest.raises(ValueError): m.compare_categories(a, b)
    else:
        # Different cohort centering may change the subtraction's final bits.
        b['contrasts'][0]['design_vector'][0] = 1e-16
        assert m.compare_categories(a, b)[0]['percent_effect']['median_change'] == 1
