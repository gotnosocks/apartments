"""Publish full-description adjudications for the 27-case movement panel."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


# Manually adjudicated after reading every distinct full description. Phrases
# locate evidence; they are not a classifier or a numerical correction rule.
REVIEW = {
    '5083167': ('luxury_bundle', 'Wraparound terraces, four exposures and two primary-suite en-suite baths; do not infer a numeric floor from penthouse wording.', ['two luxurious en-suite baths', 'wraparound terraces']),
    '790520': ('bathroom_and_layout_conflict', 'Reported one full bath conflicts with prose three baths; five bedrooms not established by a configurable build-to-suit loft. Explicit second/third-floor duplex and walkup evidence needs multilevel representation.', ['2 new kitchens and 3 baths', '2nd and 3rd floor', 'will be built out']),
    '1926797': ('bedroom_configuration_conflict', 'Reported two bedrooms versus currently one with possible conversion to two or three. Preserve present-layout versus potential-layout distinction and caretaker/studio wording.', ['currently set up as a fabulous one bedroom', 'can easily be converted']),
    '2756894': ('layout_and_ensuite_evidence', 'Three bedrooms plus flexible office/sleeping area and four described en-suite bathrooms. No supported numerical correction; track flexible-room and en-suite evidence separately.', ['home office / sleeping area', 'own ensuite bathroom']),
    '4210456': ('bedroom_configuration_conflict', 'Reported four bedrooms versus three bedrooms plus dedicated office in prose. Combined label 5AE alone is not explicit floor evidence.', ['a dedicated home office, three bedrooms and four full baths']),
    '3915487': ('luxury_bundle', 'Private heated pool, multiple terraces and explicit 4.5 baths; bathroom count agrees. Whole duplex levels are not a building-floor correction.', ['private pool', '4.5 baths']),
    '4811825': ('residential_location_corroboration', 'Own prose consistently describes a residential condo at 133 W14. Loft 4 is a unit identifier, not a numeric floor claim; do not quarantine siblings of a bad advertisement.', ['Loft 4 at 133 West 14th Street', 'keyed elevator landing']),
    '1376670': ('furnished_term_bundle', 'Furnished offer for 3–24 months; establish package at historical ask before feature projection or price comparison.', ['elegantly furnished, from 3-24 months']),
    '1543471': ('explicit_nonresidential', 'Explicit commercial-use loft and business offer. Prepare exact-ad residential-scope quarantine; retain quoted source price.', ['all commercial uses', 'start your business']),
    '4892020': ('whole_townhouse', 'Whole four-story townhouse with private elevator/garden. Interior second-floor suite does not give a single advertised floor. Multiple-half-bath source review remains separate.', ['Four-story Greek Revival townhouse', 'Elevator with access to all floors']),
    '610152': ('luxury_bundle', 'Private-floor penthouse with two terraces. Building height of 23 stories is not apartment-floor evidence; description ends abruptly.', ['private floor penthouse', '23-story tower']),
    '3967693': ('explicit_floor_extraction_gap', 'Explicit second floor with unit label one; retain independent floor and unit number. Virtual staging does not establish furnished availability.', ['FLOOR TWO, UNIT ONE', 'entire second floor', 'Furnished photos are virtually staged']),
    '2391701': ('explicit_nonresidential', 'Recording studio in commercial co-op, with client/employee space and commercial lease terms. Prepare exact-ad residential-scope quarantine.', ['FULLY BUILT OUT RECORDING STUDIO', 'Commercial Co-op', 'employees/Clients']),
    '4153172': ('parking_package', 'Included valet garage space, terrace and en-suite bathrooms are product features. Residence 9 and full-floor wording do not independently establish numeric floor.', ['PARKING GARAGE SPACE WITH VALET IS INCLUDED', 'both have en-suite baths']),
    '4189081': ('residential_location_corroboration', 'Residential full-floor condo, terrace-free description with private elevator, luxury baths and basement storage. No explicit numeric floor; turn-key does not prove furnished.', ['south-facing full floor condo', 'keyed private elevator access']),
    '754637': ('optional_furnishing', 'Explicit vacant or semi-furnished alternatives; historical ask package is unresolved. High ceilings and perched-up-high wording do not establish floor.', ['Available vacant or semi-furnished']),
    '776029': ('explicit_floor_extraction_gap', 'Explicit first-floor walkup claim while analytical floor is unknown. Preserve advertised floor separately from physical height.', ['This first floor walk-up apartment']),
    '2976274': ('luxury_bundle', 'Duplex with private pool and three private terraces. Future-tense building services are not proof they were available at initial ask.', ['rooftop terrace with its own private pool', 'will include indulgent services']),
    '3865188': ('private_garage_bundle', 'Private attached garage via car elevator, plus passenger elevator and duplex layout; distinguish vehicle and passenger access.', ['private garage attached to your apartment', 'passenger elevator']),
    '2021775': ('furnished_offer', 'Explicit furnished rental, already annotated in candidate source issues. Preserve strength of wording and same-ad historical timing caveat.', ['This furnished rental']),
    '806884': ('explicit_nonresidential', 'Event/office space offered daily and weekly with no advertised prose price. Prepare exact-ad scope quarantine; do not interpret recorded ask as monthly apartment rent.', ['We are renting the space daily and weekly', 'Office spaces are limited']),
    '1451209': ('luxury_bundle', 'Terrace and multiple exposures with two en-suite bedrooms and separate laundry/utility room. No new count contradiction identified.', ['285-square foot terrace', 'second bedroom features access to the terrace']),
    '4549241': ('luxury_bundle', 'Four bedrooms each with en-suite bath plus powder room agree with reported composition. Anticipated hotel services are future claims.', ['three additional generously sized bedrooms, each with its own en-suite bath', 'Anticipated Faena Hotel services']),
    '4316485': ('whole_townhouse', 'Whole townhouse with terraces, garden and separately accessed garden level. Third-floor primary suite is not a single unit-floor measurement.', ['entire third floor is dedicated to the primary suite', 'With its own private entrance, the garden level']),
    '916757': ('flexible_bedroom_layout', 'Three reported bedrooms; prose mixes two bedrooms, a convertible den and an upstairs fourth bedroom. Review present versus potential bedroom count; no automatic correction.', ['a den that can be the 3rd bedroom', 'a 4th bedroom']),
    '3883529': ('residential_location_corroboration', 'Residential full-floor condo and private terrace with explicit 2.5 baths; supports retaining this ad despite a different same-building location-conflict ad.', ['full floor condo loft with a private terrace', '2.5 spa-like baths']),
    '947730': ('explicit_nonresidential', 'Explicit gallery/office commercial condo with showroom/retail use. Prepare exact-ad residential-scope quarantine, not building-wide exclusion.', ['loft/gallery/office commercial condo', 'showroom and retail events']),
}


def run(inputs, archive, output):
    inputs, archive, output = map(Path, (inputs, archive, output))
    if digest(inputs/'complete.json') != 'fee67720a2e5d9d6dfb4d163f6d2760a45c36fced708de26205b00396238867c':
        raise ValueError('Manual review applies only to the exact reviewed input bundle')
    manifest, files = _verified_bundle(inputs, retain={'cases.jsonl', 'group-review-examples.json'})
    cases = [json.loads(line) for line in files['cases.jsonl'].decode().split('\n') if line]
    assert len(cases) == 27 and {c['observation']['source_listing_id'] for c in cases} == set(REVIEW)
    queue, witnesses = [], []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for case in cases:
            row = case['observation']
            ad = row['source_listing_id']
            kind, finding, phrases = REVIEW[ad]
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
                if kind == 'explicit_nonresidential':
                    found = db.execute('SELECT raw_listing_json FROM read_parquet(?) WHERE snapshot_id=?',
                        [str(archive/'listing_observations/*.parquet'), capture['capture_id']]).fetchall()
                    assert len(found) == 1
                    raw = found[0][0]
                    assert hashlib.sha256(raw.encode()).hexdigest() == capture['raw_listing_sha256']
                    assert str(json.loads(raw)['id']) == ad
                    witnesses.append({'source_listing_id': ad, 'capture_id': capture['capture_id'],
                        'raw_listing_sha256': capture['raw_listing_sha256'], 'raw_listing_json': raw})
            queue.append({**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'analysis_price_basis')},
                'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
                'kind': kind, 'finding': finding, 'literal_evidence': evidence,
                'selection_reasons': case['selection_reasons'], 'movement': case['movement'],
                'source_or_model_changes': False})
    assert len(witnesses) == 7
    publish_bundle(output, {'queue.jsonl': ''.join(canonical(r)+'\n' for r in queue),
        'raw-scope-witnesses.jsonl': ''.join(canonical(r)+'\n' for r in witnesses),
        'group-review-examples.json': files['group-review-examples.json'].decode(),
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'reviewed-residual-scope-movements-v1',
        'input_manifest_sha256': digest(inputs/'complete.json'),
        'source_manifest_sha256': manifest['source_manifest_sha256'],
        'comparison_manifest_sha256': manifest['comparison_manifest_sha256'],
        'cases': 27, 'explicit_nonresidential_ads': 4, 'raw_scope_witnesses': 7,
        'source_or_model_changes': False,
        'temporal_scope': 'Retrospective own-ad claims; physical/offer effective dates unverified'})
    _verified_bundle(output)
    return {'output': str(output), 'manifest_sha256': digest(output/'complete.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'archive', 'output'):
        parser.add_argument('--'+name, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
