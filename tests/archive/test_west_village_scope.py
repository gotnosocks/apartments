from streeteasy_archive.scope import configure, expand, directory_page
from streeteasy_archive.store import ArchiveStore


def test_west_village_scope_excludes_other_neighborhoods(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood='west-village')
    data = {'scripts': [{'json': [
        {'areaName': 'West Village', 'urlPath': '/building/inside/1a'},
        {'areaName': 'Chelsea', 'urlPath': '/building/outside/1a'},
    ]}], 'links': [{'url': 'https://streeteasy.com/for-rent/west-village?page=2'},
                   {'url': 'https://streeteasy.com/for-rent/chelsea?page=2'}]}
    expand(store, generation, data, 'https://streeteasy.com/for-rent/west-village',
           neighborhood='west-village')
    urls = {r[0] for r in store.db.execute('SELECT url FROM scope_urls')}
    assert 'https://streeteasy.com/building/inside/1a' in urls
    assert 'https://streeteasy.com/for-rent/west-village?page=2' in urls
    assert not any('chelsea' in url or 'outside' in url for url in urls)
    assert directory_page('https://streeteasy.com/buildings/west-village', 'west-village')
    assert not directory_page('https://streeteasy.com/buildings/chelsea', 'west-village')
    store.close()
