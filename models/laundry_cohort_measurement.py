"""Measure laundry claims for every fitted capture without changing model inputs."""
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re

from apartments import bayesian_evidence, granular_parse, laundry_measurement
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from .laundry_source_audit import identity, records

VERSION = 'full-cohort-scoped-laundry-measurement-v1'


def measure_capture(row, evidence, raw):
    if hashlib.sha256(raw.encode()).hexdigest() != evidence['raw_listing_sha256']:
        raise ValueError('Laundry raw capture hash differs')
    payload = json.loads(raw)
    if str(payload.get('id')) != row['source_listing_id']:
        raise ValueError('Laundry raw advertisement identity differs')
    replay = deepcopy(payload)
    replay['description'] = evidence['description']
    measurement = laundry_measurement.extract(replay)
    for claim in measurement['claims']:
        if claim['source_path'] == '/description':
            if evidence['description'][claim['start']:claim['end']] != claim['literal']:
                raise ValueError('Laundry literal span differs')
    return {**{k: evidence[k] for k in ('audit_id', 'capture_id', 'source_listing_id', 'unit_id',
            'body_sha256', 'raw_listing_sha256', 'description_sha256', 'source_collected_at',
            'known_at', 'description_interpreted_at', 'source_path')},
            **{k: row[k] for k in ('building', 'analysis_price_basis', 'laundry_type')},
            'measurement': measurement}


def run(dataset, descriptions, historical_descriptions, historical, archive, refresh_roots, output):
    import duckdb

    dataset, descriptions, historical_descriptions, historical, archive, output = map(
        Path, (dataset, descriptions, historical_descriptions, historical, archive, output))
    refresh_roots = list(map(Path, refresh_roots))
    _, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    em, _ = _verified_bundle(descriptions, retain=set())
    old, _ = _verified_bundle(historical_descriptions, retain=set())
    hm, hf = _verified_bundle(historical, retain={'source-files.json'})
    if (em.get('historical_evidence_manifest_sha256') != digest(historical_descriptions/'complete.json')
            or old.get('historical_manifest') != hm):
        raise ValueError('Historical description lineage differs')
    mapping = bayesian_evidence.load_evidence(dataset, descriptions)
    rows = {r['audit_id']: r for r in records(df['observations.jsonl'])}
    history, current = {}, []
    for key, captures in mapping.items():
        row = rows[key]
        for evidence in captures:
            if row['analysis_price_basis'] == 'historical_initial_own_advertisement_ask':
                history.setdefault(evidence['capture_id'], []).append((row, evidence))
            elif row['analysis_price_basis'] == 'current_capture_gross_ask':
                current.append((row, evidence))
            else:
                raise ValueError('Unknown laundry source price basis')
    del mapping, df
    seen, results = set(), []
    inventory = json.loads(hf['source-files.json'])
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
                    results.extend(measure_capture(row, e, raw) for row, e in history[capture])
    if seen != history.keys():
        raise ValueError('Missing historical laundry capture')
    for row, evidence in current:
        provenance = row['refresh_provenance']
        sha = provenance['body_sha256']
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) or sha != evidence['body_sha256']:
            raise ValueError('Invalid current laundry body identity')
        matches = [p/'archive/bodies'/sha[:2]/(sha+'.gz') for p in refresh_roots]
        matches = [p for p in matches if p.is_file()]
        if not matches:
            raise ValueError('Missing archived current laundry body: '+sha)
        body = gzip.decompress(matches[0].read_bytes())
        if hashlib.sha256(body).hexdigest() != sha:
            raise ValueError('Current laundry body hash differs')
        parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
        results.append(measure_capture(row, evidence, parsed['raw_listing_json']))
    results.sort(key=identity)
    if len({identity(r) for r in results}) != len(results):
        raise ValueError('Duplicate measured observation/capture')
    by_row = {key: [] for key in rows}
    for result in results:
        by_row[result['audit_id']].append(result)
    observations = []
    for key, captures in by_row.items():
        if not captures:
            raise ValueError('Unmeasured analytical observation')
        categories = {r['measurement']['most_convenient_reported_option'] for r in captures}
        agreed = len(categories) == 1
        observations.append({'audit_id': key, 'unit_id': rows[key]['unit_id'], 'building': rows[key]['building'],
            'analysis_price_basis': rows[key]['analysis_price_basis'], 'old_laundry_type': rows[key]['laundry_type'],
            'capture_categories': sorted(categories, key=lambda x: x or ''),
            'all_captures_agree': agreed, 'candidate_category': next(iter(categories)) if agreed else None,
            'capture_ids': [r['capture_id'] for r in captures]})
    counts = {}
    for category in ('in_unit', 'on_floor', 'in_building', 'none', 'unknown'):
        group = [r for r in observations if (r['candidate_category'] or 'unknown') == category]
        counts[category] = {'observations': len(group), 'units': len({r['unit_id'] for r in group}),
                           'buildings': len({r['building'] for r in group}),
                           'current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in group)}
    summary = {'version': VERSION, 'extractor_version': laundry_measurement.VERSION,
        'captures': len(results), 'observations': len(observations), 'candidate_support': counts,
        'capture_category_disagreement_rows': sum(not r['all_captures_agree'] for r in observations),
        'capture_conflicts': sum(bool(r['measurement']['conflicts']) for r in results),
        'capture_installation_review': sum(r['measurement']['installation_review_required'] for r in results),
        'model_inputs_changed': False,
        'policy': 'Candidate measurements only, covering every capture attached to fitted observations. No lexical prefilter. A candidate category requires unanimity across attached captures, including unknowns; mixed captures are withheld. No facility installation/removal date is inferred. Manual validation is required before projection.'}
    code = [Path(__file__), Path(laundry_measurement.__file__), Path(bayesian_evidence.__file__)]
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'captures.jsonl': ''.join(canonical(r)+'\n' for r in results),
        'observations.jsonl': ''.join(canonical(r)+'\n' for r in observations),
        **{p.name: p.read_text() for p in code}}, {'version': VERSION,
        'dataset_manifest_sha256': digest(dataset/'complete.json'),
        'descriptions_manifest_sha256': digest(descriptions/'complete.json'),
        'historical_manifest_sha256': digest(historical/'complete.json'),
        'implementation_sha256': {p.name: digest(p) for p in code}})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'descriptions', 'historical_descriptions', 'historical', 'archive', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--refresh-roots', type=Path, nargs='+', required=True)
    print(canonical(run(**vars(parser.parse_args()))), flush=True)
