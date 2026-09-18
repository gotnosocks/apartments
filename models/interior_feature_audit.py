"""Screen same-advertisement text for interior evidence across a fitted cohort.

This publishes review candidates, not new model features or physical assertions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re

from apartments import granular_parse, interior_evidence
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'cohort-interior-evidence-screen-v1'


def json_rows(data):
    # Literal Unicode paragraph/line separators can occur inside JSON strings.
    return [json.loads(line) for line in data.decode().split('\n') if line.strip()]


def checked_description(raw, body_hash, recovery, row):
    raw_hash = hashlib.sha256(raw.encode()).hexdigest()
    payload = json.loads(raw)
    if recovery:
        if (recovery['original_raw_listing_sha256'] != raw_hash
                or recovery['source_body_sha256'] != body_hash
                or str(recovery['listing_id']) != str(row['source_listing_id'])
                or recovery['canonical_unit_url'] != row['canonical_unit_url']
                or instant(recovery['interpreted_at']) > instant(row['known_at'])):
            raise ValueError('Recovered description identity, source or clock mismatch')
        payload['description'] = recovery['resolved_description']
    value = payload.get('description')
    # Unresolved React references are not description text.
    description = value if isinstance(value, str) and not re.fullmatch(r'\$L?[0-9a-fA-F]+', value) else None
    return description, raw_hash


def run(dataset, archive, historical, recovery, refresh, residuals, output):
    import duckdb
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    hm, hf = _verified_bundle(historical, retain={'source-files.json'})
    rm, rf = _verified_bundle(recovery, retain={'accepted.jsonl'})
    fm, _ = _verified_bundle(Path(refresh) / 'snapshot')
    residual_manifest, residual_files = _verified_bundle(residuals, retain={'review-queue.jsonl'})
    if (dm.get('historical_manifest') != hm or dm.get('current_snapshot_manifest') != fm
            or residual_manifest.get('dataset_manifest') != dm):
        raise ValueError('Source and residual bundles must bind the supplied cohort')
    rows = json_rows(df['observations.jsonl'])
    by_id = {r['audit_id']: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError('Duplicate analytical identity')
    queue = {r['audit_id']: r for r in json_rows(residual_files['review-queue.jsonl'])}
    if not queue.keys() <= by_id.keys():
        raise ValueError('Residual queue contains unknown analytical identities')
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
    recovered = {r['snapshot_id']: r for r in json_rows(rf['accepted.jsonl'])}
    targets = {}
    current = []
    for row in rows:
        if row['analysis_price_basis'] == 'current_capture_gross_ask':
            current.append(row)
        elif row['analysis_price_basis'] == 'historical_initial_own_advertisement_ask':
            for capture in row['capture_ids']:
                if capture in targets:
                    raise ValueError('Duplicate source capture membership')
                targets[capture] = row
        else:
            raise ValueError('Unsupported target basis')
    evidence = []
    counts = Counter()
    covered = set()
    seen = set()

    def consume(row, capture, raw, body_hash, collected_at, rec=None):
        description, raw_hash = checked_description(raw, body_hash, rec, row)
        counts['captures'] += 1
        if description:
            counts['text_captures'] += 1
            covered.add(row['audit_id'])
        if rec:
            counts['recovered_text_captures'] += 1
        findings = interior_evidence.screen(description)
        if findings:
            evidence.append({'audit_id': row['audit_id'], 'source_listing_id': str(row['source_listing_id']),
                'unit_id': row['unit_id'], 'building_id': row['building'],
                'canonical_unit_url': row['canonical_unit_url'], 'capture_id': capture,
                'source_collected_at': collected_at,
                'body_sha256': body_hash, 'raw_listing_sha256': raw_hash,
                'description_sha256': hashlib.sha256(description.encode()).hexdigest(),
                'description_interpreted_at': rec['interpreted_at'] if rec else None,
                'analysis_price_basis': row['analysis_price_basis'], 'period': row['period'],
                'known_at': row['known_at'], 'description': description, 'findings': findings,
                'status': 'unreviewed_candidate_not_model_feature'})

    with duckdb.connect(config={'threads': '2', 'memory_limit': '1GB'}) as db:
        for table in paths:
            db.read_parquet([str(p) for p in paths[table]]).create_view(table)
        cursor = db.execute('SELECT l.snapshot_id,l.listing_id,l.canonical_unit_url,l.raw_listing_json,s.body_hash,l.collected_at '
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
    for row in sorted(current, key=lambda r: r['audit_id']):
        provenance = row['refresh_provenance']
        sha = provenance['body_sha256']
        body = gzip.decompress((Path(refresh) / 'archive/bodies' / sha[:2] / (sha + '.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha:
            raise ValueError('Current body hash mismatch')
        parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
        if str(parsed['listing_id']) != str(row['source_listing_id']) or parsed['canonical_unit_url'] != row['canonical_unit_url']:
            raise ValueError('Current source identity mismatch')
        consume(row, row['capture_id'], parsed['raw_listing_json'], sha, row['collected_at'])
    evidence.sort(key=lambda r: (r['audit_id'], str(r['capture_id'])))
    features = defaultdict(set)
    flags = defaultdict(set)
    for item in evidence:
        for finding in item['findings']:
            features[finding['feature']].add(item['audit_id'])
            for flag in finding['flags']:
                flags[flag].add(item['audit_id'])
    support = {}
    for feature, ids in sorted(features.items()):
        support[feature] = {'candidate_rows': len(ids),
            'units': len({by_id[i]['unit_id'] for i in ids}),
            'buildings': len({by_id[i]['building'] for i in ids}),
            'residual_queue_rows': len(ids & queue.keys()),
            'current_rows': sum(by_id[i]['analysis_price_basis'] == 'current_capture_gross_ask' for i in ids)}
    queue_evidence = []
    for key, row in sorted(queue.items()):
        captures = [e for e in evidence if e['audit_id'] == key]
        queue_evidence.append({k: row[k] for k in ('audit_id', 'source_listing_id', 'asking_rent', 'fitted_rent',
                               'asking_vs_fitted_percent', 'selection_reasons', 'current_capture')} |
                              {'candidate_features': sorted({f['feature'] for e in captures for f in e['findings']}),
                               'evidence_capture_ids': [e['capture_id'] for e in captures],
                               'has_description': key in covered})
    report = {'version': VERSION, 'cohort_rows': len(rows), 'rows_with_description': len(covered),
        'capture_counts': dict(counts), 'candidate_captures': len(evidence),
        'candidate_rows': len({e['audit_id'] for e in evidence}), 'feature_support': support,
        'advisory_flag_rows': {k: len(v) for k, v in sorted(flags.items())},
        'policy': 'Text screen candidates only. Unmentioned is unknown; no automatic physical attributes, model terms, price corrections or backward filling.',
        'historical_scope': 'Same-advertisement descriptions may have been collected after the price event; capture binding does not establish historical feature validity.'}
    lines = ['# Interior evidence screening', '',
             f"Screened {len(rows):,} fitted rows; {len(covered):,} have resolved description text.", '',
             '| Text candidate | Rows | Units | Buildings | Residual queue | Current |',
             '|---|---:|---:|---:|---:|---:|']
    for feature, values in support.items():
        lines.append('| ' + feature + ' | ' + ' | '.join(str(v) for v in values.values()) + ' |')
    lines += ['', report['policy'], '', report['historical_scope'], '',
              'Counts describe candidate wording, not verified physical feature prevalence. Repeated captures count once per analytical row in this table. Exact text, offsets, source hashes and ambiguity flags are retained in evidence.jsonl.']
    return publish_bundle(output, {'evidence.jsonl': ''.join(canonical(r) + '\n' for r in evidence),
        'residual-queue-evidence.jsonl': ''.join(canonical(r) + '\n' for r in queue_evidence),
        'report.json': canonical(report) + '\n', 'report.md': '\n'.join(lines) + '\n',
        'screen.py': Path(interior_evidence.__file__).read_text(), 'audit.py': Path(__file__).read_text()},
        {'version': VERSION, 'dataset_manifest': dm, 'historical_manifest': hm, 'recovery_manifest': rm,
         'refresh_manifest': fm, 'residual_manifest': residual_manifest, 'report': report,
         'implementation_sha256': {p.name: digest(p) for p in (Path(__file__), Path(interior_evidence.__file__), Path(granular_parse.__file__))}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('dataset', 'archive', 'historical', 'recovery', 'refresh', 'residuals', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    print(canonical(run(**vars(args))['report']))
