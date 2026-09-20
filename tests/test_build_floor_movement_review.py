from copy import deepcopy
import json

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from apartments.reviewed_cohort_quarantine import records_hash, sha
from docs.analysis.scripts import build_floor_movement_review as m
from tests.test_expanded_floor_projection import example, extend, bundle, mask_for


def fixture(expanded=True, masked=False):
    parent, row, old_change, _ = example(advertised=3 if masked else None)
    # Add the minimal movement target, preserving the exact older projection.
    before = deepcopy(row)
    for name in m.floor_label_projection.FIELDS:
        before.pop(name)
    before.pop('listed_floor', None)
    before['asking_rent'] = 3000.
    row['asking_rent'] = 3000.
    old_change['source_row_sha256'] = sha(before)
    parent['source_manifest']['files']['observations.jsonl'] = records_hash([before])
    parent['source_manifest_sha256'] = records_hash([parent['source_manifest']])
    parent['files']['observations.jsonl'] = records_hash([row])
    parent['files'][m.floor_label_projection.SIDECAR] = records_hash([old_change])
    if expanded:
        manifest, rows, changes = extend(parent, [row], [old_change])
        if masked:
            policy = manifest['policy']
            policy['floor_masks'] = [mask_for(row, old_change)]
            manifest, rows, changes = bundle(parent, [row], [old_change], policy)
        files = {'observations.jsonl': (canonical(rows[0])+'\n').encode(),
            m.floor_label_projection.SIDECAR: (canonical(old_change)+'\n').encode(),
            m.expanded_floor_projection.SIDECAR: (canonical(changes[0])+'\n').encode()}
        manifest['files'][m.floor_label_projection.SIDECAR] = records_hash([old_change])
    else:
        manifest, rows = parent, [row]
        files = {'observations.jsonl': (canonical(row)+'\n').encode(),
            m.floor_label_projection.SIDECAR: (canonical(old_change)+'\n').encode()}
    return manifest, files, rows


@pytest.mark.parametrize('expanded', [False, True])
def test_loads_correct_building_evidence_and_every_projection_stage(expanded):
    manifest, files, rows = fixture(expanded)
    version = m.EXPANDED_COMPARISON if expanded else 'matched-floor-spline-fit-comparison-v1'
    got, old_changes, new_changes, evidence = m.verified_floor_source(manifest, files, version)
    assert got == rows
    assert old_changes[0]['captures'][0]['literal'] == '601'
    assert evidence['b'][0]['floor_count'] == 12
    if expanded:
        assert new_changes[0]['original_change'] == old_changes[0]
        assert 'building_floor_evidence' not in manifest
    else:
        assert new_changes is None


@pytest.mark.parametrize('fault', ['wrong_source_version', 'wrong_comparison_version', 'missing_old_sidecar',
    'missing_new_sidecar', 'tampered_old_sidecar', 'tampered_new_sidecar', 'tampered_row', 'tampered_building_context'])
def test_expanded_source_rejects_wrong_versions_and_sidecar_ancestry(fault):
    manifest, files, _ = fixture()
    version = m.EXPANDED_COMPARISON
    if fault == 'wrong_source_version': manifest['version'] = m.floor_label_projection.VERSION
    elif fault == 'wrong_comparison_version': version = 'matched-floor-spline-fit-comparison-v1'
    elif fault == 'missing_old_sidecar': files.pop(m.floor_label_projection.SIDECAR)
    elif fault == 'missing_new_sidecar': files.pop(m.expanded_floor_projection.SIDECAR)
    elif fault == 'tampered_old_sidecar':
        changes = m.records(files[m.floor_label_projection.SIDECAR]); changes[0]['source_index'] = 2
        files[m.floor_label_projection.SIDECAR] = (canonical(changes[0])+'\n').encode()
        manifest['files'][m.floor_label_projection.SIDECAR] = records_hash(changes)
    elif fault == 'tampered_new_sidecar':
        changes = m.records(files[m.expanded_floor_projection.SIDECAR]); changes[0]['source_index'] = 2
        files[m.expanded_floor_projection.SIDECAR] = (canonical(changes[0])+'\n').encode()
        manifest['files'][m.expanded_floor_projection.SIDECAR] = records_hash(changes)
    elif fault == 'tampered_row':
        rows = m.records(files['observations.jsonl']); rows[0]['asking_rent'] += 100
        files['observations.jsonl'] = (canonical(rows[0])+'\n').encode()
        manifest['files']['observations.jsonl'] = records_hash(rows)
    elif fault == 'tampered_building_context':
        manifest['policy']['building_floor_evidence']['b'][0]['floor_count'] = 30
        manifest['policy_sha256'] = sha(manifest['policy'])
    with pytest.raises(ValueError): m.verified_floor_source(manifest, files, version)


def test_legacy_comparison_rejects_hidden_expanded_stage():
    manifest, files, _ = fixture(False)
    files[m.expanded_floor_projection.SIDECAR] = b'{}\n'
    with pytest.raises(ValueError, match='Unexpected expanded'):
        m.verified_floor_source(manifest, files, 'matched-label-floor-fit-comparison-v1')


def test_records_preserve_literal_unicode_line_separator():
    assert m.records('{"label":"3RW\u2028literal"}\n'.encode()) == [{'label': '3RW\u2028literal'}]


def test_scope_sidecars_are_selected_after_exact_outer_reconstruction(monkeypatch):
    from tests.test_residual_scope_projection import fixture as scope_fixture
    rows, _, (manifest, kept, changes) = scope_fixture()
    source = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in kept).encode(),
        m.residual_scope_projection.SIDECAR: ''.join(canonical(c)+'\n' for c in changes).encode()}
    implementation = m.verified_floor_source
    old = [{'original': r['audit_id']} for r in rows]
    expanded = [{'expanded': r['audit_id']} for r in rows]
    # Inner floor contracts have real fixtures above; isolate alignment across
    # the real scope inverse, which removes indices zero and two here.
    def inner(parent, files, version):
        assert parent == manifest['source_manifest'] and version == m.EXPANDED_COMPARISON
        assert m.records(files['observations.jsonl']) == rows
        assert m.residual_scope_projection.SIDECAR not in files
        return rows, old, expanded, {'building': ['exact context']}
    monkeypatch.setattr(m, 'verified_floor_source', inner)
    got, a, b, context = implementation(manifest, source, m.SCOPE_COMPARISON)
    assert got == kept and a == [old[1], old[3]] and b == [expanded[1], expanded[3]]
    assert context == {'building': ['exact context']}
    damaged = deepcopy(source)
    damaged[m.residual_scope_projection.SIDECAR] = b'{}\n'
    with pytest.raises(ValueError): implementation(manifest, damaged, m.SCOPE_COMPARISON)


def test_scope_comparison_requires_outer_sidecar_and_rejects_hidden_stage():
    manifest, files, _ = fixture()
    with pytest.raises(ValueError, match='Missing residual-scope'):
        m.verified_floor_source(manifest, files, m.SCOPE_COMPARISON)
    files[m.residual_scope_projection.SIDECAR] = b'{}\n'
    with pytest.raises(ValueError, match='Unexpected residual-scope'):
        m.verified_floor_source(manifest, files, m.EXPANDED_COMPARISON)


@pytest.mark.parametrize('expanded', [False, True])
@pytest.mark.parametrize('fault', [None, 'wrong_source_binding', 'movement_identity', 'ranked_movement'])
def test_published_cases_include_both_stages_and_keep_existing_identity_guards(tmp_path, monkeypatch, expanded, fault):
    manifest, files, rows = fixture(expanded, masked=expanded)
    dataset, comparison, evidence, output = [tmp_path/name for name in ('dataset', 'comparison', 'evidence', 'output')]
    publish_bundle(dataset, {k: v.decode() for k, v in files.items()}, {k: v for k, v in manifest.items() if k != 'files'})
    publish_bundle(evidence, {'evidence.jsonl': '{}\n'}, {'version': 'test-evidence'})
    movement = {**{k: rows[0][k] for k in ('audit_id', 'unit_id', 'building', 'source_listing_id', 'asking_rent')},
        'fitted_rent_change': 100.}
    result = {'version': m.EXPANDED_COMPARISON if expanded else 'matched-floor-spline-fit-comparison-v1',
        'fits': [{}, {'bindings': {'source': digest(dataset/'complete.json')}}],
        'largest_distinct_unit_movements': [deepcopy(movement)],
        'largest_unit_offset_movements': [{'id': rows[0]['unit_id']}],
        'largest_common_reference_building_movements': [{'id': rows[0]['building']}]}
    if fault == 'wrong_source_binding': result['fits'][1]['bindings']['source'] = 'a'*64
    elif fault == 'movement_identity': movement['source_listing_id'] = 'different'
    elif fault == 'ranked_movement': result['largest_distinct_unit_movements'][0]['fitted_rent_change'] = 20.
    publish_bundle(comparison, {'comparison.json': canonical(result)+'\n',
        'residual-movements.jsonl': canonical(movement)+'\n'}, {'version': result['version']})
    # Full evidence-lineage verification is separately exercised by the evidence
    # tests; this fixture isolates selection, publishing and source-stage binding.
    monkeypatch.setattr(m, 'load_evidence', lambda *args: {rows[0]['audit_id']: [{'description': 'own literal'}]})
    if fault:
        with pytest.raises(ValueError): m.run(comparison, dataset, evidence, output)
        assert not (output/'complete.json').exists()
    else:
        published = m.run(comparison, dataset, evidence, output)
        case = json.loads((output/'cases.jsonl').read_text())
        assert published['source_projection_version'] == manifest['version']
        assert published['cases'] == 1 and published['selection_reasons'] == 3
        assert case['floor_projection']['captures'][0]['literal'] == '601'
        assert case['building_floor_evidence'][0]['floor_count'] == 12
        assert ('expanded_floor_projection' in case) is expanded
        if expanded:
            assert case['expanded_floor_projection']['original_change'] == case['floor_projection']
            assert case['expanded_floor_mask']['correction_record']['id'] == 'correction-1'
            assert sha(case['expanded_floor_mask']) == case['observation']['expanded_floor_provenance']['floor_mask_sha256']
        assert case['descriptions'] == [{'description': 'own literal'}]
