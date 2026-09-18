"""Reconstruct initial asking rents using attributes of the same advertisement.

This is explicitly retrospective evidence, not a claim that attributes captured
in 2026 were known in 2015. No other advertisement's attributes are backfilled.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
from itertools import groupby
import json
import math
from pathlib import Path
import re

from . import analytical, corrections, research_pipeline
from .corrections import Overlay, canonical, instant

VERSION = 'historical-own-advertisement-v1'
TIME_BASIS = 'retrospective_own_advertisement_initial_active_event'
LIMITATIONS = [
    'Attributes are retrospectively reconstructed from captures of the same advertisement, not contemporaneously verified at its initial ACTIVE event.',
    'Historical holdouts measure reconstruction generalization, not real-time forecasting with historically available information.',
    'Canonical URLs establish source unit identity, not independently verified physical apartment identity.',
    'Collection reflects archive discovery and survival; coverage is not a random sample of Chelsea or NYC rentals.',
    'Targets gross initial advertised asking rent, not signed leases or verified transaction prices.',
]


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _time(value):
    return datetime.fromtimestamp(value, UTC).isoformat() if isinstance(value, (float, int)) else instant(value).isoformat()


def _unique(values):
    return [json.loads(s) for s in sorted({canonical(v) for v in values if v is not None})]


def _description_furnished(description):
    """Positive own-advertisement phrases; do not match 'unfurnished'."""
    pattern = r'\b(?:blueground|fully[ -]furnished|comes furnished|furnished apartment)\b'
    for match in re.finditer(pattern, description.lower()):
        prefix = description[max(0, match.start() - 32):match.start()].lower()
        if not re.search(r"\b(?:not|no|never|isn't|aren't)\s+(?:(?:a|an|any)\s+)?$", prefix):
            return True
    return False


def _extract(raw):
    # Kept separate so evidence extraction can evolve without changing the clock contract.
    from .attribute_evidence import extract_attribute_evidence
    return extract_attribute_evidence(raw)


def _load_recoveries(directory, db, source_files, root):
    """Verify parser interpretations against independently read source identities."""
    manifest, data = research_pipeline._verified_bundle(directory, retain={'accepted.jsonl', 'source-files.json'})
    if manifest.get('recovery_version') != 'description-recovery-v1':
        raise ValueError('Unsupported description recovery version')
    if set(data) != {'accepted.jsonl', 'source-files.json'}:
        raise ValueError('Recovery bundle is missing verified source inventory or accepted records')
    inventory = json.loads(data['source-files.json'])
    inventory_hash = hashlib.sha256(json.dumps(inventory, sort_keys=True, ensure_ascii=False,
                                                 separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if manifest.get('source_manifest_sha256') != inventory_hash:
        raise ValueError('Recovery source inventory hash mismatch')
    for name, expected in inventory.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or (root / path).resolve().is_relative_to(root.resolve()) is False:
            raise ValueError('Invalid recovery source inventory path')
        if research_pipeline.digest(root / path) != expected:
            raise ValueError(f'Recovery source mismatch: {name}')
    # The body-hash evidence must cover the exact independently consumed snapshot shards.
    for name, expected in source_files.items():
        if name == 'complete.json' or name.startswith(('snapshots/', 'listing_observations/')):
            if inventory.get(name) != expected:
                raise ValueError(f'Recovery source inventory omits or mismatches {name}')
    recoveries = {}
    required = {'snapshot_id', 'listing_id', 'source_body_sha256', 'original_raw_listing_sha256',
                'original_description_reference', 'resolved_description', 'description_sha256',
                'interpreted_at', 'parser_version', 'recovery_version'}
    for line in data['accepted.jsonl'].decode().split('\n'):
        if not line.strip():
            continue
        record = json.loads(line)
        if not required <= record.keys() or not isinstance(record['snapshot_id'], int) or isinstance(record['snapshot_id'], bool):
            raise ValueError('Malformed description recovery record')
        if record['snapshot_id'] in recoveries:
            raise ValueError('Duplicate description recovery snapshot')
        if record['parser_version'] != manifest.get('parser_version') or record['recovery_version'] != manifest.get('recovery_version'):
            raise ValueError('Recovery parser version mismatch')
        if not isinstance(record['original_description_reference'], str) or not re.fullmatch(r'\$[A-Za-z0-9]+', record['original_description_reference']):
            raise ValueError('Recovery must resolve an original description reference')
        if not isinstance(record['resolved_description'], str) or not record['resolved_description'].strip():
            raise ValueError('Recovered description must be nonempty text')
        if hashlib.sha256(record['resolved_description'].encode()).hexdigest() != record['description_sha256']:
            raise ValueError('Recovered description hash mismatch')
        instant(record['interpreted_at'])
        recoveries[record['snapshot_id']] = record
    if manifest.get('coverage', {}).get('accepted') != len(recoveries):
        raise ValueError('Recovery accepted record count mismatch')
    db.execute('CREATE TEMP TABLE recovery_ids(snapshot_id BIGINT)')
    if recoveries:
        db.executemany('INSERT INTO recovery_ids VALUES (?)', [(sid,) for sid in sorted(recoveries)])
    cursor = db.execute("""SELECT l.snapshot_id,l.listing_id,l.raw_listing_json,l.canonical_unit_url,
                          s.body_hash,s.url,s.observed_at
                          FROM listing_observations l JOIN snapshots s USING(snapshot_id)
                          JOIN recovery_ids r USING(snapshot_id)""")
    seen = set()
    while batch := cursor.fetchmany(128):
        for sid, listing, raw, unit_url, body, url, observed in batch:
            record = recoveries[sid]
            if sid in seen:
                raise ValueError('Recovery source snapshot is ambiguous')
            seen.add(sid)
            if str(listing) != str(record['listing_id']) or body != record['source_body_sha256']:
                raise ValueError('Recovery source body or listing identity mismatch')
            if hashlib.sha256(raw.encode()).hexdigest() != record['original_raw_listing_sha256']:
                raise ValueError('Recovery original listing hash mismatch')
            original = json.loads(raw)
            if str(original.get('id')) != str(listing):
                raise ValueError('Recovery raw listing identity mismatch')
            if original.get('description') != record['original_description_reference']:
                raise ValueError('Recovery original description reference mismatch')
            if 'canonical_unit_url' in record and record['canonical_unit_url'] != unit_url:
                raise ValueError('Recovery canonical URL mismatch')
            if 'source_url' in record and record['source_url'] != url:
                raise ValueError('Recovery source URL mismatch')
            if 'source_observed_at' in record and instant(_time(record['source_observed_at'])) != instant(_time(observed)):
                raise ValueError('Recovery source observation clock mismatch')
            if instant(record['interpreted_at']) < instant(_time(observed)):
                raise ValueError('Recovery interpretation precedes source observation')
    if seen != recoveries.keys():
        raise ValueError('Recovery references a missing source snapshot')
    return manifest, recoveries


def project_advertisement(captures, memberships, events, *, as_of, overlay=None,
                          start='2010-01-01', end=None, description_recoveries=None):
    """Return one accepted row or explicit exclusion, plus normalized raw audit.

    Selectors are immutable source fields. Patches apply to a normalized raw
    document at the initial event date, never at collection time. Both the raw
    candidate rent and patched value survive in the separate audit record.
    """
    cutoff = instant(as_of)
    captures = sorted((c for c in captures if instant(_time(c['collected_at'])) <= cutoff
                       and instant(_time(c['parsed_at'])) <= cutoff), key=lambda c: c['snapshot_id'])
    if not captures:
        return None, {'reasons': ['no_evidence_at_knowledge_cutoff']}
    listing_id = str(captures[0]['listing_id'])
    audit = {'source_listing_id': listing_id, 'source_capture_ids': [c['snapshot_id'] for c in captures],
             'captures': [], 'reasons': []}
    identities = {(m.get('unit_id'), m.get('canonical_unit_url')) for m in memberships
                  if m.get('status') == 'associated' and m.get('rule') == 'canonical-url-v1'}
    if len(identities) != 1 or any(not all(pair) for pair in identities):
        audit['reasons'].append('unresolved_or_conflicting_identity')
    identity = next(iter(identities)) if len(identities) == 1 else (None, None)
    unit_id, url = identity
    match = re.fullmatch(r'https://streeteasy\.com/building/([^/]+)/([^/?#]+)', url or '')
    if not match or any(c.get('canonical_unit_url') != url for c in captures):
        audit['reasons'].append('unresolved_or_conflicting_canonical_url')
    snapshot_ids = {c['snapshot_id'] for c in captures}
    own = [e for e in events if e['snapshot_id'] in snapshot_ids
           and str(e.get('event_listing_id')) == listing_id
           and e.get('event_category') == 'rental' and e.get('status') == 'ACTIVE']
    dated = []
    for event in own:
        try:
            when = instant(event['event_date'])
        except (ValueError, TypeError):
            audit['reasons'].append('invalid_own_active_event_date')
            continue
        if when > cutoff:
            audit['reasons'].append('future_own_active_event')
        dated.append((when, event))
    if not dated:
        audit['reasons'].append('no_dated_own_active_event')
        return None, audit
    when = min(t for t, _ in dated)
    initial = [e for t, e in dated if t == when]
    prices = [json.loads(s) for s in sorted({canonical(e.get('price')) for e in initial})]
    audit.update(price_at=when.isoformat(), initial_events=initial)
    if when < instant(start) or (end is not None and when >= instant(end) + timedelta(days=1)):
        audit['reasons'].append('outside_date_window')
    projections, clocks, interpretation_times = [], [], []
    for capture in captures:
        original = json.loads(capture.get('raw_listing_json') or '{}')
        interpreted = deepcopy(original)
        recovery = (description_recoveries or {}).get(capture['snapshot_id'])
        visible_recovery = recovery if recovery and instant(recovery['interpreted_at']) <= cutoff else None
        if visible_recovery:
            interpreted['description'] = visible_recovery['resolved_description']
            clocks.append(visible_recovery['interpreted_at'])
            interpretation_times.append(visible_recovery['interpreted_at'])
        original_evidence = _extract(original)
        evidence = _extract(interpreted) if visible_recovery else original_evidence
        attrs = {key: capture.get(key) for key in ('bedrooms', 'bathrooms', 'square_feet')}
        attrs.update({k: v for k, v in evidence['attributes'].items() if v is not None and k not in attrs})
        conflicts = evidence.get('conflicts', {})
        # Conflicting optional attributes are unknown, with full evidence in audit.
        for key in conflicts:
            attrs[key] = None
        raw = {'source': 'streeteasy', 'source_listing_id': listing_id,
               'canonical_url': capture.get('canonical_unit_url'),
               'captured_at': _time(capture['collected_at']),
               'attributes': attrs,
               'home_features': json.loads(capture.get('features_json') or '[]'),
               'building_amenities': json.loads(capture.get('amenities_json') or '[]'),
               'archive_listing': interpreted}
        context = {'source': 'streeteasy', 'source_listing_id': listing_id,
                   'episode_id': listing_id, 'capture_id': str(capture['snapshot_id']),
                   'version_id': str(capture['snapshot_id']),
                   'building_slug': capture.get('building_slug') or '',
                   'unit': capture.get('unit_label') or ''}
        captured_audit = {'snapshot_id': capture['snapshot_id'], 'selectors': context,
                          'collected_at': _time(capture['collected_at']),
                          'parsed_at': _time(capture['parsed_at']),
                          'source_created_at': capture.get('source_created_at'),
                          'source_updated_at': capture.get('source_updated_at'),
                          'raw_listing_sha256': hashlib.sha256((capture.get('raw_listing_json') or '{}').encode()).hexdigest(),
                          'raw_values': {k: deepcopy(v) for k, v in raw.items() if k != 'archive_listing'},
                          'parser_interpretation': deepcopy(visible_recovery),
                          'attribute_evidence': evidence, 'projections': []}
        if visible_recovery:
            captured_audit['original_description'] = original.get('description')
            captured_audit['original_attribute_evidence'] = original_evidence
            # Preserve original normalized values separately from interpreted attributes.
            original_attrs = {key: capture.get(key) for key in ('bedrooms', 'bathrooms', 'square_feet')}
            original_attrs.update({k: v for k, v in original_evidence['attributes'].items() if v is not None and k not in original_attrs})
            for key in original_evidence.get('conflicts', {}):
                original_attrs[key] = None
            captured_audit['raw_values']['attributes'] = original_attrs
            captured_audit['interpreted_attributes'] = deepcopy(attrs)
        clocks.extend([_time(capture['collected_at']), _time(capture['parsed_at'])])
        for price in prices:
            candidate = {**raw, 'asking_rent': price}
            corrected, applied = overlay.apply(candidate, context, effective_at=when) if overlay else (candidate, [])
            attributes = analytical.attributes(corrected)
            # Description is evidence only within this advertisement, never another episode.
            flags = analytical._rental_flags(corrected)
            description = str((corrected.get('archive_listing') or {}).get('description') or '').lower()
            if flags['furnished'] is None and _description_furnished(description):
                flags['furnished'] = True
            projection = {**attributes, **flags, 'rent': corrected.get('asking_rent')}
            projections.append(projection)
            captured_audit['projections'].append({'raw_initial_ask': price, 'corrected_values': projection, 'corrections': applied})
            clocks.extend(e['recorded_at'] for e in applied)
        audit['captures'].append(captured_audit)
    merged, conflicts = {}, {}
    for key in projections[0]:
        values = _unique(p[key] for p in projections)
        if len(values) > 1:
            conflicts[key] = values
        merged[key] = values[0] if len(values) == 1 else None
    audit['conflicting_values'] = conflicts
    if 'rent' in conflicts or any(p['rent'] is None for p in projections):
        audit['reasons'].append('conflicting_or_missing_initial_prices')
    if any(key in conflicts for key in ('bedrooms', 'bathrooms', 'square_feet')):
        audit['reasons'].append('conflicting_layout_within_advertisement')
    for key in ('furnished', 'short_term', 'concession'):
        merged[key] = True if any(p[key] is True for p in projections) else merged[key]
        if merged[key] is True:
            audit['reasons'].append('excluded_' + key)
    rent, beds, baths = (merged[k] for k in ('rent', 'bedrooms', 'bathrooms'))
    valid_number = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    if not valid_number(rent) or not 750 <= rent <= 50000:
        audit['reasons'].append('invalid_or_extreme_initial_ask')
    if not valid_number(beds) or not 0 <= beds <= 5 or beds % 1 or not valid_number(baths) or not 1 <= baths <= 5 or (baths * 2) % 1:
        audit['reasons'].append('invalid_or_missing_layout')
    sqft = merged.get('square_feet')
    if sqft is not None and (not valid_number(sqft) or not 150 <= sqft <= 6000):
        merged['square_feet'] = None
        audit['square_feet_invalid'] = True
    audit['reasons'] = sorted(set(audit['reasons']))
    if audit['reasons']:
        return None, audit
    row = {**merged, 'unit_id': unit_id, 'building_id': match[1],
           'canonical_unit_url': url, 'source': 'streeteasy',
           'source_listing_id': listing_id, 'price_at': when.isoformat(),
           'observed_at': when.isoformat(), 'time_basis': TIME_BASIS,
           'collected_at': max(_time(c['collected_at']) for c in captures),
           'known_at': max(clocks, key=instant), 'capture_ids': sorted(snapshot_ids),
           'description_interpreted_at': max(interpretation_times, key=instant) if interpretation_times else None,
           'attribute_assumption': 'retrospective_same_advertisement',
           'audit_id': _hash(audit)}
    audit['audit_id'] = row['audit_id']
    return row, audit


def build_historical_dataset(dataset, output, *, as_of, ledger=None,
                             start='2010-01-01', end=None, description_recovery=None):
    """Hash every consumed shard, reconstruct rows, and atomically publish a bundle."""
    import duckdb
    root = Path(dataset)
    complete = json.loads((root / 'complete.json').read_text())
    if complete.get('unit_association_rule') != 'canonical-url-v1':
        raise ValueError('A completed canonical-url-v1 transform is required')
    cutoff = instant(as_of)
    if not isinstance(complete.get('finished_at'), (int, float)) or isinstance(complete.get('finished_at'), bool):
        raise ValueError('Source completion timestamp is required for canonical membership knowledge')
    identity_known_at = _time(complete['finished_at'])
    if cutoff < instant(identity_known_at):
        raise ValueError('Knowledge cutoff predates source canonical membership completion')
    from . import attribute_evidence
    code_paths = {'historical_dataset': __file__, 'analytical': analytical.__file__,
                  'corrections': corrections.__file__, 'research_pipeline': research_pipeline.__file__,
                  'attribute_evidence': attribute_evidence.__file__}
    implementation = {name: research_pipeline.digest(path) for name, path in code_paths.items()}
    overlay = Overlay(ledger, as_of=as_of) if ledger is not None else None
    names = ('listing_observations', 'rental_unit_memberships', 'event_mentions')
    if description_recovery is not None:
        names += ('snapshots',)
    source_files = {'complete.json': research_pipeline.digest(root / 'complete.json')}
    canonical_metadata = None
    if (root / 'canonical-units.json').exists():
        source_files['canonical-units.json'] = research_pipeline.digest(root / 'canonical-units.json')
        canonical_metadata = json.loads((root / 'canonical-units.json').read_text())
    shards = {}
    for name in names:
        shards[name] = sorted((root / name).glob('*.parquet'))
        if not shards[name]:
            raise ValueError(f'Missing source shards: {name}')
        for path in shards[name]:
            source_files[str(path.relative_to(root))] = research_pipeline.digest(path)
    db = duckdb.connect(config={'memory_limit': '1GB', 'threads': '2'})
    rows, audits = [], []
    try:
        for name in names:
            db.read_parquet([str(p) for p in shards[name]]).create_view(name)
        for name in names:
            expected = complete.get('counts', {}).get(name)
            actual = db.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
            if not isinstance(expected, int) or isinstance(expected, bool) or actual != expected:
                raise ValueError(f'Source row count mismatch for {name}: expected {expected}, actual {actual}')
        if canonical_metadata is not None:
            expected = canonical_metadata.get('output_sha256', {}).get('rental_unit_memberships')
            if not expected or len(shards['rental_unit_memberships']) != 1 or research_pipeline.digest(shards['rental_unit_memberships'][0]) != expected:
                raise ValueError('Canonical membership artifact digest mismatch')
            if canonical_metadata.get('counts', {}).get('rental_unit_memberships') != complete['counts']['rental_unit_memberships']:
                raise ValueError('Canonical membership row count mismatch')
        recovery_manifest, recoveries = _load_recoveries(description_recovery, db, source_files, root) if description_recovery is not None else (None, {})
        db.execute('CREATE TEMP TABLE captures AS SELECT * FROM listing_observations WHERE listing_type=\'rental\' AND collected_at <= ? AND parsed_at <= ?', [cutoff.timestamp(), cutoff.timestamp()])
        memberships = defaultdict(list)
        result = db.execute('SELECT * FROM rental_unit_memberships ORDER BY listing_id')
        keys = [d[0] for d in result.description]
        for values in result.fetchall():
            record = dict(zip(keys, values))
            memberships[str(record['listing_id'])].append(record)
        events = defaultdict(list)
        result = db.execute('''SELECT DISTINCT e.* FROM event_mentions e JOIN captures l USING(snapshot_id)
            WHERE e.event_listing_id=l.listing_id AND e.event_category='rental' AND e.status='ACTIVE'
            ORDER BY e.event_listing_id,e.event_date,e.snapshot_id,e.event_index''')
        keys = [d[0] for d in result.description]
        for values in result.fetchall():
            record = dict(zip(keys, values))
            # JSON contains redundant original event values; the source shards are retained by hash.
            record.pop('event_json', None)
            events[str(record['event_listing_id'])].append(record)
        result = db.execute('SELECT * FROM captures ORDER BY listing_id,snapshot_id')
        keys = [d[0] for d in result.description]
        def records():
            while batch := result.fetchmany(250):
                yield from (dict(zip(keys, values)) for values in batch)
        for listing, group in groupby(records(), key=lambda c: str(c['listing_id'])):
            row, audit = project_advertisement(list(group), memberships[listing], events[listing],
                                              as_of=as_of, overlay=overlay, start=start, end=end,
                                              description_recoveries=recoveries)
            audits.append(audit)
            if row:
                row['identity_known_at'] = identity_known_at
                row['known_at'] = max(row['known_at'], identity_known_at, key=instant)
                rows.append(row)
    finally:
        db.close()
    # Do not arbitrate inconsistent layouts across advertisements of one unit/month.
    groups = defaultdict(list)
    for row in rows:
        groups[(row['unit_id'], row['price_at'][:7])].append(row)
    conflicts = {key for key, group in groups.items() if len({(r['bedrooms'], r['bathrooms']) for r in group}) > 1}
    rejected = {r['source_listing_id'] for key in conflicts for r in groups[key]}
    for audit in audits:
        if audit['source_listing_id'] in rejected:
            audit['reasons'].append('conflicting_layout_same_unit_month')
    rows = sorted((r for r in rows if r['source_listing_id'] not in rejected), key=lambda r: (r['price_at'], r['unit_id'], r['source_listing_id']))
    # Detect changed inputs during a build rather than publish hashes of different bytes.
    if any(research_pipeline.digest(root / name) != digest for name, digest in source_files.items()):
        raise ValueError('Source dataset changed during build')
    report = {'advertisements': len(audits), 'accepted': len(rows),
              'description_recovery_available': len(recoveries),
              'description_recovery_at_cutoff': sum(instant(r['interpreted_at']) <= cutoff for r in recoveries.values()),
              'description_recovery_captures_used': sum(c.get('parser_interpretation') is not None for a in audits for c in a['captures']),
              'accepted_rows_with_description_recovery': sum(r['description_interpreted_at'] is not None for r in rows),
              'excluded': sum(bool(a['reasons']) for a in audits),
              'exclusion_reasons': dict(sorted(Counter(r for a in audits for r in a['reasons']).items())),
              'units': len({r['unit_id'] for r in rows}), 'buildings': len({r['building_id'] for r in rows}),
              'earliest_price_at': min((r['price_at'] for r in rows), default=None),
              'latest_price_at': max((r['price_at'] for r in rows), default=None)}
    if any(research_pipeline.digest(path) != implementation[name] for name, path in code_paths.items()):
        raise ValueError('Implementation changed during build')
    return research_pipeline.publish_bundle(output, {
        'observations.jsonl': ''.join(canonical(r) + '\n' for r in rows),
        'audit.jsonl': ''.join(canonical(a) + '\n' for a in audits),
        'coverage.json': canonical(report) + '\n',
        'source-files.json': canonical(source_files) + '\n',
    }, {'dataset_version': VERSION, 'time_basis': TIME_BASIS,
        'clock_contract': {'observed_at': 'alias of price_at, not collection/knowledge time',
                           'price_at': 'earliest own-advertisement ACTIVE rental event',
                           'collected_at': 'latest contributing capture',
                           'identity_known_at': 'completion timestamp of canonical source membership transform',
                           'description_interpreted_at': 'latest contributing verified archived-description interpretation',
                           'known_at': 'latest contributing collection, parse, description interpretation, correction, or identity derivation time'},
        'as_of': cutoff.isoformat(), 'start': start, 'end': end,
        'overlay': overlay.manifest if overlay else None,
        'description_recovery': recovery_manifest,
        'source_manifest_sha256': _hash(source_files), 'implementation_sha256': implementation,
        'coverage': report, 'limitations': LIMITATIONS})
