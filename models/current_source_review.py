"""Apply bounded current-source review without changing reported prices or counts."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import current_source_audit as audit
from . import refresh_analysis_cohort as cohort

VERSION = 'reviewed-capture-refreshed-analysis-v1'
POLICY_VERSION = 'current-capture-source-review-policy-v1'
IDENTITY = ('audit_id', 'capture_id', 'unit_id', 'source_listing_id', 'canonical_unit_url')
MASK = 'reviewed_bathroom_composition_conflict'


def apply_case(row, evidence, review, case, *, interpreted_at):
    """Bind a named decision to an exact capture and literal source evidence."""
    if (review['source_row_sha256'] != cohort.hashed(row)
            or review['source_evidence_sha256'] != cohort.hashed(evidence)
            or any(row.get(k) != evidence.get(k) for k in IDENTITY)
            or any(review.get(k) != row.get(k) for k in IDENTITY if k != 'capture_id')
            or review['body_sha256'] != evidence['body_sha256']
            or review['raw_listing_sha256'] != evidence['raw_listing_sha256']):
        raise ValueError('Current review source binding differs')
    if instant(interpreted_at) < max(instant(row['known_at']), instant(evidence['collected_at'])):
        raise ValueError('Review predates source knowledge')
    action = case.get('action')
    if action not in ('retain_source', 'mask_bathroom_composition') or not case.get('reason', '').strip():
        raise ValueError('Unsupported action or missing reason')
    if case.get('source_listing_id') != row['source_listing_id']:
        raise ValueError('Named review belongs to another advertisement')
    text = evidence['description'] or ''
    spans = []
    for literal in case.get('quotes', []):
        if not isinstance(literal, str) or not literal or text.count(literal) != 1:
            raise ValueError('Review quote must match exactly once')
        start = text.index(literal)
        spans.append({'source_path': '/description', 'start': start,
                      'end': start+len(literal), 'literal': literal})
    expected = case.get('expected_reported_bathrooms')
    if expected is not None and expected != [row['reported_full_bathrooms'], row['reported_half_bathrooms']]:
        raise ValueError('Reviewed bathroom counts changed')
    if action == 'mask_bathroom_composition' and (not spans or expected is None):
        raise ValueError('Composition mask needs literal evidence and expected counts')
    decision = {**{k: row[k] for k in IDENTITY}, 'action': action,
        'reason': case['reason'], 'interpreted_at': interpreted_at,
        'source_row_sha256': cohort.hashed(row), 'source_evidence_sha256': cohort.hashed(evidence),
        'source_audit_sha256': cohort.hashed(review), 'evidence': spans,
        'residual_review_tags': case.get('residual_review_tags', [])}
    decision['decision_id'] = cohort.hashed(decision)
    result = deepcopy(row)
    if action == 'mask_bathroom_composition':
        counts = result['bathroom_count_evidence']
        if MASK in counts['flags']:
            raise ValueError('Composition review already applied')
        counts['flags'].append(MASK)
        counts['composition_status'] = 'reviewed_composition_conflict_unknown'
        result.setdefault('research_review_history', []).append({
            'decision_id': decision['decision_id'], 'action': action, 'reason': case['reason'],
            'interpreted_at': interpreted_at, 'source_projection_row_sha256': cohort.hashed(row),
            'before_bathroom_count_evidence': deepcopy(row['bathroom_count_evidence'])})
    return result, decision


def assemble(rows, evidence, reviews, policy):
    if policy.get('version') != POLICY_VERSION:
        raise ValueError('Unsupported current review policy')
    current = [r for r in rows if r['analysis_price_basis'] == 'current_capture_gross_ask']
    indexes = []
    for values in (rows, current, evidence, reviews):
        index = {r['audit_id']: r for r in values}
        if len(index) != len(values): raise ValueError('Duplicate source or review identity')
        indexes.append(index)
    _, by_current, by_evidence, by_review = indexes
    if by_current.keys() != by_evidence.keys() or by_current.keys() != by_review.keys():
        raise ValueError('Current audit coverage differs')
    cases = {c['source_listing_id']: c for c in policy['cases']}
    if (len(cases) != len(policy['cases'])
            or not cases.keys() <= {r['source_listing_id'] for r in current}):
        raise ValueError('Duplicate or absent named advertisement')
    kept, decisions = [], []
    for row in rows:
        if row['audit_id'] not in by_current:
            kept.append(row)
            continue
        r = by_review[row['audit_id']]
        case = cases.get(row['source_listing_id'])
        if case is None:
            if r['flags'] or r['wording_findings']:
                raise ValueError('Flagged source requires an explicit review disposition')
            case = {'source_listing_id': row['source_listing_id'], 'action': 'retain_source',
                'reason': 'Retain observed structured source values. The bounded price/product/scope screen found no review flag; this is not certification of all attributes.'}
        result, decision = apply_case(row, by_evidence[row['audit_id']], r, case,
                                      interpreted_at=policy['interpreted_at'])
        kept.append(result); decisions.append(decision)
    history = lambda rr: [r for r in rr if r['analysis_price_basis'] != 'current_capture_gross_ask']
    if history(rows) != history(kept): raise ValueError('Historical rows changed')
    return kept, decisions


def run(dataset, source_audit, policy, output):
    dataset, source_audit, policy = map(Path, (dataset, source_audit, policy))
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl'})
    am, af = _verified_bundle(source_audit, retain={'review.jsonl'})
    rule = json.loads(policy.read_text())
    if (dm.get('version') != cohort.VERSION or am.get('version') != audit.VERSION
            or am['dataset_manifest_sha256'] != digest(dataset/'complete.json')
            or am['dataset_observations_sha256'] != dm['files']['observations.jsonl']
            or rule.get('dataset_manifest_sha256') != digest(dataset/'complete.json')
            or rule.get('audit_manifest_sha256') != digest(source_audit/'complete.json')):
        raise ValueError('Current source/audit/policy lineage differs')
    original = cohort.records(df['observations.jsonl'])
    kept, decisions = assemble(original, cohort.records(df['current-source-evidence.jsonl']),
                              cohort.records(af['review.jsonl']), rule)
    summary = {'rows': len(kept), 'current_rows': len(decisions),
        'historical_rows': len(kept)-len(decisions), 'historical_rows_preserved_exactly': True,
        'units': len({r['unit_id'] for r in kept}), 'buildings': len({r['building'] for r in kept}),
        'action_counts': dict(Counter(d['action'] for d in decisions)),
        'tagged_current_rows': sum(bool(d['residual_review_tags']) for d in decisions),
        'prices_reported_counts_and_membership_preserved': True,
        'policy': 'Limited price/product/scope and named bathroom review for exploratory fitting. Preserve unresolved source claims and original knowledge clocks; interpreted_at dates this review, not a physical change. No blanket accuracy claim or model promotion.'}
    return publish_bundle(output, {
        'observations.jsonl': ''.join(canonical(r)+'\n' for r in kept),
        'current-source-evidence.jsonl': df['current-source-evidence.jsonl'].decode(),
        'source-audit.jsonl': af['review.jsonl'].decode(),
        'decisions.jsonl': ''.join(canonical(d)+'\n' for d in decisions),
        'review-policy.json': canonical(rule)+'\n', 'summary.json': canonical(summary)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': VERSION, 'source_manifest_sha256': digest(dataset/'complete.json'),
        'source_observations_sha256': dm['files']['observations.jsonl'],
        'source_audit_manifest_sha256': digest(source_audit/'complete.json'),
        'review_status': 'limited_source_review_for_exploratory_fit',
        'reviewed_at': rule['interpreted_at'], 'summary': summary,
        'implementation_sha256': {Path(m.__file__).name: digest(m.__file__) for m in (cohort, audit)}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'source_audit', 'policy', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
