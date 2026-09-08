"""Evidence-based Chelsea scope; excludes Hudson Yards and unrelated page links."""
from __future__ import annotations
import json
import re
from urllib.parse import urlsplit, parse_qsl
from .extract import canonical_url, kind_for, flight_text, is_unavailable_url

SEEDS = [f'https://streeteasy.com/{kind}/{area}'
         for kind in ('for-rent', 'for-sale', 'buildings')
         for area in ('chelsea', 'west-chelsea')]
AREAS = {'chelsea', 'west-chelsea'}


def summary_counts(data, key):
    """Read both inline summaries and Flight reference-backed summary arrays."""
    stream = flight_text(data.get('scripts', []))
    records = {}
    for marker in re.finditer(r'(?<![A-Za-z0-9_])([0-9a-f]+):(?=[{\[])', stream):
        try:
            records[marker[1]], _ = json.JSONDecoder().raw_decode(stream[marker.end():])
        except ValueError:
            pass
    def resolve(value, depth=0):
        if isinstance(value, str) and value.startswith('$') and depth < 4:
            return resolve(records.get(value[1:]), depth + 1)
        return value
    totals = []
    for obj in objects(data):
        rows = resolve(obj.get(key))
        if isinstance(rows, list) and rows:
            rows = [resolve(x) for x in rows]
            if all(isinstance(x, dict) for x in rows):
                totals.append(sum(x.get('unavailableCount', 0) for x in rows))
    return totals


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
    scripts = data.get('scripts', [])
    for script in scripts:
        yield from walk(script.get('json'))
    stream = flight_text(scripts)
    for marker in re.finditer(r'(?<![A-Za-z0-9_])[0-9a-f]+:(?=[{\[])', stream):
        try:
            value, _ = json.JSONDecoder().raw_decode(stream[marker.end():])
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


def discovery_links(data, source_url, include_unavailable=True):
    """Keep complete extraction, but select which edges the crawl follows."""
    records = list(objects(data))
    histories = {canonical_url(e['listingUrl']) for o in records
                 for e in (o.get('priceHistories') or []) if isinstance(e, dict) and e.get('listingUrl')} if include_unavailable is False else set()
    links = {u: {'url': u, 'kind': kind_for(u), 'lastmod': link.get('lastmod')}
             for link in data.get('links', [])
             if (u := canonical_url(link.get('url', ''), source_url)) and kind_for(u)
             and (include_unavailable or (u not in histories and not is_unavailable_url(u)))}
    if not include_unavailable and kind_for(source_url) in ('listing', 'sitemap', 'inventory'):
        # Current detail pages may report years of price history. Retain that
        # evidence in the capture, but don't recursively fetch the old episodes.
        links = {u: link for u, link in links.items() if link['kind'] != 'listing'}
    root = building_root(source_url)
    if include_unavailable and root == source_url:
        for category, key in [('rentals', 'rentalSummary'), ('sales', 'saleSummary')]:
            totals = summary_counts(data, key)
            if totals and max(totals) == 0:
                continue
            u = root + '?archive_view=unavailable-' + category
            links[u] = {'url': u, 'kind': 'inventory'}
    if include_unavailable:
        for link in data.get('inventory', {}).get('links', []):
            links[link['url']] = link
    return list(links.values())


def expand(store, generation, data, source_url, include_unavailable=True, building=None):
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
    if trusted_property and include_unavailable:
        for obj in records:
            for event in obj.get('priceHistories', []) if isinstance(obj.get('priceHistories'), list) else []:
                if isinstance(event, dict) and event.get('listingUrl'):
                    url = canonical_url(event['listingUrl'])
                    if url and kind_for(url) == 'listing':
                        candidates[url] = 'property history of ' + source_url
    # A directory's result ItemList can contain buildings with no active listing.
    # Keep the source filter as evidence; missing result lists are not guessed.
    if directory_page(source_url) and '/buildings/' in source_url:
        for item in data.get('directory_buildings', []):
            url = canonical_url(item.get('url') or '')
            if url and kind_for(url) == 'building' and re.search(r'\bin (?:West )?Chelsea$', item.get('area_label', '').strip()):
                roots.add(building_root(url))
                candidates[url] = 'directory result card with explicit Chelsea neighborhood'
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
    if include_unavailable and is_unavailable_url(source_url) and source_root in roots:
        for link in data.get('inventory', {}).get('links', []):
            candidates[link['url']] = 'property history unavailable inventory of ' + source_root
    for link in discovery_links(data, source_url, include_unavailable):
        url = canonical_url(link.get('url', ''))
        if not url or not kind_for(url):
            continue
        if directory_page(url):
            candidates[url] = 'Chelsea search/directory pagination'
        elif building_root(url) in roots:
            candidates[url] = 'child of verified Chelsea building'
    if building:
        roots = {building}
        candidates = {u: reason for u, reason in candidates.items()
                      if building_root(u) == building or reason.startswith('property history')}
    enroll(store, generation, candidates, roots)
    return len(candidates)


def configure(store, generation, include_unavailable=True):
    if not include_unavailable:
        with store._tx():
            store.db.execute('DELETE FROM scope_urls WHERE generation=?', (generation,))
    enroll(store, generation, {u: 'Chelsea excluding Hudson Yards seed' for u in SEEDS})
    # Reuse successful archived content without downloading it again. Run on each
    # resume, also recovering scope expansion interrupted after a response commit.
    rows = store.db.execute('''SELECT s.url,s.extracted FROM snapshots s WHERE EXISTS
        (SELECT 1 FROM observations o WHERE o.url=s.url AND o.body_hash=s.body_hash
         AND o.error IS NULL AND (o.status BETWEEN 200 AND 299 OR o.status=304))''')
    for row in rows:
        if include_unavailable or kind_for(row['url']) in ('building', 'directory', 'search'):
            expand(store, generation, json.loads(row['extracted']), row['url'], include_unavailable)


def configure_building(store, generation, building, include_unavailable=True):
    # Reconstruct the selected scope from archived evidence. No completed response
    # is reset, and a wider previous neighborhood scope cannot leak into this run.
    with store._tx():
        store.db.execute('DELETE FROM scope_urls WHERE generation=?', (generation,))
        store.db.execute('DELETE FROM scope_buildings WHERE generation=?', (generation,))
    enroll(store, generation, {building: 'explicit building seed'}, [building])
    rows = store.db.execute('SELECT url,extracted FROM snapshots ORDER BY id').fetchall()
    for row in rows:
        associated = building_root(row['url']) == building or store.db.execute(
            'SELECT 1 FROM scope_urls WHERE generation=? AND url=?', (generation, row['url'])).fetchone()
        if associated and (include_unavailable or row['url'] == building):
            expand(store, generation, json.loads(row['extracted']), row['url'], include_unavailable, building=building)
