"""Replay a laundry extractor revision against every archived capture.

The old extractor must exactly reproduce its saved output from recovered prose
and its structured laundry-code witnesses. This verifies the minimal input used
by both versions; it does not claim to re-download or re-parse the raw pages.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy
import sqlite3
import tempfile

from apartments import laundry_measurement
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from . import cohort_spatial_features as verified

VERSION = 'full-cohort-laundry-extractor-revision-v1'
FIELDS = ('audit_id', 'capture_id', 'source_listing_id', 'unit_id', 'body_sha256',
          'raw_listing_sha256', 'description_sha256', 'source_collected_at',
          'known_at', 'description_interpreted_at')


def identity(row):
    value = row['capture_id']
    if type(value) not in (int, str) or value in ('', 0):
        raise ValueError('Invalid typed capture identity')
    return canonical([row['audit_id'], type(value).__name__, value])


def replay_payload(capture, evidence):
    if any(capture[k] != evidence[k] or type(capture[k]) is not type(evidence[k]) for k in FIELDS):
        raise ValueError('Archived laundry and description capture bindings differ')
    text, source_path = evidence.get('description'), evidence.get('source_path') or '/description'
    details = evidence.get('property_details')
    if isinstance(details, dict) and isinstance(details.get('description'), str):
        text, source_path = details['description'], '/propertyDetails/description'
    if text is not None and not isinstance(text, str): raise ValueError('Nonliteral description')
    if (source_path != capture['source_path'] or (capture['description_sha256'] is not None and
            (not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != capture['description_sha256']))):
        raise ValueError('Description literal or path differs')
    payload = {'description': text, 'propertyDetails': {}}
    for claim in capture['measurement']['claims']:
        if claim['method'] != 'structured': continue
        match = re.fullmatch(r'/propertyDetails/(features|amenities)(/list)?/(\d+)', claim['source_path'])
        if match is None or claim['literal'] not in ('LAUNDRY', 'WASHER_DRYER'):
            raise ValueError('Unsupported structured laundry witness')
        section, nested, index = match[1], bool(match[2]), int(match[3])
        if index > 10000: raise ValueError('Unreasonable source list index')
        container = payload['propertyDetails'].setdefault(section, {'list': []} if nested else [])
        if isinstance(container, dict) != nested: raise ValueError('Conflicting structured source paths')
        codes = container['list'] if nested else container
        codes.extend([None]*(index+1-len(codes)))
        if codes[index] is not None: raise ValueError('Duplicate structured source witness')
        codes[index] = claim['literal']
    return payload


def compare_capture(capture, evidence, old_extract):
    payload = replay_payload(capture, evidence)
    before = old_extract(payload)
    if before != capture['measurement']:
        raise ValueError('Minimal replay does not reproduce the complete frozen measurement')
    after = laundry_measurement.extract(payload)
    for claim in after['claims']:
        if claim['method'] == 'description' and payload['description'][claim['start']:claim['end']] != claim['literal']:
            raise ValueError('Revised literal span differs')
    return before, after, payload['description']


def support(rows, field):
    counts = {}
    for category in ('in_unit', 'on_floor', 'in_building', 'none', 'unknown'):
        group = [r for r in rows if (r[field] or 'unknown') == category]
        counts[category] = {'observations': len(group), 'units': len({r['unit_id'] for r in group}),
            'buildings': len({r['building'] for r in group}),
            'current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in group)}
    return counts


def run(baseline, descriptions, output):
    baseline, descriptions, output = map(Path, (baseline, descriptions, output))
    bindings = [(p, digest(p/'complete.json')) for p in (baseline, descriptions)]
    bm, em = [verified.verified_manifest(p) for p, _ in bindings]
    if (bm['version'] != 'full-cohort-scoped-laundry-measurement-v1'
            or bm['descriptions_manifest_sha256'] != bindings[1][1]):
        raise ValueError('Full-cohort measurement and description archive binding differ')
    old = runpy.run_path(str(baseline/'laundry_measurement.py'))
    if old['VERSION'] != 'scoped-laundry-measurement-v3': raise ValueError('Expected frozen v3 reference')
    old_summary = json.loads((baseline/'summary.json').read_text())
    code_paths = [Path(__file__), Path(laundry_measurement.__file__), Path(verified.__file__)]
    code = {p.name: p.read_text() for p in code_paths}
    rows, changed, seen, transitions = {}, [], 0, Counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Disk index keeps full descriptions out of RAM while another sampler runs.
    with tempfile.TemporaryDirectory(prefix='laundry-replay-', dir=output.parent) as scratch, \
         sqlite3.connect(Path(scratch)/'descriptions.sqlite') as db:
        db.execute('PRAGMA cache_size=-8192')
        db.execute('CREATE TABLE evidence (id TEXT PRIMARY KEY, body TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0)')
        db.executemany('INSERT INTO evidence(id, body) VALUES (?,?)',
            ((identity(e), canonical(e)) for e in verified.records(descriptions/'evidence.jsonl')))
        for capture in verified.records(baseline/'captures.jsonl'):
            key = identity(capture)
            found = db.execute('SELECT body, used FROM evidence WHERE id=?', (key,)).fetchone()
            if found is None or found[1]: raise ValueError('Missing or duplicate replay capture')
            db.execute('UPDATE evidence SET used=1 WHERE id=?', (key,))
            before, after, text = compare_capture(capture, json.loads(found[0]), old['extract'])
            seen += 1
            a, b = (m['most_convenient_reported_option'] for m in (before, after))
            row = rows.setdefault(capture['audit_id'], {
                **{k: capture[k] for k in ('audit_id', 'unit_id', 'building', 'source_listing_id', 'analysis_price_basis', 'laundry_type')},
                'before': set(), 'after': set(), 'captures': 0})
            if any(row[k] != capture[k] for k in ('unit_id', 'building', 'source_listing_id', 'analysis_price_basis', 'laundry_type')):
                raise ValueError('Observation identity differs across captures')
            row['before'].add(a)
            row['after'].add(b)
            row['captures'] += 1
            transitions[(a or 'unknown', b or 'unknown')] += 1
            if {**after, 'version': before['version']} != before:
                changed.append({**{k: v for k, v in capture.items() if k != 'measurement'},
                                'before': before, 'after': after, 'description': text})
        if db.execute('SELECT count(*) FROM evidence WHERE used=0').fetchone()[0]:
            raise ValueError('Description archive contains unmeasured captures')
    observations = []
    for row in rows.values():
        r = dict(row)
        for field in ('before', 'after'):
            values = r[field]
            r[field+'_capture_categories'] = sorted(values, key=lambda x: x or '')
            r[field+'_all_captures_agree'] = len(values) == 1
            r[field] = next(iter(values)) if len(values) == 1 else None
        observations.append(r)
    observations.sort(key=lambda r: r['audit_id'])
    before_support, after_support = [support(observations, field) for field in ('before', 'after')]
    if (seen != old_summary['captures'] or len(observations) != old_summary['observations']
            or before_support != old_summary['candidate_support']):
        raise ValueError('Frozen cohort coverage or support differs')
    changed_rows = [r for r in observations if r['before_capture_categories'] != r['after_capture_categories']]
    summary = {'version': VERSION, 'before_version': old['VERSION'], 'after_version': laundry_measurement.VERSION,
        'captures_replayed_exactly': seen, 'observations': len(observations),
        'changed_measurement_captures': len(changed),
        'changed_category_captures': sum(count for (a, b), count in transitions.items() if a != b),
        'changed_observations': len(changed_rows), 'changed_units': len({r['unit_id'] for r in changed_rows}),
        'changed_buildings': len({r['building'] for r in changed_rows}),
        'changed_current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in changed_rows),
        'before_support': before_support, 'after_support': after_support,
        'capture_transitions': [{'before': a, 'after': b, 'captures': count} for (a, b), count in sorted(transitions.items())],
        'model_inputs_changed': False,
        'policy': 'Full exact v3 replay from hash-bound descriptions and structured witnesses precedes v4 extraction. Only changed outputs are published as candidates; no raw reparse, correction, backward propagation or independent accuracy claim.'}
    files = {'summary.json': canonical(summary)+'\n',
        'changed-captures.jsonl': ''.join(canonical(r)+'\n' for r in sorted(changed, key=identity)),
        'changed-observations.jsonl': ''.join(canonical(r)+'\n' for r in changed_rows),
        'previous-laundry-measurement.py': (baseline/'laundry_measurement.py').read_text(), **code}
    for (p, expected), manifest in zip(bindings, (bm, em)):
        if digest(p/'complete.json') != expected or verified.verified_manifest(p) != manifest:
            raise ValueError('Replay input changed')
    if any(p.read_text() != code[p.name] for p in code_paths): raise ValueError('Replay implementation changed')
    publish_bundle(output, files, {'version': VERSION, 'baseline_manifest_sha256': bindings[0][1],
        'descriptions_manifest_sha256': bindings[1][1], 'dataset_manifest_sha256': bm['dataset_manifest_sha256']})
    print(canonical(summary), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'descriptions', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
