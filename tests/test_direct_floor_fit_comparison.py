from copy import deepcopy

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import direct_floor_fit_comparison as comparison
from tests.test_direct_floor_projection import example


def test_exact_source_revision_and_tampering(example, tmp_path):
    manifest, rows, changes = example
    reference, candidate = tmp_path/'reference', tmp_path/'candidate'
    parent = manifest['source_manifest']
    before = [changes[0]['before']]
    publish_bundle(reference, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in before)},
                   {k: v for k, v in parent.items() if k != 'files'})
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows),
             comparison.projection.SIDECAR: ''.join(canonical(r)+'\n' for r in changes)}
    publish_bundle(candidate, files, {k: v for k, v in manifest.items() if k != 'files'})
    assert comparison.verify_revision(reference, candidate) == (before, rows)
    tampered = deepcopy(rows)
    tampered[0]['asking_rent'] = 1
    files['observations.jsonl'] = ''.join(canonical(r)+'\n' for r in tampered)
    bad = tmp_path/'tampered'
    publish_bundle(bad, files, {k: v for k, v in manifest.items() if k != 'files'})
    with pytest.raises(ValueError, match='forward replay'):
        comparison.verify_revision(reference, bad)


def test_residual_slices_use_floor_alias_and_exact_membership():
    before = [{'audit_id': str(i), 'building': 'b', 'unit_id': str(i),
        'analysis_price_basis': 'current_capture_gross_ask', 'listed_floor': value,
        'advertised_floor': alias} for i, (value, alias) in enumerate([(None, None), (None, 4), (None, None)])]
    after = deepcopy(before)
    after[0].update(listed_floor=2, advertised_floor=2)
    movements = [{'audit_id': str(i), 'unit_id': str(i), 'reference': {'residual_log': .2},
                  'candidate': {'residual_log': .1}, 'fitted_rent_change': 10} for i in range(3)]
    result = comparison.residual_slices(before, after, movements)
    assert result['all']['rows'] == result['current_capture']['rows'] == 3
    assert result['new_explicit_floor']['rows'] == 1
    assert result['previously_known_floor']['rows'] == 1
    assert result['remaining_unknown_floor']['rows'] == 1
    for invalid in (movements[:-1], movements + [movements[0]]):
        with pytest.raises(ValueError, match='membership'):
            comparison.residual_slices(before, after, invalid)
