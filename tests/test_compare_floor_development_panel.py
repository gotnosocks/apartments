import json

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from docs.analysis.scripts.compare_floor_development_panel import run


def inputs(tmp_path, version, *, source_index=0, damage=False):
    panel, comparison, output = (tmp_path/name for name in ('panel', 'comparison', 'output'))
    cases, movements = [], []
    for i in range(26):
        source = {'audit_id': str(i), 'unit_id': f'unit:{i}', 'building': f'building:{i//2}',
                  'source_listing_id': str(100+i), 'period': '2020-01-01', 'asking_rent': 3000.}
        cases.append({'observation': source, 'panel_cell': f'cell:{i//2}'})
        movements.append({**source, 'reference': {'residual_log': .1},
                          'candidate': {'residual_log': .09}, 'fitted_rent_change': 10.})
    if damage:
        movements[0]['asking_rent'] = 4000.
    publish_bundle(panel, {'cases.jsonl': ''.join(canonical(r)+'\n' for r in cases)},
                   {'version': 'floor-source-development-panel-v1', 'dataset_manifest_sha256': 'panel-source'})
    bindings = [{'bindings': {'source': 'other'}}, {'bindings': {'source': 'other'}}]
    bindings[source_index]['bindings']['source'] = 'panel-source'
    publish_bundle(comparison, {'comparison.json': canonical({'version': version, 'fits': bindings}),
                                'residual-movements.jsonl': ''.join(canonical(r)+'\n' for r in movements)},
                   {'version': version})
    return panel, comparison, output


@pytest.mark.parametrize('version,index', [
    ('matched-expanded-floor-spline-fit-comparison-v1', 0),
    ('matched-floor-spline-fit-comparison-v1', 1),
])
def test_fixed_panel_uses_bound_source_without_changing_membership(tmp_path, version, index):
    args = inputs(tmp_path, version, source_index=index)
    run(*args)
    summary = json.loads((args[2]/'summary.json').read_text())
    cases = [json.loads(line) for line in (args[2]/'cases.jsonl').read_text().splitlines()]
    assert summary['rows'] == 26 and summary['membership_unchanged']
    assert summary['panel_source_fit_index'] == index
    assert [r['audit_id'] for r in cases] == [str(i) for i in range(26)]
    assert summary['candidate_median_absolute_log_residual'] == .09


@pytest.mark.parametrize('version,index', [
    ('matched-expanded-floor-spline-fit-comparison-v1', 1),
    ('matched-floor-spline-fit-comparison-v1', 0),
])
def test_panel_bound_to_wrong_side_is_rejected(tmp_path, version, index):
    with pytest.raises(ValueError, match='Panel source differs'):
        run(*inputs(tmp_path, version, source_index=index))


def test_expanded_panel_does_not_accept_changed_targets(tmp_path):
    with pytest.raises(ValueError, match='source identity/target changed'):
        run(*inputs(tmp_path, 'matched-expanded-floor-spline-fit-comparison-v1', damage=True))


def scope_inputs(tmp_path, damage=None):
    panel, ancestor, _ = inputs(tmp_path, 'matched-expanded-floor-spline-fit-comparison-v1')
    result = json.loads((ancestor/'comparison.json').read_text())
    common = dict(result['fits'][1]['bindings'])
    rows = [json.loads(line) for line in (ancestor/'residual-movements.jsonl').read_text().splitlines()]
    for row in rows:
        row['reference'] = dict(row['candidate'])
        row['candidate'] = {'residual_log': .08}
    if damage == 'source': common['source'] = 'unrelated-source'
    if damage == 'fit': common['fit'] = 'different-fit-on-same-source'
    if damage == 'residual': rows[0]['reference']['residual_log'] = .099
    if damage == 'identity': rows[0]['unit_id'] = 'another-unit'
    if damage == 'missing': rows.pop()
    comparison = tmp_path/'scope-comparison'
    publish_bundle(comparison, {
        'comparison.json': canonical({'version': 'matched-residual-scope-spline-fit-comparison-v1',
            'fits': [{'bindings': common}, {'bindings': {'source': 'scope-source'}}]}),
        'residual-movements.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
        {'version': 'matched-residual-scope-spline-fit-comparison-v1'})
    return panel, comparison, tmp_path/'scope-output', ancestor


def test_scope_panel_retains_original_cells_and_proves_common_fit(tmp_path):
    panel, comparison, output, ancestor = scope_inputs(tmp_path)
    run(panel, comparison, output, panel_ancestry=ancestor)
    summary = json.loads((output/'summary.json').read_text())
    rows = [json.loads(line) for line in (output/'cases.jsonl').read_text().splitlines()]
    assert summary['rows'] == 26 and summary['membership_unchanged']
    assert summary['panel_source_fit_index'] is None
    assert summary['panel_ancestor_source_fit_index'] == 0
    assert summary['unchanged_reference_fit_verified']
    assert summary['reference_median_absolute_log_residual'] == .09
    assert summary['candidate_median_absolute_log_residual'] == .08
    assert [r['panel_cell'] for r in rows] == [f'cell:{i//2}' for i in range(26)]
    # Identical invocation reuses the same completed output.
    before = (output/'complete.json').read_bytes()
    run(panel, comparison, output, panel_ancestry=ancestor)
    assert (output/'complete.json').read_bytes() == before


@pytest.mark.parametrize('damage', ['source', 'fit', 'residual', 'identity', 'missing'])
def test_scope_panel_rejects_broken_ancestry_or_membership(tmp_path, damage):
    panel, comparison, output, ancestor = scope_inputs(tmp_path, damage)
    with pytest.raises(ValueError):
        run(panel, comparison, output, panel_ancestry=ancestor)
    assert not (output/'complete.json').exists()


def test_scope_panel_requires_explicit_ancestry(tmp_path):
    panel, comparison, output, _ = scope_inputs(tmp_path)
    with pytest.raises(ValueError, match='requires.*ancestry'):
        run(panel, comparison, output)


def test_other_comparisons_reject_unexpected_ancestry(tmp_path):
    panel, comparison, output = inputs(tmp_path, 'matched-expanded-floor-spline-fit-comparison-v1')
    with pytest.raises(ValueError, match='Unexpected panel ancestry'):
        run(panel, comparison, output, panel_ancestry=comparison)
