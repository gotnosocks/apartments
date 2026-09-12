import json
import sqlite3
import time

import pytest

from streeteasy_archive.extract import extract
from streeteasy_archive.listing_identity import capture_evidence, listing_key
from streeteasy_archive.scope import enroll
from streeteasy_archive.store import ArchiveStore

DIRECT='https://streeteasy.com/rental/123'
NESTED='https://streeteasy.com/building/example/rental/123'


def data(identifier='123', category='rental', history=True):
    value={'id':identifier, 'propertyDetails':{'address':{'street':'123 Test Street','displayUnit':'#04C'}}}
    if history:
        value['propertyHistory']=[{'listingId':'100',category+'EventsOfInterest':[{'date':'2015-01-31','price':3120}]}]
    stream='0:'+json.dumps({'listing':value})
    body=('<script>self.__next_f.push('+json.dumps([1,stream])+')</script>').encode()
    return body, extract(body,DIRECT,'text/html')


def setup(tmp_path):
    store=ArchiveStore(tmp_path); gen=store.new_generation()
    store.enqueue(gen,[{'url':DIRECT,'kind':'listing'},{'url':NESTED,'kind':'listing'}])
    return store,gen


def record(store, gen, url=DIRECT, **kwargs):
    body,extracted=data(**kwargs)
    return store.record(gen,url,200,{'ETag':'own-route'},body,'text/html',extracted)


def test_identity_keeps_types_intents_and_zero_padded_unit_labels_separate():
    assert listing_key(DIRECT)==listing_key(NESTED)=='rental:123:detail'
    assert listing_key(DIRECT.replace('/rental/','/sale/'))=='sale:123:detail'
    for url in (DIRECT+'/media_gallery',DIRECT+'?page=2',DIRECT+'?archive_view=x',
                'https://streeteasy.com/building/example/04c','https://streeteasy.com/building/example/4c',
                'https://other.test/rental/123',DIRECT+'-unknown'):
        assert listing_key(url) is None
    assert listing_key(DIRECT.replace('123','124')) != listing_key(DIRECT)


def test_claims_serialize_same_id_then_reuse_success_and_preserve_capture(tmp_path):
    s,g=setup(tmp_path)
    assert s.claim(g)['url']==DIRECT
    assert s.claim(g) is None
    digest=record(s,g)
    assert s.claim(g) is None
    row=s.db.execute('SELECT * FROM frontier WHERE url=?',(NESTED,)).fetchone()
    assert row['state']=='superseded' and row['attempts']==0
    alias=s.db.execute('SELECT * FROM url_aliases WHERE url=?',(NESTED,)).fetchone()
    proof=json.loads(alias['reason'])
    assert alias['target_url']==DIRECT and proof['body_hash']==digest and proof['history_events']==1
    assert s.db.execute('SELECT count(*) FROM observations').fetchone()[0]==1
    assert s.get_body(digest)==data()[0]
    s.close(); s=ArchiveStore(tmp_path);s.recover_inflight(g)
    enroll(s,g,{NESTED:'rediscovery'})
    assert s.claim(g) is None


@pytest.mark.parametrize('failure',['partial','wrong_id','http_error','missing_body','missing_snapshot','unresolved_history'])
def test_failed_or_unproven_capture_does_not_suppress_other_route(tmp_path,failure):
    s,g=setup(tmp_path);s.claim(g)
    if failure=='partial':record(s,g,history=False)
    elif failure=='wrong_id':record(s,g,identifier='999')
    elif failure=='http_error':s.record_gap(g,DIRECT,404,{},'not found',body=b'not found')
    elif failure=='missing_body':s.record(g,DIRECT,200,{},None,extracted=data()[1])
    elif failure=='missing_snapshot':s.record(g,DIRECT,200,{},b'no extraction')
    else:
        body,extracted=data();extracted['scripts'][0]['flight_chunks'][0][1]='0:{"listing":{"id":"123","propertyDetails":{"address":{"street":"x"}},"propertyHistory":"$a"}}'
        s.record(g,DIRECT,200,{},body,extracted=extracted)
    assert s.claim(g)['url']==NESTED


def test_transient_failure_leaves_alternate_available_and_restart_recovers_reservation(tmp_path):
    s,g=setup(tmp_path);s.claim(g);s.close()
    s=ArchiveStore(tmp_path);assert s.claim(g) is None
    s.recover_inflight(g);assert s.claim(g)['url']==DIRECT
    s.record_gap(g,DIRECT,503,{},'temporary',complete=False,retry_seconds=300)
    assert s.claim(g)['url']==NESTED


def test_source_scope_transfers_and_old_generation_never_satisfies_new(tmp_path):
    s,g=setup(tmp_path);record(s,g)
    enroll(s,g,{NESTED:'verified property'})
    assert s.apply_listing_rules(g)['listing_aliases_superseded']==1
    assert s.db.execute('SELECT 1 FROM scope_urls WHERE generation=? AND url=?',(g,DIRECT)).fetchone()
    new=s.new_generation('refresh');s.revisit_known(new,interval=0)
    assert s.claim(new)['url'] in (DIRECT,NESTED)
    assert s.claim(new) is None
    claimed=s.db.execute("SELECT url FROM frontier WHERE generation=? AND state='inflight'",(new,)).fetchone()[0]
    record(s,new,claimed)
    assert s.claim(new) is None
    assert s.db.execute('SELECT count(*) FROM observations WHERE generation=?',(new,)).fetchone()[0]==1


def test_newer_error_invalidates_previously_usable_capture(tmp_path):
    s,g=setup(tmp_path);record(s,g)
    s.record_gap(g,DIRECT,404,{},'new failure',body=b'gone')
    assert s.claim(g)['url']==NESTED


def test_gallery_cleanup_preserves_old_observations_and_prevents_refresh(tmp_path):
    s,g=setup(tmp_path)
    gallery=NESTED+'/media_gallery'
    s.enqueue(g,[{'url':gallery,'kind':'listing'}])
    assert not s.db.execute('SELECT 1 FROM frontier WHERE url=?',(gallery,)).fetchone()
    with s._tx():
        s.db.execute('INSERT INTO frontier(generation,url,kind) VALUES(?,?,?)',(g,gallery,'listing'))
    assert s.apply_listing_rules(g)['galleries_excluded']==1
    assert s.apply_listing_rules(g)['galleries_excluded']==0
    s.record(g,gallery,200,{},b'old gallery',extracted={'images':[{'src':'old.jpg'}]})
    with s._tx():s.db.execute("UPDATE frontier SET state='done'")
    new=s.new_generation();s.revisit_known(new)
    assert not s.db.execute('SELECT 1 FROM frontier WHERE generation=? AND url=?',(new,gallery)).fetchone()
    assert s.db.execute('SELECT count(*) FROM observations WHERE url=?',(gallery,)).fetchone()[0]==1


def test_upgrade_populates_existing_typed_keys_without_reading_bodies(tmp_path):
    s,g=setup(tmp_path);s.close()
    db=sqlite3.connect(tmp_path/'archive.sqlite3')
    db.execute('DROP INDEX frontier_listing_identity');db.execute('ALTER TABLE frontier DROP COLUMN listing_key');db.commit();db.close()
    s=ArchiveStore(tmp_path)
    assert {r[0] for r in s.db.execute('SELECT listing_key FROM frontier')}=={'rental:123:detail'}
    assert s.claim(g)['url']==DIRECT and s.claim(g) is None


def test_sale_requires_sale_history_and_does_not_reuse_rental_history():
    url=DIRECT.replace('rental','sale')
    assert capture_evidence(data(category='sale')[1],url)['listing_key']=='sale:123:detail'
    assert capture_evidence(data(category='rental')[1],url) is None


def test_interval_refresh_defers_alias_using_proof_without_copying_validators(tmp_path):
    s,g=setup(tmp_path);record(s,g);s.apply_listing_rules(g)
    new=s.new_generation('refresh');s.revisit_known(new,interval=86400)
    assert s.claim(new) is None
    assert dict(s.db.execute('SELECT url,state FROM frontier WHERE generation=?',(new,)))=={DIRECT:'deferred',NESTED:'deferred'}
    assert s.conditional_headers(new,NESTED)=={}
    s.enqueue(new,[{'url':NESTED,'kind':'listing','lastmod':'2026-09-13'}])
    assert s.claim(new)['url']==NESTED


def test_gallery_trailing_slash_stays_excluded():
    from streeteasy_archive.extract import kind_for
    assert kind_for(NESTED+'/media_gallery/') is None


def test_missing_archived_body_file_cannot_satisfy_alias(tmp_path):
    s,g=setup(tmp_path);digest=record(s,g)
    s.body_path(digest).unlink()
    assert s.claim(g)['url']==NESTED


def test_compact_same_listing_copies_do_not_hide_the_full_history():
    body,extracted=data()
    summary={'listing':{'id':'123','propertyDetails':{'address':{'street':'123 Test Street'}}}}
    extracted['scripts'].append({'flight_chunks':[[1,'1:'+json.dumps(summary)]]})
    assert capture_evidence(extracted,DIRECT)['history_events']==1
    summary['listing']['id']='999'
    extracted['scripts'][-1]={'flight_chunks':[[1,'1:'+json.dumps(summary)]]}
    assert capture_evidence(extracted,DIRECT) is None


def test_reuse_lookup_uses_identity_index_instead_of_scanning_generation(tmp_path):
    s,g=setup(tmp_path);record(s,g)
    queries=[];s.db.set_trace_callback(queries.append)
    s.apply_listing_rules(g);s.db.set_trace_callback(None)
    lookup=next(q for q in queries if 'SELECT url FROM frontier' in q and 'listing_key=' in q)
    plan=s.db.execute('EXPLAIN QUERY PLAN '+lookup).fetchall()
    assert any('frontier_listing_identity' in row[3] and 'listing_key=?' in row[3] for row in plan)
