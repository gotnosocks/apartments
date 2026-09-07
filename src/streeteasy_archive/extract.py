"""Lossless-friendly extraction; raw archived bodies remain the source of truth.

No JavaScript is evaluated. React Flight strings are decoded only as JSON strings.
"""
from __future__ import annotations

import gzip
import io
import json
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from parsel import Selector
from lxml import etree

VERSION = 1
_TRACKING = {'featured', 'infeed', 'lstt', 'showcase', 'similarhdp2', 'from', 'source', 'ref', 'referrer', 'gclid', 'fbclid'}


def canonical_url(value: str, base: str = 'https://streeteasy.com/') -> str | None:
    try:
        p = urlsplit(urljoin(base, value.strip()))
        if p.scheme not in ('http', 'https') or p.hostname not in ('streeteasy.com', 'www.streeteasy.com'):
            return None
        if p.username or p.password or p.port not in (None, 80, 443):
            return None
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in _TRACKING]
        return urlunsplit(('https', 'streeteasy.com', p.path.rstrip('/') or '/', urlencode(sorted(query)), ''))
    except ValueError:
        return None


def kind_for(url: str) -> str | None:
    path = urlsplit(url).path
    if re.fullmatch(r'/sitemaps/secure/nyc_(?:sitemap_index\.xml|(?:off_market_buildings|buildings|building_searches|rental_searches|sale_searches|sales|rentals)_\d+\.xml(?:\.gz)?)', path):
        return 'sitemap'
    if re.match(r'^/(?:rental|sale)/\d+(?:[-/]|$)', path):
        return 'listing'
    if re.match(r'^/building/[^/]+/(?:rental|sale)/\d+(?:[-/]|$)', path):
        return 'listing'
    if re.fullmatch(r'/building/[^/]+', path):
        return 'building'
    if re.fullmatch(r'/building/[^/]+/(?:sales|rentals|past-sales|past-rentals|sold|rented|for-sale|for-rent|units|history)(?:/.*)?', path):
        return 'building'
    if re.fullmatch(r'/building/[^/]+/[a-zA-Z0-9_-]+', path):
        if path.rsplit('/', 1)[1] not in {'documents', 'floorplans', 'photos', 'media_gallery', 'export_owner_list', 'contact', 'messages', 'edit', 'manage', 'units', 'history'}:
            return 'listing'
    if re.match(r'^/buildings(?:/|$)', path):
        return None if re.search(r'new-jersey|hoboken|jersey-city|hudson-county|newport|bergen-lafayette|bayonne|east-newark|union-city|north-bergen|weehawken|guttenberg|harrison|kearny|secaucus|west-new-york', path) else 'directory'
    if re.match(r'^/for-(?:rent|sale)/', path):
        return None if re.search(r'new-jersey|hoboken|jersey-city|hudson-county|newport|bergen-lafayette|bayonne|east-newark|union-city|north-bergen|weehawken|guttenberg|harrison|kearny|secaucus|west-new-york', path) else 'search'
    return None


def _unpack(body: bytes) -> bytes:
    if not body.startswith(b'\x1f\x8b'):
        return body
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
        decoded = stream.read(64 * 1024 * 1024 + 1)
    if len(decoded) > 64 * 1024 * 1024:
        raise ValueError('decompressed sitemap exceeds 64 MiB')
    return decoded


def _selector(body: bytes) -> Selector:
    return Selector(root=etree.fromstring(body.strip() or b'<html/>', etree.HTMLParser(no_network=True)), type='html')


def _scripts(sel: Selector) -> list[dict]:
    result = []
    for script in sel.css('script'):
        text = script.xpath('string(.)').get() or ''
        item = {'attributes': dict(script.attrib), 'text': text}
        try:
            item['json'] = json.loads(text)
        except (ValueError, TypeError):
            pass
        # Flight consists of calls with JSON arguments, never eval JavaScript.
        chunks = []
        for match in re.finditer(r'self\.__next_f\.push\(', text):
            try:
                value, _ = json.JSONDecoder().raw_decode(text[match.end():])
                chunks.append(value)
            except ValueError:
                pass
        if chunks:
            item['flight_chunks'] = chunks
        result.append(item)
    return result


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def discover(body: bytes, url: str, content_type: str = '') -> list[dict]:
    body = _unpack(body)
    found = {}

    def add(value, lastmod=None):
        normalized = canonical_url(value, url)
        kind = kind_for(normalized) if normalized else None
        if kind:
            found[normalized] = {'url': normalized, 'kind': kind, 'lastmod': lastmod}

    if 'json' in content_type or body.lstrip().startswith((b'{', b'[')):
        try:
            for value in _strings(json.loads(body)):
                add(value)
            return list(found.values())
        except ValueError:
            pass

    if body.lstrip().startswith(b'<?xml') or re.search(br'<(?:\w+:)?(?:urlset|sitemapindex)\b', body[:500]):
        sel = Selector(root=etree.fromstring(body, etree.XMLParser(resolve_entities=False, no_network=True)), type='xml')
        sel.remove_namespaces()
        for node in sel.xpath('//sitemap | //url'):
            loc = node.xpath('loc/text()').get()
            if loc:
                add(loc, node.xpath('lastmod/text()').get())
    else:
        sel = _selector(body)
        for link in sel.css('a::attr(href), link[rel="next"]::attr(href)'):
            add(link.get())
        for script in _scripts(sel):
            candidates = [script['text'], *_strings(script.get('json')), *_strings(script.get('flight_chunks'))]
            for text in candidates:
                # Flight payload URLs may be JSON-escaped inside strings.
                text = text.replace('\\/', '/').replace('\\u0026', '&')
                for value in re.findall(r'(?:https?://(?:www\.)?streeteasy\.com)?/(?:building|buildings|sale|rental|for-sale|for-rent)/[^\s"<>\\]+', text):
                    add(value)
    return list(found.values())


def extract(body: bytes, url: str, content_type: str = '') -> dict:
    body = _unpack(body)
    result = {'extraction_version': VERSION, 'url': url, 'links': discover(body, url, content_type)}
    if 'json' in content_type:
        try:
            result['json'] = json.loads(body)
            return result
        except ValueError:
            pass
    sel = _selector(body)
    result.update({
        'title': sel.css('title::text').get(),
        'meta': [dict(x.attrib) for x in sel.css('meta')],
        'scripts': _scripts(sel),
        'data_attributes': [dict(x.attrib) for x in sel.xpath('//*[@*[starts-with(name(), "data-")]]')],
        'text': sel.xpath('//body//text()[not(ancestor::script) and not(ancestor::style)]').getall(),
        'anchors': [{'attributes': dict(x.attrib), 'text': x.xpath('string(.)').get()} for x in sel.css('a')],
        'images': [dict(x.attrib) for x in sel.css('img, source')],
        'tables': [x.get() for x in sel.css('table')],
    })
    return result
