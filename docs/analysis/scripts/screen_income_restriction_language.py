"""Screen own-advertisement evidence for income-product research candidates.

This is a lexical review queue, not an eligibility classifier or a model feature.
It neither assigns restrictions to historical price dates nor treats nonmatches
as unrestricted market rents.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'income-restriction-language-screen-v1'
PATTERNS = {
    'explicit_income_restriction': r'\bincome[\s-]+restrict(?:ion|ions|ed)\b',
    'income_ceiling': r'\bmax(?:imum)?\s+(?:annual\s+)?(?:household\s+)?income\b',
    'income_upper_bound': r'\bincome\s+(?:(?:must|may|can)\s+not\s+exceed|cannot\s+exceed|must\s+be\s+(?:below|under))\b',
    'affordable_housing': r'\baffordable\s+housing\b',
    'housing_lottery': r'\bhousing\s+lottery\b',
    'area_median_income': r'\b(?:area\s+median\s+income|AMI)\b',
}


def run(dataset, evidence, output):
    dataset, evidence, output = map(Path, (dataset, evidence, output))
    source_hash, evidence_hash = digest(dataset/'complete.json'), digest(evidence/'complete.json')
    _, source_files = _verified_bundle(dataset, retain={'observations.jsonl'})
    _, evidence_files = _verified_bundle(evidence, retain={'evidence.jsonl'})
    rows = [json.loads(line) for line in source_files['observations.jsonl'].splitlines()]
    by_id = {row['audit_id']: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError('Duplicate analytical observation')
    compiled = {name: re.compile(pattern, re.I) for name, pattern in PATTERNS.items()}
    hits = defaultdict(list)
    scanned, skipped = 0, 0
    for line in evidence_files['evidence.jsonl'].splitlines():
        item = json.loads(line)
        row = by_id.get(item['audit_id'])
        if row is None:
            skipped += 1
            continue
        if (item['unit_id'] != row['unit_id']
                or item['source_listing_id'] != row['source_listing_id']
                or item['capture_id'] not in (row.get('capture_ids') or [row.get('capture_id')])):
            raise ValueError('Evidence is not attached to this own-advertisement observation')
        text = item.get('description') or ''
        if text and hashlib.sha256(text.encode()).hexdigest() != item['description_sha256']:
            raise ValueError('Description content hash differs')
        scanned += 1
        matches = []
        for name, pattern in compiled.items():
            for match in pattern.finditer(text):
                matches.append({'pattern': name, 'start': match.start(), 'end': match.end(),
                                'literal': match.group(),
                                'context': text[max(0, match.start()-100):match.end()+250]})
        if matches:
            hits[row['audit_id']].append({
                'capture_id': item['capture_id'], 'body_sha256': item['body_sha256'],
                'raw_listing_sha256': item['raw_listing_sha256'],
                'description_sha256': item['description_sha256'],
                'source_collected_at': item['source_collected_at'],
                'known_at': item['known_at'], 'matches': matches})
    cases = []
    for identity, witnesses in sorted(hits.items()):
        row = by_id[identity]
        cases.append({key: row.get(key) for key in (
            'audit_id', 'unit_id', 'source_listing_id', 'building', 'asking_rent',
            'period', 'analysis_price_basis', 'price_at', 'collected_at')}
            | {'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
               'witnesses': witnesses})
    summary = {
        'version': VERSION, 'source_rows': len(rows), 'scanned_own_captures': scanned,
        'out_of_cohort_evidence_rows_skipped': skipped, 'candidate_rows': len(cases),
        'candidate_units': len({row['unit_id'] for row in cases}),
        'candidate_advertisements': len({row['source_listing_id'] for row in cases}),
        'candidate_buildings': dict(Counter(row['building'] for row in cases)),
        'rows_by_pattern': dict(Counter(name for row in cases for name in
            {match['pattern'] for witness in row['witnesses'] for match in witness['matches']})),
        'interpretation': 'Lexical review candidates only. Context may refer to a different offer, negate a restriction or describe an administrative requirement. Nonmatches remain unclassified. Capture-time prose does not establish restriction status at an earlier asking-price event. No source, model or selection changes.'}
    if (digest(dataset/'complete.json') != source_hash
            or digest(evidence/'complete.json') != evidence_hash):
        raise ValueError('Input manifest changed during screening')
    publish_bundle(output, {'cases.jsonl': ''.join(canonical(row)+'\n' for row in cases),
        'summary.json': canonical(summary)+'\n', 'patterns.json': canonical(PATTERNS)+'\n',
        Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'source_manifest_sha256': source_hash,
         'evidence_manifest_sha256': evidence_hash})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
