"""Publish a complete, source-bound manual review of label-floor conflicts."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'unit-label-floor-conflict-review-v1'
DECISIONS = {'retain_explicit_floor_claim', 'withhold_floor_due_to_scope',
             'withhold_floor_due_to_source_conflict'}


def records(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line.strip()]


def capture_key(row):
    return row['audit_id'], type(row['capture_id']).__name__, row['capture_id']


def adjudicate(conflicts, labels, evidence, policy):
    rules = {r['audit_id']: r for r in policy['cases']}
    if (len(rules) != len(policy['cases']) or len({r['audit_id'] for r in conflicts}) != len(conflicts)
            or rules.keys() != {r['audit_id'] for r in conflicts}):
        raise ValueError('Review must cover every conflict once, with no additional targets')
    by_capture = {capture_key(r): r for r in labels}
    if len(by_capture) != len(labels): raise ValueError('Duplicate label capture')
    results = []
    for row in conflicts:
        rule = rules[row['audit_id']]
        if (rule['decision'] not in DECISIONS or not rule['reason'].strip()
                or rule['expected_candidate_floor'] != row['candidate_floor']
                or rule['expected_explicit_floor'] != row['explicit_floor']):
            raise ValueError('Review decision or floor binding differs')
        captures = []
        for e in evidence[row['audit_id']]:
            label = by_capture.get(capture_key(e))
            if (label is None or any(label[k] != e[k] for k in
                ('source_listing_id', 'unit_id', 'body_sha256', 'raw_listing_sha256'))
                    or rule['source_listing_id'] != e['source_listing_id']
                    or label['candidate_floor'] != row['candidate_floor']
                    or label['explicit_floor'] != row['explicit_floor']
                    or instant(policy['interpreted_at']) < instant(e['known_at'])):
                raise ValueError('Review label/description/clock binding differs')
            text = e['description'] or ''
            spans = []
            for match in re.finditer(r'floor|flight|video|photo', text, re.I):
                start, end = max(0, match.start()-90), min(len(text), match.end()+150)
                if spans and start <= spans[-1]['end']:
                    spans[-1]['end'] = max(end, spans[-1]['end'])
                    spans[-1]['literal'] = text[spans[-1]['start']:spans[-1]['end']]
                else:
                    spans.append({'start': start, 'end': end, 'literal': text[start:end]})
            if not spans: raise ValueError('Manual floor review needs source text')
            captures.append({**e, 'label_evidence': label, 'review_spans': spans})
        expected = {capture_key(r) for r in labels if r['audit_id'] == row['audit_id']}
        if not captures or {capture_key(e) for e in captures} != expected:
            raise ValueError('Review capture coverage differs')
        extra = [e for values in evidence.values() for e in values
                 if e['source_listing_id'] in rule.get('supporting_advertisements', [])]
        if ({e['source_listing_id'] for e in extra} != set(rule.get('supporting_advertisements', []))
                or any(e['unit_id'] != row['unit_id'] for e in extra)):
            raise ValueError('Supporting advertisement must belong to the same source unit')
        for e in extra:
            if instant(e['known_at']) > instant(policy['interpreted_at']):
                raise ValueError('Supporting evidence postdates review')
        results.append({**row, **rule, 'captures': captures, 'supporting_captures': extra,
            'reviewer': policy['reviewer'], 'interpreted_at': policy['interpreted_at'],
            'proposed_analytical_floor': (row['explicit_floor']
                if rule['decision'] == 'retain_explicit_floor_claim' else None),
            'label_prefix_validated_as_floor': False,
            'status': 'review_complete_recommendation_not_yet_projected'})
    return results


def run(dataset, descriptions, label_audit, policy, output):
    dataset, descriptions, label_audit, policy = map(Path, (dataset, descriptions, label_audit, policy))
    lm, lf = _verified_bundle(label_audit, retain={'disagreements.jsonl', 'captures.jsonl'})
    rules = json.loads(policy.read_text())
    if (lm.get('version') != 'unit-label-floor-research-v1'
            or lm['summary']['source_manifest_sha256'] != digest(dataset/'complete.json')
            or rules['label_audit_manifest_sha256'] != digest(label_audit/'complete.json')
            or rules['descriptions_manifest_sha256'] != digest(descriptions/'complete.json')):
        raise ValueError('Manual floor review source lineage differs')
    evidence = load_evidence(dataset, descriptions)
    conflicts = records(lf['disagreements.jsonl'])
    labels = records(lf['captures.jsonl'])
    results = adjudicate(conflicts, labels, evidence, rules)
    summary = {'observations': len(results), 'units': len({r['unit_id'] for r in results}),
        'buildings': len({r['building'] for r in results}),
        'reviewed_captures': sum(len(r['captures']) for r in results),
        'decisions': dict(Counter(r['decision'] for r in results)),
        'interpretations': dict(Counter(r['interpretation'] for r in results)),
        'policy': 'Complete source review of the fixed disagreement inventory, not ground truth or an accuracy estimate. Preserve literal labels separately. No building-wide offset, alias merge, physical height/change date, or new analytical value is automatically applied.'}
    return publish_bundle(output, {'decisions.jsonl': ''.join(canonical(r)+'\n' for r in results),
        'summary.json': canonical(summary)+'\n', 'review-policy.json': canonical(rules)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {'version': VERSION,
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'label_audit_manifest_sha256': digest(label_audit/'complete.json'),
        'descriptions_manifest_sha256': digest(descriptions/'complete.json'), 'summary': summary})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'descriptions', 'label_audit', 'policy', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
