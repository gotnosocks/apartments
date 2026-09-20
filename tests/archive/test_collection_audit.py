import json

from streeteasy_archive.collection_audit import audit
from streeteasy_archive.collection_policy import setup
from streeteasy_archive.extract import extract
from streeteasy_archive.store import ArchiveStore

UNIT = 'https://streeteasy.com/building/example/4c'
URL = 'https://streeteasy.com/rental/123'


def test_readonly_audit_distinguishes_resolved_and_conflicting_identity(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation(); setup(s, g)
    listing = {'id': '123', 'propertyDetails': {'address': {'street': 'Example'}},
               'propertyHistory': [{'listingId': '123', 'rentalEventsOfInterest': [{'date': '2020-01-01', 'price': 3000}]}]}
    raw = ('<head><link rel="canonical" href="'+UNIT+'"></head><body><script type="application/json">'+json.dumps({'listing':listing})+'</script></body>').encode()
    s.record(g,URL,200,{},raw,'text/html',extract(raw,URL,'text/html'))
    with s._tx():
        s.db.execute('INSERT INTO collection_exclusions VALUES(?,?,?,?)',(g,URL,'captured_listing_not_eligible',0))
        s.db.execute('INSERT INTO collection_memberships VALUES(?,?,?,?,?,?)',(g,'rental:123:detail',UNIT,UNIT,'proof',0))
    before = list(s.db.iterdump())
    report = audit(tmp_path)
    assert report['current_exclusion_interpretations'] == {'association_now_supported':1}
    assert report['historical_exclusions'] == {'captured_listing_not_eligible':1}
    assert list(s.db.iterdump()) == before
    with s._tx():
        s.db.execute('UPDATE collection_memberships SET unit_url=?',(UNIT+'-different',))
    assert audit(tmp_path)['current_exclusion_interpretations'] == {'canonical_unit_mismatch':1}
    s.record_gap(g,URL,503,{},'blocked',body=b'blocked')
    assert audit(tmp_path)['current_exclusion_interpretations'] == {'latest_capture_failed':1}
    s.close()
