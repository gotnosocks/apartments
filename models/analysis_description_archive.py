"""Publish every fitted source capture's description, independent of feature wording."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import gzip
import hashlib
import json
from pathlib import Path

from apartments import granular_parse
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import interior_feature_audit as source_helpers
from .interior_feature_audit import checked_description, json_rows

VERSION = 'fitted-description-archive-v1'


def run(dataset, archive, historical, recovery, refresh, output):
    import duckdb

    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    hm, hf = _verified_bundle(historical, retain={'source-files.json'})
    rm, rf = _verified_bundle(recovery, retain={'accepted.jsonl'})
    fm, ff = _verified_bundle(Path(refresh) / 'snapshot', retain={'candidates.jsonl'})
    if dm.get('historical_manifest') != hm or dm.get('current_snapshot_manifest') != fm:
        raise ValueError('Sources do not bind the supplied fitted dataset')
    rows = json_rows(df['observations.jsonl'])
    if len({r['audit_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate analytical identities')
    inventory = json.loads(hf['source-files.json'])
    archive = Path(archive)
    paths = {}
    for table in ('listing_observations', 'snapshots'):
        paths[table] = [archive / p for p in inventory if p.startswith(table + '/') and p.endswith('.parquet')]
        if not paths[table]:
            raise ValueError('Missing source table')
        for path in paths[table]:
            if not path.resolve().is_relative_to(archive.resolve()) or digest(path) != inventory[str(path.relative_to(archive))]:
                raise ValueError('Source shard hash mismatch')
    recovered_rows = json_rows(rf['accepted.jsonl'])
    recovered = {r['snapshot_id']: r for r in recovered_rows}
    if len(recovered) != len(recovered_rows):
        raise ValueError('Duplicate recovered capture identity')
    candidates = json_rows(ff['candidates.jsonl'])
    fresh = {r['capture_id']: r for r in candidates}
    if len(fresh) != len(candidates):
        raise ValueError('Duplicate current capture identity')
    targets, current = {}, []
    for row in rows:
        if row['analysis_price_basis'] == 'current_capture_gross_ask':
            current.append(row)
        elif row['analysis_price_basis'] == 'historical_initial_own_advertisement_ask':
            if not row.get('capture_ids'):
                raise ValueError('Historical row has no source captures')
            for capture in row['capture_ids']:
                if capture in targets:
                    raise ValueError('Duplicate source capture membership')
                targets[capture] = row
        else:
            raise ValueError('Unknown price basis')
    evidence, seen, emitted = [], set(), set()

    def consume(row, capture, raw, body_hash, collected_at, rec=None):
        description, raw_hash = checked_description(raw, body_hash, rec, row)
        observed = datetime.fromtimestamp(collected_at, UTC) if isinstance(collected_at, (int, float)) else instant(collected_at)
        if observed > instant(row['known_at']):
            raise ValueError('Capture later than row knowledge clock')
        key = (row['audit_id'], capture)
        if key in emitted:
            raise ValueError('Duplicate emitted source capture')
        emitted.add(key)
        evidence.append({
            'audit_id': row['audit_id'], 'unit_id': row['unit_id'],
            'building_id': row.get('building_id', row.get('building')),
            'source_listing_id': str(row['source_listing_id']), 'canonical_unit_url': row['canonical_unit_url'],
            'capture_id': capture, 'body_sha256': body_hash, 'raw_listing_sha256': raw_hash,
            'source_collected_at': observed.isoformat(), 'known_at': row['known_at'],
            'description': description,
            'description_sha256': hashlib.sha256(description.encode()).hexdigest() if description is not None else None,
            'description_interpreted_at': rec['interpreted_at'] if rec else None,
            'source_path': '/description', 'description_source': 'verified_recovery' if rec else 'parsed_source',
            'analysis_price_basis': row['analysis_price_basis'], 'period': row['period'],
        })

    with duckdb.connect(config={'threads': '2', 'memory_limit': '1GB'}) as db:
        for table in paths:
            db.read_parquet([str(p) for p in paths[table]]).create_view(table)
        cursor = db.execute(
            'SELECT l.snapshot_id,l.listing_id,l.canonical_unit_url,l.raw_listing_json,s.body_hash,l.collected_at '
            'FROM listing_observations l JOIN snapshots s USING(snapshot_id) '
            'WHERE l.snapshot_id IN (SELECT unnest(?)) ORDER BY l.snapshot_id', [sorted(targets)])
        while batch := cursor.fetchmany(128):
            for capture, listing, url, raw, body_hash, collected_at in batch:
                row = targets[capture]
                if capture in seen or str(listing) != str(row['source_listing_id']) or url != row['canonical_unit_url']:
                    raise ValueError('Source capture identity mismatch or duplicate')
                seen.add(capture)
                consume(row, capture, raw, body_hash, collected_at, recovered.get(capture))
    if seen != set(targets):
        raise ValueError('Missing source captures')
    current_seen = set()
    for row in sorted(current, key=lambda r: r['audit_id']):
        capture = row['capture_id']
        candidate = fresh.get(capture)
        if (candidate is None or capture in current_seen
                or any(candidate.get(key) != row.get(key) for key in
                       ('unit_id', 'source_listing_id', 'canonical_unit_url', 'collected_at', 'refresh_provenance'))):
            raise ValueError('Current snapshot identity or provenance mismatch')
        current_seen.add(capture)
        provenance = row['refresh_provenance']
        sha = provenance['body_sha256']
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Invalid current body hash')
        body = gzip.decompress((Path(refresh) / 'archive/bodies' / sha[:2] / (sha + '.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha:
            raise ValueError('Current body hash mismatch')
        parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
        if str(parsed['listing_id']) != str(row['source_listing_id']) or parsed['canonical_unit_url'] != row['canonical_unit_url']:
            raise ValueError('Current capture identity mismatch')
        consume(row, capture, parsed['raw_listing_json'], sha, row['collected_at'])
    evidence.sort(key=lambda r: (r['audit_id'], str(r['capture_id'])))
    covered = {r['audit_id'] for r in evidence}
    if covered != {r['audit_id'] for r in rows}:
        raise ValueError('Description inventory does not cover the fitted cohort')
    with_text = [r for r in evidence if r['description']]
    summary = {
        'rows': len(rows), 'captures': len(evidence), 'description_captures': len(with_text),
        'no_text_captures': len(evidence) - len(with_text),
        'rows_with_description': len({r['audit_id'] for r in with_text}),
        'rows_without_description': len(rows) - len({r['audit_id'] for r in with_text}),
        'current_rows': len(current), 'current_description_captures': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in with_text),
        'policy': 'Every fitted capture is retained, including absent or unresolved description text. No selection by feature wording and no feature inference.',
    }
    code = [Path(__file__), Path(granular_parse.__file__), Path(source_helpers.__file__)]
    return publish_bundle(output, {
        'evidence.jsonl': ''.join(canonical(r) + '\n' for r in evidence),
        'summary.json': canonical(summary) + '\n', **{p.name: p.read_text() for p in code},
    }, {'version': VERSION, 'dataset_manifest': dm, 'historical_manifest': hm, 'recovery_manifest': rm,
        'refresh_manifest': fm, 'summary': summary, 'implementation_sha256': {p.name: digest(p) for p in code}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'archive', 'historical', 'recovery', 'refresh', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
