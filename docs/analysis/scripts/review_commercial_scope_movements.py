"""Publish the manually reviewed 27-case cumulative scope movement panel."""
import argparse
import hashlib
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


# Findings follow full-description reading; spans locate claims, not classifiers.
NEW = {
    '1741581': ('bathroom_composition_conflict', 'Four reported full baths and zero half baths conflict with explicit two baths and two powder rooms. Triplex interior levels do not establish one building floor. Review bathroom composition before interpreting its contribution.', ['3 bed - 2 bath - 2 powder room', 'second powder room']),
    '2938067': ('within_source_location_conflict', 'Manhattan address conflicts with repeated Park Slope/Brooklyn location claims. Separate raw-payload review verifies both captures; propose exact-ad quarantine without replacing location or price.', ['Gorgeous Park Slope 1 bedroom', 'Brooklyn Public Library']),
    '2851560': ('luxury_and_area_evidence', 'Description supplies 3840 interior square feet despite missing analytical area, plus balcony and en-suite bedrooms. Area is retrospective own-ad evidence, not yet a dated measurement. Building parking is not an included private garage.', ['3840 square feet interior', 'three additional bedrooms with en-suite baths']),
    '2944291': ('luxury_bundle', 'Five bedrooms and five baths agree with reported counts. Three terraces, multi-zone HVAC, two living rooms and duplex layout merit separate features; twelve-story building height is not the apartment floor.', ['five bedrooms and five baths', 'multi-zone HVAC system', 'three beautifully landscaped terraces']),
    '1901171': ('luxury_bundle', 'Three bedrooms and three-and-a-half baths agree. Large private terrace, home office and en-suite secondary bedrooms describe luxury features; do not count the office as a bedroom.', ['three bedrooms and three and a half bathrooms', '1,026 square-feet', 'en suite bathrooms']),
    '1262316': ('luxury_bundle', 'Two bedrooms and 2.5 baths agree. Private terrace, fireplace, multiple views and both bedrooms with en-suite baths support feature research, not count corrections.', ['2-bedroom, 2.5 bathroom', '285-square foot terrace', 'an en suite bath']),
    '4730943': ('bathroom_composition_and_live_work', 'Reported two full and two half baths conflict with the summary of two full bathrooms and one powder room. Later studio full-bath wording leaves enumeration ambiguous; do not automatically set counts. Explicit live/work residence is not a commercial-only offer.', ['rare live/work residence', 'two full bathrooms, and a powder room', 'complete with its own full bath']),
    '4094604': ('unfurnished_luxury_bundle', 'Explicitly unfurnished offer with three full bathrooms and powder room, agreeing with composition. Large private terrace and laundry closet are independent features. Offer dates remain own-ad claims.', ['delivered Unfurnished', 'three full bathrooms, and a powder room', '1,061-square feet of terrace']),
    '701563': ('furnished_short_term', 'Furnished offer for three months to one year. Terms and furnishing may affect rent; preserve historical timing uncertainty rather than treating this as an ordinary unfurnished lease.', ['Available perfectly furnished, from 3 months up to one year']),
    '3973940': ('private_pool_bundle', 'Duplex penthouse with private pool and multiple private terraces. Three bedrooms and 3.5 baths agree. Private amenities differ from shared building amenities; no numeric floor inferred.', ['three-bedroom, three-and-a-half-bathroom', 'rooftop terrace with its own private pool']),
    '1540611': ('mixed_live_work', 'Commercial condo wording coexists with explicit live/work use and residential kitchen/bath features. Retain as mixed-use research case, not an automatic commercial-only exclusion. High-floor wording supplies no numeric floor.', ['high-floor commercial condo loft', 'This apartment can be used as a live/work space']),
    '1902660': ('private_car_elevator_bundle', 'Private car lift and terraces describe a distinctive rental package. Vehicle lift is not evidence of passenger elevator access. Three bedrooms and 3.5 baths agree; penthouse wording supplies no numeric floor.', ['three-bedroom, three-and-a-half-bathroom', 'car lift which ascends from the building']),
    '2687524': ('floor_access_and_price_timing', 'Explicit one-flight-up walkup and parlor-floor residence; preserve access and advertised-floor semantics separately. Description says price reduced to 9900, not proof of initial ask. Three bedrooms and two baths agree.', ['PRICE ADJUSTMENT REDUCED TO $9900', 'Just one flight up', '6-unit walk-up building']),
    '4681420': ('bathroom_composition_corroboration', 'Unusual two-bedroom/3.5-bath combination is explicitly stated as three full baths and one half bath. Do not correct it merely for being unusual. Parking is available for purchase, not included.', ['2BR with 3 full bathrooms and 1 additional half bath', 'Parking and Storage are available for purchase']),
    '5076855': ('luxury_bundle', 'Two bedrooms and 2.5 baths agree, with two en-suite baths, private terrace and river views. Concurrent sale listing does not itself invalidate the rental offer.', ['two-bedroom and two-and-a-half bathroom', '472 square feet of outdoor space', 'Also listed for sale']),
    '1171083': ('short_term_and_floor_access', 'Explicit month-to-month rental with two full baths, en-suite primary bath, washer/dryer and one-flight-up access. Investigate lease-term premium separately from building effects; access does not independently establish canonical numeric floor.', ['Available for short term, month to month leases', 'two full baths', 'One flight up']),
}


def run(inputs, prior_inputs, prior_review, location_review, output):
    inputs, prior_inputs, prior_review, location_review, output = map(
        Path, (inputs, prior_inputs, prior_review, location_review, output))
    expected = [(inputs, 'cd8d5229dd8dc83ec3058ebe9f7828422caab22b5b913c83a2da70c8ac546031'),
                (prior_inputs, 'fee67720a2e5d9d6dfb4d163f6d2760a45c36fced708de26205b00396238867c'),
                (prior_review, '26a6949af94a168aa5f8f4a930dcb5b8b1dd10d0273209d91b0d09dd5069e70d'),
                (location_review, 'e69a5bd1af646ff887b564294ed13beaa4a3ff9189a4c34ce498828c1e890042')]
    for root, sha in expected:
        if digest(root/'complete.json') != sha:
            raise ValueError('Manual review binding changed: ' + str(root))
    manifest, files = _verified_bundle(inputs, retain={'cases.jsonl'})
    _, old_files = _verified_bundle(prior_inputs, retain={'cases.jsonl'})
    _, review_files = _verified_bundle(prior_review, retain={'queue.jsonl'})
    _verified_bundle(location_review)
    parse = lambda data: [json.loads(s) for s in data.decode().split('\n') if s]
    cases = parse(files['cases.jsonl'])
    old = {c['observation']['source_listing_id']: c for c in parse(old_files['cases.jsonl'])}
    reviewed = {r['source_listing_id']: r for r in parse(review_files['queue.jsonl'])}
    queue, reused = [], 0
    for case in cases:
        row = case['observation']; ad = row['source_listing_id']
        row_hash = hashlib.sha256(canonical(row).encode()).hexdigest()
        if ad not in NEW:
            assert case['observation'] == old[ad]['observation']
            assert case['descriptions'] == old[ad]['descriptions']
            previous = reviewed[ad]
            assert previous['source_row_sha256'] == row_hash
            result = {**previous, 'reused_review_manifest_sha256': digest(prior_review/'complete.json')}
            reused += 1
        else:
            kind, finding, phrases = NEW[ad]
            evidence = []
            for capture in case['descriptions']:
                description = capture['description']
                assert hashlib.sha256(description.encode()).hexdigest() == capture['description_sha256']
                spans = []
                for phrase in phrases:
                    start = description.index(phrase)
                    spans.append({'start': start, 'end': start+len(phrase), 'text': phrase})
                evidence.append({'capture_id': capture['capture_id'],
                                 'description_sha256': capture['description_sha256'], 'spans': spans})
            result = {**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'analysis_price_basis')},
                      'source_row_sha256': row_hash, 'kind': kind, 'finding': finding,
                      'literal_evidence': evidence, 'source_or_model_changes': False}
            if ad == '2938067':
                result['raw_review_manifest_sha256'] = digest(location_review/'complete.json')
        queue.append({**result, 'selection_reasons': case['selection_reasons'], 'movement': case['movement']})
    assert len(queue) == 27 and reused == 11
    assert {r['source_listing_id'] for r in queue if 'reused_review_manifest_sha256' not in r} == set(NEW)
    publish_bundle(output, {'queue.jsonl': ''.join(canonical(r)+'\n' for r in queue),
                           Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'reviewed-commercial-scope-movements-v1', 'cases': 27,
        'exact_prior_reviews_reused': reused, 'new_full_description_reviews': len(NEW),
        'input_manifest_sha256': digest(inputs/'complete.json'),
        'source_manifest_sha256': manifest['source_manifest_sha256'],
        'comparison_manifest_sha256': manifest['comparison_manifest_sha256'],
        'prior_input_manifest_sha256': digest(prior_inputs/'complete.json'),
        'prior_review_manifest_sha256': digest(prior_review/'complete.json'),
        'location_review_manifest_sha256': digest(location_review/'complete.json'),
        'source_or_model_changes': False,
        'limitations': 'Retrospective own-ad claims; effective dates unverified. Description review does not establish physical truth or legal occupancy. No source corrections applied.'})
    _verified_bundle(output)
    return {'output': str(output), 'manifest_sha256': digest(output/'complete.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'prior_inputs', 'prior_review', 'location_review', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), required=True)
    print(canonical(run(**vars(parser.parse_args()))))
