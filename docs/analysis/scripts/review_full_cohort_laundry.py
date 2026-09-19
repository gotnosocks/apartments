"""Compare full-cohort laundry v3 against existing development labels and v2.

The labels now informed development. Their agreement is not independent accuracy.
"""
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models.laundry_source_audit import identity, records


def main():
    root = Path(__file__).resolve().parents[3]
    base = root/'data/model'
    v2 = base/'chelsea-full-cohort-laundry-v2-20260919'
    v3 = base/'chelsea-full-cohort-laundry-v3-20260919'
    first = base/'chelsea-laundry-location-adjudication-20260918'
    second = base/'chelsea-scoped-laundry-validation-20260919'
    bundles = [_verified_bundle(p, retain={'captures.jsonl', 'observations.jsonl', 'summary.json'}) for p in (v2, v3)]
    a, b = ({identity(r): r for r in records(payload['captures.jsonl'])} for _, payload in bundles)
    assert a.keys() == b.keys()
    _, dev = _verified_bundle(first, retain={'decisions.jsonl'})
    _, validation = _verified_bundle(second, retain={'decisions.jsonl'})
    labels = records(dev['decisions.jsonl']) + records(validation['decisions.jsonl'])
    comparisons = []
    for label in labels:
        key = identity(label)
        assert key in b
        row = b[key]
        assert row['description_sha256'] == label['description_sha256']
        positive = label.get('expected_same_floor_positive_claim', label.get('decision') == 'shared_on_floor_claim')
        denial = label.get('expected_shared_building_denial', label.get('decision') == 'no_building_laundry_claim')
        hooks = label.get('expected_hookup_review', label.get('decision') == 'hookup_only_claim')
        state = row['measurement']['states']
        comparisons.append({**label, 'measurement': row['measurement'],
            'same_floor_agrees': (state['shared_same_floor'] is True) == positive,
            'shared_denial_detected': not denial or state['shared_building'] is False,
            'hookup_review_detected': not hooks or any(r['kind'] == 'optional_or_uninstalled' for r in row['measurement']['review'])})
    changed = []
    for key in sorted(a):
        before, after = a[key]['measurement'], b[key]['measurement']
        if before['most_convenient_reported_option'] != after['most_convenient_reported_option']:
            changed.append({**{k: b[key][k] for k in ('audit_id', 'capture_id', 'source_listing_id', 'unit_id', 'building', 'description_sha256')},
                'before': before, 'after': after})
    summary = {'version': 'full-cohort-laundry-development-review-v1', 'labeled_cases': len(comparisons),
        'same_floor_disagreements': sum(not r['same_floor_agrees'] for r in comparisons),
        'shared_denial_misses': sum(not r['shared_denial_detected'] for r in comparisons),
        'hookup_review_misses': sum(not r['hookup_review_detected'] for r in comparisons),
        'changed_capture_categories': len(changed),
        'changed_units': len({r['unit_id'] for r in changed}),
        'changed_buildings': len({r['building'] for r in changed}),
        'model_inputs_changed': False,
        'interpretation': 'All 52 labels informed development by v3. Full-cohort category changes are candidate measurement changes, not validated correction effects. V2 over-withheld installed equipment because generic will/could wording was treated as installation uncertainty. V3 narrows that rule; independent validation and scope review remain required.'}
    publish_bundle(base/'chelsea-full-cohort-laundry-v3-review-20260919', {
        'summary.json': canonical(summary)+'\n',
        'labeled-comparison.jsonl': ''.join(canonical(r)+'\n' for r in comparisons),
        'changed-captures.jsonl': ''.join(canonical(r)+'\n' for r in changed),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': summary['version'], 'inputs': {str(p.relative_to(root)): digest(p/'complete.json') for p in (v2, v3, first, second)}})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    main()
