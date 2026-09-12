from streeteasy_archive.store import ArchiveStore
from streeteasy_archive.scope import enroll

ROOT = 'https://streeteasy.com/building/example'


def legacy(store, generation, url, kind='building', state='pending'):
    with store._tx():
        store.db.execute('INSERT INTO frontier(generation,url,kind,state) VALUES(?,?,?,?)',
                         (generation, url, kind, state))
        store.db.execute('INSERT INTO scope_urls VALUES(?,?,?)', (generation, url, 'legacy scope'))


def state(store, generation, url):
    row = store.db.execute('SELECT state FROM frontier WHERE generation=? AND url=?',
                           (generation, url)).fetchone()
    return row[0] if row else None


def test_migration_is_evidenced_idempotent_and_preserves_history_and_intents(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation()
    s.enqueue(g, [{'url': ROOT, 'kind': 'building'}])
    digest = s.record(g, ROOT, 200, {}, b'main', extracted={'title': 'main'})
    alias = ROOT + '?unit_type=rentals'; legacy(s, g, alias)
    captured = ROOT + '?similar=1'; legacy(s, g, captured)
    s.record(g, captured, 200, {}, b'old variant', extracted={'title': 'variant'})
    separate = [ROOT+'?archive_view=unavailable-rentals', ROOT+'?archive_view=unavailable-sales',
                ROOT+'?page=2&unit_type=rentals', ROOT+'?future=1', ROOT+'/4c',
                'https://streeteasy.com/rental/123', 'https://streeteasy.com/rental/124']
    for url in separate:
        legacy(s, g, url, 'inventory' if 'archive_view' in url else 'listing' if '/4c' in url or '/rental/' in url else 'building')
    assert s.deduplicate_building_views(g, dry_run=True)['superseded'] == 1
    assert state(s,g,alias) == 'pending'
    assert s.db.execute('SELECT count(*) FROM url_aliases').fetchone()[0] == 0
    assert s.deduplicate_building_views(g)['superseded'] == 1
    assert state(s,g,alias) == 'superseded'
    assert state(s,g,captured) == 'done'
    assert all(state(s,g,url) == 'pending' for url in separate)
    assert s.db.execute('SELECT count(*) FROM observations').fetchone()[0] == 2
    assert s.db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 2
    assert s.get_body(digest) == b'main'
    assert s.deduplicate_building_views(g)['superseded'] == 0
    s.close()
    s = ArchiveStore(tmp_path); s.recover_inflight(g)
    enroll(s,g,{alias:'rediscovered variant'})
    assert state(s,g,alias) == 'superseded'
    assert state(s,g,ROOT) == 'done'
    assert s.db.execute('SELECT target_url FROM url_aliases WHERE url=?',(alias,)).fetchone()[0] == ROOT


def test_alias_only_scope_transfers_to_unfetched_canonical(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation()
    alias = ROOT+'?unit_type=sales'
    enroll(s,g,{alias:'building card'})
    assert state(s,g,alias) is None
    assert s.claim(g,scoped=True)['url'] == ROOT
    assert s.db.execute('SELECT reason FROM scope_urls WHERE url=?',(ROOT,)).fetchone()[0] == 'building card'


def test_no_success_or_old_generation_does_not_suppress_target(tmp_path):
    s=ArchiveStore(tmp_path); old=s.new_generation()
    s.enqueue(old,[{'url':ROOT,'kind':'building'}]); s.record(old,ROOT,200,{},b'old')
    g=s.new_generation('update'); alias=ROOT+'?similar=1'; legacy(s,g,alias)
    assert s.deduplicate_building_views(g)['awaiting_canonical_capture'] == 1
    s.resolve_obsolete_url(g,alias,ROOT,'building')
    assert state(s,g,alias) == 'superseded'
    assert s.claim(g,scoped=True)['url'] == ROOT
    s.record(g,ROOT,403,{},b'blocked',error='challenge')
    another=ROOT+'?unit_type=rentals'; legacy(s,g,another)
    assert s.deduplicate_building_views(g)['awaiting_canonical_capture'] == 1
    assert state(s,g,another) == 'pending'


def test_incremental_copies_one_canonical_and_preserves_validators_and_freshness(tmp_path):
    s=ArchiveStore(tmp_path); g=s.new_generation()
    s.enqueue(g,[{'url':ROOT,'kind':'building','lastmod':'2026-01-01'}])
    s.record(g,ROOT,200,{'ETag':'main'},b'main')
    for suffix in ('?similar=1','?unit_type=rentals','?unit_type=sales'):
        legacy(s,g,ROOT+suffix)
        s.record(g,ROOT+suffix,200,{'ETag':'variant'},b'variant')
    new=s.new_generation('update'); s.revisit_known(new,interval=86400)
    assert s.db.execute('SELECT count(*) FROM frontier WHERE generation=?',(new,)).fetchone()[0] == 1
    assert state(s,new,ROOT) == 'deferred'
    assert s.conditional_headers(new,ROOT) == {'If-None-Match':'main'}
    enroll(s,new,{ROOT+'?similar=1':'rediscovery'})
    assert s.claim(new,scoped=True) is None
    s.enqueue(new,[{'url':ROOT+'?unit_type=sales','kind':'building','lastmod':'2026-02-01'}])
    assert s.claim(new,scoped=True)['url'] == ROOT


def test_alias_capture_does_not_supply_canonical_validator_or_freshness(tmp_path):
    s=ArchiveStore(tmp_path); g=s.new_generation(); alias=ROOT+'?similar=1'
    legacy(s,g,alias); s.record(g,alias,200,{'ETag':'variant'},b'variant')
    new=s.new_generation('update'); s.revisit_known(new,interval=86400)
    assert state(s,new,ROOT) == 'pending'
    assert s.conditional_headers(new,ROOT) == {}


def test_reporting_counts_resources_separately_from_completed_variants(tmp_path):
    from streeteasy_archive.web import create_app
    s=ArchiveStore(tmp_path); g=s.new_generation()
    enroll(s,g,{ROOT:'main'},roots=[ROOT]); s.record(g,ROOT,200,{},b'main')
    legacy(s,g,ROOT+'?similar=1'); s.record(g,ROOT+'?similar=1',200,{},b'variant')
    legacy(s,g,ROOT+'?unit_type=sales'); s.deduplicate_building_views(g)
    view=ROOT+'?archive_view=unavailable-rentals'
    s.enqueue(g,[{'url':view,'kind':'inventory'}]); s.record(g,view,200,{},b'inventory')
    expected={'known_scope_roots':1,'main_pages_captured':1,'expanded_inventories_captured':1,
              'building_urls_done':2,'building_urls_superseded':1}
    assert s.status(g)['building_coverage'] == expected
    client=create_app(tmp_path).test_client()
    assert client.get('/api/summary').json['building_coverage'] == expected
    assert client.get('/api/pages?state=superseded').json['total'] == 1
