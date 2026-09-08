import json
from streeteasy_archive.scope import expand, configure, SEEDS
from streeteasy_archive.store import ArchiveStore


def payload(*objects, links=()):
    text = ''.join(f'{i:x}:' + json.dumps(obj) + '\n' for i, obj in enumerate(objects))
    return {'scripts': [{'flight_chunks': [[1, text]]}], 'links': [{'url': u} for u in links]}


def test_scope_uses_area_evidence_not_neighborhood_dictionary(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    root = 'https://streeteasy.com/building/inside'
    outside = 'https://streeteasy.com/building/outside'
    d = payload(
        {'areaName': 'Chelsea', 'urlPath': '/building/inside/1a'},
        {'areaName': 'Hudson Yards', 'urlPath': '/building/outside/1a'},
        {'id': '115', 'name': 'Chelsea', 'short': 'chelsea'},
        links=[root + '/2b', outside + '/2b', '/for-rent/hudson-yards', '/for-rent/chelsea?page=2', '/for-rent/chelsea/price:5000-6000'])
    expand(s, g, d, SEEDS[0])
    urls = {r[0] for r in s.db.execute('SELECT url FROM scope_urls')}
    assert root in urls and root + '/2b' in urls
    assert not any('outside' in u or 'hudson-yards' in u or 'price:' in u for u in urls)
    assert 'https://streeteasy.com/for-rent/chelsea?page=2' in urls
    s.enqueue(g, [{'url': outside + '/1a', 'kind': 'listing'}])
    s.close()
    s = ArchiveStore(tmp_path)
    while row := s.claim(g, now=9999999999, scoped=True):
        assert row['url'] in urls
        s.record(g, row['url'], 200, {}, b'fixture')
    assert s.claim(g, now=9999999999)['url'] == outside + '/1a'
    s.close()


def test_history_links_require_property_association(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation()
    source = 'https://streeteasy.com/building/ten23/4c'
    history = {'priceHistories': [{'listingUrl': 'https://streeteasy.com/rental/123'}]}
    expand(s, g, payload(history), 'https://streeteasy.com/')
    assert s.db.execute('SELECT count(*) FROM scope_urls').fetchone()[0] == 0
    expand(s, g, payload({'name': 'TEN23', 'slug': 'ten23', 'area': {'id': 'west-chelsea'}}, history), source)
    assert s.db.execute('SELECT 1 FROM scope_urls WHERE url=?', ('https://streeteasy.com/rental/123',)).fetchone()
    s.close()


def test_directory_includes_off_market_and_reuses_completed(tmp_path):
    s = ArchiveStore(tmp_path);g = s.new_generation()
    root = 'https://streeteasy.com/building/no-current-listings'
    expand(s, g, payload({'@type': 'ItemList', 'itemListElement': [{'item': {'url': root}}]}), 'https://streeteasy.com/buildings/chelsea')
    s.record(g,root,200,{},b'archived')
    configure(s,g)
    assert s.db.execute('SELECT state FROM frontier WHERE url=?',(root,)).fetchone()[0] == 'done'
    assert s.db.execute('SELECT 1 FROM scope_buildings WHERE url=?',(root,)).fetchone()
    s.close()


def test_inline_flight_records_and_related_building_rejection(tmp_path):
    s = ArchiveStore(tmp_path);g = s.new_generation()
    primary = {'name': 'Inside', 'slug': 'inside', 'area': {'id': 'chelsea'}}
    related = {'name': 'Unrelated', 'slug': 'unrelated', 'area': {'id': 'chelsea'}}
    data = {'scripts': [{'flight_chunks': [[1, 'a:T4,text<b:' + json.dumps(primary) + '\n' + 'c:' + json.dumps(related)]]}], 'links': []}
    expand(s,g,data,'https://streeteasy.com/building/inside/1a')
    roots = {r[0] for r in s.db.execute('SELECT url FROM scope_buildings')}
    assert roots == {'https://streeteasy.com/building/inside'}
    s.close()


def test_membership_split_across_flight_scripts(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation()
    text = 'a:' + json.dumps({'areaName': 'Chelsea', 'urlPath': '/building/inside/09b'})
    data = {'scripts': [{'flight_chunks': [[1, text[:20]]]}, {'flight_chunks': [[1, text[20:]]]}], 'links': []}
    expand(s,g,data,'https://streeteasy.com/for-rent/chelsea')
    assert s.db.execute('SELECT 1 FROM scope_urls WHERE url=?', ('https://streeteasy.com/building/inside/09b',)).fetchone()
    s.close()
