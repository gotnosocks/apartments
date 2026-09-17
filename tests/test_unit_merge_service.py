import json

import pytest

from apartments.review_ledger import ReviewConflict
from apartments.unit_merge_service import UnitMergeService
from .test_review_service import service


def save(service, detail, request_id='merge-test'):
    return service.merge({'listing_ids':detail['listing_ids'], 'identity_revision':detail['identity_revision'],
        'review_revision':detail['review_revision'], 'request_id':request_id,
        'author':'Ben', 'reason':'Verified rental IDs refer to the same home'})


def test_merge_creates_unit_record_and_one_history_without_changing_source(service):
    s = service
    u = UnitMergeService(s)
    s.db.execute("UPDATE rental SET unit_label='4C' WHERE snapshot_id=2")
    candidates = u.candidates({})
    assert candidates['total'] == 1
    assert candidates['rows'][0]['listing_ids'] == ['1','2']
    assert u.candidates({'search':'A #4C'})['total'] == 1
    detail = u.inspect({'listing_ids':['1','2']})
    assert detail['unit_id'] is None
    assert detail['history_mentions'] == 4 and detail['history_events'] == 2
    assert all(len(e['occurrences']) == 2 for e in detail['history'])
    before = [s.observation({'snapshot_id':sid}) for sid in [1,2]]
    event = save(u, detail)
    assert save(u, detail)['id'] == event['id']
    assert u.candidates({})['total'] == 0
    assert u.candidates({'mode':'merged'})['total'] == 1
    reopened = UnitMergeService(s)
    unit = reopened.inspect({'unit_id':event['unit_id']})
    assert unit['listing_ids'] == ['1','2']
    assert unit['history_mentions'] == 4 and unit['history_events'] == 2
    assert unit['latest_merge']['id'] == event['id']
    for sid, original in zip([1,2], before):
        updated = s.observation({'snapshot_id':sid})
        assert updated['unit_id'] == event['unit_id']
        assert {k:v for k,v in updated.items() if k != 'unit_id'} == {k:v for k,v in original.items() if k != 'unit_id'}
    assert {r['unit_id'] for r in s.observations({})['rows']} == {event['unit_id']}
    assert reopened.mapping({})['listing_to_unit'] == {'1':event['unit_id'], '2':event['unit_id']}
    assert s.ledger.events() == []
    reopened.undo({'merge_id':event['id'], 'identity_revision':unit['identity_revision'],
        'author':'Ben','reason':'undo','request_id':'undo-test'})
    assert reopened.candidates({})['total'] == 1
    assert reopened.candidates({'mode':'merged'})['total'] == 0


def test_corrected_identity_candidates_and_conflicting_history_remain_separate(service):
    s = service
    s.ledger.correct([2], [{'op':'replace','path':'/unit_label','value':'4C'},
        {'op':'replace','path':'/bedrooms','value':2},
        {'op':'replace','path':'/archive_listing/propertyHistory/0/rentalEventsOfInterest/0/price','value':100}],
        'Ben','source evidence',s.ledger.revision())
    u = UnitMergeService(s)
    assert u.candidates({})['total'] == 1
    detail = u.inspect({'listing_ids':['1','2']})
    assert detail['attribute_disagreements']['bedrooms'] == [1.0,2]
    assert detail['history_events'] == 3
    assert len([e for e in detail['history'] if e['conflicting_version']]) == 2
    save(u, detail)
    assert u.inspect({'listing_ids':['1']})['listing_ids'] == ['1','2']


def test_missing_labels_are_not_grouped_and_manual_ids_work(service):
    u = UnitMergeService(service)
    assert u.candidates({})['total'] == 0
    detail = u.inspect({'listing_ids':'1,2'})
    assert detail['capture_count'] == 2
    with pytest.raises(ValueError, match='unknown rental'):
        u.inspect({'listing_ids':['3']})
    with pytest.raises(ValueError):
        u.inspect({'listing_ids':[]})
    with pytest.raises(ValueError):
        u.candidates({'search':'x'*201})
    assert u.candidates({'search':"' OR 1=1"})['total'] == 0


def test_merge_refuses_stale_review_or_identity_and_unknown_listing(service):
    s = service
    u = UnitMergeService(s)
    detail = u.inspect({'listing_ids':['1','2']})
    s.review({'snapshot_id':1,'stage':'identity','decision':'confirmed','author':'Ben'})
    with pytest.raises(ReviewConflict):
        save(u, detail)
    assert u.ledger.events() == []
    detail = u.inspect({'listing_ids':['1','2']})
    with pytest.raises(ValueError, match='unknown rental'):
        save(u, {**detail,'listing_ids':['1','3']})
    event = save(u, detail)
    with pytest.raises(ReviewConflict):
        save(u, detail, 'another-request')
    assert len(u.ledger.events()) == 1


def test_repeat_capture_of_same_listing_is_one_source_identity(service):
    s = service
    s.db.execute("UPDATE rental SET listing_id='1',unit_label='4C' WHERE snapshot_id=2")
    u = UnitMergeService(s)
    assert u.candidates({})['total'] == 0
    detail = u.inspect({'listing_ids':['1']})
    assert detail['listing_ids'] == ['1'] and detail['capture_count'] == 2
    assert detail['history_events'] == 2


def test_listing_count_sort_across_pages_filters_and_merged_units(service):
    s = service
    s.db.execute("UPDATE rental SET unit_label='4C'")
    groups = [('a',['1','2']),('b',['10','11','12','13']),('c',['20','21','22']),('d',['30','31'])]
    for building, ids in groups[1:]:
        for lid in ids:
            s.db.execute("INSERT INTO rental SELECT * REPLACE(? AS snapshot_id,? AS listing_id,? AS building_slug) FROM rental WHERE snapshot_id=1",[int(lid),lid,building])
    u = UnitMergeService(s)
    desc = {'sort':'listing_count','direction':'desc','limit':2}
    default = u.candidates({'limit':2})
    assert (default['sort'], default['direction']) == ('listing_count', 'desc')
    assert [r['listing_count'] for r in default['rows']] == [4,3]
    first = u.candidates(desc)
    second = u.candidates({**desc,'offset':2})
    assert [r['listing_count'] for r in first['rows']] == [4,3]
    assert [r['building'] for r in second['rows']] == ['a','d']
    assert first['total'] == second['total'] == 4
    assert [r['listing_count'] for r in u.candidates({**desc,'direction':'asc'})['rows']] == [2,2]
    assert u.candidates({**desc,'search':'b'})['rows'][0]['listing_count'] == 4
    partial = u.ledger.write('merge',listing_ids=['10','11'],author='test',reason='fixture',request_id='partial',
                            expected_revision=u.ledger.revision(u.ledger.events()))
    # A partial merge remains in the list, but Next moves beyond the current unit.
    assert u.candidates({'limit':1})['rows'][0]['building'] == 'b'
    assert u.candidates({'limit':1,'exclude_unit_id':partial['unit_id']})['rows'][0]['building'] == 'c'
    for building, ids in groups:
        u.ledger.write('merge',listing_ids=ids,author='test',reason='fixture',request_id=building,
                       expected_revision=u.ledger.revision(u.ledger.events()))
    merged = u.candidates({**desc,'mode':'merged'})
    assert [r['listing_count'] for r in merged['rows']] == [4,3]
    assert u.candidates({'limit':1,'exclude_unit_id':partial['unit_id']})['rows'] == []
    with pytest.raises(ValueError,match='sort order'):
        u.candidates({'sort':'unknown'})


def ready_service(s):
    from .test_unit_source import evidence
    s.db.execute("UPDATE rental SET unit_label='4C'")
    u=UnitMergeService(s);u._source=evidence()
    return u


def test_source_association_preview_apply_export_and_undo(service):
    from apartments.unit_identity import identity_map
    u=ready_service(service)
    assert u.candidates({'queue':'supported'})['total']==1
    assert u.candidates({'queue':'review'})['total']==0
    preview=u.association_preview({'search':'a 4c'})
    assert preview['group_count']==1 and preview['listing_count']==2
    assert u.ledger.events()==[]
    assert u.proposal({'token':preview['token']})['proposals'][0]['evidence']['canonical_url'].endswith('/a/4c')
    saved=u.association_apply({'token':preview['token'],'author':'Ben'})
    assert u.association_apply({'token':preview['token'],'author':'Ben'})==saved
    detail=u.inspect({'listing_ids':['1']})
    assert detail['listing_ids']==['1','2'] and detail['association_basis']=='streeteasy'
    assert detail['source_evidence']['snapshot_ids']==[1,2]
    assert set(u.mapping({})['unit_basis'].values())=={'streeteasy'}
    assert u.candidates({'mode':'merged'})['rows'][0]['basis']=='streeteasy'
    u.undo({'merge_id':detail['latest_merge']['id'],'author':'Ben','reason':'wrong association','request_id':'undo','identity_revision':detail['identity_revision']})
    assert identity_map(u.ledger.events())=={}
    assert u.candidates({'queue':'supported'})['total']==0
    assert u.candidates({'queue':'review'})['total']==1  # Undo is respected, not re-suggested in bulk.
    assert u.batches({})['rows'][0]['active_groups']==0


def test_association_preview_refuses_stale_or_changed_evidence(service):
    u=ready_service(service)
    preview=u.association_preview({})
    service.review({'snapshot_id':1,'stage':'identity','decision':'confirmed','author':'Ben'})
    with pytest.raises(ReviewConflict,match='changed'):
        u.association_apply({'token':preview['token'],'author':'Ben'})
    preview=u.association_preview({})
    u._source.digest='changed';u._assessments=None
    with pytest.raises(ReviewConflict,match='Source evidence'):
        u.association_apply({'token':preview['token'],'author':'Ben'})
    assert u.ledger.events()==[]
    with pytest.raises(ValueError,match='token'):
        u.proposal({'token':'../../some-file'})


def test_canonical_groups_surface_different_labels_without_overlapping_actions(service):
    from .test_unit_source import evidence
    s=service
    s.db.execute("UPDATE rental SET unit_label='Different' WHERE snapshot_id=2")
    u=UnitMergeService(s);u._source=evidence()
    groups=u.candidates({'queue':'review'})
    assert groups['total']==1
    assert groups['rows'][0]['listing_ids']==['1','2']
    assert 'Building or unit labels differ' in groups['rows'][0]['assessment']['reasons']
    assert u.candidates({'queue':'supported'})['total']==0
    # A label match overlapping that canonical group becomes one reviewable group.
    s.db.execute("INSERT INTO rental SELECT * REPLACE(5 AS snapshot_id,'5' AS listing_id) FROM rental WHERE snapshot_id=2")
    u=UnitMergeService(s);u._source=evidence()
    groups=u.candidates({})
    assert groups['total']==1 and groups['rows'][0]['listing_ids']==['1','2','5']
