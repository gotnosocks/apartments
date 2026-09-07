"""Evidence-based Chelsea scope; excludes Hudson Yards and unrelated page links."""
from __future__ import annotations
import json
import re
from urllib.parse import urlsplit, parse_qsl
from .extract import canonical_url, kind_for

SEEDS = [f'https://streeteasy.com/{kind}/{area}'
         for kind in ('for-rent', 'for-sale', 'buildings')
         for area in ('chelsea', 'west-chelsea')]
AREAS = {'chelsea', 'west-chelsea'}


def objects(data):
    """Read JSON values from Flight records; never execute the scripts."""
    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    for script in data.get('scripts', []):
        yield from walk(script.get('json'))
        for chunk in script.get('flight_chunks', []):
            if not isinstance(chunk, list) or len(chunk) < 2 or not isinstance(chunk[1], str):
                continue
            for marker in re.finditer(r'(?<![A-Za-z0-9_])[0-9a-f]+:(?=[{\[])', chunk[1]):
                try:
                    value, _ = json.JSONDecoder().raw_decode(chunk[1][marker.end():])
                except ValueError:
                    continue
                yield from walk(value)


def building_root(url):
    if not url:
        return None
    match = re.match(r'^/building/([^/]+)', urlsplit(url).path)
    return 'https://streeteasy.com/building/' + match[1] if match else None


def directory_page(url):
    p = urlsplit(url)
    root = f'https://streeteasy.com{p.path}'
    return root in SEEDS and all(k == 'page' and v.isdigit() for k, v in parse_qsl(p.query))


def enroll(store, generation, urls, roots=()):
    """Persist membership and queue state together, preserving completed URLs."""
    with store._tx():
        for root in roots:
            store.db.execute('INSERT OR IGNORE INTO scope_buildings VALUES(?,?)', (generation, root))
        for url, reason in urls.items():
            kind = kind_for(url)
            if kind:
                store.db.execute('INSERT OR IGNORE INTO scope_urls VALUES(?,?,?)', (generation, url, reason))
                store._enqueue(generation, [{'url': url, 'kind': kind}])


def expand(store, generation, data, source_url):
    candidates = {}
    roots = {r[0] for r in store.db.execute('SELECT url FROM scope_buildings WHERE generation=?', (generation,))}
    records = list(objects(data))
    # Search result cards carry explicit neighborhood names. The citywide area
    # dictionary and suggested neighborhood links cannot grant membership.
    for obj in records:
        if obj.get('areaName') in ('Chelsea', 'West Chelsea') and isinstance(obj.get('urlPath'), str):
            url = canonical_url(obj['urlPath'])
            if url and kind_for(url) == 'listing':
                candidates[url] = 'listing card areaName=' + obj['areaName']
                root = building_root(url)
                if root:
                    roots.add(root)
        area = obj.get('area')
        if (isinstance(area, dict) and area.get('id') in AREAS
                and isinstance(obj.get('slug'), str) and (obj.get('address') or obj.get('name'))):
            root = canonical_url('/building/' + obj['slug'])
            if root and kind_for(root) == 'building' and (root == building_root(source_url) or root in roots):
                roots.add(root)
    for root in roots:
        candidates[root] = 'building associated with Chelsea/West Chelsea property'
    source_root = building_root(source_url)
    trusted_property = source_root in roots or bool(store.db.execute(
        'SELECT 1 FROM scope_urls WHERE generation=? AND url=? AND reason LIKE ?',
        (generation, source_url, 'property history%')).fetchone())
    # Only explicitly associated historical listing URLs are promoted, never all
    # /rental/ links from recommendation cards or global navigation.
    if trusted_property:
        for obj in records:
            for event in obj.get('priceHistories', []) if isinstance(obj.get('priceHistories'), list) else []:
                if isinstance(event, dict) and event.get('listingUrl'):
                    url = canonical_url(event['listingUrl'])
                    if url and kind_for(url) == 'listing':
                        candidates[url] = 'property history of ' + source_url
    # A directory's result ItemList can contain buildings with no active listing.
    # Keep the source filter as evidence; missing result lists are not guessed.
    if directory_page(source_url) and '/buildings/' in source_url:
        for obj in records:
            if obj.get('@type') == 'ItemList':
                for item in obj.get('itemListElement', []):
                    if not isinstance(item, dict):
                        continue
                    item = item.get('item', item)
                    url = canonical_url(item.get('url', '')) if isinstance(item, dict) else None
                    if url and kind_for(url) == 'building':
                        roots.add(building_root(url))
                        candidates[url] = 'filtered building directory ItemList'
    for link in data.get('links', []):
        url = canonical_url(link.get('url', ''))
        if not url or not kind_for(url):
            continue
        if directory_page(url):
            candidates[url] = 'Chelsea search/directory pagination'
        elif building_root(url) in roots:
            candidates[url] = 'child of verified Chelsea building'
    enroll(store, generation, candidates, roots)
    return len(candidates)


def configure(store, generation):
    enroll(store, generation, {u: 'Chelsea excluding Hudson Yards seed' for u in SEEDS})
    # Reuse successful archived content without downloading it again. Run on each
    # resume, also recovering scope expansion interrupted after a response commit.
    rows = store.db.execute('''SELECT s.url,s.extracted FROM snapshots s WHERE EXISTS
        (SELECT 1 FROM observations o WHERE o.url=s.url AND o.body_hash=s.body_hash
         AND o.error IS NULL AND (o.status BETWEEN 200 AND 299 OR o.status=304))''')
    for row in rows:
        expand(store, generation, json.loads(row['extracted']), row['url'])
