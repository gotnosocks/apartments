from copy import deepcopy

import numpy as np
import pytest

from models import laundry_floor_fit_comparison as m
from models.bayesian_floor_increment_design import FeatureDesign
from tests.test_bayesian_category_contrasts import training


def protocols():
    a = {'version': 'observable-bayesian-floor-experiment-v4', 'source_version': m.split.PARENT,
        'chains': 4, 'draws': 6000, 'tune': 4000, 'seed': 5, 'prior_multiplier': 1,
        'adaptation': 'diag', 'target_accept': .93, 'backend': 'numba',
        'building_prior_scale': .35, 'floor_levels': [1, 3, 4], 'residual_scale': 'shared',
        'implementation_sha256': {'math.py': 'same', 'bayesian_feature_experiment_v3.py': 'old',
                                  'reviewed_source_lineage.py': 'old'}}
    b = deepcopy(a)
    b['source_version'] = m.split.VERSION
    b['implementation_sha256'].update({'laundry_floor_split.py': 'new', 'bayesian_feature_experiment_v3.py': 'new',
                                      'reviewed_source_lineage.py': 'new'})
    return a, b


def test_only_loader_and_source_changes_allowed():
    a, b = protocols()
    assert m.check_protocols(a, b) == ['bayesian_feature_experiment_v3.py', 'reviewed_source_lineage.py']


def test_adaptation_change_requires_explicit_option_and_preserves_other_checks():
    a, b = protocols()
    b['adaptation'] = 'low_rank'
    with pytest.raises(ValueError, match='Sampling'): m.check_protocols(a, b)
    assert m.check_protocols(a, b, allow_adaptation_change=True) == [
        'bayesian_feature_experiment_v3.py', 'reviewed_source_lineage.py']


@pytest.mark.parametrize('key,value', [('draws', 50), ('tune', 50), ('chains', 2), ('seed', 99),
    ('target_accept', .8), ('backend', 'jax'), ('adaptation', 'flow'), ('adaptation', None),
    ('building_prior_scale', .1), ('extra_sampler_setting', True)])
def test_adaptation_option_is_not_a_general_protocol_bypass(key, value):
    a, b = protocols()
    b['adaptation'] = 'low_rank'
    b[key] = value
    with pytest.raises(ValueError): m.check_protocols(a, b, allow_adaptation_change=True)


@pytest.mark.parametrize('fault', ['prior', 'noise', 'draws', 'floor', 'math', 'inventory'])
def test_conflated_experiment_is_rejected(fault):
    a, b = protocols()
    if fault == 'prior': b['building_prior_scale'] *= 2
    elif fault == 'noise': b['residual_scale'] = 'bedroom'
    elif fault == 'draws': b['draws'] = 50
    elif fault == 'floor': b['floor_levels'].append(9)
    elif fault == 'math': b['implementation_sha256']['math.py'] = 'changed'
    elif fault == 'inventory': b['implementation_sha256']['extra.py'] = 'new'
    with pytest.raises(ValueError): m.check_protocols(a, b)


@pytest.mark.parametrize('fault', [None, 'area', 'prior', 'centering'])
def test_actual_category_split_preserves_other_model_columns(fault):
    before = training()
    before['advertised_floor'] = np.random.default_rng(399).integers(1, 6, len(before))
    after = before.copy()
    selected = after.index[after.laundry_type.eq('in_building')][:10]
    after.loc[selected, 'laundry_type'] = 'on_floor'
    a, b = FeatureDesign(before), FeatureDesign(after)
    if fault == 'area': after.loc[0, 'square_feet'] *= 2
    elif fault == 'prior': b.prior_scales[b.features.index('bedrooms_gt_0')] *= 2
    elif fault == 'centering': b.means[b.features.index('bedrooms_gt_0')] += .1
    if fault:
        with pytest.raises(ValueError, match='Nonlaundry'): m.check_designs(a, b, before, after)
    else:
        names = m.check_designs(a, b, before, after)
        assert 'listed_floor_gt_1' in names and 'laundry_type.unknown' in names
        assert len(b.features) == len(a.features)+1


def residual_fixture():
    rows = [{'audit_id': str(i), 'unit_id': 'u'+str(i), 'building': 'b', 'source_listing_id': str(i),
        'period': '2026-01-01', 'asking_rent': 3000, 'laundry_type': 'in_building',
        'analysis_price_basis': 'current_capture_gross_ask'} for i in range(2)]
    before = [{k: r[k] for k in ('audit_id', 'unit_id', 'building', 'source_listing_id', 'period', 'asking_rent')}
              | {'fitted_rent': 2800., 'residual_log': .1} for r in rows]
    after = deepcopy(before)
    after[0].update(fitted_rent=2850., residual_log=.08)
    after[1].update(fitted_rent=2600., residual_log=.14)
    return before, after, rows


def test_movements_align_identity_not_row_position_and_include_worse_residuals():
    before, after, rows = residual_fixture()
    result = m.movement_rows(before, after[::-1], rows)
    assert [r['audit_id'] for r in result] == ['1', '0']
    assert [r['fitted_rent_change'] for r in result] == [-200., 50.]
    summary = m.summarize_slice(result)
    assert summary['candidate_median_absolute_log_residual'] == pytest.approx(.11)
    assert summary['reference_median_absolute_log_residual'] == pytest.approx(.1)
    assert summary['median_absolute_fitted_change'] == 125.


@pytest.mark.parametrize('fault', ['price', 'ad', 'duplicate', 'missing'])
def test_residual_membership_or_targets_must_not_drift(fault):
    a, b, rows = residual_fixture()
    if fault == 'price': b[0]['asking_rent'] += 1
    elif fault == 'ad': b[0]['source_listing_id'] = 'other'
    elif fault == 'duplicate': b.append(deepcopy(b[0]))
    elif fault == 'missing': b.pop()
    with pytest.raises(ValueError): m.movement_rows(a, b, rows)


@pytest.mark.parametrize('fault', [None, 'posterior', 'source', 'fit_binding', 'draw_count', 'gate', 'interval'])
def test_category_analysis_must_bind_the_exact_complete_posterior(tmp_path, fault):
    from types import SimpleNamespace
    from apartments.research_pipeline import publish_bundle, digest
    from apartments.corrections import canonical

    experiment, dataset, analysis = [tmp_path/name for name in ('experiment', 'dataset', 'analysis')]
    for directory in (experiment/'fit', experiment/'protocol', dataset):
        publish_bundle(directory, {'placeholder.json': '{}\n'}, {'version': 'test'})
    fit = {'report': {'protocol_sha256': 'protocol'}, 'protocol': {
        'source_observations_sha256': 'source', 'chains': 4, 'draws': 6000},
        'provenance': {'fit_manifest': {'files': {'posterior.nc': 'posterior'}}},
        'design': SimpleNamespace(features=['x'])}
    value = {'version': m.categories.VERSION,
        'bindings': {k: digest(p/'complete.json') for k, p in [('fit', experiment/'fit'), ('protocol', experiment/'protocol'), ('source', dataset)]},
        'protocol_sha256': 'protocol', 'posterior_sha256': 'posterior', 'source_observations_sha256': 'source',
        'status': 'all_supported_contrasts_converged', 'all_joint_beta_draws': True,
        'chains': 4, 'draws_per_chain': 6000, 'design_features': ['x'],
        'contrasts': [{'diagnostics': {'acceptable': True}, 'log_effect': {}, 'percent_effect': {}}]}
    if fault == 'posterior': value['posterior_sha256'] = 'different'
    elif fault == 'source': value['source_observations_sha256'] = 'different'
    elif fault == 'fit_binding': value['bindings']['fit'] = 'different'
    elif fault == 'draw_count': value['draws_per_chain'] = 50
    elif fault == 'gate': value['contrasts'][0]['diagnostics']['acceptable'] = False
    elif fault == 'interval': value['contrasts'][0]['percent_effect'] = None
    publish_bundle(analysis, {'contrasts.json': canonical(value)+'\n'}, {'version': 'test'})
    if fault:
        with pytest.raises(ValueError): m.category_result(analysis, experiment, dataset, fit)
    else:
        assert m.category_result(analysis, experiment, dataset, fit) == value
