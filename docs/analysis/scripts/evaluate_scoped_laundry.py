"""Replay the experimental laundry extractor on source-bound phrase candidates.

The 36 earlier reviews are development cases. A separate building-disjoint
sample is exported for manual validation; its accuracy is not presumed.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from apartments import laundry_measurement
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models.laundry_source_audit import identity, records


def replay_payload(candidate, audit):
    for field in ('audit_id', 'capture_id', 'source_listing_id', 'unit_id', 'building',
                  'body_sha256', 'description_sha256', 'source_collected_at', 'known_at'):
        assert candidate[field] == audit[field], field
    assert hashlib.sha256(candidate['description'].encode()).hexdigest() == candidate['description_sha256']
    raw = {'description': candidate['description'], 'propertyDetails': {}}
    # Reconstruct only audited codes, at their original pointers. Unfilled slots
    # remain unknown; this is not a reconstructed full raw listing.
    for evidence in audit['laundry_assertions']:
        if evidence['method'] != 'structured':
            continue
        match = re.fullmatch(r'/propertyDetails/(features|amenities)(/list)?/(\d+)', evidence['source_path'])
        assert match and evidence['literal'] in ('LAUNDRY', 'WASHER_DRYER')
        section, nested, index = match.groups()
        container = raw['propertyDetails'].setdefault(section, {'list': []} if nested else [])
        values = container['list'] if nested else container
        index = int(index)
        values.extend([None] * max(0, index+1-len(values)))
        assert values[index] in (None, evidence['literal'])
        values[index] = evidence['literal']
    return raw


def main():
    root = Path(__file__).resolve().parents[3]
    base = root/'data/model'
    paths = [base/'chelsea-laundry-location-phrase-audit-20260918',
             base/'chelsea-laundry-capture-source-audit-v4-20260918',
             base/'chelsea-laundry-location-adjudication-20260918']
    _, phrases = _verified_bundle(paths[0], retain={'candidates.jsonl'})
    _, audited = _verified_bundle(paths[1], retain={'captures.jsonl'})
    _, reviewed = _verified_bundle(paths[2], retain={'decisions.jsonl'})
    candidates, captures, decisions = (records(payload[name]) for payload, name in
        [(phrases, 'candidates.jsonl'), (audited, 'captures.jsonl'), (reviewed, 'decisions.jsonl')])
    by_capture = {identity(r): r for r in captures}
    assert len(by_capture) == len(captures) == len(candidates)
    assert by_capture.keys() == {identity(r) for r in candidates}
    development = {identity(r): r for r in decisions}
    development_buildings = {r['building'] for r in decisions}
    results = []
    for candidate in candidates:
        key = identity(candidate)
        result = laundry_measurement.extract(replay_payload(candidate, by_capture[key]))
        for claim in result['claims']:
            if claim['source_path'] == '/description':
                assert candidate['description'][claim['start']:claim['end']] == claim['literal']
        label = development.get(key)
        if label:
            assert label['description_sha256'] == candidate['description_sha256']
        results.append({**candidate, 'measurement': result, 'development_review': label,
                        'raw_listing_sha256': by_capture[key]['raw_listing_sha256'],
                        'structured_replay_scope': 'Only same-capture audited laundry codes at original JSON pointers; recovered literal description.'})
    # Freeze a deterministic sample from buildings untouched by the 36-case review.
    selected, units = [], set()
    for family in sorted({f['kind'] for r in candidates for f in r['findings']}):
        pool = sorted((r for r in results if r['building'] not in development_buildings
                       and any(f['kind'] == family for f in r['findings'])),
                      key=lambda r: hashlib.sha256(canonical(identity(r)).encode()).hexdigest())
        count = 0
        for row in pool:
            if row['unit_id'] in units:
                continue
            selected.append({**row, 'selected_for': family, 'validation_status': 'awaiting_manual_review'})
            units.add(row['unit_id'])
            count += 1
            if count == 4:
                break
    development_cases = [r for r in results if r['development_review']]
    mismatches = [{'audit_id': r['audit_id'], 'capture_id': r['capture_id'],
                   'source_listing_id': r['source_listing_id'], 'decision': r['development_review']['decision'],
                   'detected_same_floor': r['measurement']['states']['shared_same_floor'] is True}
                  for r in development_cases if (r['measurement']['states']['shared_same_floor'] is True)
                  != (r['development_review']['decision'] == 'shared_on_floor_claim')]
    summary = {'version': 'scoped-laundry-candidate-evaluation-v1', 'extractor_version': laundry_measurement.VERSION,
        'captures': len(results), 'development_cases': len(development_cases),
        'development_same_floor_disagreements': mismatches,
        'category_counts': dict(Counter(r['measurement']['most_convenient_reported_option'] or 'unknown' for r in results)),
        'installation_review_captures': sum(r['measurement']['installation_review_required'] for r in results),
        'heldout_cases': len(selected), 'heldout_buildings': len({r['building'] for r in selected}),
        'heldout_labels_reviewed': False, 'model_inputs_changed': False,
        'limitations': ['Lexically selected candidates, not full-corpus coverage or recall.',
                       'The 36 reviews informed development; their agreement is not independent accuracy.',
                       'Building-disjoint validation sample awaits manual labels. No four-level model has been fitted.']}
    publish_bundle(base/'chelsea-scoped-laundry-evaluation-20260919', {
        'summary.json': canonical(summary)+'\n',
        'captures.jsonl': ''.join(canonical(r)+'\n' for r in results),
        'validation-sample.jsonl': ''.join(canonical(r)+'\n' for r in selected),
        Path(__file__).name: Path(__file__).read_text(),
        'laundry_measurement.py': Path(laundry_measurement.__file__).read_text()},
        {'version': summary['version'], 'inputs': {str(path.relative_to(root)): digest(path/'complete.json') for path in paths},
         'extractor_sha256': digest(laundry_measurement.__file__)})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    main()
