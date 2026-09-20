import copy
import hashlib
import json

import pytest

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle


def fixtures(*, cleaned=False):
    original={'dataset_version':'historical-plus-current-capture-analysis-v1',
              'files':{'observations.jsonl':'original-exact-cohort-hash'}}
    reported={'version':'reported-bathroom-counts-projection-v1','dataset_manifest':original}
    reviewed={'version':'reviewed-bathroom-counts-projection-v1','projection_manifest':reported}
    manifest=reviewed
    if cleaned:
        manifest={'version':'reviewed-scope-composition-projection-v2','source_manifest':reviewed,
                  'source_manifest_sha256':hashlib.sha256((canonical(reviewed)+'\n').encode()).hexdigest()}
    rows=[{'audit_id':'kept','source_listing_id':'123','unit_id':'u1','capture_ids':[12,13],
           'known_at':'2026-09-18T12:00:00+00:00'},
          {'audit_id':'no-text','source_listing_id':'124','unit_id':'u2','capture_id':14,
           'known_at':'2026-09-18T12:00:00+00:00'}]
    literal='Literal <script>alert(1)</script> en-suite.\u2028Second line'
    captures=[{'audit_id':'kept','source_listing_id':'123','unit_id':'u1','capture_id':12,
               'description':literal,'description_sha256':hashlib.sha256(literal.encode()).hexdigest(),
               'source_collected_at':'2026-09-10T10:00:00+00:00','known_at':'2026-09-18T10:00:00+00:00',
               'description_interpreted_at':'2026-09-17T10:00:00+00:00',
               'body_sha256':'body-hash','raw_listing_sha256':'raw-hash',
               'extraction':{'inferred_ensuite_count':9}},
              {'audit_id':'quarantined','source_listing_id':'999','unit_id':'removed','capture_id':99,
               'description':'Excluded ad; never joined by unit or ad alone.'}]
    evidence={'version':'fitted-description-archive-v1','dataset_manifest':original}
    return manifest,rows,evidence,captures


def publish(tmp_path,parts):
    manifest,rows,evidence,captures=parts
    dataset=tmp_path/'dataset';archive=tmp_path/'archive'
    publish_bundle(dataset,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},manifest)
    publish_bundle(archive,{'evidence.jsonl':''.join(canonical(r)+'\n' for r in captures)},evidence)
    return dataset,archive


@pytest.mark.parametrize('cleaned',[False,True])
def test_exact_lineage_survivors_and_literal_text_only(tmp_path,cleaned):
    parts=fixtures(cleaned=cleaned)
    mapping=load_evidence(*publish(tmp_path,parts))
    assert set(mapping)=={'kept','no-text'}
    assert mapping['no-text']==[]
    assert mapping['kept'][0]['description']==parts[3][0]['description']
    assert mapping['kept'][0]['source_path']=='/description'
    assert mapping['kept'][0]['body_sha256']=='body-hash'
    assert 'extraction' not in mapping['kept'][0]
    assert 'inferred_ensuite_count' not in mapping['kept'][0]


@pytest.mark.parametrize('field,value',[
    ('source_listing_id','999'),('unit_id','u2'),('capture_id',14),('capture_id','12'),
    ('capture_id',True),('source_collected_at','2026-09-19'),
    ('known_at','2026-09-19'),('known_at','2026-09-09'),
    ('description_interpreted_at','2026-09-19'),('description_interpreted_at','2026-09-09'),
    ('description_sha256','bad'),('description',{'not':'literal'})])
def test_surviving_identity_clock_or_literal_mismatch_rejected(tmp_path,field,value):
    parts=fixtures();parts[3][0][field]=value
    with pytest.raises(ValueError):load_evidence(*publish(tmp_path,parts))


def test_recovery_cannot_postdate_capture_knowledge_even_before_row_cutoff(tmp_path):
    parts=fixtures();parts[3][0]['description_interpreted_at']='2026-09-18T11:00:00+00:00'
    with pytest.raises(ValueError,match='clock'):load_evidence(*publish(tmp_path,parts))


def test_duplicate_capture_and_duplicate_observation_rejected(tmp_path):
    parts=fixtures();parts[3].append(copy.deepcopy(parts[3][0]))
    with pytest.raises(ValueError,match='duplicated'):load_evidence(*publish(tmp_path,parts))
    parts=fixtures();parts[1].append(copy.deepcopy(parts[1][0]))
    with pytest.raises(ValueError,match='duplicate observation'):
        load_evidence(*publish(tmp_path/'second',parts))


@pytest.mark.parametrize('fault',['wrong_original','unrelated_nested_match','parent_hash','wrong_parent_version','decision_conflict'])
def test_lineage_is_explicit_not_an_arbitrary_nested_manifest_match(tmp_path,fault):
    parts=fixtures(cleaned=True);manifest=parts[0]
    if fault=='wrong_original':parts[2]['dataset_manifest']= {'dataset_version':'historical-plus-current-capture-analysis-v1','files':{}}
    if fault=='unrelated_nested_match':
        manifest['source_manifest']['projection_manifest']['dataset_manifest']={'dataset_version':'wrong'}
        manifest['unrelated_dataset_manifest']=parts[2]['dataset_manifest']
    if fault=='parent_hash':manifest['source_manifest_sha256']='bad'
    if fault=='wrong_parent_version':manifest['source_manifest']['version']='unrelated-projection'
    if fault=='decision_conflict':manifest['source_manifest']['decision_manifest']={'projection_manifest':{}}
    if fault!='parent_hash':
        manifest['source_manifest_sha256']=hashlib.sha256((canonical(manifest['source_manifest'])+'\n').encode()).hexdigest()
    with pytest.raises(ValueError):load_evidence(*publish(tmp_path,parts))


def test_property_details_literal_precedence_and_missing_text(tmp_path):
    parts=fixtures();capture=parts[3][0]
    literal='Nested <b>private bath</b>'
    capture['property_details']={'description':literal}
    capture['description_sha256']=hashlib.sha256(literal.encode()).hexdigest()
    missing=copy.deepcopy(capture);missing.update(capture_id=13,description=None,description_sha256=None)
    del missing['property_details']
    parts[3].append(missing)
    result=load_evidence(*publish(tmp_path,parts))['kept']
    assert result[0]['description']==literal and result[0]['source_path']=='/propertyDetails/description'
    assert result[1]['description'] is None


def test_bundle_tampering_rejected_before_attachment(tmp_path):
    dataset,archive=publish(tmp_path,fixtures())
    (archive/'evidence.jsonl').write_text('{}\n')
    with pytest.raises(ValueError,match='integrity'):load_evidence(dataset,archive)


def test_fitted_archive_requires_capture_knowledge_clock(tmp_path):
    parts=fixtures();del parts[3][0]['known_at']
    with pytest.raises(ValueError,match='knowledge clock'):load_evidence(*publish(tmp_path,parts))


def refreshed_parts(tmp_path):
    _, rows, _, captures = fixtures()
    captures = [captures[0], {**captures[0], 'capture_id': 13},
        {**captures[0], 'audit_id': 'no-text', 'source_listing_id': '124', 'unit_id': 'u2',
         'capture_id': 14, 'description': None, 'description_sha256': None}]
    dataset = tmp_path/'dataset'
    dm = publish_bundle(dataset, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                        {'version': 'reviewed-capture-refreshed-analysis-v1'})
    em = {'version': 'refreshed-fitted-description-archive-v1',
          'dataset_manifest_sha256': digest(dataset/'complete.json'),
          'dataset_observations_sha256': dm['files']['observations.jsonl']}
    return dataset, em, captures


def test_refreshed_evidence_exact_binding_full_coverage_and_literal_text(tmp_path):
    dataset, em, captures = refreshed_parts(tmp_path)
    archive = tmp_path/'archive'
    publish_bundle(archive, {'evidence.jsonl': ''.join(canonical(c)+'\n' for c in captures)}, em)
    result = load_evidence(dataset, archive)
    assert len(result['kept']) == 2 and result['no-text'][0]['description'] is None
    assert result['kept'][0]['description'] == captures[0]['description']


@pytest.mark.parametrize('fault', ['manifest', 'observations', 'missing_capture', 'capture_type', 'clock'])
def test_refreshed_evidence_rejects_wrong_binding_coverage_or_clock(tmp_path, fault):
    dataset, em, captures = refreshed_parts(tmp_path)
    if fault == 'manifest': em['dataset_manifest_sha256'] = 'bad'
    if fault == 'observations': em['dataset_observations_sha256'] = 'bad'
    if fault == 'missing_capture': captures.pop()
    if fault == 'capture_type': captures[0]['capture_id'] = '12'
    if fault == 'clock': captures[0]['known_at'] = '2026-09-19'
    archive = tmp_path/'archive'
    publish_bundle(archive, {'evidence.jsonl': ''.join(canonical(c)+'\n' for c in captures)}, em)
    with pytest.raises(ValueError): load_evidence(dataset, archive)


@pytest.mark.parametrize('fault', [None, 'missing_sidecar', 'changed_excluded_row', 'changed_retained_row'])
def test_quarantine_evidence_requires_inverse_lineage_and_returns_survivors_only(tmp_path, fault):
    from apartments.reviewed_source_lineage import REFRESHED, LAUNDRY, FLOOR
    from tests.test_reviewed_source_lineage import revise
    from tests.test_reviewed_cohort_quarantine import quarantine_last

    old, em, captures = refreshed_parts(tmp_path)
    rows = [json.loads(s) for s in (old/'observations.jsonl').read_text().split('\n') if s]
    for row in rows:
        row.update(laundry_type='in_building', advertised_floor=3,
                   analysis_price_basis='historical_initial_own_advertisement_ask')
        if 'capture_ids' not in row: row['capture_ids'] = [row['capture_id']]
    original = tmp_path/'original'
    parent = publish_bundle(original, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                            {'version': REFRESHED})
    em.update(dataset_manifest_sha256=digest(original/'complete.json'),
              dataset_observations_sha256=parent['files']['observations.jsonl'])
    archive = tmp_path/'archive'
    publish_bundle(archive, {'evidence.jsonl': ''.join(canonical(c)+'\n' for c in captures)}, em)
    manifest, rows = revise(parent, rows, LAUNDRY, 'laundry_type', 'laundry')
    manifest, rows = revise(manifest, rows, FLOOR, 'advertised_floor', 'floor', index=1)
    manifest, kept, sidecar = quarantine_last(manifest, rows)
    if fault == 'changed_excluded_row': sidecar[0]['observation']['advertised_floor'] = 9
    if fault == 'changed_retained_row': kept[0]['unit_id'] = 'different'
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in kept)}
    if fault != 'missing_sidecar': files['quarantined.jsonl'] = ''.join(canonical(r)+'\n' for r in sidecar)
    dataset = tmp_path/'quarantine'
    publish_bundle(dataset, files, {k: v for k, v in manifest.items() if k != 'files'})
    if fault:
        with pytest.raises(ValueError): load_evidence(dataset, archive)
    else:
        result = load_evidence(dataset, archive)
        assert set(result) == {'kept'} and len(result['kept']) == 2
        assert result['kept'][0]['description'] == captures[0]['description']


@pytest.mark.parametrize('fault,outer_scope', [(fault,outer) for outer in (False,True)
    for fault in (None,'missing_expansion','missing_parent_sidecar','changed_price','changed_expansion')]
    + [('missing_scope_sidecar',True),('changed_scope_observation',True)])
def test_expanded_floor_evidence_verifies_each_inverse_stage(tmp_path, fault, outer_scope):
    from apartments import reviewed_source_lineage as lineage
    from tests.test_reviewed_source_lineage import revise
    from tests.test_reviewed_cohort_quarantine import quarantine_last
    from tests.test_elevator_correction_projection import extend as elevator_extend
    from tests.test_floor_label_projection import extend as label_extend
    from tests.test_expanded_floor_projection import extend as expanded_extend

    old, em, captures = refreshed_parts(tmp_path)
    rows = [json.loads(s) for s in (old/'observations.jsonl').read_text().split('\n') if s]
    for row in rows:
        row.update(laundry_type='in_building', advertised_floor=3, elevator=True,
                   building='building', asking_rent=3000,
                   analysis_price_basis='historical_initial_own_advertisement_ask')
        if 'capture_ids' not in row:
            row['capture_ids'] = [row['capture_id']]
    if outer_scope:
        from tests.test_residual_scope_projection import add_scope_row
        rows = add_scope_row(rows)
        # Preserve the old fixture's separate final quarantine candidate.
        rows[-1],rows[-2] = rows[-2],rows[-1]
    original = tmp_path/'original'
    parent = publish_bundle(original, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                            {'version': lineage.REFRESHED})
    em.update(dataset_manifest_sha256=digest(original/'complete.json'),
              dataset_observations_sha256=parent['files']['observations.jsonl'])
    archive = tmp_path/'archive'
    publish_bundle(archive, {'evidence.jsonl': ''.join(canonical(c)+'\n' for c in captures)}, em)
    manifest, rows = revise(parent, rows, lineage.LAUNDRY, 'laundry_type', 'laundry')
    manifest, rows = revise(manifest, rows, lineage.FLOOR, 'advertised_floor', 'floor')
    manifest, rows, quarantine = quarantine_last(manifest, rows)
    manifest, rows, elevators = elevator_extend(manifest, rows, index=0)
    manifest, rows, labels = label_extend(manifest, rows)
    manifest, rows, expanded = expanded_extend(manifest, rows, labels)
    if outer_scope:
        from tests.test_residual_scope_projection import extend
        manifest, rows, residual_scope = extend(manifest, rows, expanded)
    if fault == 'changed_scope_observation':
        residual_scope[0]['observation']['asking_rent'] += 1
    if fault == 'changed_price':
        rows[0]['asking_rent'] += 1
    if fault == 'changed_expansion':
        expanded[0]['source_row_sha256'] = 'f'*64
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows),
             'quarantined.jsonl': ''.join(canonical(r)+'\n' for r in quarantine),
             'elevator-corrections.jsonl': ''.join(canonical(r)+'\n' for r in elevators),
             'floor-label-projection.jsonl': ''.join(canonical(r)+'\n' for r in labels),
             'expanded-floor-projection.jsonl': ''.join(canonical(r)+'\n' for r in expanded)}
    if outer_scope:
        files['residual-scope-quarantine.jsonl'] = ''.join(canonical(r)+'\n' for r in residual_scope)
    if fault == 'missing_scope_sidecar':
        del files['residual-scope-quarantine.jsonl']
    if fault == 'missing_expansion':
        del files['expanded-floor-projection.jsonl']
    if fault == 'missing_parent_sidecar':
        del files['floor-label-projection.jsonl']
    dataset = tmp_path/'expanded'
    publish_bundle(dataset, files, {k:v for k,v in manifest.items() if k != 'files'})
    if fault:
        with pytest.raises(ValueError):
            load_evidence(dataset, archive)
    else:
        result = load_evidence(dataset, archive)
        assert list(result) == ['kept']
        assert len(result['kept']) == 2
        assert result['kept'][0]['description'] == captures[0]['description']
