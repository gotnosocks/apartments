"""Audit a unit-label floor hypothesis against source claims; never patch floors."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re

from apartments import granular_parse
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'unit-label-floor-research-v1'
RULE = 'one-or-two-digit-positive-prefix-single-letter-v1'


def infer_label(label):
    """A deliberately testable first hypothesis, not a building numbering rule."""
    if label is None:
        return {'literal': None, 'normalized_label': None, 'candidate_floor': None,
                'status': 'missing', 'rule': RULE}
    if not isinstance(label, str):
        raise ValueError('Unit display label must be text or null')
    normalized = label.strip().removeprefix('#').strip().upper()
    match = re.fullmatch(r'([1-9][0-9]?)[A-Z]', normalized)
    return {'literal': label, 'normalized_label': normalized,
            'candidate_floor': int(match[1]) if match else None,
            'status': 'inferred_candidate' if match else 'unresolved_label', 'rule': RULE}


def summarize(records):
    byrow = defaultdict(list)
    for record in records:
        byrow[record['audit_id']].append(record)
    observations = []
    for identity, captures in sorted(byrow.items()):
        first = captures[0]
        for row in captures:
            if any(row[k] != first[k] for k in ('unit_id', 'building', 'explicit_floor')):
                raise ValueError('Conflicting analytical identities or floor references')
        values = sorted({r['candidate_floor'] for r in captures if r['candidate_floor'] is not None})
        candidate = values[0] if len(values) == 1 else None
        explicit = first['explicit_floor']
        comparison = ('not_comparable' if explicit is None or candidate is None
                      else 'agrees' if candidate == explicit else 'disagrees')
        observations.append({'audit_id': identity, 'unit_id': first['unit_id'], 'building': first['building'],
            'captures': len(captures), 'candidate_floors': values, 'candidate_floor': candidate,
            'capture_label_conflict': len(values) > 1, 'explicit_floor': explicit, 'comparison': comparison,
            'unresolved_capture_labels': sum(r['candidate_floor'] is None for r in captures)})
    comparable = [r for r in observations if r['comparison'] != 'not_comparable']
    units = defaultdict(list)
    for row in comparable:
        units[row['unit_id']].append(row)
    unit_results = Counter()
    for values in units.values():
        unit_results['any_disagreement' if any(r['comparison'] == 'disagrees' for r in values) else 'all_agree'] += 1
    return observations, {'captures': len(records), 'observations': len(observations),
        'units': len({r['unit_id'] for r in observations}),
        'capture_statuses': dict(Counter(r['status'] for r in records)),
        'candidate_observations': sum(r['candidate_floor'] is not None for r in observations),
        'candidate_units': len({r['unit_id'] for r in observations if r['candidate_floor'] is not None}),
        'candidate_buildings': len({r['building'] for r in observations if r['candidate_floor'] is not None}),
        'capture_label_conflict_observations': sum(r['capture_label_conflict'] for r in observations),
        'reference_observations': len(comparable), 'reference_units': len(units),
        'reference_comparisons': dict(Counter(r['comparison'] for r in comparable)),
        'reference_unit_comparisons': dict(unit_results)}


def run(dataset, descriptions, archive, historical, refresh, output):
    import duckdb

    dataset, descriptions, archive, historical, refresh = map(Path, (dataset, descriptions, archive, historical, refresh))
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    em, ef = _verified_bundle(descriptions, retain={'evidence.jsonl'})
    hm, hf = _verified_bundle(historical, retain={'source-files.json'})
    if em.get('historical_manifest') != hm:
        raise ValueError('Description archive and historical source differ')
    source_rows = list(map(json.loads, df['observations.jsonl'].decode().splitlines()))
    rows = {r['audit_id']: r for r in source_rows}
    if len(rows) != len(source_rows):
        raise ValueError('Duplicate analytical observation')
    evidence = [e for e in map(json.loads, ef['evidence.jsonl'].decode().splitlines()) if e['audit_id'] in rows]
    if {e['audit_id'] for e in evidence} != rows.keys():
        raise ValueError('Description inventory does not cover source cohort')
    expected = {(r['audit_id'], c) for r in source_rows
                for c in (r['capture_ids'] if r['analysis_price_basis'] == 'historical_initial_own_advertisement_ask'
                          else [r['capture_id']])}
    actual = {(e['audit_id'], e['capture_id']) for e in evidence}
    if actual != expected or len(actual) != len(evidence):
        raise ValueError('Source capture membership differs')
    history = {e['capture_id']: e for e in evidence if e['analysis_price_basis'] == 'historical_initial_own_advertisement_ask'}
    current = [e for e in evidence if e['analysis_price_basis'] == 'current_capture_gross_ask']
    if len(history) + len(current) != len(evidence):
        raise ValueError('Duplicate capture or unknown price basis')
    records = []

    def consume(e, raw):
        if hashlib.sha256(raw.encode()).hexdigest() != e['raw_listing_sha256']:
            raise ValueError('Raw listing differs from verified capture')
        payload = json.loads(raw); row = rows[e['audit_id']]
        if str(payload['id']) != str(row['source_listing_id']) or row['unit_id'] != e['unit_id']:
            raise ValueError('Source listing or unit identity differs')
        label = (payload.get('propertyDetails', {}).get('address') or {}).get('displayUnit')
        explicit = row.get('listed_floor')
        if explicit is None:
            explicit = row.get('advertised_floor')
        records.append({**{k: e[k] for k in ('audit_id', 'capture_id', 'source_listing_id', 'body_sha256', 'raw_listing_sha256')},
            'unit_id': row['unit_id'], 'building': row['building'], 'explicit_floor': explicit,
            'source_path': '/propertyDetails/address/displayUnit', **infer_label(label)})

    inventory = json.loads(hf['source-files.json'])
    paths = [archive / p for p in inventory if p.startswith('listing_observations/') and p.endswith('.parquet')]
    seen = set()
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        for path in sorted(paths):
            if not path.resolve().is_relative_to(archive.resolve()) or digest(path) != inventory[str(path.relative_to(archive))]:
                raise ValueError('Historical shard differs from bound source')
            cursor = db.execute('SELECT snapshot_id,raw_listing_json FROM read_parquet(?)', [str(path)])
            while batch := cursor.fetchmany(64):
                for capture, raw in batch:
                    if capture not in history:
                        continue
                    if capture in seen:
                        raise ValueError('Duplicate historical capture')
                    seen.add(capture); consume(history[capture], raw)
    if seen != history.keys():
        raise ValueError('Missing historical capture')
    for e in current:
        row = rows[e['audit_id']]; provenance = row['refresh_provenance']; sha = provenance['body_sha256']
        if not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Invalid raw-body hash')
        body = gzip.decompress((refresh / 'archive/bodies' / sha[:2] / (sha + '.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha or e['body_sha256'] != sha:
            raise ValueError('Current body differs from source')
        parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
        consume(e, parsed['raw_listing_json'])
    observations, summary = summarize(records)
    summary.update(version=VERSION, rule=RULE, source_manifest_sha256=digest(dataset / 'complete.json'),
        descriptions_manifest_sha256=digest(descriptions / 'complete.json'), historical_manifest_sha256=digest(historical / 'complete.json'),
        limitations=['Prefix candidates are inferred floor labels, never measured height or verified building numbering.',
            'Existing explicit floor references are sparse, selected source claims, not independent ground truth; agreement is not corpus accuracy.',
            'Numeric-only, leading-zero, letter-prefix, compound and penthouse labels remain unresolved under this first rule.',
            'No analytical values, source claims, model inputs or physical change dates are altered.'])
    return publish_bundle(output, {'summary.json': canonical(summary) + '\n',
        'captures.jsonl': ''.join(canonical(r) + '\n' for r in sorted(records, key=lambda x: (x['audit_id'], str(x['capture_id'])))),
        'observations.jsonl': ''.join(canonical(r) + '\n' for r in observations),
        'disagreements.jsonl': ''.join(canonical(r) + '\n' for r in observations if r['comparison'] == 'disagrees'),
        Path(__file__).name: Path(__file__).read_text(), 'granular_parse.py': Path(granular_parse.__file__).read_text()},
        {'version': VERSION, 'summary': summary})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'descriptions', 'archive', 'historical', 'refresh', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(canonical(run(**vars(args))['summary']))
