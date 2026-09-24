"""Opt-in rental collection with source-evidenced canonical-unit membership.

Unknown unit routes may be fetched once to establish evidence. Advertisement-ID
routes require membership from an eligible unit capture before spending credits.
All captures are retained; exclusions affect future requests, not raw evidence.
"""
import json
import re
import time
from urllib.parse import urlsplit

from .extract import kind_for
from .listing_identity import listing_key

POLICY = 'rental-canonical-v1'


def enabled(store, generation):
    row = store.db.execute('SELECT value FROM metadata WHERE key=?',
                           (f'collection_policy:{generation}',)).fetchone()
    return bool(row and row[0] == POLICY)


def setup(store, generation):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS collection_memberships(
            generation INTEGER, listing_key TEXT, unit_url TEXT, source_url TEXT,
            body_hash TEXT, created REAL,
            PRIMARY KEY(generation,listing_key,unit_url,body_hash));
        CREATE TABLE IF NOT EXISTS collection_exclusions(
            generation INTEGER, url TEXT, reason TEXT, created REAL,
            PRIMARY KEY(generation,url,reason));
    ''')
    with store._tx():
        store.db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',
                         (f'collection_policy:{generation}', POLICY))
    # Reuse archived bytes to establish membership, with no provider calls.
    # Extractions are large; list identities first and load one at a time.
    for row in store.db.execute('''SELECT s.id, s.url, s.body_hash FROM snapshots s WHERE generation=?
        AND EXISTS(SELECT 1 FROM observations o WHERE o.generation=s.generation
          AND o.url=s.url AND o.body_hash=s.body_hash AND o.error IS NULL
          AND (o.status BETWEEN 200 AND 299 OR o.status=304)) ORDER BY id''', (generation,)).fetchall():
        if kind_for(row['url']) == 'listing':
            extracted = store.db.execute('SELECT extracted FROM snapshots WHERE id=?', (row['id'],)).fetchone()[0]
            annotate(store, generation, json.loads(extracted),
                     store.get_body(row['body_hash']), row['url'], row['body_hash'])
    enroll_inventory_probes(store, generation)


def exclusion_reason(store, generation, url):
    if not enabled(store, generation):
        return None
    path = urlsplit(url).path
    if ('unavailable-sales' in url or re.search(r'/(?:sale|sales|for-sale|past-sales|sold)(?:/|$)', path)
            or re.search(r'/nyc_(?:sales|sale_searches)_', path)):
        return 'sale_route'
    key = listing_key(url)
    if not key and re.search(r'/(?:rental|sale)/', path):
        return 'unsupported_advertisement_route'
    if key:
        rows = store.db.execute('SELECT DISTINCT unit_url FROM collection_memberships WHERE generation=? AND listing_key=?',
                                (generation, key)).fetchall()
        if len(rows) != 1:
            return 'missing_canonical_unit_association' if not rows else 'conflicting_canonical_unit_association'
    return None


def exclude(store, generation, url, reason):
    # Caller owns the transaction. Completed observations are never rewritten.
    store.db.execute('INSERT OR IGNORE INTO collection_exclusions VALUES(?,?,?,?)',
                     (generation, url, reason, time.time()))
    store.db.execute("UPDATE frontier SET state='excluded' WHERE generation=? AND url=? AND state IN ('pending','deferred')",
                     (generation, url))


def annotate(store, generation, data, body, url, body_hash=None, persist=True):
    if not enabled(store, generation) or kind_for(url) != 'listing':
        return
    from apartments.granular_parse import parse_listing
    import hashlib
    row, events = parse_listing(body, url)
    unit = row.get('canonical_unit_url')
    rental_events = [e for e in events if e['event_category'] == 'rental']
    eligible = bool(unit and kind_for(unit) == 'listing' and not listing_key(unit) and not row.get('canonical_unit_error') and row.get('listing_id')
                    and row.get('listing_type') == 'rental' and rental_events
                    and row.get('parse_status') == 'ok')
    key = listing_key(url)
    if key and eligible:
        known = {r[0] for r in store.db.execute('SELECT DISTINCT unit_url FROM collection_memberships WHERE generation=? AND listing_key=?', (generation, key))}
        eligible = known == {unit}
    data['collection_policy'] = {'version': POLICY, 'eligible': eligible,
        'canonical_unit_url': unit, 'listing_type': row.get('listing_type'),
        'parse_status': row.get('parse_status'), 'error': row.get('canonical_unit_error') or row.get('error')}
    if persist and not eligible:
        with store._tx():
            exclude(store, generation, url, 'captured_listing_not_eligible')
    # Only the unit page establishes membership. Episode pages cannot recursively
    # authorize other advertisements, even if they contain related history.
    if eligible and url == unit and persist:
        keys = {f"rental:{e['event_listing_id']}:detail" for e in rental_events
                if str(e.get('event_listing_id', '')).isdigit()}
        keys.add(f"rental:{row['listing_id']}:detail")
        with store._tx():
            for member in keys:
                store.db.execute('INSERT OR IGNORE INTO collection_memberships VALUES(?,?,?,?,?,?)',
                    (generation, member, unit, url, body_hash or hashlib.sha256(body).hexdigest(), time.time()))
                # Later evidence may resolve a formerly unknown route. Preserve
                # its earlier exclusion audit while making it eligible again.
                store.db.execute("UPDATE frontier SET state='pending' WHERE generation=? AND listing_key=? AND state='excluded' AND url IN (SELECT url FROM collection_exclusions WHERE generation=? AND reason='missing_canonical_unit_association')",
                                 (generation, member, generation))


PROBE_RULE = 'inventory-label-unit-probe-v1'
_CELL = re.compile(r'<td\b[^>]*>(.*?)</td>', re.S)
_HREF = re.compile(r'href="([^"]+)"')


def inventory_unit_probes(data, source_url):
    """Map unit routes guessed from rental-inventory labels to their source ad.

    A guess is only a request target. Membership still comes solely from the
    probed page's own canonical URL and rental history, so a wrong guess costs
    one request and authorizes nothing. Chelsea's source-declared pairs match
    this normalization for 93% of labels; padded or suffixed routes are missed.
    """
    from .extract import canonical_url
    from .scope import building_root
    root = building_root(source_url)
    if not root or 'archive_view=unavailable-rentals' not in source_url:
        return {}
    probes = {}
    for html in data.get('inventory', {}).get('rows', []):
        cells = _CELL.findall(html or '')
        href = _HREF.search(html or '')
        if len(cells) < 2 or not href:
            continue
        ad = canonical_url(href[1])
        slug = re.sub(r'[^a-z0-9]+', '', re.sub(r'<[^>]+>', '', cells[1]).strip().lstrip('#').lower())
        unit = f'{root}/{slug}' if slug else None
        if (ad and listing_key(ad) and listing_key(ad).startswith('rental:') and unit
                and kind_for(unit) == 'listing' and not listing_key(unit)):
            probes.setdefault(unit, ad)
    return probes


def enroll_inventory_probes(store, generation):
    """Replay archived in-scope rental inventories into unit probes, offline."""
    from .scope import _enroll, building_root
    roots = {r[0] for r in store.db.execute('SELECT url FROM scope_buildings WHERE generation=?', (generation,))}
    probes = {}
    for row in store.db.execute('''SELECT id, url FROM snapshots WHERE generation=?
            AND url LIKE '%archive_view=unavailable-rentals%' ORDER BY id''', (generation,)).fetchall():
        if building_root(row['url']) in roots:
            extracted = store.db.execute('SELECT extracted FROM snapshots WHERE id=?', (row['id'],)).fetchone()[0]
            for unit, ad in inventory_unit_probes(json.loads(extracted), row['url']).items():
                probes.setdefault(unit, f'{PROBE_RULE} from {ad}')
    with store._tx():
        _enroll(store, generation, probes)
    return len(probes)


def reuse_unit_capture(store, generation, row):
    """Reuse the same advertisement on a canonical unit route, never its neighbors.

    Caller holds the writer transaction. Membership alone is insufficient:
    the latest source capture must identify this exact advertisement and retain
    complete inline history. An alias records actual source evidence, not a fetch.
    """
    if not enabled(store, generation) or not row['listing_key']:
        return False
    from .listing_identity import capture_evidence
    units = store.db.execute('SELECT DISTINCT unit_url FROM collection_memberships WHERE generation=? AND listing_key=?',
                             (generation, row['listing_key'])).fetchall()
    if len(units) != 1:
        return False
    target = units[0][0]
    observation = store.db.execute('''SELECT * FROM observations WHERE generation=? AND url=?
        ORDER BY fetched DESC,id DESC LIMIT 1''', (generation, target)).fetchone()
    if (not observation or observation['error'] is not None or not observation['body_hash']
            or observation['status'] is None or not (200 <= observation['status'] < 300 or observation['status'] == 304)
            or not store.body_path(observation['body_hash']).is_file()):
        return False
    snapshot = store.db.execute('SELECT id,extracted FROM snapshots WHERE generation=? AND url=? AND body_hash=?',
                                (generation, target, observation['body_hash'])).fetchone()
    if not snapshot:
        return False
    data = json.loads(snapshot['extracted'])
    if 'collection_policy' not in data:
        # Older snapshots predate the policy. Interpret their immutable bytes
        # offline without overwriting the historical extraction.
        annotate(store, generation, data, store.get_body(observation['body_hash']), target, persist=False)
    policy = data.get('collection_policy', {})
    if not policy.get('eligible') or policy.get('canonical_unit_url') != target:
        return False
    # The requested advertisement ID selects which listing object must be
    # present in the saved source payload; history mentions cannot satisfy it.
    proof = capture_evidence(data, row['url'])
    if not proof:
        return False
    proof = dict(proof, validation='canonical-unit-same-advertisement-v1',
                 snapshot_id=snapshot['id'], observation_id=observation['id'],
                 body_hash=observation['body_hash'], reason='same advertisement already captured on canonical unit page')
    store._remember_alias(generation, row['url'], target, json.dumps(proof, sort_keys=True))
    store.db.execute("UPDATE frontier SET state='superseded' WHERE generation=? AND url=?",
                     (generation, row['url']))
    return True
