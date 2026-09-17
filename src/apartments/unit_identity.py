"""Durable, reversible identity declarations for StreetEasy rental listings.

Listing IDs identify advertisements; unit IDs identify associated homes.
Associations retain a manual or StreetEasy source basis.
Archive observations are never rewritten. Consumers can freeze this ledger's hash.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from pathlib import Path

from .corrections import canonical
from .review_ledger import GENESIS, ReviewConflict, ReviewLedgerError, _now


def listing_ids(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 5000
        or any(not isinstance(x, str) or not x.isascii() or not x.isdigit() for x in value)
        or len(set(value)) != len(value)):
        raise ValueError("Select 1–5,000 unique StreetEasy rental listing IDs")
    return sorted(value)


def merge_decisions(events):
    """Expand a batch into individually reversible associations for all consumers."""
    result = []
    for e in events:
        if e['action'] == 'merge':
            result.append({**e, 'basis': e.get('basis', 'manual')})
        elif e['action'] == 'associate_batch':
            for proposal, unit in zip(e['proposals'], e['units']):
                result.append({'id':unit['id'], 'unit_id':unit['unit_id'],
                    'listing_ids':proposal['listing_ids'], 'evidence':proposal['evidence'],
                    'basis':'streeteasy', 'batch_id':e['id'], 'action':'merge',
                    'author':e['author'], 'reason':e['reason'], 'recorded_at':e['recorded_at'],
                    'review_revision':e['review_revision']})
    return result


def undone_decisions(events):
    batches = {e['batch_id'] for e in events if e['action'] == 'undo_batch'}
    return ({e['merge_id'] for e in events if e['action'] == 'undo'} |
            {u['id'] for e in events if e['action'] == 'associate_batch' and e['id'] in batches for u in e['units']})


def active_decisions(events):
    undone = undone_decisions(events)
    return [e for e in merge_decisions(events) if e['id'] not in undone]


def identity_map(events):
    result = {}
    for event in active_decisions(events):
        for lid in event['listing_ids']:
            result[lid] = event['unit_id']
    return result


def resolve_unit(listing_id, events):
    return identity_map(events).get(listing_id, f'streeteasy:rental:{listing_id}')


def expand_ids(ids, events):
    mapping = identity_map(events)
    units = {mapping[lid] for lid in ids if lid in mapping}
    return sorted(set(ids) | {lid for lid, unit in mapping.items() if unit in units})


class UnitIdentityLedger:
    def __init__(self, path, dataset):
        self.path, self.dataset = Path(path), dataset

    def _read(self, stream):
        events, previous, seen = [], GENESIS, set()
        for line in stream:
            try:
                if not line.endswith('\n'):
                    raise ValueError('Incomplete tail')
                event = json.loads(line)
                payload = {k: v for k, v in event.items() if k != 'hash'}
                if (event['schema_version'] != 1 or event['dataset'] != self.dataset
                    or event['source'] != 'streeteasy' or event['listing_type'] != 'rental'
                    or event['id'] in seen or event['previous_hash'] != previous
                    or hashlib.sha256(canonical(payload).encode()).hexdigest() != event['hash']):
                    raise ValueError('Invalid identity event or hash chain')
                if not event['author'].strip() or not event['reason'].strip():
                    raise ValueError('Author and reason required')
                if event['action'] == 'merge':
                    if len(listing_ids(event['listing_ids'])) < 2 or not event['unit_id'].startswith('unit:'):
                        raise ValueError('Invalid merged unit')
                elif event['action'] == 'undo':
                    if not any(e['id'] == event['merge_id'] for e in merge_decisions(events)):
                        raise ValueError('Unknown merge')
                elif event['action'] == 'associate_batch':
                    proposals = event['proposals']; units = event['units']
                    if not 1 <= len(proposals) <= 20000 or len(proposals) != len(units):
                        raise ValueError('Invalid association batch')
                    members = set(); unit_ids = set(); decision_ids = set()
                    for proposal, unit in zip(proposals, units):
                        ids = listing_ids(proposal['listing_ids'])
                        if (len(ids)<2 or members.intersection(ids) or unit['id'] in decision_ids
                            or unit['unit_id'] in unit_ids or not unit['unit_id'].startswith('unit:')
                            or not isinstance(proposal['evidence'], dict)):
                            raise ValueError('Invalid association group')
                        members.update(ids); unit_ids.add(unit['unit_id']); decision_ids.add(unit['id'])
                elif event['action'] == 'undo_batch':
                    if not any(e['id']==event['batch_id'] and e['action']=='associate_batch' for e in events):
                        raise ValueError('Unknown association batch')
                else:
                    raise ValueError('Unknown identity action')
                events.append(event)
                seen.add(event['id'])
                previous = event['hash']
            except (KeyError, TypeError, AttributeError, ValueError) as error:
                raise ReviewLedgerError(f'Invalid unit identity ledger: {error}') from error
        return events

    def events(self):
        if not self.path.exists():
            return []
        with self.path.open(encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            return self._read(stream)

    @staticmethod
    def revision(events):
        return events[-1]['hash'] if events else GENESIS

    def write(self, action, *, author, reason, request_id, expected_revision, **data):
        if not all(isinstance(x, str) and x.strip() for x in (author, reason, request_id)):
            raise ValueError('Reviewer, reason, and request ID are required')
        if action not in {'merge', 'undo', 'associate_batch', 'undo_batch'}:
            raise ValueError('Unknown identity action')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a+', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            events = self._read(stream)
            prior = next((e for e in events if e['request_id'] == request_id), None)
            if prior:
                if any(prior.get(k) != v for k, v in dict(action=action, author=author, reason=reason, **data).items()):
                    raise ReviewConflict('Request ID already used for a different identity decision')
                return prior
            if self.revision(events) != expected_revision:
                raise ReviewConflict('Unit identities changed; compare the listings again')
            if action == 'merge':
                ids = listing_ids(data['listing_ids'])
                if len(ids) < 2 or expand_ids(ids, events) != ids:
                    raise ValueError('A merge must include every listing of its existing units')
                mapping = identity_map(events)
                units = {mapping.get(lid, f'streeteasy:rental:{lid}') for lid in ids}
                if len(units) < 2:
                    raise ValueError('These listings already belong to one unit')
                # Retain an existing canonical identity when expanding a merged unit.
                unit_id = next((e['unit_id'] for e in active_decisions(events) if e['action'] == 'merge'
                                and e['unit_id'] in units), 'unit:' + str(uuid.uuid4()))
                data = {**data, 'listing_ids': ids, 'unit_id': unit_id}
            elif action == 'associate_batch':
                proposals = data.get('proposals')
                if not isinstance(proposals, list) or not 1 <= len(proposals) <= 20000:
                    raise ValueError('Select 1–20,000 supported groups')
                members = set(); mapping = identity_map(events); units = []
                for proposal in proposals:
                    ids = listing_ids(proposal['listing_ids'])
                    if (len(ids)<2 or members.intersection(ids) or any(lid in mapping for lid in ids)
                        or not isinstance(proposal.get('evidence'), dict)):
                        raise ValueError('Association groups must be distinct and not already merged')
                    members.update(ids)
                    units.append({'id':str(uuid.uuid4()), 'unit_id':'unit:'+str(uuid.uuid4())})
                data = {**data, 'units':units}
            else:
                decisions = merge_decisions(events); undone = undone_decisions(events)
                if action == 'undo':
                    targets = [e for e in decisions if e['id'] == data['merge_id'] and e['id'] not in undone]
                else:
                    batch = next((e for e in events if e['id']==data['batch_id'] and e['action']=='associate_batch'), None)
                    if batch is None or any(e['action']=='undo_batch' and e['batch_id']==data['batch_id'] for e in events):
                        raise ValueError('Batch is unknown or already undone')
                    targets = [e for e in decisions if e.get('batch_id')==data['batch_id'] and e['id'] not in undone]
                if not targets:
                    raise ValueError('Merge is unknown or already undone')
                target_ids = {e['id'] for e in targets}
                positions = {e['id']:i for i,e in enumerate(decisions)}
                protected = {lid:positions[e['id']] for e in targets for lid in e['listing_ids']}
                if any(e['id'] not in undone and e['id'] not in target_ids
                       and any(i > protected[lid] for lid in e['listing_ids'] if lid in protected)
                       for i,e in enumerate(decisions)):
                    raise ValueError('Undo the later merge involving these listings first')
            event = {'schema_version': 1, 'id': str(uuid.uuid4()), 'dataset': self.dataset,
                     'source': 'streeteasy', 'listing_type': 'rental', 'action': action,
                     'recorded_at': _now(), 'author': author, 'reason': reason,
                     'request_id': request_id, 'previous_hash': self.revision(events), **data}
            event['hash'] = hashlib.sha256(canonical(event).encode()).hexdigest()
            stream.seek(0, os.SEEK_END)
            stream.write(canonical(event) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
            return event
