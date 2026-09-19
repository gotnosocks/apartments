"""Reconcile laundry phrase candidates with the same capture's structured claims.

This is a source review, not an attribute correction or a new laundry encoder.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re

from apartments import attribute_evidence, bayesian_evidence, granular_parse
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'laundry-capture-source-audit-v1'


def records(data):
    return [json.loads(line) for line in data.decode().split('\n') if line.strip()]


def identity(row):
    value = row['capture_id']
    return row['audit_id'], type(value).__name__, value


def bind_candidate(candidate, row, evidence):
    """Require the phrase, model category, and literal to describe one capture."""
    for field in ('audit_id', 'unit_id', 'source_listing_id', 'body_sha256',
                  'description_sha256', 'source_collected_at', 'known_at', 'description'):
        if candidate.get(field) != evidence.get(field):
            raise ValueError('Laundry candidate differs from verified description: '+field)
    if identity(candidate) != identity(evidence):
        raise ValueError('Laundry capture identity differs')
    for field in ('building', 'unit_id', 'laundry_type', 'analysis_price_basis'):
        if candidate.get(field) != row.get(field):
            raise ValueError('Laundry candidate differs from analytical row: '+field)
    text = evidence['description']
    if not isinstance(text, str) or not candidate.get('findings'):
        raise ValueError('Laundry candidate needs literal findings')
    for finding in candidate['findings']:
        start, end = finding['start'], finding['end']
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                or text[start:end] != finding['literal']):
            raise ValueError('Laundry finding offsets differ')


def inspect_capture(candidate, row, evidence, raw):
    bind_candidate(candidate, row, evidence)
    if hashlib.sha256(raw.encode()).hexdigest() != evidence['raw_listing_sha256']:
        raise ValueError('Raw laundry source hash differs')
    payload = json.loads(raw)
    if str(payload.get('id')) != row['source_listing_id']:
        raise ValueError('Raw laundry source advertisement differs')
    # Recovery replaces only the description for this diagnostic replay. It
    # does not mutate the source payload or invent a new raw-payload hash.
    replay = deepcopy(payload)
    replay['description'] = evidence['description']
    result = attribute_evidence.extract_attribute_evidence(replay)
    assertions = [e for e in result['evidence'] if e['attribute'] == 'laundry_type']
    structured = [e for e in assertions if e['method'] == 'structured']
    return {
        **{k: candidate[k] for k in ('audit_id', 'capture_id', 'source_listing_id', 'unit_id',
             'building', 'body_sha256', 'description_sha256', 'source_collected_at',
             'known_at', 'laundry_type', 'analysis_price_basis', 'findings')},
        'raw_listing_sha256': evidence['raw_listing_sha256'],
        'description_interpreted_at': evidence['description_interpreted_at'],
        'description_source_path': evidence['source_path'],
        'laundry_assertions': assertions,
        'structured_in_unit_claim': any(e['value'] == 'in_unit' for e in structured),
        'structured_in_building_claim': any(e['value'] == 'in_building' for e in structured),
        'replayed_laundry_type': result['attributes']['laundry_type'],
        'replayed_conflicts': result['conflicts'].get('laundry_type'),
        'replay_version': attribute_evidence.VERSION,
        'status': 'source_evidence_for_review_no_data_action',
    }


def support(rows):
    return {'captures': len(rows), 'observations': len({r['audit_id'] for r in rows}),
        'units': len({r['unit_id'] for r in rows}), 'buildings': len({r['building'] for r in rows}),
        'recorded_categories': dict(Counter(r['laundry_type'] or 'unknown' for r in rows)),
        'structured_in_unit_captures': sum(r['structured_in_unit_claim'] for r in rows),
        'structured_in_building_captures': sum(r['structured_in_building_claim'] for r in rows),
        'replay_category_disagreements': sum(r['laundry_type'] != r['replayed_laundry_type'] for r in rows)}


def run(dataset, descriptions, phrase_audit, archive, historical, refresh, output):
    import duckdb

    dataset, descriptions, phrase_audit, archive, historical, refresh = map(
        Path, (dataset, descriptions, phrase_audit, archive, historical, refresh))
    _, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    em, _ = _verified_bundle(descriptions, retain=set())
    _, pf = _verified_bundle(phrase_audit, retain={'summary.json', 'candidates.jsonl'})
    hm, hf = _verified_bundle(historical, retain={'source-files.json'})
    summary = json.loads(pf['summary.json'])
    if (summary.get('version') != 'laundry-location-phrase-audit-v1'
            or summary['source_manifest_sha256'] != digest(dataset/'complete.json')
            or summary['description_manifest_sha256'] != digest(descriptions/'complete.json')
            or em.get('historical_manifest') != hm):
        raise ValueError('Laundry source lineage differs')
    verified = bayesian_evidence.load_evidence(dataset, descriptions)
    rows = {r['audit_id']: r for r in records(df['observations.jsonl'])}
    candidates = records(pf['candidates.jsonl'])
    evidence = {identity(e): e for captures in verified.values() for e in captures}
    if len({identity(c) for c in candidates}) != len(candidates):
        raise ValueError('Duplicate laundry candidate capture')
    history, current = {}, []
    for candidate in candidates:
        row = rows[candidate['audit_id']]
        e = evidence[identity(candidate)]
        bind_candidate(candidate, row, e)
        if row['analysis_price_basis'] == 'historical_initial_own_advertisement_ask':
            # A single capture may support more than one analytical row.
            history.setdefault(candidate['capture_id'], []).append((candidate, row, e))
        elif row['analysis_price_basis'] == 'current_capture_gross_ask':
            current.append((candidate, row, e))
        else:
            raise ValueError('Unsupported laundry price basis')
    inventory = json.loads(hf['source-files.json'])
    seen, captures = set(), []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        for relative in sorted(inventory):
            if not relative.startswith('listing_observations/') or not relative.endswith('.parquet'):
                continue
            path = archive/relative
            if not path.resolve().is_relative_to(archive.resolve()) or digest(path) != inventory[relative]:
                raise ValueError('Historical laundry shard differs')
            cursor = db.execute('SELECT snapshot_id,raw_listing_json FROM read_parquet(?)', [str(path)])
            while batch := cursor.fetchmany(64):
                for capture, raw in batch:
                    if capture not in history:
                        continue
                    if capture in seen:
                        raise ValueError('Duplicate historical laundry capture')
                    seen.add(capture)
                    captures.extend(inspect_capture(c, r, e, raw) for c, r, e in history[capture])
    if seen != history.keys():
        raise ValueError('Missing historical laundry capture')
    for candidate, row, e in current:
        provenance = row['refresh_provenance']; sha = provenance['body_sha256']
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Invalid laundry body hash')
        body = gzip.decompress((refresh/'archive/bodies'/sha[:2]/(sha+'.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha or sha != e['body_sha256']:
            raise ValueError('Current laundry body differs')
        parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
        captures.append(inspect_capture(candidate, row, e, parsed['raw_listing_json']))
    kinds = sorted({f['kind'] for r in captures for f in r['findings']})
    summary = {**support(captures), 'by_phrase': {
        kind: support([r for r in captures if any(f['kind'] == kind for f in r['findings'])])
        for kind in kinds}, 'policy': 'Exact-capture source review only. Structured codes remain claims, not proof of installed equipment. Hookup wording does not by itself deny installed equipment. Replay replaces only the verified description; no source/model values or physical change dates are altered.'}
    paths = [Path(__file__), Path(attribute_evidence.__file__), Path(bayesian_evidence.__file__)]
    return publish_bundle(output, {
        'captures.jsonl': ''.join(canonical(r)+'\n' for r in sorted(captures, key=identity)),
        'summary.json': canonical(summary)+'\n', **{p.name: p.read_text() for p in paths}}, {
        'version': VERSION, 'summary': summary,
        'dataset_manifest_sha256': digest(dataset/'complete.json'),
        'descriptions_manifest_sha256': digest(descriptions/'complete.json'),
        'phrase_audit_manifest_sha256': digest(phrase_audit/'complete.json'),
        'historical_manifest_sha256': digest(historical/'complete.json'),
        'implementation_sha256': {p.name: digest(p) for p in paths}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'descriptions', 'phrase_audit', 'archive', 'historical', 'refresh', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
