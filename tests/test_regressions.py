import json
import time

import pytest
from scrapy import Request
from scrapy.http import Response

from streeteasy_archive.cli import acquire_lock, export, import_har, main
from streeteasy_archive.crawler import ArchiveSpider, is_challenge
from streeteasy_archive.store import ArchiveStore

URL = 'https://streeteasy.com/building/example'


def recorded(tmp_path):
    store = ArchiveStore(tmp_path)
    gen = store.new_generation()
    store.enqueue(gen, [{'url': URL, 'kind': 'building', 'lastmod': '2026-01-01'}])
    store.record(gen, URL, 200, {'ETag': 'v1'}, b'<a href="/rental/123">history</a>', 'text/html')
    store.finish(gen)
    return store, gen


def test_update_latest_validators_and_deferred_rediscovery(tmp_path):
    store, first = recorded(tmp_path)
    second = store.new_generation('update')
    store.revisit_known(second, interval=86400)
    assert store.status(second)['deferred'] == 1
    store.enqueue(second, [{'url': URL, 'kind': 'building', 'lastmod': '2026-01-01'}])
    assert store.claim(second) is None
    store.enqueue(second, [{'url': URL, 'kind': 'building', 'lastmod': '2026-02-01'}])
    assert store.claim(second)['url'] == URL
    assert store.conditional_headers(second, URL) == {'If-None-Match': 'v1'}
    store.record(second, URL, 200, {'ETag': 'v2'}, b'changed')
    third = store.new_generation('update')
    store.revisit_known(third, interval=0)
    assert store.conditional_headers(third, URL) == {'If-None-Match': 'v2'}
    store.record(third, URL, 200, {}, b'no validators')
    assert store.conditional_headers(third, URL) == {}


def test_transaction_failure_keeps_request_and_discovery_atomic(tmp_path):
    store = ArchiveStore(tmp_path)
    gen = store.new_generation()
    store.enqueue(gen, [{'url': URL}])
    store.claim(gen)
    with pytest.raises(KeyError):
        store.record(gen, URL, 200, {}, b'body', discovered=[{'url': URL + '/1a'}, {}])
    assert list(store.observations(gen)) == []
    assert store.status(gen)['inflight'] == 1
    assert store.db.execute('SELECT count(*) FROM frontier').fetchone()[0] == 1


def test_304_rediscovery_and_missing_body_gap(tmp_path):
    store, first = recorded(tmp_path)
    second = store.new_generation('update')
    store.revisit_known(second)
    store.claim(second)
    spider = ArchiveSpider(data_dir=tmp_path, generation=second, max_requests=1)
    spider.sent = 1
    request = Request(URL, meta={'archive_url': URL})
    list(spider.parse(Response(URL, status=304, request=request)))
    rows = list(store.observations(second))
    assert rows[0]['content_type'] == 'text/html'
    assert rows[0]['body_hash'] == store.latest_body(None, URL)
    assert store.db.execute('SELECT 1 FROM frontier WHERE generation=? AND url=?', (second, 'https://streeteasy.com/rental/123')).fetchone()
    assert store.db.execute('SELECT count(*) FROM bodies').fetchone()[0] == 1
    spider.store.close()


@pytest.mark.parametrize('status', [403, 429, 503])
def test_error_archived_and_cooldown_atomic(tmp_path, status):
    store = ArchiveStore(tmp_path)
    gen = store.new_generation()
    store.enqueue(gen, [{'url': URL}, {'url': URL + '/1a'}])
    store.claim(gen)
    spider = ArchiveSpider(data_dir=tmp_path, generation=gen)
    request = Request(URL, meta={'archive_url': URL})
    assert list(spider.parse(Response(URL, status=status, headers={'Retry-After': '900'}, body=b'blocked body', request=request))) == []
    state = store.status(gen)
    assert state['pending'] == 2
    assert state['cooldown'] > time.time() + 890
    assert store.claim(gen) is None
    with pytest.raises(RuntimeError):
        store.new_generation('update')
    assert store.get_body(next(iter(store.observations(gen)))['body_hash']) == b'blocked body'
    assert store.latest_body(None, URL) is None
    spider.store.close()


def test_har_idempotence_missing_body_and_export_errors(tmp_path):
    store = ArchiveStore(tmp_path / 'archive')
    entry = {'startedDateTime': '2026-01-01T00:00:00Z', 'request': {'url': URL, 'method': 'GET', 'headers': [{'name': 'Cookie', 'value': 'SECRET'}]},
             'response': {'status': 200, 'headers': [{'name': 'Set-Cookie', 'value': 'SECRET'}], 'content': {'text': '<title>Example</title>', 'mimeType': 'text/html'}}}
    evil = {'request': {'url': 'https://streeteasy.com.evil.test/building/a'}, 'response': entry['response']}
    missing = {'request': {'url': URL + '/1a'}, 'response': {'status': 200, 'content': {}}}
    har = tmp_path / 'sample.har'
    har.write_text(json.dumps({'log': {'entries': [entry, evil, missing]}}))
    import_har(store, har)
    import_har(store, har)
    gen = store.current_generation()
    assert len(list(store.observations(gen))) == 1
    assert store.db.execute('SELECT count(*) FROM bodies').fetchone()[0] == 1
    store.record_gap(gen, URL, 404, {}, 'missing page coverage gap', body=b'gone')
    output = tmp_path / 'output.jsonl'
    export(store, None, output, True)
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert 'SECRET' not in output.read_text()
    assert records[0]['fetched'] == 1767225600
    assert records[1]['error'] == 'missing page coverage gap'
    assert (store.root / records[0]['body_path']).exists()


def test_cli_lock_prevents_mutation_and_status_works(tmp_path):
    lock = acquire_lock(tmp_path)
    try:
        assert main(['--data', str(tmp_path), 'backfill', '--max-requests', '1']) == 2
        assert not (tmp_path / 'archive.sqlite3').exists()
        assert main(['--data', str(tmp_path), 'status']) == 0
    finally:
        lock.close()


def test_challenge_not_normal_captcha_library():
    assert not is_challenge(b'<title>Listing</title><script src="recaptcha.js"></script>')
    assert is_challenge(b'<title>Access to this page has been denied</title>')


def test_cli_offline_cooldown_and_completed_status(tmp_path, capsys):
    store, gen = recorded(tmp_path)
    assert store.status()['status'] == 'complete'
    store.enqueue(gen, [{'url': URL + '/1a', 'kind': 'listing'}])
    store.cooldown(gen, 900, 'blocked')
    store.close()
    assert main(['--data', str(tmp_path), 'resume', '--max-requests', '1']) == 3
    store = ArchiveStore(tmp_path)
    assert store.status(gen)['pending'] == 1
    assert store.status(gen)['inflight'] == 0
    assert store.current_generation() == gen


def test_archive_relocation_and_old_har_does_not_replace_new(tmp_path):
    import shutil
    store, gen = recorded(tmp_path / 'original')
    body_hash = store.latest_body(None, URL)
    store.record(gen, URL, 200, {'ETag': 'ancient'}, b'old', fetched=1)
    assert store.latest_body(None, URL) == body_hash
    assert store.conditional_headers(gen, URL) == {'If-None-Match': 'v1'}
    store.close()
    shutil.copytree(tmp_path / 'original', tmp_path / 'copy')
    copy = ArchiveStore(tmp_path / 'copy')
    assert copy.get_body(body_hash).startswith(b'<a ')


def test_detail_pages_take_priority_over_searches(tmp_path):
    store = ArchiveStore(tmp_path)
    gen = store.new_generation()
    store.enqueue(gen, [{'url': 'https://streeteasy.com/for-rent/nyc', 'kind': 'search'},
                        {'url': 'https://streeteasy.com/building/example/5a', 'kind': 'listing'},
                        {'url': 'https://streeteasy.com/rental/123', 'kind': 'listing'}])
    assert store.claim(gen)['url'] == 'https://streeteasy.com/building/example/5a'
    store.record(gen, 'https://streeteasy.com/building/example/5a', 200, {}, b'<title>Detail</title>')
    assert store.claim(gen)['url'] == 'https://streeteasy.com/rental/123'


def test_search_discovers_and_archives_actual_detail_body(tmp_path):
    store = ArchiveStore(tmp_path)
    gen = store.new_generation()
    search = 'https://streeteasy.com/for-rent/nyc'
    detail = 'https://streeteasy.com/building/example/4a'
    store.enqueue(gen, [{'url': search, 'kind': 'search'}])
    store.claim(gen)
    spider = ArchiveSpider(data_dir=tmp_path, generation=gen)
    search_response = Response(search, body=f'<a href="{detail}">Apartment 4A</a>'.encode(), request=Request(search, meta={'archive_url': search}))
    requests = list(spider.parse(search_response))
    assert len(requests) == 1 and requests[0].url == detail
    detail_body = b'<title>Apartment 4A</title><script type="application/ld+json">{"price":4200,"numberOfBedrooms":2}</script><table><tr><td>Rented 2021</td></tr></table>'
    assert list(spider.parse(Response(detail, body=detail_body, headers={'Content-Type': 'text/html'}, request=requests[0]))) == []
    assert store.get_body(store.latest_body(None, detail)) == detail_body
    snapshot = json.loads(store.db.execute('SELECT extracted FROM snapshots WHERE url=?', (detail,)).fetchone()[0])
    assert snapshot['title'] == 'Apartment 4A'
    assert snapshot['scripts'][0]['json']['price'] == 4200
    assert 'Rented 2021' in snapshot['tables'][0]
    spider.store.close()
