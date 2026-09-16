"""Human edits as a separate, append-only, bitemporal JSON Patch ledger.

No write in this module touches archive bodies or capture interpretations.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import uuid

import jsonpatch
from jsonpointer import JsonPointer, JsonPointerException

DEFAULT_LEDGER = Path('config/corrections.jsonl')
TARGET_KEYS = {'source', 'source_listing_id', 'episode_id', 'building_slug', 'unit',
               'version_id', 'capture_id'}
# Identity and collection provenance remain in the envelope, independent of edits.
PROTECTED = {'source', 'source_listing_id', 'captured_at', 'schema_version',
             'street_easy_rental_id', 'canonical_url'}
GENESIS = '0' * 64


class CorrectionError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def instant(value):
    """Date-only values mean midnight UTC; timestamps must include a zone."""
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if len(value) == 10:
            parsed = parsed.replace(tzinfo=UTC)
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise CorrectionError('Expected an ISO date or timezone-aware timestamp')
    if parsed.tzinfo is None:
        raise CorrectionError('Timestamps require an explicit timezone')
    return parsed.astimezone(UTC)


def now():
    return datetime.now(UTC)


def validate_edit(spec):
    if not isinstance(spec, dict):
        raise CorrectionError('Edit specification must be an object')
    required = {'target', 'patch', 'validity'}
    if not required <= spec.keys() or spec.keys() - required - {'supersedes'}:
        raise CorrectionError('Edit requires target, patch, validity; only supersedes is optional')
    if 'supersedes' in spec and (not isinstance(spec['supersedes'], str) or not spec['supersedes'].strip()):
        raise CorrectionError('supersedes must be an active correction ID')
    target = spec['target']
    if not isinstance(target, dict) or not target or target.keys() - TARGET_KEYS:
        raise CorrectionError('Unknown or empty correction target')
    if not all(isinstance(v, str) and v.strip() for v in target.values()):
        raise CorrectionError('Target values must be nonempty strings')
    if 'source' not in target or not (target.keys() & (TARGET_KEYS - {'source', 'unit'})):
        raise CorrectionError('Target needs source and a building, unit identity, episode, capture or version')
    validity = spec['validity']
    if not (isinstance(validity, dict) and set(validity) == {'all_time'} and validity['all_time'] is True):
        if not isinstance(validity, dict) or not validity or validity.keys() - {'from', 'until'}:
            raise CorrectionError('Choose explicit all_time:true or a from/until interval')
        start = instant(validity['from']) if validity.get('from') else None
        end = instant(validity['until']) if validity.get('until') else None
        if (start is None and end is None) or (start and end and start >= end):
            raise CorrectionError('Invalid or empty effective-time interval')
    patch = spec['patch']
    if not isinstance(patch, list) or not patch:
        raise CorrectionError('Patch must contain at least one operation')
    writes = 0
    for op in patch:
        if not isinstance(op, dict) or op.get('op') not in {'add', 'replace', 'remove', 'test'}:
            raise CorrectionError('Supported JSON Patch operations: add, replace, remove, test')
        expected = {'op', 'path'} | ({'value'} if op['op'] != 'remove' else set())
        if set(op) != expected:
            raise CorrectionError('Unexpected or missing patch operation fields')
        try:
            parts = JsonPointer(op['path']).parts
        except (JsonPointerException, TypeError, AttributeError) as e:
            raise CorrectionError('Invalid JSON Pointer') from e
        if not parts or parts[0] in PROTECTED or parts == ['archive_listing'] or parts[:2] == ['archive_listing', 'id']:
            raise CorrectionError('Cannot replace the document or edit its collection/identity metadata')
        writes += op['op'] != 'test'
    if not writes:
        raise CorrectionError('A correction must change an attribute')
    canonical(spec)  # Reject NaN and other non-JSON values.


def _active(records):
    active = {}
    for record in records:
        previous = record.get('supersedes') if record['action'] == 'edit' else record.get('retracts')
        if previous:
            if previous not in active:
                raise CorrectionError('Revision/withdrawal must reference a currently active edit')
            old = active.pop(previous)
            if record['action'] == 'edit' and any(record[k] != old[k] for k in ('target', 'validity')):
                raise CorrectionError('A revision must preserve target and validity; retract and add to change scope')
        if record['action'] == 'edit':
            active[record['id']] = record
    return list(active.values())


def _read(stream):
    records, previous, last_time = [], GENESIS, None
    ids = set()
    for line in stream:
        if not line.endswith('\n'):
            raise CorrectionError('Incomplete ledger tail; restore the last complete version before appending')
        try:
            record = json.loads(line)
            signature = record['hash']
            payload = {k: v for k, v in record.items() if k != 'hash'}
            if record['previous_hash'] != previous or hashlib.sha256(canonical(payload).encode()).hexdigest() != signature:
                raise CorrectionError('Correction ledger hash chain mismatch')
            if record['id'] in ids or record['schema_version'] != 1 or record['action'] not in {'edit', 'retract'}:
                raise CorrectionError('Invalid correction record')
            recorded = instant(record['recorded_at'])
            if last_time and recorded < last_time:
                raise CorrectionError('Correction timestamps must be monotonic')
            if record['action'] == 'edit':
                validate_edit({k: record[k] for k in ('target', 'patch', 'validity', 'supersedes') if k in record})
            if not record['author'].strip() or not record['reason'].strip():
                raise CorrectionError('Correction author and reason are required')
            records.append(record)
            ids.add(record['id'])
            previous, last_time = signature, recorded
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            raise CorrectionError(f'Invalid ledger record {len(records)+1}: {e}') from e
    _active(records)
    return records


def append(ledger, *, author, reason, edit=None, retracts=None, evidence=None):
    """Append one edit/revision/withdrawal under an inter-process lock.

    recorded_at is generated here, never supplied by a human edit specification.
    """
    if not isinstance(author, str) or not author.strip() or not isinstance(reason, str) or not reason.strip():
        raise CorrectionError('Author and reason are required')
    if (edit is None) == (retracts is None):
        raise CorrectionError('Supply exactly one of edit or retracts')
    if edit is not None:
        validate_edit(edit)
    if retracts is not None and (not isinstance(retracts, str) or not retracts.strip()):
        raise CorrectionError('Withdrawal requires an active correction ID')
    if evidence is not None and (not isinstance(evidence, list) or not all(isinstance(x, str) for x in evidence)):
        raise CorrectionError('Evidence must be a list of references or notes')
    path = Path(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+', encoding='utf-8') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        records = _read(stream)
        record = {'schema_version': 1, 'id': str(uuid.uuid4()), 'recorded_at': now().isoformat(),
                  'author': author, 'reason': reason, 'evidence': evidence or [],
                  'action': 'edit' if edit is not None else 'retract',
                  'previous_hash': records[-1]['hash'] if records else GENESIS}
        record.update(deepcopy(edit) if edit is not None else {'retracts': retracts})
        if records and instant(record['recorded_at']) < instant(records[-1]['recorded_at']):
            raise CorrectionError('System clock precedes the last correction')
        _active([*records, record])
        record['hash'] = hashlib.sha256(canonical(record).encode()).hexdigest()
        stream.seek(0, os.SEEK_END)
        stream.write(canonical(record) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return record


def _overlap(a, b):
    return a[:len(b)] == b or b[:len(a)] == a


def _footprint(document, path):
    """Treat any array mutation as a write to the array, avoiding index shifts."""
    parts = JsonPointer(path).parts
    current, prefix = document, []
    for part in parts:
        if isinstance(current, list):
            return tuple(prefix)
        prefix.append(part)
        current = current.get(part) if isinstance(current, dict) else None
    return tuple(parts)


class Overlay:
    def __init__(self, ledger, *, as_of=None, enabled=True):
        self.enabled = enabled
        self.as_of = instant(as_of) if as_of is not None else now()
        # An explicitly supplied nonexistent ledger is an error, never raw fallback.
        with Path(ledger).open(encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            records = _read(stream)
        self.records = [r for r in records if instant(r['recorded_at']) <= self.as_of]
        self.active = _active(self.records)
        # Index one immutable selector per rule, so large exports do not scan all edits.
        self.index = {}
        for r in self.active:
            key = next(k for k in ('version_id', 'capture_id', 'episode_id', 'source_listing_id', 'building_slug') if k in r['target'])
            self.index.setdefault((key, r['target'][key]), []).append(r)

    @property
    def manifest(self):
        return {'schema_version': 1, 'enabled': self.enabled, 'corrections_as_of': self.as_of.isoformat(),
                'ledger_prefix_sha256': self.records[-1]['hash'] if self.records else GENESIS,
                'visible_records': len(self.records), 'active_ids': [r['id'] for r in self.active]}

    def apply(self, raw, context, *, effective_at=None):
        result = deepcopy(raw)
        if not self.enabled:
            return result, []
        effective = instant(effective_at) if effective_at is not None else None
        edits = []
        for key, value in context.items():
            for r in self.index.get((key, value), []):
                if not all(context.get(k) == v for k, v in r['target'].items()):
                    continue
                valid = r['validity']
                if valid != {'all_time': True}:
                    if effective is None:
                        raise CorrectionError(f"Correction {r['id']} needs an explicit effective_at; collection time is not effective time")
                    if valid.get('from') and effective < instant(valid['from']):
                        continue
                    if valid.get('until') and effective >= instant(valid['until']):
                        continue
                edits.append(r)
        writes, evidence = [], []
        for r in edits:
            # Check tests as well: a different rule must not alter a test's input.
            touched = [(_footprint(raw, op['path']), op['op'] != 'test') for op in r['patch']]
            for path, write in touched:
                for earlier, earlier_write, earlier_id in writes:
                    if (write or earlier_write) and _overlap(path, earlier):
                        raise CorrectionError(f"Conflicting corrections {earlier_id} and {r['id']}; revise or retract explicitly")
            writes.extend((p, w, r['id']) for p, w in touched)
            try:
                updated = jsonpatch.apply_patch(result, r['patch'], in_place=False)
            except (jsonpatch.JsonPatchException, JsonPointerException, TypeError) as e:
                raise CorrectionError(f"Correction {r['id']} cannot apply: {e}") from e
            evidence.append({k: deepcopy(r[k]) for k in ('id', 'recorded_at', 'author', 'reason', 'evidence', 'target', 'validity', 'patch')})
            evidence[-1]['changes'] = jsonpatch.make_patch(result, updated).patch
            result = updated
        return result, evidence
