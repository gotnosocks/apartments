import json
import sqlite3

import pytest
from scrapy import Request
from scrapy.crawler import Crawler
from scrapy.http import HtmlResponse
from scrapy.settings import Settings

from streeteasy_archive import cli, crawler
from streeteasy_archive.crawler import ArchiveSpider
from streeteasy_archive.store import ArchiveStore


URL = 'https://streeteasy.com/building/example'


@pytest.mark.parametrize('status,parser_fails', [(200, False), (200, True), (403, False), (404, False), (302, False)])
def test_every_response_preserves_redacted_capture(tmp_path, monkeypatch, status, parser_fails):
    spider = ArchiveSpider(data_dir=tmp_path, max_requests=1)
    spider.store.enqueue(spider.generation, [{'url': URL, 'kind': 'building'}])
    request = next(spider.start_requests())
    request.meta['archive_provider'] = {
        'submission_attempts': 2,
        'results': [{'job_id': 'job-1', 'content': '<html>original</html>',
                     'password': 'SECRET', 'api_key': 'SECRET',
                     'headers': [{'name': 'Authorization', 'value': 'SECRET'},
                                 {'name': 'ETag', 'value': 'safe'}]}],
    }
    if parser_fails:
        def fail(*args):
            raise ValueError('invalid parser fixture')
        monkeypatch.setattr(crawler, 'extract', fail)
    list(spider.parse(HtmlResponse(URL, status=status, body=b'<html>original</html>', request=request)))
    row = next(iter(spider.store.observations(spider.generation)))
    capture = json.loads(row['capture_metadata'])
    assert capture['transport'] == 'oxylabs'
    assert capture['provider']['submission_attempts'] == 2
    assert capture['provider']['results'][0]['job_id'] == 'job-1'
    assert capture['provider']['results'][0]['headers'] == [{'name': 'ETag', 'value': 'safe'}]
    assert 'SECRET' not in row['capture_metadata']
    assert 'content' not in capture['provider']['results'][0]
    assert spider.store.get_body(row['body_hash']) == b'<html>original</html>'
    spider.store.close()


def test_repeated_body_keeps_distinct_capture_and_export(tmp_path):
    store = ArchiveStore(tmp_path / 'archive')
    generation = store.new_generation()
    for job in ['first', 'second']:
        store.record(generation, URL, 200, {}, b'<html/>', extracted={'extraction_version': 1},
                     capture={'job_id': job, 'password': 'SECRET'})
    assert store.db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 1
    output = tmp_path / 'export.jsonl'
    cli.export(store, generation, output, False)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert [r['capture_metadata'] for r in rows] == [{'job_id': 'first'}, {'job_id': 'second'}]
    store.close()


def test_old_archive_adds_capture_column_without_altering_raw_data(tmp_path):
    db = sqlite3.connect(tmp_path / 'archive.sqlite3')
    db.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY, generation INTEGER, url TEXT, fetched REAL, status INTEGER, content_type TEXT, headers TEXT, body_hash TEXT, not_modified INTEGER DEFAULT 0, error TEXT)')
    db.execute("INSERT INTO observations(generation,url,fetched,status,headers) VALUES(1,?,10,200,'{}')", (URL,))
    db.commit()
    db.close()
    store = ArchiveStore(tmp_path)
    row = store.db.execute('SELECT * FROM observations').fetchone()
    assert row['url'] == URL and row['fetched'] == 10
    assert json.loads(row['capture_metadata']) == {}
    store.close()


def test_default_spider_installs_provider_handler(tmp_path):
    instance = Crawler(ArchiveSpider, Settings())
    spider = ArchiveSpider.from_crawler(instance, data_dir=tmp_path)
    assert spider.transport == 'oxylabs'
    assert instance.settings.getdict('DOWNLOAD_HANDLERS')['https'].endswith('OxylabsDownloadHandler')
    spider.store.close()


@pytest.mark.parametrize('transport', ['http', 'firefox'])
def test_cli_rejects_direct_collection_before_creating_archive(tmp_path, transport):
    path = tmp_path / 'never-created'
    with pytest.raises(SystemExit):
        cli.main(['--data', str(path), 'backfill', '--transport', transport])
    assert not path.exists()
