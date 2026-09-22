from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import expanded_floor_fit_comparison as m
from tests.test_bayesian_floor_increment_design import train
from tests.test_bayesian_floor_spline_design import spline_train
from tests.test_floor_spline_fit_comparison import protocols as original_protocols
from tests.test_expanded_floor_projection import example, extend
from tests.test_bayesian_feature_report import publish_binary


def protocols():
    _, a = original_protocols()
    a.update(source_version=m.projection.PARENT, rows=100, units=50)
    b = deepcopy(a)
    b.update(source_version=m.projection.VERSION, source_manifest_sha256='new',
        source_observations_sha256='new', source_directory='candidate')
    b['implementation_sha256']['expanded_floor_projection.py'] = 'new'
    for name in m.LOADER_CODE:
        a['implementation_sha256'][name] = 'old'; b['implementation_sha256'][name] = 'new'
    return a, b


@pytest.mark.parametrize('fault', [None, 'math', 'sampler_code', 'added_code', 'removed_code', 'missing_contract',
    'prior', 'group_prior', 'noise', 'draws', 'maxdepth', 'seed', 'rows', 'units', 'knots', 'anchor', 'policy',
    'version', 'floor_order', 'floor_nonfinite', 'both_short'])
def test_source_revision_cannot_hide_specification_or_sampling_changes(fault):
    a, b = protocols()
    if fault == 'math': b['implementation_sha256']['bayesian_floor_spline_design.py'] = 'changed'
    elif fault == 'sampler_code': b['implementation_sha256']['bayesian_disk_sampling.py'] = 'changed'
    elif fault == 'added_code': b['implementation_sha256']['surprise.py'] = 'changed'
    elif fault == 'removed_code': b['implementation_sha256'].pop('bayesian_floor_spline_design.py')
    elif fault == 'missing_contract': b['implementation_sha256'].pop('expanded_floor_projection.py')
    elif fault == 'prior': b['floor_prior_scale'] = .2
    elif fault == 'group_prior': b['unit_prior_scale'] = .8
    elif fault == 'noise': b['residual_scale'] = 'bedroom'
    elif fault == 'draws': b['draws'] = 50
    elif fault == 'maxdepth': b['maxdepth'] = 14
    elif fault == 'seed': b['seed'] = 1
    elif fault == 'rows': b['rows'] += 1
    elif fault == 'units': b['units'] += 1
    elif fault == 'knots': b['floor_knots'] = [1, 10]
    elif fault == 'anchor': b['floor_reference'] = 3
    elif fault == 'policy': b['floor_policy'] = {}
    elif fault == 'version': b['source_version'] = 'wrong'
    elif fault == 'floor_order': b['floor_levels'].reverse()
    elif fault == 'floor_nonfinite': b['floor_levels'][-1] = float('inf')
    elif fault == 'both_short': a['draws'] = b['draws'] = 50
    if fault:
        with pytest.raises(ValueError): m.check_protocols(a, b)
    else:
        assert set(m.check_protocols(a, b)) == m.LOADER_CODE


def test_observed_support_can_expand_inside_identical_basis():
    a, b = protocols()
    b['floor_levels'] = sorted(b['floor_levels']+[4.])
    assert set(m.check_protocols(a, b)) == m.LOADER_CODE


BEFORE = '''
from pathlib import Path

def load_data(dataset):
    floor_label_sidecar = reviewed_source_lineage.floor_label_projection.SIDECAR
    manifest, files = _verified_bundle(dataset, retain={'observations.jsonl', floor_label_sidecar})
    reviewed_source_lineage.source_lineage(manifest, rows, floor_label_changes=None)
    data = pd.DataFrame(rows)
    return data

def implementation_paths():
    modules = (base, reviewed_source_lineage.floor_label_projection)
    return [Path(m.__file__) for m in modules]

def make_model(data):
    return data * 2
'''
AFTER = BEFORE.replace('    manifest, files',
    '    expanded_floor_sidecar = reviewed_source_lineage.expanded_floor_projection.SIDECAR\n    manifest, files')
AFTER = AFTER.replace("'observations.jsonl', floor_label_sidecar}", "'observations.jsonl', floor_label_sidecar, expanded_floor_sidecar}")
AFTER = AFTER.replace('floor_label_changes=None)', "floor_label_changes=None, expanded_floor_changes=[json.loads(s) for s in files[expanded_floor_sidecar].decode().split('\\n') if s.strip()] if expanded_floor_sidecar in files else None)")
AFTER = AFTER.replace('modules = (base, reviewed_source_lineage.floor_label_projection)',
    'modules = (base, reviewed_source_lineage.floor_label_projection, reviewed_source_lineage.expanded_floor_projection)')


@pytest.mark.parametrize('fault', [None, 'model', 'sampler', 'loader_transform', 'plumbing_value', 'new_import'])
def test_v3_filename_allowance_does_not_allow_arbitrary_math_or_loader_changes(fault):
    after = AFTER
    if fault == 'model': after = after.replace('data * 2', 'data * 3')
    elif fault == 'sampler': after += '\ndef sample():\n    return approximate_sampler()\n'
    elif fault == 'loader_transform': after = after.replace('pd.DataFrame(rows)', 'pd.DataFrame(rows).fillna(0)')
    elif fault == 'plumbing_value': after = after.replace("files[expanded_floor_sidecar].decode()", 'unrelated().decode()')
    elif fault == 'new_import': after = 'import unrelated\n'+after
    if fault:
        with pytest.raises(ValueError): m.check_v3_loader_change(BEFORE, after)
    else:
        assert m.check_v3_loader_change(BEFORE, after)


@pytest.fixture
def fits(tmp_path, spline_train):
    a = spline_train.copy(); b = a.copy()
    b.loc[b.listed_floor.isna(), 'listed_floor'] = 7.
    result = []
    for name, frame in [('a', a), ('b', b)]:
        design = m.spline.FeatureDesign(frame)
        target = tmp_path/name/'fit'; design.save(target)
        manifest = publish_binary(target, {p.name: p.read_bytes() for p in target.iterdir()}, {})
        result.append({'root': target.parent, 'data': frame, 'design': design,
            'provenance': {'fit_manifest': manifest}, 'reconstruction': {'time_arrays': {'same': 'same'}}})
    return result


@pytest.mark.parametrize('fault', [None, 'value', 'prior', 'center', 'order', 'time', 'floor_prior', 'knots', 'unknown_prior'])
def test_floor_coverage_change_preserves_nonfloor_and_time_design(fits, fault):
    a, b = fits; design = b['design']
    index = next(i for i, name in enumerate(design.features) if not m.smooth.is_floor(name))
    if fault == 'value': b['data'].loc[0, 'bedrooms'] = 6
    elif fault == 'prior': design.prior_scales[index] *= 2
    elif fault == 'center': design.means[index] += .1
    elif fault == 'order': design.features[index] = 'unexpected'
    elif fault == 'time': b['reconstruction']['time_arrays']['same'] = 'different'
    elif fault == 'floor_prior': design.floor_prior_scale *= 2
    elif fault == 'knots': design.floor_knots[-1] += 1
    elif fault == 'unknown_prior':
        # Keep some unknown rows in the candidate to retain its reporting term.
        b['data'].loc[b['data'].index[-1], 'listed_floor'] = np.nan
        b['design'] = m.spline.FeatureDesign(b['data'])
        b['design'].prior_scales[b['design'].features.index('listed_floor.unknown')] *= 2
    if fault:
        with pytest.raises(ValueError): m.check_designs(a, b)
    else:
        assert not any(m.smooth.is_floor(name) for name in m.check_designs(a, b))
        assert 'listed_floor.unknown' in a['design'].features
        assert 'listed_floor.unknown' not in b['design'].features


def test_residual_slices_distinguish_new_inferences_and_photo_corrections():
    before = [{'audit_id': str(i), 'unit_id': str(i), 'building': 'b', 'advertised_floor': floor,
        'analysis_price_basis': 'current_capture_gross_ask' if i == 0 else 'historical'}
        for i, floor in enumerate([None, 3, 2, None])]
    after = deepcopy(before)
    after[0]['listed_floor'] = 5
    after[1].update(advertised_floor=None, listed_floor=6, expanded_floor_provenance={'correction_id': 'c'})
    movement = [{**row, 'reference': {'residual_log': .1}, 'candidate': {'residual_log': .05},
        'fitted_rent_change': 2.} for row in after]
    result = m.residual_slices(before, after, movement)
    assert {key: value['rows'] for key, value in result.items()} == {
        'all': 4, 'current_capture': 1, 'newly_inferred_floor': 1, 'corrected_photo_floor': 1,
        'previously_known_floor': 1, 'remaining_unknown_floor': 1}
    with pytest.raises(ValueError): m.residual_slices(before, after[::-1], movement)
    with pytest.raises(ValueError): m.residual_slices(before, after, movement[:-1])


@pytest.mark.parametrize('fault', [None, 'bedrooms', 'price', 'identity', 'sidecar', 'wrong_reference'])
def test_published_revision_requires_exact_inverse_and_nonfloor_identity(tmp_path, fault):
    parent, row, old_change, _ = example()
    source, destination = tmp_path/'source', tmp_path/'expanded'
    publish_bundle(source, {'observations.jsonl': canonical(row)+'\n',
        m.projection.original.SIDECAR: canonical(old_change)+'\n'},
        {k: v for k, v in parent.items() if k != 'files'})
    parent = json.loads((source/'complete.json').read_text())
    manifest, after, changes = extend(parent, [row], [old_change])
    if fault == 'bedrooms': after[0]['bedrooms'] = 9
    elif fault == 'price': after[0]['asking_rent'] = 99000
    elif fault == 'identity': after[0]['audit_id'] = 'other'
    elif fault == 'sidecar': changes[0]['source_row_sha256'] = 'a'*64
    publish_bundle(destination, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in after),
        m.projection.SIDECAR: ''.join(canonical(r)+'\n' for r in changes)},
        {k: v for k, v in manifest.items() if k != 'files'})
    if fault == 'wrong_reference':
        source = tmp_path/'other'
        publish_bundle(source, {'observations.jsonl': canonical(row)+'\n',
            m.projection.original.SIDECAR: canonical(old_change)+'\n'},
            {**{k: v for k, v in parent.items() if k != 'files'}, 'unrelated': True})
    if fault:
        with pytest.raises(ValueError): m.verify_revision(source, destination)
    else:
        assert m.verify_revision(source, destination) == ([row], after)


def test_curves_use_joint_within_fit_draws_without_cross_fit_pairing(spline_train):
    design = m.spline.FeatureDesign(spline_train)
    rng = np.random.default_rng(754)
    beta = rng.normal(size=(4, 1000, len(design.features)))
    i, j = [design.features.index('listed_floor_spline_'+str(n)) for n in (0, 1)]
    beta[:, :, j] = -.95*beta[:, :, i]+rng.normal(scale=.01, size=beta.shape[:2])
    curve = m.smooth.curve_from_draws(design, beta, 1.)
    target = next(row for row in curve['points'] if row['floor'] == 10.)
    joint = np.einsum('cdf,f->cd', beta, design.contrast_vector(2., 10.)).ravel()
    assert target['log_effect']['median'] == pytest.approx(np.median(joint))
    assert target['log_effect']['lower_95'] == pytest.approx(np.quantile(joint, .025))
    result = {'curves': [curve, curve]}
    files = m.render(result)
    assert files == m.render(result)
    assert files['floor-curves.png'].startswith(b'\x89PNG')
    assert b'Expanded floor coverage' in files['floor-curves.svg']


def test_support_driven_boundary_change_allowed_and_joint_prior_difference_exposed(spline_train):
    a, b = protocols()
    b['floor_levels'].append(12.)
    b['floor_knots'], b['floor_reference'] = m.spline.knot_specification(b['floor_levels'])
    assert set(m.check_protocols(a, b)) == m.LOADER_CODE
    source = spline_train.copy()
    revised = source.copy()
    revised.loc[revised.listed_floor.isna(), 'listed_floor'] = 57.
    designs = [m.spline.FeatureDesign(frame) for frame in (source, revised)]
    m.check_design_arrays(*designs, source, revised)
    result = m.prior_comparison(*designs, 1.)
    assert result['reference_knots'][-1] == 52.
    assert result['candidate_knots'][-1] == 57.
    assert result['maximum_absolute_log_sd_change'] > 0
    assert result['maximum_absolute_log_covariance_change'] > 0
    i = result['common_floors'].index(10.)
    j = result['common_floors'].index(20.)
    for key, design in zip(['reference', 'candidate'], designs, strict=True):
        first = design.contrast_vector(2., 10.)*design.prior_scales
        second = design.contrast_vector(2., 20.)*design.prior_scales
        assert result[key+'_log_curve_covariance'][i][j] == pytest.approx(first @ second)
    same = m.prior_comparison(designs[0], designs[0], 1.)
    assert same['maximum_absolute_log_covariance_change'] == 0


@pytest.mark.parametrize('fault', [None, 'contract', 'v3_math'])
def test_archived_contract_and_changed_v3_scope_are_verified(monkeypatch, fault):
    a = {'root': Path('reference'), 'provenance': {'protocol_manifest': {}}}
    b = {'root': Path('candidate'), 'provenance': {'protocol_manifest': {}}}
    def bound(root, name, manifest):
        if name == 'expanded_floor_projection.py':
            return b'wrong contract' if fault == 'contract' else Path(m.projection.__file__).read_bytes()
        if root == a['root']/'protocol':
            return BEFORE.encode()
        return (AFTER.replace('data * 2', 'data * 9') if fault == 'v3_math' else AFTER).encode()
    monkeypatch.setattr(m.shared.common, 'bound_bytes', bound)
    if fault:
        with pytest.raises(ValueError): m.check_implementation_sources(a, b, ['bayesian_feature_experiment_v3.py'])
    else:
        assert m.check_implementation_sources(a, b, ['bayesian_feature_experiment_v3.py']) == {
            'v3_exact_sidecar_plumbing_only': True, 'expanded_contract_matches_archive': True}
