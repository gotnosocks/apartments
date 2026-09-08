import asyncio
import pytest
from streeteasy_archive.extract import extract, kind_for
from streeteasy_archive.scope import configure_building, discovery_links, expand
from streeteasy_archive.store import ArchiveStore

ROOT = 'https://streeteasy.com/building/the-sierra-chelsea'
VIEW = ROOT + '?archive_view=unavailable-rentals'


def inventory_html(count=2):
    return f'''<div role="dialog"><button aria-pressed="true">For rent</button>
    <button role="tab">All ({count})</button><table><tbody>
    <tr><td><a href="/rental/123">#1A</a></td></tr>
    <tr><td><a href="/rental/456">#2A</a></td></tr>
    </tbody></table></div>'''.encode()


def test_complete_inventory_discovers_detail_pages_and_rejects_truncation():
    d = extract(inventory_html(), VIEW)
    assert d['inventory']['count'] == 2
    assert {x['url'] for x in d['inventory']['links']} == {
        'https://streeteasy.com/rental/123', 'https://streeteasy.com/rental/456'}
    assert kind_for(VIEW) == 'inventory'
    with pytest.raises(ValueError, match='incomplete'):
        extract(inventory_html(393), VIEW)
    with pytest.raises(ValueError, match='category'):
        extract(inventory_html(), ROOT + '?archive_view=unavailable-sales')


def test_backfill_reuses_building_and_adds_inventory_and_history(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation()
    d = extract(b'<a href="/building/the-sierra-chelsea/3j">3J</a>', ROOT)
    s.enqueue(g, [{'url': ROOT, 'kind': 'building'}])
    s.record(g, ROOT, 200, {}, b'building', 'text/html', d)
    configure_building(s, g, ROOT)
    assert s.db.execute('SELECT state FROM frontier WHERE url=?', (ROOT,)).fetchone()[0] == 'done'
    assert s.db.execute('SELECT 1 FROM scope_urls WHERE url=?', (VIEW,)).fetchone()
    inv = extract(inventory_html(), VIEW)
    s.record(g, VIEW, 200, {}, inventory_html(), 'text/html', inv)
    expand(s, g, inv, VIEW, building=ROOT)
    assert s.db.execute("SELECT 1 FROM scope_urls WHERE url='https://streeteasy.com/rental/123'").fetchone()
    configure_building(s, g, ROOT)  # Resume does not download completed inventory again.
    assert s.db.execute('SELECT state FROM frontier WHERE url=?', (VIEW,)).fetchone()[0] == 'done'
    configure_building(s, g, ROOT, False)
    urls = {r[0] for r in s.db.execute('SELECT url FROM scope_urls')}
    assert urls == {ROOT, ROOT + '/3j'}
    s.close()


def test_current_discovery_does_not_follow_price_event_urls():
    d = {'scripts': [{'json': {'priceHistories': [{'listingUrl': '/rental/123'}]}}],
         'links': [{'url': '/rental/123'}, {'url': ROOT + '/3j'}]}
    assert discovery_links(d, ROOT + '/3j', False) == []


def test_flight_summary_prevents_false_empty_inventory():
    script = b'''<script>self.__next_f.push([1,"a:{\\"rentalSummary\\":\\"$b\\",\\"saleSummary\\":\\"$d\\"}\\nb:[\\"$c\\"]\\nc:{\\"unavailableCount\\":393}\\nd:[\\"$e\\"]\\ne:{\\"unavailableCount\\":0}\\n"])</script>'''
    data = extract(script, ROOT)
    urls = {x['url'] for x in discovery_links(data, ROOT)}
    assert VIEW in urls
    assert ROOT + '?archive_view=unavailable-sales' not in urls
    empty = b'<div role="dialog"><button aria-pressed="true">For rent</button><button role="tab">All (0)</button></div>'
    with pytest.raises(ValueError, match='summary'):
        extract(script + empty, VIEW)


def test_inventory_transport_expands_correct_category(monkeypatch):
    from scrapy import Request
    from streeteasy_archive.oxylabs import OxylabsDownloadHandler
    from streeteasy_archive import oxylabs
    monkeypatch.setattr(oxylabs, '_credentials', lambda: ('user', 'password'))
    payloads = []
    class Result:
        status_code = 200
        headers = {}
        def json(self):
            return {'results': [{'status_code': 200, 'content': inventory_html().decode()}]}
    def post(*args, **kwargs):
        payloads.append(kwargs['json'])
        return Result()
    monkeypatch.setattr(oxylabs.requests, 'post', post)
    response = asyncio.run(OxylabsDownloadHandler().download_request(Request(VIEW)))
    assert payloads[0]['url'] == ROOT
    assert payloads[0]['render'] == 'html'
    assert 'For rent' in payloads[0]['browser_instructions'][2]['selector']['value']
    assert response.url == VIEW  # Distinct durable queue/capture identity.
