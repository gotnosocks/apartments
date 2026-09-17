"""Manual rental-listing identity resolution and canonical unit histories."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict

from .corrections import canonical
from .review_ledger import GENESIS, ReviewConflict
from .unit_identity import UnitIdentityLedger, expand_ids, identity_map, listing_ids


def records(cursor):
    keys = [c[0] for c in cursor.description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def search_text(value):
    value = re.sub(r'(?<=\d)(?:st|nd|rd|th)\b', '', value.casefold())
    return ' '.join(re.findall(r'[a-z0-9]+', value))


class UnitMergeService:
    def __init__(self, service):
        self.s = service
        self.ledger = UnitIdentityLedger(service.state / 'unit-identities.jsonl', service.dataset)
        self._cache = None

    def catalog(self, review_events, identity_events):
        revision = review_events[-1]['hash'] if review_events else GENESIS
        key = (revision, self.ledger.revision(identity_events))
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        rows = records(self.s.db.execute(
            'SELECT snapshot_id,listing_id,building_slug,unit_label FROM rental ORDER BY snapshot_id'
        ))
        by_sid = {row['snapshot_id']: row for row in rows}
        retracted = {e['correction_id'] for e in review_events if e['action'] == 'retract'}
        corrected_ids = {sid for e in review_events
                         if e['action'] == 'correct' and e['id'] not in retracted
                         and any(p['path'] in {'/building_slug', '/unit_label'} for p in e['patch'])
                         for sid in e['snapshot_ids'] if sid in by_sid}
        if corrected_ids:
            for row, raw in self.s.raw_batch(sorted(corrected_ids)):
                corrected, _ = self.s.ledger.apply(raw, row['snapshot_id'], events=review_events)
                by_sid[row['snapshot_id']].update(
                    building_slug=corrected.get('building_slug'), unit_label=corrected.get('unit_label'))
        mapping = identity_map(identity_events)
        listings = {}
        for row in rows:
            lid = row['listing_id']
            if not lid:
                continue
            item = listings.setdefault(lid, {'listing_id': lid,
                'unit_id': mapping.get(lid, f'streeteasy:rental:{lid}'), 'captures': []})
            item['captures'].append(row)
        self._cache = (key, listings)
        return listings

    def candidates(self, args):
        review_events, identity_events = self.s.ledger.events(), self.ledger.events()
        catalog = self.catalog(review_events, identity_events)
        search = str(args.get('search', '')).strip().casefold()
        if len(search) > 200:
            raise ValueError('Search is too long')
        building = str(args.get('building') or '')
        mode = args.get('mode', 'candidates')
        if mode not in {'candidates', 'merged'}:
            raise ValueError('Unknown unit list')
        sort = args.get('sort', 'building')
        direction = args.get('direction', 'asc')
        if sort not in {'building', 'listing_count'} or direction not in {'asc', 'desc'}:
            raise ValueError('Unknown sort order')
        groups = defaultdict(set)
        if mode == 'candidates':
            for lid, listing in catalog.items():
                for capture in listing['captures']:
                    b, u = capture['building_slug'], capture['unit_label']
                    if not b or not u or not u.strip() or re.search(r'bedroom|studio|[0-9] *br|layout|floorplan', u, re.I):
                        continue
                    groups[(b, u)].add(lid)
        else:
            for lid, unit_id in identity_map(identity_events).items():
                if lid in catalog:
                    groups[unit_id].add(lid)
        result = []
        for key, ids in groups.items():
            units = {catalog[lid]['unit_id'] for lid in ids}
            if mode == 'candidates' and len(units) < 2:
                continue
            captures = [c for lid in ids for c in catalog[lid]['captures']]
            labels = sorted({(c['building_slug'] or '', c['unit_label'] or '') for c in captures})
            text = ' '.join(b + ' ' + u for b, u in labels) + ' ' + ' '.join(sorted(ids))
            if building and not any(b == building for b, _ in labels):
                continue
            if search and not all(word in search_text(text) for word in search_text(search).split()):
                continue
            result.append({'building': key[0] if mode == 'candidates' else labels[0][0],
                           'unit_label': key[1] if mode == 'candidates' else labels[0][1],
                           'unit_id': key if mode == 'merged' else None,
                           'listing_ids': sorted(ids), 'listing_count': len(ids),
                           'capture_count': len(captures), 'identities': len(units)})
        result.sort(key=lambda r: (r['building'], r['unit_label'], r['listing_ids']))
        if sort == 'listing_count':
            # Stable tie order, applied to all matches before selecting a page.
            result.sort(key=lambda r: r['listing_count'], reverse=direction == 'desc')
        elif direction == 'desc':
            result.reverse()
        limit = min(100, max(1, int(args.get('limit', 25))))
        offset = max(0, int(args.get('offset', 0)))
        offset = min(offset, max(0, ((len(result) - 1) // limit) * limit))
        return {'rows': result[offset:offset + limit], 'total': len(result), 'offset': offset,
                'limit': limit, 'sort': sort, 'direction': direction,
                'identity_revision': self.ledger.revision(identity_events)}

    def inspect(self, args):
        identity_events, review_events = self.ledger.events(), self.s.ledger.events()
        catalog = self.catalog(review_events, identity_events)
        if args.get('unit_id'):
            ids = sorted(lid for lid, row in catalog.items() if row['unit_id'] == args['unit_id'])
            if not ids:
                raise ValueError('Unit not found')
        else:
            supplied = args.get('listing_ids')
            ids = listing_ids(supplied.split(',') if isinstance(supplied, str) else supplied)
        ids = expand_ids(ids, identity_events)
        if len(ids) > 200:
            raise ValueError('Compare at most 200 listing IDs at a time')
        if any(lid not in catalog for lid in ids):
            raise ValueError('Selection contains an unknown rental listing ID')
        capture_ids = sorted({c['snapshot_id'] for lid in ids for c in catalog[lid]['captures']})
        if len(capture_ids) > 1000:
            raise ValueError('Selection exceeds 1,000 captures; narrow the comparison')
        documents, observations = {}, []
        fields = ('building_slug', 'unit_label', 'bedrooms', 'bathrooms', 'square_feet', 'room_count', 'asking_price')
        for row, raw in self.s.raw_batch(capture_ids):
            corrected, evidence = self.s.ledger.apply(raw, row['snapshot_id'], events=review_events)
            documents[row['snapshot_id']] = (raw, corrected)
            observations.append({**row,
                                 'attributes': {k: v for k, v in corrected.items() if k != 'archive_listing'},
                                 'raw_attributes': {k: v for k, v in raw.items() if k != 'archive_listing'},
                                 'correction_ids': [e['id'] for e in evidence]})
        history = records(self.s.db.execute(
            "SELECT snapshot_id,episode_index,event_index,event_listing_id,event_date,price,status,event_json "
            "FROM event_mentions WHERE snapshot_id IN (SELECT unnest(?)) AND event_category='rental' "
            "ORDER BY event_date, snapshot_id,episode_index,event_index LIMIT 100001", [capture_ids]))
        if len(history) > 100000:
            raise ValueError('History comparison exceeds 100,000 mentions; narrow the selection')
        combined, versions = {}, defaultdict(set)
        for event in history:
            sid = event['snapshot_id']
            self.s._event_price(event, *documents[sid])
            source = json.loads(event['event_json'])
            # Exact source event equality plus effective price; no date-only deduplication.
            key = canonical([event['event_listing_id'] or ['unknown', sid], source, event['price'],
                             event.get('price_edit_error')])
            item = combined.setdefault(key, {k: event[k] for k in
                ('event_listing_id', 'event_date', 'price', 'raw_price', 'status')})
            item['event_id'] = hashlib.sha256(key.encode()).hexdigest()
            item.setdefault('occurrences', []).append({k: event[k] for k in
                ('snapshot_id', 'episode_index', 'event_index', 'price', 'raw_price')})
            item['source_event'] = source
            if event.get('price_edit_error'):
                item['overlay_warning'] = event['price_edit_error']
            versions[(event['event_listing_id'], event['event_date'], event['status'])].add(key)
        for key, item in combined.items():
            item['conflicting_version'] = len(versions[(item['event_listing_id'], item['event_date'], item['status'])]) > 1
        conflicts = {field: sorted({canonical(o['attributes'][field]) for o in observations
                                   if o['attributes'][field] is not None}) for field in fields if field != 'asking_price'}
        conflicts = {k: [json.loads(v) for v in values] for k, values in conflicts.items() if len(values) > 1}
        units = sorted({catalog[lid]['unit_id'] for lid in ids})
        undone = {e['merge_id'] for e in identity_events if e['action'] == 'undo'}
        merge = next((e for e in reversed(identity_events) if e['action'] == 'merge'
                      and e['id'] not in undone and len(units) == 1 and e['unit_id'] == units[0]), None)
        return {'dataset': self.s.dataset, 'listing_ids': ids, 'unit_ids': units,
                'unit_id': units[0] if len(units) == 1 else None,
                'listings': [{'listing_id': lid, 'unit_id': catalog[lid]['unit_id'],
                              'capture_count': len(catalog[lid]['captures'])} for lid in ids],
                'observations': observations, 'attribute_disagreements': conflicts,
                'history': list(combined.values()), 'history_mentions': len(history),
                'history_events': len(combined), 'capture_count': len(capture_ids),
                'identity_revision': self.ledger.revision(identity_events),
                'review_revision': review_events[-1]['hash'] if review_events else GENESIS,
                'latest_merge': merge}

    def merge(self, args):
        ids = listing_ids(args.get('listing_ids'))
        identity_events = self.ledger.events()
        prior = next((e for e in identity_events if e['request_id'] == args.get('request_id')), None)
        if prior is None:
            review_events = self.s.ledger.events()
            if (review_events[-1]['hash'] if review_events else GENESIS) != args.get('review_revision'):
                raise ReviewConflict('Reviewed attributes changed; compare the listings again')
            catalog = self.catalog(review_events, identity_events)
            if any(lid not in catalog for lid in ids):
                raise ValueError('Selection contains an unknown rental listing ID')
        return self.ledger.write('merge', listing_ids=ids, review_revision=args.get('review_revision'),
                                 expected_revision=args.get('identity_revision'),
                                 author=args.get('author'), reason=args.get('reason'), request_id=args.get('request_id'))

    def mapping(self, args):
        events = self.ledger.events()
        return {'dataset': self.s.dataset, 'source': 'streeteasy', 'listing_type': 'rental',
                'identity_revision': self.ledger.revision(events),
                'listing_to_unit': identity_map(events),
                'unmerged_unit_id_format': 'streeteasy:rental:<listing_id>'}

    def undo(self, args):
        return self.ledger.write('undo', merge_id=args.get('merge_id'),
                                 expected_revision=args.get('identity_revision'), author=args.get('author'),
                                 reason=args.get('reason'), request_id=args.get('request_id'))
