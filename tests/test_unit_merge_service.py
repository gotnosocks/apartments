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
