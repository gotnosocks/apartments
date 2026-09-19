"""Replay all source-bound captures of ads mentioning non-elevator access.

This is a targeted extraction regression audit, not general elevator validation
or a correction projection. Structured/text conflicts remain unknown.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import runpy

from apartments import attribute_evidence, bayesian_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from .cohort_spatial_features import verified_manifest, records

VERSION = 'non-elevator-capture-replay-v1'
PATTERN = re.compile(r'\bnon(?:\s+|[-\u2010-\u2014]\s*)elevator\b', re.I)


def replay(row, capture, raw, old_extract):
    if hashlib.sha256(raw.encode()).hexdigest() != capture['raw_listing_sha256']:
        raise ValueError('Original payload hash differs')
    payload = json.loads(raw)
    if str(payload.get('id')) != row['source_listing_id']:
        raise ValueError('Original advertisement identity differs')
    payload = deepcopy(payload)
    payload['description'] = capture['description']
    before, after = old_extract(payload), attribute_evidence.extract_attribute_evidence(payload)
    for result in (before, after):
        for claim in result['evidence']:
            if claim['source_path'] == '/description':
                if payload['description'][claim['start']:claim['end']] != claim['literal']:
                    raise ValueError('Extraction span differs from literal description')
    def elevator(result):
        return {'value': result['attributes']['elevator'],
                'claims': [e for e in result['evidence'] if e['attribute'] == 'elevator'],
                'conflicts': result['conflicts'].get('elevator', [])}
    # The narrow version change must not alter unrelated attributes/assertions.
    def unrelated(result):
        result = deepcopy(result)
        result.pop('version', None)
        result['attributes'].pop('elevator')
        result['conflicts'].pop('elevator', None)
        result['evidence'] = [e for e in result['evidence'] if e['attribute'] != 'elevator']
        return result
    if unrelated(before) != unrelated(after): raise ValueError('Unrelated extraction behavior changed')
    return {**capture, 'building': row['building'], 'analysis_price_basis': row['analysis_price_basis'],
            'stored_elevator': row.get('elevator'), 'before': elevator(before), 'after': elevator(after)}


def summarize_row(row, captures):
    values = {c['after']['value'] for c in captures}
    return {'audit_id': row['audit_id'], 'source_listing_id': row['source_listing_id'],
            'building': row['building'], 'unit_id': row['unit_id'],
            'stored_elevator': row.get('elevator'), 'captures': len(captures),
            'candidate_elevator': next(iter(values)) if len(values) == 1 else None,
            'capture_values': sorted(values, key=lambda v: -1 if v is None else int(v)),
            'all_captures_agree': len(values) == 1,
            'conflicting_claim_captures': sum(bool(c['after']['conflicts']) for c in captures)}


def run(dataset, descriptions, historical, archive, previous_extractor, output):
    import duckdb
    dataset, descriptions, historical, archive, previous_extractor = map(
        Path, (dataset, descriptions, historical, archive, previous_extractor))
    bindings = [(p, digest(p/'complete.json')) for p in (dataset, descriptions, historical)]
    manifests = [verified_manifest(p) for p, _ in bindings]
    previous_code = previous_extractor.read_text()
    old = runpy.run_path(str(previous_extractor))
    if old['VERSION'] != 'attribute-evidence-v4' or attribute_evidence.VERSION != 'attribute-evidence-v5':
        raise ValueError('Expected exact v4 to v5 extraction revision')
    code_paths = [Path(__file__), Path(attribute_evidence.__file__), Path(bayesian_evidence.__file__)]
    code = {p.name: p.read_text() for p in code_paths}
    rows = {r['audit_id']: r for r in records(dataset/'observations.jsonl')}
    evidence = bayesian_evidence.load_evidence(dataset, descriptions)
    selected = {k: captures for k, captures in evidence.items()
                if any(PATTERN.search(c.get('description') or '') for c in captures)}
    history = {}
    for key, captures in selected.items():
        row = rows[key]
        for c in captures:
            if row['analysis_price_basis'] != 'historical_initial_own_advertisement_ask' or type(c['capture_id']) is not int:
                raise ValueError('Selected nonhistorical capture needs an explicit raw-body reader')
            history.setdefault(c['capture_id'], []).append((row, c))
    del evidence
    inventory = json.loads((historical/'source-files.json').read_text())
    seen, results = set(), []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        for relative in sorted(inventory):
            if not relative.startswith('listing_observations/') or not relative.endswith('.parquet'): continue
            path = archive/relative
            if not path.resolve().is_relative_to(archive.resolve()) or digest(path) != inventory[relative]:
                raise ValueError('Historical payload shard changed')
            cursor = db.execute('SELECT snapshot_id,raw_listing_json FROM read_parquet(?)', [str(path)])
            while batch := cursor.fetchmany(64):
                for capture_id, raw in batch:
                    if capture_id not in history: continue
                    if capture_id in seen: raise ValueError('Duplicate raw capture')
                    seen.add(capture_id)
                    results.extend(replay(row, c, raw, old['extract_attribute_evidence']) for row, c in history[capture_id])
    if seen != history.keys(): raise ValueError('Missing original capture payload')
    results.sort(key=lambda r: (r['audit_id'], r['capture_id']))
    grouped = {key: [] for key in selected}
    for r in results: grouped[r['audit_id']].append(r)
    observations = [summarize_row(rows[key], grouped[key]) for key in sorted(selected)]
    transitions = Counter((r['stored_elevator'], r['candidate_elevator']) for r in observations)
    summary = {'version': VERSION, 'source_observations': len(rows), 'selected_observations': len(selected),
        'all_attached_captures_replayed': len(results),
        'matching_phrase_captures': sum(bool(PATTERN.search(r['description'] or '')) for r in results),
        'changed_elevator_value_captures': sum(r['before']['value'] != r['after']['value'] for r in results),
        'changed_claim_captures': sum(r['before'] != r['after'] for r in results),
        'candidate_transitions': [{'stored': a, 'candidate': b, 'rows': n}
            for (a, b), n in sorted(transitions.items(), key=lambda kv: str(kv[0]))],
        'conflicting_claim_captures': sum(bool(r['after']['conflicts']) for r in results),
        'changed_current_rows': 0, 'model_inputs_changed': False,
        'limitations': ['Targeted lexical regression audit, not independent extraction accuracy or physical building verification.',
            'Every capture attached to each selected observation is replayed, including captures without the triggering phrase.',
            'Original structured payloads and source-bound recovered descriptions are combined; source assertion conflicts stay unknown.',
            'Candidate values are not patches, temporal facility change dates or building-wide truth.']}
    if any(digest(p/'complete.json') != h or verified_manifest(p) != m for (p, h), m in zip(bindings, manifests)):
        raise ValueError('Audit inputs changed')
    if previous_extractor.read_text() != previous_code or any(p.read_text() != code[p.name] for p in code_paths):
        raise ValueError('Replay implementation changed')
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'captures.jsonl': ''.join(canonical(r)+'\n' for r in results),
        'observations.jsonl': ''.join(canonical(r)+'\n' for r in observations),
        'previous-attribute-evidence.py': previous_code, **code},
        {'version': VERSION, 'dataset_manifest_sha256': bindings[0][1],
         'descriptions_manifest_sha256': bindings[1][1], 'historical_manifest_sha256': bindings[2][1]})
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'descriptions', 'historical', 'archive', 'previous_extractor', 'output'):
        p.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    print(canonical(run(**vars(p.parse_args()))), flush=True)
