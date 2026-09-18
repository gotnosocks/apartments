"""Deterministic, knowledge-dated projections of immutable rental captures.

An observation is evidence at collection time, not proof of an attribute's real
change date. Intervals explicitly use last-observation-carried-forward; they
never backfill current attributes onto a source's historical price events.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import tempfile

from .corrections import Overlay, canonical, instant

VERSION = 'dated-analytical-v1'
TIME_BASIS = 'last_observation_carried_forward; change date unverified'
CONTEXT_KEYS = ('source', 'source_listing_id', 'episode_id', 'version_id',
                'capture_id', 'building_slug', 'unit')
ATTRIBUTE_KEYS = ('bedrooms', 'bathrooms', 'square_feet', 'advertised_floor',
                  'physical_floor', 'floors_above_ground', 'elevator', 'laundry_type',
                  'doorman_type', 'hvac_type', 'pet_policy', 'view_exposures',
                  'window_exposures')


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _codes(value):
    if isinstance(value, dict):
        value = value.get('list', [])
    return {v.upper() for v in value if isinstance(v, str)} if isinstance(value, list) else set()


def attributes(raw):
    """Keep unknowns null; absent feature codes do not establish absence.

    Explicit normalized attributes take precedence. No floor is guessed from a
    unit label, and an advertised 14th floor is not assumed to be 14 above ground.
    """
    explicit = raw.get('attributes') or {}
    result = {k: deepcopy(explicit.get(k)) for k in ATTRIBUTE_KEYS}
    for key in ('bedrooms', 'bathrooms', 'square_feet', 'advertised_floor',
                'physical_floor', 'floors_above_ground'):
        result[key] = _number(result[key])
    if result['advertised_floor'] is None:
        result['advertised_floor'] = _number(explicit.get('listed_floor'))
    if result['pet_policy'] is None:
        result['pet_policy'] = explicit.get('pet_rules')
    codes = _codes(raw.get('home_features')) | _codes(raw.get('building_amenities'))
    if 'elevator' not in explicit and 'ELEVATOR' in codes:
        result['elevator'] = True
    # Generic source amenity codes do not identify service hours or equipment type.
    mappings = {
        'laundry_type': [('WASHER_DRYER', 'in_unit'), ('LAUNDRY', 'in_building')],
        'doorman_type': [('FULL_TIME_DOORMAN', 'full_time'), ('PART_TIME_DOORMAN', 'part_time'), ('DOORMAN', 'unspecified')],
        'hvac_type': [('CENTRAL_AC', 'central_ac')],
    }
    for key, pairs in mappings.items():
        if key not in explicit:
            result[key] = next((label for code, label in pairs if code in codes), None)
    if 'pet_policy' not in explicit and 'pet_rules' not in explicit and 'PETS_ALLOWED' in codes:
        result['pet_policy'] = 'allowed_restrictions_unknown'
    return result


def _price(raw):
    # StreetEasy pricing.price is gross advertised rent; netEffectiveRent,
    # rentedPrice and price_history are deliberately not training targets.
    if 'asking_rent' in raw:
        return _number(raw['asking_rent']), '/asking_rent'
    pricing = (raw.get('archive_listing') or {}).get('pricing') or {}
    return _number(pricing.get('price')), '/archive_listing/pricing/price'


def _identity(envelope):
    if envelope.get('unit_id'):
        return str(envelope['unit_id'])
    source, listing = envelope.get('source'), envelope.get('source_listing_id')
    if not source or not listing:
        return None
    # This is a source-page identity, never a verified physical apartment ID.
    return f'{source}:{listing}'


def _boundaries(rows, start, end, overlay):
    points = {start}
    if overlay is not None and overlay.enabled:
        for record in overlay.active:
            if not any(all(r['observation'].get(k) == v for k, v in record['target'].items()) for r in rows):
                continue
            for key in ('from', 'until'):
                value = record['validity'].get(key)
                if value:
                    point = instant(value)
                    if start < point and (end is None or point < end):
                        points.add(point)
    return sorted(points)


def _project(row, when, overlay):
    envelope = row['observation']
    context = {k: envelope.get(k) for k in CONTEXT_KEYS}
    if overlay is None:
        corrected, edits = deepcopy(row['raw']), []
    else:
        corrected, edits = overlay.apply(row['raw'], context, effective_at=when)
    return {'observation': deepcopy(envelope), 'raw': deepcopy(row['raw']),
            'corrected': corrected, 'provenance': deepcopy(row.get('provenance', {})),
            'corrections': edits}


def project_records(records, *, as_of, overlay=None):
    """Build flat price observations and separately labeled attribute intervals.

    Inputs use the observation_dataset envelope (observation/raw/provenance).
    Knowledge requires both collection and interpretation clocks <= as_of. Every
    same-time interpretation is preserved; disagreement quarantines that interval
    instead of choosing an arbitrary parser or capture. A later reparse is not
    silently treated as a correction of an earlier interpretation.
    """
    cutoff = instant(as_of)
    if overlay is not None and overlay.as_of > cutoff:
        raise ValueError('Correction knowledge exceeds as_of')
    grouped, quarantine, inputs = defaultdict(lambda: defaultdict(list)), [], {}
    for original in records:
        row = deepcopy(original)
        env = row['observation']
        # Normalization makes caller order and timestamp spellings irrelevant.
        for key in ('collected_at', 'recorded_at'):
            value = env.get(key)
            if value is not None:
                env[key] = instant(value).isoformat()
        token = _hash(row)
        inputs[token] = row
    for token, row in sorted(inputs.items()):
        env = row['observation']
        if any(env.get(key) and instant(env[key]) > cutoff for key in ('collected_at', 'recorded_at')):
            continue
        if not env.get('collected_at') or not env.get('recorded_at'):
            quarantine.append({'reason': 'unknown_collection_or_knowledge_time', 'input_sha256': token, 'evidence': row})
            continue
        collected, recorded = instant(env['collected_at']), instant(env['recorded_at'])
        if collected > cutoff or recorded > cutoff:
            continue
        identity = _identity(env)
        if identity is None:
            quarantine.append({'reason': 'unresolved_unit_identity', 'input_sha256': token, 'evidence': row})
            continue
        grouped[identity][collected].append(row)
    intervals, observations = [], []
    for identity, by_time in sorted(grouped.items()):
        times = sorted(by_time)
        for index, start in enumerate(times):
            rows = by_time[start]
            end = times[index+1] if index+1 < len(times) else None
            points = _boundaries(rows, start, end, overlay)
            for pi, point in enumerate(points):
                until = points[pi+1] if pi+1 < len(points) else end
                projections = [_project(row, point, overlay) for row in rows]
                variants = {canonical(attributes(row['corrected'])) for row in projections}
                buildings = {row['corrected'].get('building_slug') or row['observation'].get('building_slug') for row in projections}
                base = {'unit_id': identity, 'valid_from': point.isoformat(),
                        'valid_until': until.isoformat() if until else None,
                        'known_as_of': cutoff.isoformat(), 'attribute_time_basis': TIME_BASIS,
                        'observed_at': start.isoformat(), 'evidence': projections}
                if len(variants) != 1 or len(buildings) != 1:
                    quarantine.append({**base, 'reason': 'conflicting_same_time_attributes'})
                    continue
                attr = json.loads(next(iter(variants)))
                interval = {**base, 'building_id': next(iter(buildings)), **attr}
                interval['row_id'] = _hash(interval)
                intervals.append(interval)
                # Patch-boundary splits are not new asking-price observations.
                if point != start:
                    continue
                prices = [_price(p['corrected']) for p in projections]
                statuses = {str(p['corrected'].get('status') or (p['corrected'].get('archive_listing') or {}).get('status') or '').upper() for p in projections}
                rents = {p[0] for p in prices}
                if statuses != {'ACTIVE'}:
                    reason = 'listing_not_confirmed_active'
                elif len(rents) != 1:
                    reason = 'conflicting_same_time_asking_rent'
                elif next(iter(rents)) is None or next(iter(rents)) <= 0:
                    reason = 'missing_or_invalid_contemporary_asking_rent'
                else:
                    reason = None
                if reason:
                    quarantine.append({**base, 'reason': reason})
                    continue
                obs = {k: v for k, v in interval.items() if k not in ('row_id', 'valid_from', 'valid_until', 'attribute_time_basis')}
                flags = [_rental_flags(p['corrected']) for p in projections]
                obs.update({k: True if any(f[k] is True for f in flags) else
                            False if all(f[k] is False for f in flags) else None
                            for k in flags[0]})
                obs.update(rent=next(iter(rents)), price_basis='gross_advertised_rent',
                           price_paths=sorted({p[1] for p in prices}), listing_status='ACTIVE')
                obs['row_id'] = _hash(obs)
                observations.append(obs)
    assertions = _assertions(grouped, overlay, cutoff)
    return {'intervals': intervals, 'observations': observations,
            'attribute_assertions': assertions,
            'quarantine': quarantine, 'source_sha256': _hash(sorted(inputs))}


def _rental_flags(raw):
    pricing = (raw.get('archive_listing') or {}).get('pricing') or {}
    positive = lambda key: (_number(pricing.get(key)) or 0) > 0
    term = _number(pricing.get('leaseTermMonths'))
    flags = {'furnished': True if 'FURNISHED' in _codes(raw.get('home_features')) or positive('furnishedRent') else None,
             'short_term': term < 6 if term is not None and term > 0 else None,
             'concession': True if positive('monthsFree') or positive('netEffectiveRent') else None}
    # Normalized corrections are authoritative, including explicit unknowns.
    explicit = raw.get('attributes') or {}
    for key in flags:
        if key in explicit or key in raw:
            value = explicit[key] if key in explicit else raw[key]
            flags[key] = value if isinstance(value, bool) else None
    return flags


def _assertions(grouped, overlay, cutoff):
    """Publish sparse explicit human facts, including before first collection.

    These differ from observational carry-forward intervals. Only fields named
    in a patch become assertions; no other captured values or rents are dated
    backwards. A removal asserts unknown, not a negative amenity value.
    """
    if overlay is None or not overlay.enabled:
        return []
    output = {}
    for identity, by_time in sorted(grouped.items()):
        rows = [row for at in sorted(by_time) for row in by_time[at]]
        for edit in overlay.active:
            matching = [row for row in rows if all(row['observation'].get(k) == v for k, v in edit['target'].items())]
            if not matching:
                continue
            valid = edit['validity']
            start = instant(valid['from']) if valid.get('from') else None
            end = instant(valid['until']) if valid.get('until') else None
            # Validate patches at all intersecting rule boundaries, even when
            # the asserted interval predates observations. This catches conflicts
            # that observational carry-forward alone cannot encounter.
            representative = start or (end-timedelta(microseconds=1) if end else instant(matching[0]['observation']['collected_at']))
            points = {representative}
            for other in overlay.active:
                if not any(all(row['observation'].get(k) == v for k, v in other['target'].items()) for row in matching):
                    continue
                for bound in ('from', 'until'):
                    if other['validity'].get(bound):
                        point = instant(other['validity'][bound])
                        if (start is None or point >= start) and (end is None or point < end):
                            points.add(point)
            for row in matching:
                for point in sorted(points):
                    _project(row, point, overlay)  # Fail closed on tests/conflicting writes.
            asserted_document = _project(matching[0], representative, overlay)['corrected']
            for operation in edit['patch']:
                if operation['op'] == 'test':
                    continue
                from jsonpointer import JsonPointer
                parts = JsonPointer(operation['path']).parts
                # Attributes only: historical corrected prices stay evidence in
                # the ledger, never enter this contemporary-price training table.
                if not parts or parts[0] != 'attributes':
                    continue
                writes = [(operation['path'], operation.get('value'))]
                if parts == ['attributes'] and isinstance(operation.get('value'), dict):
                    writes = [('/attributes/'+key.replace('~','~0').replace('/','~1'), value)
                              for key, value in sorted(operation['value'].items())]
                for path, value in writes:
                    from jsonpointer import JsonPointerException
                    try:
                        value = JsonPointer(path).resolve(asserted_document)
                        kind = 'value'
                    except JsonPointerException:
                        value, kind = None, 'unknown'
                    fact = {'unit_id': identity, 'path': path, 'value': deepcopy(value),
                            'assertion_kind': kind,
                            'valid_from': start.isoformat() if start else None,
                            'valid_until': end.isoformat() if end else None,
                            'known_as_of': cutoff.isoformat(), 'recorded_at': edit['recorded_at'],
                            'attribute_time_basis': 'explicit_correction_validity',
                            'correction': deepcopy(edit),
                            'source_version_ids': sorted({row['observation'].get('version_id') for row in matching if row['observation'].get('version_id')})}
                    fact['row_id'] = _hash(fact)
                    output[fact['row_id']] = fact
    return [output[key] for key in sorted(output)]


def iter_database_records(db):
    """Read the legacy capture-history database without mutating its tables."""
    cursor = db.execute('''SELECT version_id,capture_id,source,source_listing_id,
        episode_id,building_slug,unit,
        strftime(collected_at AT TIME ZONE 'UTC','%Y-%m-%dT%H:%M:%S.%fZ') collected_at,
        strftime(recorded_at AT TIME ZONE 'UTC','%Y-%m-%dT%H:%M:%S.%fZ') recorded_at,
        collection_time_basis,parser_version,structured_json,provenance_json
        FROM attribute_versions ORDER BY version_id''')
    names = [c[0] for c in cursor.description]
    while batch := cursor.fetchmany(128):
        for values in batch:
            envelope = dict(zip(names, values))
            raw = json.loads(envelope.pop('structured_json'))
            provenance = json.loads(envelope.pop('provenance_json') or '{}')
            yield {'observation': envelope, 'raw': raw, 'provenance': provenance}


def build_dataset(db, output, *, as_of, ledger=None):
    """Publish a reproducible bundle; identical reruns verify and return it.

    db accepts an open DuckDB connection, database path, or iterable of record
    envelopes. A changed input/cutoff/ledger requires a new output directory.
    A completion marker is written last; partial runs may be safely retried.
    """
    import duckdb

    overlay = Overlay(ledger, as_of=as_of) if ledger is not None else None
    owned = isinstance(db, (str, Path))
    connection = duckdb.connect(str(db), read_only=True) if owned else db
    try:
        records = iter_database_records(connection) if hasattr(connection, 'execute') else iter(connection)
        result = project_records(records, as_of=as_of, overlay=overlay)
    finally:
        if owned:
            connection.close()
    files = {f'{name}.jsonl': ''.join(canonical(row)+'\n' for row in result[name])
             for name in ('intervals', 'observations', 'attribute_assertions', 'quarantine')}
    files['corrections.jsonl'] = ''.join(canonical(row)+'\n' for row in overlay.records) if overlay else ''
    manifest = {'dataset_version': VERSION, 'known_as_of': instant(as_of).isoformat(),
                'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes() + Path(__file__).with_name('corrections.py').read_bytes()).hexdigest(),
                'source_sha256': result['source_sha256'],
                'corrections': overlay.manifest if overlay else None,
                'counts': {name: len(result[name]) for name in ('intervals', 'observations', 'attribute_assertions', 'quarantine')},
                'files': {name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()},
                'attribute_time_basis': TIME_BASIS,
                'limitations': ['Intervals carry observations forward, not verified real-world validity.',
                                'No backward attribution to historic price events.',
                                'Source page identities are not independently verified physical units.',
                                'Only explicitly ACTIVE current gross asking rents enter observations.']}
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    # Serialize concurrent publishers and leave raw source/ledger untouched.
    import fcntl
    with (root/'.build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = root/'complete.json'
        if marker.exists():
            previous = json.loads(marker.read_text())
            if previous != manifest:
                raise ValueError('Analytical run identity changed; choose a new output directory')
            for name, digest in manifest['files'].items():
                if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
                    raise ValueError(f'Completed analytical artifact failed integrity check: {name}')
            return manifest
        intent = root/'plan.json'
        if intent.exists() and json.loads(intent.read_text()) != manifest:
            raise ValueError('Partial analytical run identity changed; choose a new output directory')
        if not intent.exists() and any(p.name != '.build.lock' for p in root.iterdir()):
            raise ValueError('Output directory contains unrelated files')
        files = {'plan.json': canonical(manifest)+'\n', **files, 'complete.json': canonical(manifest)+'\n'}
        for name, content in files.items():
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=root, prefix='.partial-', delete=False) as temp:
                temp.write(content)
                temp_path = Path(temp.name)
            temp_path.replace(root/name)
    return manifest
