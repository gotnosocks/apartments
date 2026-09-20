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
