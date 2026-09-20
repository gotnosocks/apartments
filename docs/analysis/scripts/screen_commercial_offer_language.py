"""Find commercial-offer review candidates without assigning residential scope."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'commercial-offer-language-screen-v1'
PATTERNS = {
    'commercial_word': r'\bcommercial\b',
    'business_use': r'\b(?:business|professional)\s+use\b',
    'office_space': r'\boffice\s+spaces?\b',
    'recording_studio': r'\brecording\s+studios?\b',
    'event_space': r'\b(?:event\s+(?:space|venue)|corporate\s+events?|fashion\s+shows?)\b',
    'retail_showroom': r'\b(?:showroom|retail\s+(?:space|use|events?))\b',
    'daily_weekly': r'\b(?:daily\s+(?:and|or)\s+weekly|(?:rent(?:ed|ing)?|rental)\s+(?:daily|hourly))\b',
    'restaurant_lease': r'\b(?:key\s+money|liquor\s+(?:license|rights)|restaurant\s+(?:space|lease))\b',
}


def matches(text):
    found = []
    for name, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text, re.I):
            found.append({'pattern': name, 'start': match.start(), 'end': match.end(),
                'literal': match.group(), 'context': text[max(0, match.start()-100):match.end()+250]})
    return found


def run(dataset, evidence, output):
    dataset, evidence, output = map(Path, (dataset, evidence, output))
    source_hash, evidence_hash = digest(dataset/'complete.json'), digest(evidence/'complete.json')
    _, source_files = _verified_bundle(dataset, retain={'observations.jsonl'})
    _, evidence_files = _verified_bundle(evidence, retain={'evidence.jsonl'})
    rows = [json.loads(line) for line in source_files['observations.jsonl'].splitlines()]
    by_id = {row['audit_id']: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError('Duplicate analytical observation')
    attached, hits = defaultdict(list), defaultdict(list)
    scanned = skipped = empty = 0
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
            raise ValueError('Description hash differs')
        scanned += 1
        empty += not bool(text.strip())
        attached[row['audit_id']].append(item)
        found = matches(text)
        if found:
            hits[row['audit_id']].append({'capture_id': item['capture_id'],
                'description_sha256': item['description_sha256'], 'matches': found})
    cases = []
    for identity, witnesses in sorted(hits.items()):
        row = by_id[identity]
        cases.append({'source_row': row,
            'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
            'captures': attached[identity], 'witnesses': witnesses})
    summary = {'version': VERSION, 'source_rows': len(rows), 'scanned_own_captures': scanned,
        'empty_description_captures': empty, 'rows_without_attached_evidence': len(set(by_id)-set(attached)),
        'out_of_cohort_evidence_rows_skipped': skipped, 'candidate_rows': len(cases),
        'candidate_units': len({c['source_row']['unit_id'] for c in cases}),
        'candidate_advertisements': len({c['source_row']['source_listing_id'] for c in cases}),
        'rows_by_pattern': dict(Counter(name for c in cases for name in
            {m['pattern'] for w in c['witnesses'] for m in w['matches']})),
        'interpretation': 'Lexical candidates, not exclusions. Full own-ad review must distinguish offered product from appliances, home offices, neighborhood businesses, prior uses and negation. Nonmatches remain unclassified; historical effective dates are unverified.'}
    if digest(dataset/'complete.json') != source_hash or digest(evidence/'complete.json') != evidence_hash:
        raise ValueError('Inputs changed during screening')
    publish_bundle(output, {'cases.jsonl': ''.join(canonical(c)+'\n' for c in cases),
        'summary.json': canonical(summary)+'\n', 'patterns.json': canonical(PATTERNS)+'\n',
        Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'source_manifest_sha256': source_hash,
         'evidence_manifest_sha256': evidence_hash, 'source_or_model_changes': False})
    _verified_bundle(output)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'evidence', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
