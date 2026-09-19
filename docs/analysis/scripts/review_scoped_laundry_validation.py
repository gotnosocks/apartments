"""Record manual review of the frozen building-disjoint laundry sample."""
from collections import Counter
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models.laundry_source_audit import records


def main():
    root = Path(__file__).resolve().parents[3]
    source = root/'data/model/chelsea-scoped-laundry-evaluation-20260919'
    _, payload = _verified_bundle(source, retain={'validation-sample.jsonl', 'captures.jsonl'})
    sample = records(payload['validation-sample.jsonl'])
    expected_ids = ['4883582', '4976214', '4977707', '4942061', '1934853', '4540161',
                    '2378596', '2324001', '4601892', '3642551', '5071826', '1542416',
                    '2047104', '2031666', '1183994', '1085674']
    assert [r['source_listing_id'] for r in sample] == expected_ids
    decisions = []
    for index, row in enumerate(sample):
        same_floor = index >= 12
        denial = index in (8, 9, 11)
        hookups = index in (4, 5, 6, 7)
        if index < 4:
            reason = 'Every-floor wording modifies trash disposal. Laundry is separately reported on-site; no same-floor laundry claim.'
        elif hookups:
            reason = 'Explicit hookup/installation language does not establish installed private equipment. Preserve any conflicting same-capture structured assertion for review.'
        elif index == 9:
            reason = 'No Laundry Room On-Site denies shared laundry-room availability; it does not deny private equipment.'
        elif denial:
            reason = 'Denial explicitly concerns building laundry; private equipment remains unestablished.'
        elif index == 10:
            reason = 'Unqualified no-laundry wording has no explicit facility scope; retain for review rather than asserting two absences.'
        elif index in (12, 13):
            reason = 'The building-features clause places complimentary washer/dryer laundry on your floor. It establishes shared same-floor access; it does not establish private equipment absence.'
        elif index == 14:
            reason = 'Coordinated laundry and roof deck are described as right on the floor. Both refer to shared building amenities here.'
        else:
            reason = 'Central laundry room on the floor explicitly establishes shared same-floor facilities.'
        state = row['measurement']['states']
        detected = state['shared_same_floor'] is True
        decisions.append({**{k: row[k] for k in ('audit_id', 'capture_id', 'source_listing_id', 'unit_id', 'building', 'body_sha256', 'description_sha256')},
            'sample_index': index, 'reviewer': 'Codex manual source-text review', 'rationale': reason,
            'expected_same_floor_positive_claim': same_floor,
            'expected_shared_building_denial': denial, 'expected_hookup_review': hookups,
            'detected_same_floor_positive_claim': detected,
            'missed_same_floor': same_floor and not detected,
            'unsupported_same_floor': detected and not same_floor,
            'missed_shared_denial': denial and state['shared_building'] is not False,
            'hookup_review_present': any(r['kind'] == 'optional_or_uninstalled' for r in row['measurement']['review']),
            'changes_model_input': False})
    captures = records(payload['captures.jsonl'])
    support = {}
    for name in ('in_unit', 'on_floor', 'in_building', 'none', 'unknown'):
        group = [r for r in captures if (r['measurement']['most_convenient_reported_option'] or 'unknown') == name]
        support[name] = {'captures': len(group), 'observations': len({r['audit_id'] for r in group}),
                         'units': len({r['unit_id'] for r in group}), 'buildings': len({r['building'] for r in group})}
    summary = {'version': 'scoped-laundry-disjoint-validation-v1', 'cases': len(decisions),
        'buildings': len({r['building'] for r in decisions}),
        'same_floor_positive_cases': sum(r['expected_same_floor_positive_claim'] for r in decisions),
        'same_floor_misses': sum(r['missed_same_floor'] for r in decisions),
        'same_floor_false_positives': sum(r['unsupported_same_floor'] for r in decisions),
        'shared_denial_misses': sum(r['missed_shared_denial'] for r in decisions),
        'hookup_cases': sum(r['expected_hookup_review'] for r in decisions),
        'hookup_misses': sum(r['expected_hookup_review'] and not r['hookup_review_present'] for r in decisions),
        'candidate_support_not_final_model_support': support,
        'decision': 'Not ready for model projection. Same-floor paraphrases and a shared-room denial are missed. Broader full-corpus validation and capture reconciliation remain necessary.',
        'limitations': ['16 selected cases across 11 buildings, with clustered repeated building copy; not a population accuracy estimate.',
                       'Manual labels were recorded after extractor v1 was frozen. Any adjustment using them makes this sample development evidence for the next version.',
                       'Candidate category counts overlap units and are limited to the lexical audit; they are not full-cohort mutually exclusive support.']}
    publish_bundle(root/'data/model/chelsea-scoped-laundry-validation-20260919', {
        'summary.json': canonical(summary)+'\n', 'decisions.jsonl': ''.join(canonical(r)+'\n' for r in decisions),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': summary['version'], 'evaluation_manifest_sha256': digest(source/'complete.json')})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    main()
