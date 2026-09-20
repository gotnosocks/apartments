from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from models import residual_scope_fit_comparison as m
from tests.test_floor_spline_fit_comparison import protocols as base_protocols
from tests.test_bayesian_floor_increment_design import train
from tests.test_bayesian_floor_spline_design import spline_train
from tests.test_laundry_floor_fit_comparison import residual_fixture


def protocols():
    _, a = base_protocols()
    a.update(source_version=m.projection.PARENT, current_rows=172, rows=100, units=50, buildings=10)
    a['implementation_sha256']['expanded_floor_projection.py'] = 'same'
    for key in m.LOADER_CODE:
        a['implementation_sha256'][key] = 'old'
    b = deepcopy(a)
    b.update(source_version=m.projection.VERSION, rows=96, units=48, buildings=9,
             source_manifest_sha256='new', source_observations_sha256='new')
    b['implementation_sha256']['residual_scope_projection.py'] = 'new'
    for key in m.LOADER_CODE:
        b['implementation_sha256'][key] = 'new'
    return a, b


@pytest.mark.parametrize('fault', [None, 'math', 'inventory', 'removed', 'contract', 'prior', 'short', 'both_short',
    'current', 'knots', 'anchor', 'noise', 'seed', 'environment', 'order', 'nonfinite'])
def test_protocol_preserves_math_and_full_sampling_allows_population_revision(fault):
    a, b = protocols()
    if fault == 'math': b['implementation_sha256']['bayesian_floor_spline_design.py'] = 'changed'
    elif fault == 'inventory': b['implementation_sha256']['surprise.py'] = 'changed'
    elif fault == 'removed': b['implementation_sha256'].pop('bayesian_floor_spline_design.py')
    elif fault == 'contract': b['implementation_sha256'].pop('residual_scope_projection.py')
    elif fault == 'prior': b['unit_prior_scale'] = .8
    elif fault == 'short': b['draws'] = 50
    elif fault == 'both_short': a['draws'] = b['draws'] = 50
    elif fault == 'current': b['current_rows'] -= 1
    elif fault == 'knots': b['floor_knots'][-1] += 1
    elif fault == 'anchor': b['floor_reference'] = 3
    elif fault == 'noise': b['residual_scale'] = 'bedroom'
    elif fault == 'seed': b['seed'] += 1
    elif fault == 'environment': b['versions'] = {'numpy': 'other'}
    elif fault == 'order': b['floor_levels'].reverse()
    elif fault == 'nonfinite': b['floor_levels'][-1] = float('inf')
    if fault:
        with pytest.raises(ValueError): m.check_protocols(a, b)
    else:
        assert set(m.check_protocols(a, b)) == m.LOADER_CODE


def test_floor_support_change_recomputes_boundary_under_same_rule():
    a, b = protocols()
    b['floor_levels'].append(12.)
    b['floor_knots'], b['floor_reference'] = m.spline.knot_specification(b['floor_levels'])
    assert set(m.check_protocols(a, b)) == m.LOADER_CODE


def test_copying_contract_changes_are_tracked_for_archived_ast_validation():
    a, b = protocols()
    for name in m.replay_compatibility.FILES:
        a['implementation_sha256'][name] = 'original-copying'
        b['implementation_sha256'][name] = 'optimized-copying'
    assert set(m.check_protocols(a, b)) == m.LOADER_CODE | m.replay_compatibility.FILES


def test_archived_copying_changes_use_strict_guard(monkeypatch):
    a, b = {'root': Path('old'), 'provenance': {'protocol_manifest': {}}}, {'root': Path('new'), 'provenance': {'protocol_manifest': {}}}
    def bound(root, name, manifest):
        if name in m.replay_compatibility.FILES and root.parts[0] == 'old':
            archive = Path('data/model/chelsea-bayesian-expanded-spline-floor-disk-20260919/protocol')/name
            if not archive.exists(): pytest.skip('Local archived fit unavailable')
            return archive.read_bytes()
        return (Path('src/apartments')/name).read_bytes()
    monkeypatch.setattr(m.shared.common, 'bound_bytes', bound)
    result = m.check_implementation_sources(a, b, sorted(m.replay_compatibility.FILES))
    assert result['copying_only_floor_refactors_verified'] == sorted(m.replay_compatibility.FILES)
    def altered(root, name, manifest):
        data = bound(root, name, manifest)
        if root.parts[0] == 'new' and name == 'floor_label_projection.py':
            data = data.replace(b"result['listed_floor'] = value", b"result['listed_floor'] = value + 1")
        return data
    monkeypatch.setattr(m.shared.common, 'bound_bytes', altered)
    with pytest.raises(ValueError): m.check_implementation_sources(a, b, sorted(m.replay_compatibility.FILES))


@pytest.mark.parametrize('name', ['bayesian_feature_experiment_v3.py', 'reviewed_source_lineage.py'])
def test_real_archived_loader_changes_are_exact_plumbing_only(name):
    archive = Path('data/model/chelsea-bayesian-expanded-spline-floor-disk-20260919/protocol')/name
    if not archive.exists():
        pytest.skip('Local archived fit unavailable')
    local = Path('models')/name if name.startswith('bayesian') else Path('src/apartments')/name
    before, after = archive.read_text(), local.read_text()
    assert m.check_loader_change(before, after)
    with pytest.raises(ValueError): m.check_loader_change(before, after+'\ndef unreviewed(): return 3\n')
    if name.startswith('bayesian'):
        with pytest.raises(ValueError): m.check_loader_change(before, after.replace('v2.pd.DataFrame(rows)', 'v2.pd.DataFrame(rows).fillna(0)'))
    else:
        with pytest.raises(ValueError): m.check_loader_change(before, after.replace('deepcopy(rows)', 'rows[:5]'))
        with pytest.raises(ValueError): m.check_loader_change(before, after.replace('current, residual_scope_changes)', 'current, None)'))


def test_normalization_changes_are_accepted_but_common_priors_are_not(spline_train):
    first = m.spline.FeatureDesign(spline_train)
    second = m.spline.FeatureDesign(spline_train.iloc[:-3])
    assert not np.array_equal(first.means, second.means)
    result = m.check_designs({'design': first}, {'design': second})
    assert result['common_features']
    name = result['common_features'][0]
    second.prior_scales[second.features.index(name)] *= 2
    with pytest.raises(ValueError, match='prior'): m.check_designs({'design': first}, {'design': second})


def test_residual_tail_is_excluded_from_matched_performance():
    a, b, rows = residual_fixture()
    a[1]['residual_log'] = 50
    movements, summary = m.shared.compare_residuals(a, b[:1], rows, rows[:1])
    assert len(movements) == 1
    assert summary['common_rows']['reference_median_absolute_log_residual'] == .1
    assert summary['excluded_reference_rows'] == [a[1]]


def test_physical_contrasts_allow_different_basis_and_support_but_not_semantics():
    interval = {'median': .2, 'lower_95': -.1, 'upper_95': .4, 'probability_positive': .8}
    a = {'id': 'x', 'field': 'laundry_type', 'before': 'none', 'after': 'in_unit',
         'status': 'supported_converged', 'percent_effect': interval, 'design_vector': [1, 0], 'support_before': {'rows': 10}}
    b = deepcopy(a); b.update(design_vector=[.5, 2, 0], support_before={'rows': 8})
    assert m.matched_physical_contrasts([a], [b])['matched'][0]['percent_effect']['median_change'] == 0
    b['after'] = 'in_building'
    with pytest.raises(ValueError, match='semantics'): m.matched_physical_contrasts([a], [b])
    with pytest.raises(ValueError, match='Duplicate'): m.matched_physical_contrasts([a, a], [a])
    b = deepcopy(a); b.update(status='withheld_derived_diagnostics', percent_effect=None)
    assert m.matched_physical_contrasts([a], [b])['matched'][0]['percent_effect'] is None
    assert m.matched_physical_contrasts([a], [])['reference_only'] == [a]


def test_bedroom_contrasts_use_joint_draws_size_and_shortfall(spline_train):
    design = m.spline.FeatureDesign(spline_train)
    fit = {'design': design, 'data': spline_train}
    definitions = m.bedroom_definitions([fit, fit])
    assert definitions
    rng = np.random.default_rng(593)
    beta = rng.normal(scale=.03, size=(4, 1500, len(design.features)))
    bedroom = design.features.index('bedrooms_gt_1')
    shortfall = design.features.index('full_bathroom_shortfall')
    beta[:, :, shortfall] = -.9*beta[:, :, bedroom]+rng.normal(scale=.001, size=beta.shape[:2])
    rows = m.bedroom_contrasts(fit, beta, definitions)
    target = next(r for r in rows if r['before'] == 1 and r['held_fixed']['full_bathrooms'] == 1)
    vector = np.asarray(target['design_vector'])
    assert vector[bedroom] == vector[shortfall] == 1
    size = design.features.index('log_size_within_bedrooms')
    assert vector[size] == pytest.approx(np.log(design.time.size_medians['1']/design.time.size_medians['2']))
    joint = np.einsum('cdf,f->cd', beta, vector).ravel()
    assert target['status'] == 'supported_converged'
    assert target['log_effect']['median'] == pytest.approx(np.median(joint))
    assert target['log_effect']['lower_95'] == pytest.approx(np.quantile(joint, .025))
    beta += np.arange(4)[:, None, None]*10
    bad = m.bedroom_contrasts(fit, beta, definitions)
    assert any(r['status'] == 'withheld_derived_diagnostics' and r['percent_effect'] is None for r in bad)


def test_curve_render_is_deterministic_and_labels_scope_review(spline_train):
    design = m.spline.FeatureDesign(spline_train)
    beta = np.random.default_rng(82).normal(scale=.1, size=(4, 1000, len(design.features)))
    curve = m.smooth.curve_from_draws(design, beta, 1.)
    files = m.render({'curves': [curve, curve]})
    assert files == m.render({'curves': [curve, curve]})
    assert files['floor-curves.png'].startswith(b'\x89PNG')
    assert b'Reviewed retained cohort' in files['floor-curves.svg']


@pytest.mark.parametrize('fault', [None, 'retained_value', 'inherited_layer', 'missing_floor_layer', 'ancestor', 'current_excluded', 'wrong_ads'])
@pytest.mark.parametrize('policy_mode', [None, 'explicit', 'different_bytes', 'alternate_ads'])
def test_source_inverse_preserves_exact_retained_rows_and_both_floor_layers(tmp_path, monkeypatch, fault, policy_mode):
    import json
    from apartments.corrections import canonical
    from apartments.research_pipeline import publish_bundle
    from tests.test_residual_scope_projection import fixture, decision_for, bundle
    rows, _, _ = fixture()
    rows.append({**deepcopy(rows[-1]), 'audit_id': 'kept', 'source_listing_id': 'kept'})
    decisions = []
    expected_ads = set(m.EXCLUDED_ADS)
    if policy_mode == 'alternate_ads':
        expected_ads.remove('1260588')
        expected_ads.add('new-reviewed-ad')
    for i, ad in enumerate(sorted(expected_ads)):
        row = rows[i]
        row['source_listing_id'] = ad if fault != 'wrong_ads' or i else 'unreviewed'
        row['analysis_price_basis'] = ('current_capture_gross_ask' if fault == 'current_excluded' and i == 0
                                      else 'historical_initial_own_advertisement_ask')
        captures = [{**{k: row[k] for k in m.projection.IDENTITIES}, 'capture_id': cid,
            'source_collected_at': row['known_at'], 'known_at': row['known_at'],
            'source_path': '/propertyDetails/address/displayUnit', 'literal': '3D', 'candidate_floor': 3,
            'raw_listing_sha256': 'a'*64, 'body_sha256': 'b'*64} for cid in row['capture_ids']]
        for field in ('floor_label_provenance', 'expanded_floor_provenance'):
            row[field]['source_capture_evidence_sha256'] = m.projection.records_hash(captures)
        decisions.append(decision_for(row, captures))
    rows[-1]['analysis_price_basis'] = 'current_capture_gross_ask'
    sidecars = {module.SIDECAR: '' for module in (m.lineage.reviewed_cohort_quarantine, m.lineage.elevator_corrections,
                m.lineage.floor_label_projection, m.lineage.expanded_floor_projection)}
    source, candidate = tmp_path/'source', tmp_path/'candidate'
    publish_bundle(source, {**sidecars, 'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                   {'version': m.projection.PARENT, 'interpreted_at': '2026-09-19T23:00:00Z'})
    parent = json.loads((source/'complete.json').read_text())
    policy_path = None
    if policy_mode:
        specification = {'version': 'chelsea-residual-scope-policy-v1',
            'source_manifest_sha256': m.digest(source/'complete.json'),
            'cases': [{'source_listing_id': ad, 'action': 'quarantine_nonresidential'} for ad in sorted(expected_ads)]}
        payload = canonical(specification)+'\n'
        sidecars['residual-scope-policy.json'] = payload
        policy_path = tmp_path/'review-policy.json'
        policy_path.write_text(payload + (' ' if policy_mode == 'different_bytes' else ''))
    manifest, kept, changes = bundle(parent, rows, decisions)
    if fault == 'retained_value': kept[0]['asking_rent'] += 1
    if fault == 'inherited_layer': sidecars[m.lineage.expanded_floor_projection.SIDECAR] = '{}\n'
    if fault == 'missing_floor_layer': sidecars.pop(m.lineage.floor_label_projection.SIDECAR)
    publish_bundle(candidate, {**sidecars, 'observations.jsonl': ''.join(canonical(r)+'\n' for r in kept),
        m.projection.SIDECAR: ''.join(canonical(r)+'\n' for r in changes)},
        {k: v for k, v in manifest.items() if k != 'files'})
    calls = []
    def ancestor(manifest, rows, **kwargs):
        calls.append(kwargs)
        return {'version': 'ancestor', 'files': {'observations.jsonl': 'x' if fault == 'ancestor' and len(calls) == 2 else 'same'}}
    # The scope inverse itself is real. Ancestor contracts have their own
    # complete integration tests; here verify both calls and inherited bytes.
    monkeypatch.setattr(m.lineage, 'source_lineage', ancestor)
    if fault or policy_mode == 'different_bytes':
        with pytest.raises(ValueError): m.verify_revision(source, candidate, policy=policy_path)
    else:
        assert m.verify_revision(source, candidate, policy=policy_path) == (rows, kept, changes)
        assert len(calls) == 2
        assert calls[0]['residual_scope_changes'] is None
        assert calls[1]['residual_scope_changes'] == changes
        assert all(call['floor_label_changes'] == call['expanded_floor_changes'] == [] for call in calls)


@pytest.mark.parametrize('fault', ['source', 'empty', 'duplicate', 'action', 'identity'])
def test_explicit_review_policy_rejects_invalid_membership(fault):
    spec = {'version': 'chelsea-residual-scope-policy-v1', 'source_manifest_sha256': 'a'*64,
        'cases': [{'source_listing_id': 'new', 'action': 'quarantine_nonresidential'}]}
    if fault == 'source': spec['source_manifest_sha256'] = 'b'*64
    if fault == 'empty': spec['cases'] = []
    if fault == 'duplicate': spec['cases'] *= 2
    if fault == 'action': spec['cases'][0]['action'] = 'repair_price'
    if fault == 'identity': spec['cases'][0]['source_listing_id'] = 123
    with pytest.raises(ValueError): m.reviewed_ads(spec, 'a'*64)


def test_floor_matching_uses_common_observed_endpoints_and_withholds_failures():
    interval = {'median': .2, 'lower_95': .1, 'upper_95': .3, 'probability_positive': .99}
    def point(level):
        return {'id': f'floor:2->{level}', 'floor': level, 'reference_floor': 2.,
                'status': 'supported_converged', 'percent_effect': interval}
    a = {'reference_floor': 2., 'points': [point(2), point(3), point(5)]}
    b = {'reference_floor': 2., 'points': [point(2), point(3), point(6)]}
    result = m.matched_floor_curves(a, b)
    assert [r['id'] for r in result['matched']] == ['floor:2->3']
    assert result['reference_only'][0]['after'] == 5
    assert result['candidate_only'][0]['after'] == 6
    b['points'][1].update(status='withheld_derived_diagnostics', percent_effect=None)
    assert m.matched_floor_curves(a, b)['matched'][0]['percent_effect'] is None
    b['reference_floor'] = 1
    with pytest.raises(ValueError, match='reference'): m.matched_floor_curves(a, b)
