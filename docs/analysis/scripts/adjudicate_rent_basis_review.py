"""Record a closed, manually inspected batch of quote-context recommendations.

These recommendations do not mutate the analytical dataset. The exact packet
hash prevents extending this review to newly detected cases without inspection.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from apartments import reviewed_cohort_quarantine as q
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

PACKET_SHA = 'be63518ec14f77f90b3cbc715fd10c6365a23d3c75163c966803c6edcc8e3a5f'
VERSION = 'reviewed-rent-basis-recommendations-v1'
EXCEPTIONS = {
    '2532848': ('retain_no_price_basis_exclusion',
        'The target $4,500 is explicitly Gross Price per month; a separate $4,250 offer is net. '
        'The v3 parser attached Net to the preceding gross amount. Retain this observation for this review.',
        'Gross Price per month = $4,500 Net Effective Rent with 1 Month Free on an 18 Month Lease = $4,250'),
    '2623722': ('quarantine_unresolved_gross_price_basis',
        'The target $6,000 is explicitly net versus $6,500 gross. The text distinguishes a broker-fee payment '
        'from tenant free rent; do not infer a concession calculation or backdate a gross replacement.', None),
    '2311395': ('quarantine_unresolved_gross_price_basis',
        'The target $4,453 is the stated net quote for one of two lease-term offers; $4,618 is another net quote '
        'and $5,195 is called gross. Keep the alternative terms distinct and do not backdate a replacement.', None),
    '2902349': ('quarantine_unresolved_gross_price_basis',
        'The target $3,333 is explicitly net, with inconsistent or alternative six-month and 15–18-month '
        'offer wording. Gross basis and event-specific terms remain unresolved; do not compute a replacement.', None),
}


def run(packet, dataset, reviewed_at, output):
    packet, dataset = Path(packet), Path(dataset)
    if digest(packet/'complete.json') != PACKET_SHA: raise ValueError('This packet has not received the recorded manual review')
    pm, pf = _verified_bundle(packet, retain={'cases.jsonl'})
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    if sm['version'] != q.PARENT or digest(dataset/'complete.json') != pm['source_dataset_manifest_sha256']:
        raise ValueError('Reviewed source differs from the proposal parent')
    source = {r['audit_id']: r for s in sf['observations.jsonl'].decode().split('\n') if s and (r := json.loads(s))}
    cases = [r for s in pf['cases.jsonl'].decode().split('\n') if s and (r := json.loads(s))
             and r['classification'] == 'all_captures_match_explicit_net_only']
    if len(cases) != 165: raise ValueError('Closed review membership differs')
    recommendations, findings = [], []
    for case in cases:
        row = case['source_record']; ad = row['source_listing_id']
        if source[row['audit_id']] != row or instant(reviewed_at) < instant(row['known_at']):
            raise ValueError('Reviewed row or knowledge clock differs')
        action, reason, override = EXCEPTIONS.get(ad, ('quarantine_unresolved_gross_price_basis',
            'The analytical target equals an explicitly labelled net quote in every attached capture. '
            'The own ACTIVE event matches the historical target, but the later description does not resolve a '
            'gross ask for that event. Recommend exclusion from the gross-ask cohort; do not convert or replace the price.', None))
        evidence = []
        originals = {c['capture_id']: c for c in case['original_price_records']}
        for capture in case['captures']:
            original = originals[capture['capture_id']]
            if (not original['initial_event_matches_analytical_target']
                    or original['raw_listing_sha256'] != capture['raw_listing_sha256']):
                raise ValueError('Original price evidence differs')
            if override:
                start = capture['description'].find(override)
                if start < 0: raise ValueError('Manual exception quote differs')
                spans = [{'start': start, 'end': start+len(override), 'literal': override}]
            else:
                spans = [{k: a[k] for k in ('start', 'end', 'literal')} for a in capture['measurement']['amounts']
                    if a['basis_label'] == 'net' and a['equals_analytical_target']
                    and not a['preceded_by_negation'] and not a['administrative_context']]
                if not spans: raise ValueError('Missing manually reviewed target-net quote')
            evidence.append({**deepcopy(capture), 'spans': spans, 'reviewed_original_pricing': original['pricing'],
                             'initial_active_event_evidence': original['initial_active_events']})
        finding = {**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
            'action': action, 'reason': reason, 'reviewer': 'codex', 'reviewed_at': reviewed_at,
            'source_row_sha256': q.sha(row), 'evidence': evidence,
            'adjudication_packet_manifest_sha256': PACKET_SHA, 'recommendation_only': True}
        finding['decision_id'] = q.sha(finding)
        if action.startswith('quarantine_'):
            q.validate_decision(row, finding, reviewed_at)
            recommendations.append(finding)
        findings.append(finding)
    if len(recommendations) != 164: raise ValueError('Reviewed exception count differs')
    recommendations.sort(key=lambda r: r['audit_id'])
    proposed = {r['audit_id'] for r in recommendations}
    kept = [r for r in source.values() if r['audit_id'] not in proposed]
    summary = {'version': VERSION, 'reviewed_cases': len(findings), 'proposed_quarantines': len(recommendations),
        'retained_exception_ads': ['2532848'], 'main_selection_changed': False, 'source_rows_changed': 0,
        'hypothetical_rows_after_only_these_recommendations': len(kept),
        'hypothetical_units': len({r['unit_id'] for r in kept}),
        'hypothetical_buildings': len({r['building'] for r in kept}),
        'affected_buildings': dict(Counter(source[r['audit_id']]['building'] for r in recommendations).most_common()),
        'review_scope': 'Inspected extracted literal target-quote contexts for all 165 selected observations, '
            'original pricing/event checks for every attached capture, and full descriptions of the listed exceptions. '
            'Recommendations concern unresolved gross price basis, not proof of net terms at the initial event. '
            'No numerical conversions or changes to the analytical cohort. The other 94 packet cases remain pending.'}
    publish_bundle(output, {'findings.jsonl': ''.join(canonical(r)+'\n' for r in findings),
        'proposed-quarantines.jsonl': ''.join(canonical(r)+'\n' for r in recommendations),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'reviewed_at': reviewed_at, 'packet_manifest_sha256': PACKET_SHA,
         'source_manifest_sha256': digest(dataset/'complete.json'),
         'source_observations_sha256': sm['files']['observations.jsonl']})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('packet', 'dataset', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--reviewed-at', required=True)
    run(**vars(parser.parse_args()))
