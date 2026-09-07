import gzip
import json
from streeteasy_archive.extract import canonical_url, discover, extract


def test_scope_and_identity():
    assert canonical_url('/rental/123?featured=1&utm_source=x&page=2#foo') == 'https://streeteasy.com/rental/123?page=2'
    assert canonical_url('https://streeteasy.com.evil.test/rental/123') is None
    assert not discover(b'<a href="/users/auth/google">login</a><a href="/building/x/documents">private</a>', 'https://streeteasy.com')


def test_off_market_sitemap_and_lastmod():
    xml = b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://streeteasy.com/sitemaps/secure/nyc_off_market_buildings_16.xml.gz</loc><lastmod>2026-09-07</lastmod></sitemap><sitemap><loc>https://streeteasy.com/sitemaps/secure/nyc_agents_0.xml.gz</loc></sitemap></sitemapindex>'
    links = discover(gzip.compress(xml), 'https://streeteasy.com/sitemaps/secure/nyc_sitemap_index.xml')
    assert len(links) == 1
    assert links[0]['lastmod'] == '2026-09-07'


def test_flight_history_and_unknown_fields_preserved():
    chunk = [1, 'a:["$",null,{"history":[{"url":"/building/example/rental/123","unknownFutureField":42}]}]']
    html = ('<html><body><script>self.__next_f.push(' + json.dumps(chunk) + ')</script><script type="application/ld+json">{"price":100}</script><table><tr><td>2020 rented</td></tr></table></body></html>').encode()
    data = extract(html, 'https://streeteasy.com/building/example')
    assert data['scripts'][0]['flight_chunks'] == [chunk]
    assert data['scripts'][1]['json'] == {'price':100}
    assert data['links'][0]['url'] == 'https://streeteasy.com/building/example/rental/123'
    assert '2020 rented' in data['tables'][0]


def test_modern_unit_urls_and_pagination():
    links = discover(b'<a href="/building/ruby-chelsea/n02m">unit</a><a href="/building/x/ph">penthouse</a><a href="/for-rent/chelsea?page=2">next</a>', 'https://streeteasy.com')
    assert [x['kind'] for x in links] == ['listing', 'listing', 'search']


def test_raw_json_and_security_scope():
    assert extract(b'{"unknown":{"nested":17}}', 'https://streeteasy.com/rental/1', 'application/json')['json']['unknown']['nested'] == 17
    assert canonical_url('https://user:password@streeteasy.com/rental/1') is None
    assert canonical_url('https://streeteasy.com:9999/rental/1') is None
    assert discover(b'<a href="https://streeteasy.com.evil.org/sale/123">x</a>', 'https://streeteasy.com') == []
