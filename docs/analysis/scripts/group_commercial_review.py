"""Deduplicate full descriptions for review without discarding any association."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

# Ordering hints only. Negated or historical claims deliberately remain visible.
PRIORITY = re.compile(
    r'commercial\s+(?:use|lease|space|loft|condo|co-op)|'
    r'(?:business|professional)\s+use|recording\s+studio|'
    r'daily\s+(?:and|or)\s+weekly|ground\s+floor\s+retail|pop-up\s+store', re.I)


def group_cases(cases):
    groups = {}
    seen = set()
    for case in cases:
        row = case['source_row']
        if hashlib.sha256(canonical(row).encode()).hexdigest() != case['source_row_sha256']:
            raise ValueError('Source row hash differs')
        witnesses = {canonical(w['capture_id']): w for w in case['witnesses']}
        if len(witnesses) != len(case['witnesses']):
            raise ValueError('Repeated match witness')
        for capture in case['captures']:
            text = capture.get('description') or ''
            sha = hashlib.sha256(text.encode()).hexdigest()
            if sha != capture['description_sha256']:
                raise ValueError('Full-description hash differs')
            key = (row['audit_id'], canonical(capture['capture_id']))
            if key in seen:
                raise ValueError('Repeated observation/capture association')
            seen.add(key)
            if any(capture[k] != row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')):
                raise ValueError('Capture identity differs')
            witness = witnesses.pop(canonical(capture['capture_id']), None)
            hits = [] if witness is None else witness['matches']
            if witness and witness['description_sha256'] != sha:
                raise ValueError('Match description hash differs')
            for hit in hits:
                a, b = hit['start'], hit['end']
                if not (type(a) is int and type(b) is int and 0 <= a < b <= len(text)
                        and text[a:b] == hit['literal']):
                    raise ValueError('Match span differs')
            group = groups.setdefault(sha, {'description_sha256': sha, 'description': text,
                'priority_hint': bool(PRIORITY.search(text)), 'associations': []})
            if group['description'] != text:
                raise ValueError('Description hash collision')
            group['associations'].append({
                'audit_id': row['audit_id'], 'unit_id': row['unit_id'],
                'source_listing_id': row['source_listing_id'], 'building': row['building'],
                'analysis_price_basis': row['analysis_price_basis'],
                'source_row_sha256': case['source_row_sha256'],
                'capture_id': capture['capture_id'], 'raw_listing_sha256': capture['raw_listing_sha256'],
                'source_collected_at': capture['source_collected_at'], 'matches': hits})
        if witnesses:
            raise ValueError('Match witness lacks an attached capture')
    return sorted(groups.values(), key=lambda g: (not g['priority_hint'], g['description_sha256']))


def run(screen, output):
    screen, output = Path(screen), Path(output)
    manifest, files = _verified_bundle(screen, retain={'cases.jsonl'})
    if manifest['version'] != 'commercial-offer-language-screen-v1':
        raise ValueError('Wrong input screen')
    cases = [json.loads(line) for line in files['cases.jsonl'].decode().split('\n') if line]
    groups = group_cases(cases)
    summary = {'candidate_rows': len(cases), 'unique_full_descriptions': len(groups),
        'attached_capture_associations': sum(len(g['associations']) for g in groups),
        'priority_hint_groups': sum(g['priority_hint'] for g in groups),
        'rows_by_price_basis': dict(Counter(c['source_row']['analysis_price_basis'] for c in cases)),
        'interpretation': 'All full descriptions and row/capture associations retained. Priority is a lexical ordering hint, never a scope decision. Review once per identical text, then assess each associated offer and historical timing independently.'}
    publish_bundle(output, {'groups.jsonl': ''.join(canonical(g)+'\n' for g in groups),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': 'commercial-review-description-groups-v1',
         'screen_manifest_sha256': digest(screen/'complete.json'),
         'source_manifest_sha256': manifest['source_manifest_sha256'],
         'source_or_model_changes': False})
    _verified_bundle(output)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screen', required=True)
    parser.add_argument('--output', required=True)
    print(canonical(run(**vars(parser.parse_args()))))
