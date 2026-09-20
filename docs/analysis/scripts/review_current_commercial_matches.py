"""Record full-text review of all five captured-current commercial-screen hits."""
import argparse
import hashlib
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

GROUPS = {
    '111c69378377e691361c387ac70320f108442c2f4baf21a8378c024dbaefdd04': 'residential_home_office',
    '3e5ddd2e79c39129add9621545f1ac5405aad4ddbe0c518269ff241268813e48': 'residential_shared_amenity',
    'd355f31648adf82d529a9460da767f76504f89ba2c545cddeeb70a48a76cb853': 'residential_shared_amenity',
}
CURRENT_ADS = {'5082877', '5091291', '5091292', '5122323', '5112590'}


def run(groups, output):
    groups, output = Path(groups), Path(output)
    if digest(groups/'complete.json') != '49d393e968f3c0ae81e087b0c5f23c1087296621b65de40c46a2d6fcb324d29f':
        raise ValueError('Manual review binds a different group bundle')
    _, files = _verified_bundle(groups, retain={'groups.jsonl'})
    all_groups = [json.loads(line) for line in files['groups.jsonl'].decode().split('\n') if line]
    selected = [g for g in all_groups if g['description_sha256'] in GROUPS]
    current = [a for g in selected for a in g['associations'] if a['analysis_price_basis'] == 'current_capture_gross_ask']
    all_current = [a for g in all_groups for a in g['associations'] if a['analysis_price_basis'] == 'current_capture_gross_ask']
    assert canonical(current) == canonical(all_current)
    assert {a['source_listing_id'] for a in current} == CURRENT_ADS
    assert len({a['audit_id'] for a in current}) == 5 and len(selected) == 3
    review, costs = [], []
    for group in selected:
        text = group['description']
        assert hashlib.sha256(text.encode()).hexdigest() == group['description_sha256']
        disposition = GROUPS[group['description_sha256']]
        phrases = (['Dressing room off the bath can be used as an office space.']
            if disposition == 'residential_home_office' else
            ['HOTEL-INSPIRED AMENITIES', 'Event Space', 'Price shown is Base Rent.',
             'Community Amenity Fee - $90 per resident per month [required]'])
        spans = []
        for phrase in phrases:
            start = text.index(phrase)
            spans.append({'start': start, 'end': start+len(phrase), 'literal': phrase})
        review.append({**group, 'manual_disposition': disposition,
            'literal_evidence': spans, 'scope_exclusion_supported': False,
            'interpretation': 'The matched phrase describes residential use or shared amenities; no offered nonresidential product identified in the full text. This is not a legal-occupancy finding.'})
        if disposition == 'residential_shared_amenity':
            for association in group['associations']:
                if association['analysis_price_basis'] != 'current_capture_gross_ask':
                    continue
                costs.append({'association': association,
                    'description_sha256': group['description_sha256'],
                    'base_rent_claim': True, 'required_amenity_fee': {'currency': 'USD', 'amount': 90,
                        'period': 'month', 'basis': 'resident', 'mandatory_claim': True},
                    'literal_evidence': spans[2:], 'household_resident_count': None,
                    'all_in_monthly_total': None,
                    'interpretation': 'Capture-scoped advertised fee; do not add to historical prices or infer household size. Usage-based electricity and optional/situational fees remain separate. No asking-rent correction applied.'})
    assert {c['association']['source_listing_id'] for c in costs} == CURRENT_ADS-{'5082877'}
    summary = {'reviewed_full_description_groups': 3, 'captured_current_observations': 5,
        'scope_exclusions': 0, 'current_ads_with_explicit_required_per_resident_fee': 4,
        'historical_fee_assignments': 0, 'remaining_unreviewed_groups_after_priority_and_current_batches': 506}
    publish_bundle(output, {'review.jsonl': ''.join(canonical(r)+'\n' for r in review),
        'current-fee-research.jsonl': ''.join(canonical(c)+'\n' for c in costs),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': 'current-commercial-match-review-v1',
         'groups_manifest_sha256': digest(groups/'complete.json'), 'source_or_model_changes': False})
    _verified_bundle(output)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--groups', required=True)
    p.add_argument('--output', required=True)
    print(canonical(run(**vars(p.parse_args()))))
