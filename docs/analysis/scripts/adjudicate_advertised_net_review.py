"""Publish the closed review of the remaining 94 original-price packet cases.

No historical gross prices are inferred, and this command does not alter a source
dataset. Capture-level pricing and literal wording are separate evidence.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from apartments import reviewed_cohort_quarantine as q
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from docs.analysis.scripts.adjudicate_rent_basis_review import PACKET_SHA

VERSION = 'reviewed-advertised-net-recommendations-v1'
# Explicit membership records the inspected packet, not a rule for future ads.
MATCHED_ADS = set('''1694924 1697102 1694940 1716016 1715804 1706387 1725723
1738059 1743236 2030707 2024934 2050837 2265090 2301820 2373524 2378616
2428860 2585883 2584225 2658166 2650273 2761129 2757350 2883994 2916216
2914465 2947623 2987878 2996392 3029992 3030003 3030013 3030034 3030030
3063219 3099401 3063192 3063223 3063213 3063210 3099381 3063201 3085553
3166246 3166822'''.split())
GROSS_ADS = {'2079352', '2475341', '2494632', '2530622', '2657527', '3092641'}


def records(blob):
    return [json.loads(s) for s in blob.decode().split('\n') if s]


def capture_key(value):
    return canonical({'type': type(value).__name__, 'value': value})


def review_case(case, row, reviewed_at):
    if case['source_record'] != row or instant(reviewed_at) < instant(row['known_at']):
        raise ValueError('Source row or review clock differs')
    ad = row['source_listing_id']
    captures = {capture_key(c['capture_id']): c for c in case['captures']}
    originals = {capture_key(c['capture_id']): c for c in case['original_price_records']}
    expected = {capture_key(c) for c in row['capture_ids']}
    if (len(captures) != len(case['captures']) or len(originals) != len(case['original_price_records'])
            or captures.keys() != expected or originals.keys() != expected):
        raise ValueError('Every typed source capture must have original-price evidence')
    if ad in MATCHED_ADS:
        action = 'quarantine_unresolved_gross_price_basis'
        reason = ('Every captured price equals the historical target and its description explicitly calls the '
            'advertised price net. This joins captured pricing to literal wording, not a quoted target amount. '
            'The initial own ACTIVE event agrees with the target, but event-specific gross basis remains '
            'unresolved. Recommend quarantine without calculating or backdating a replacement.')
        if ad == '2265090':
            reason = ('The furnished listing advertises $19,500, calls its advertised price net, and separately '
                'quotes $18,000 gross with one month free. These amounts conflict. Recommend quarantine for '
                'unresolved gross basis; do not interpret $19,500 as a verified net amount or repair either price.')
    elif ad in GROSS_ADS:
        action = 'retain_explicit_gross_target'
        reason = ('The historical target matches an explicit gross quote. The captured listing price differs '
            'and the ad calls its advertised price net. Retain the historical target for this review; a later '
            'net statement alone does not overturn the explicit gross-target evidence.')
    else:
        action = 'defer_event_specific_price_basis'
        reason = ('The captured price differs from the historical target. A later advertised-net statement '
            'does not identify the initial event price basis. Keep this observation unchanged pending '
            'date-specific evidence; do not certify it as gross, backdate the later terms, or calculate a price.')
    evidence = []
    for key, capture in captures.items():
        original = originals[key]
        if (original['raw_listing_sha256'] != capture['raw_listing_sha256']
                or original['source_listing_id'] != ad or capture['source_listing_id'] != ad
                or original['audit_id'] != row['audit_id'] or capture['audit_id'] != row['audit_id']
                or original['initial_event_matches_analytical_target'] is not True
                or not original['initial_active_events']
                or any(e['price'] != row['asking_rent'] or e['status'] != 'ACTIVE'
                       or e['event_listing_id'] != ad for e in original['initial_active_events'])):
            raise ValueError('Original price or listing evidence differs')
        price = original['pricing']['price']
        claims = [s for s in capture['measurement']['advertised_net_statements']
                  if not s['preceded_by_negation'] and not s['administrative_context']]
        if not claims: raise ValueError('Missing affirmative advertised-net statement')
        if ad in MATCHED_ADS and price != row['asking_rent']:
            raise ValueError('Reviewed capture price no longer matches the historical target')
        if ad not in MATCHED_ADS and price == row['asking_rent']:
            raise ValueError('Unreviewed matching captured price')
        if ad in GROSS_ADS:
            gross = [s for s in capture['measurement']['amounts'] if s['basis_label'] == 'gross'
                     and s['equals_analytical_target'] and not s['preceded_by_negation']]
            if not gross: raise ValueError('Missing explicit gross-target quote')
            # 2475341's amount is flagged administrative because board approval
            # appears later in its context window. The full ad was reviewed.
            if any(s['administrative_context'] for s in gross) and ad != '2475341':
                raise ValueError('Unreviewed administrative-context exception')
            claims += gross
        spans = [{k: s[k] for k in ('start', 'end', 'literal')} for s in claims]
        for s in spans:
            if capture['description'][s['start']:s['end']] != s['literal']:
                raise ValueError('Reviewed literal span differs')
        evidence.append({**deepcopy(capture), 'spans': spans,
            'reviewed_original_pricing': deepcopy(original['pricing']),
            'initial_active_event_evidence': deepcopy(original['initial_active_events']),
            'captured_price_equals_historical_target': price == row['asking_rent']})
    finding = {**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
        'action': action, 'reason': reason, 'reviewer': 'codex', 'reviewed_at': reviewed_at,
        'source_row_sha256': q.sha(row), 'evidence': evidence,
        'adjudication_packet_manifest_sha256': PACKET_SHA, 'recommendation_only': True}
    finding['decision_id'] = q.sha(finding)
    if action.startswith('quarantine_'): q.validate_decision(row, finding, reviewed_at)
    return finding


def run(packet, dataset, reviewed_at, output):
    packet, dataset = Path(packet), Path(dataset)
    if digest(packet/'complete.json') != PACKET_SHA:
        raise ValueError('This exact packet has not received the recorded manual review')
    pm, pf = _verified_bundle(packet, retain={'cases.jsonl'})
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    if sm['version'] != q.PARENT or digest(dataset/'complete.json') != pm['source_dataset_manifest_sha256']:
        raise ValueError('Reviewed source differs from packet parent')
    source = {r['audit_id']: r for r in records(sf['observations.jsonl'])}
    cases = [r for r in records(pf['cases.jsonl']) if r['classification'] != 'all_captures_match_explicit_net_only']
    ads = {r['source_record']['source_listing_id'] for r in cases}
    if len(cases) != 94 or len(ads) != 94 or not MATCHED_ADS | GROSS_ADS <= ads:
        raise ValueError('Closed reviewed membership differs')
    findings = [review_case(c, source[c['source_record']['audit_id']], reviewed_at) for c in cases]
    proposed = sorted([r for r in findings if r['action'].startswith('quarantine_')], key=lambda r: r['audit_id'])
    counts = dict(Counter(r['action'] for r in findings))
    if sorted(counts.values()) != [6, 43, 45]: raise ValueError('Closed review outcomes differ')
    summary = {'version': VERSION, 'reviewed_cases': len(findings), 'outcomes': counts,
        'proposed_quarantines': len(proposed), 'main_selection_changed': False, 'source_rows_changed': 0,
        'affected_buildings': dict(Counter(source[r['audit_id']]['building'] for r in proposed)),
        'retained_gross_ads': sorted(GROSS_ADS), 'contradictory_amount_ad': '2265090',
        'review_scope': 'All 94 extracted quote contexts and attached capture prices/own-event histories inspected; '
            'full descriptions additionally inspected for 1694924, 2265090, 2428860, 2475341, 2585883, 3099287, 3085553, 3166246.',
        'limitations': ['Captured prices and descriptions can postdate the historical target; matching amounts do not prove historical concession terms.',
            'The 43 deferred cases remain unchanged and unresolved, not verified gross asks.',
            'Legal-rent wording is not equated with gross; no numerical rent conversion or replacement is performed.',
            'These recommendations have not been added to the 165-exclusion source candidate or fitted.']}
    publish_bundle(output, {'findings.jsonl': ''.join(canonical(r)+'\n' for r in findings),
        'proposed-quarantines.jsonl': ''.join(canonical(r)+'\n' for r in proposed),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'reviewed_at': reviewed_at, 'packet_manifest_sha256': PACKET_SHA,
         'source_manifest_sha256': digest(dataset/'complete.json'),
         'source_observations_sha256': sm['files']['observations.jsonl']})
    print(canonical(summary), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('packet', 'dataset', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--reviewed-at', required=True)
    run(**vars(parser.parse_args()))
