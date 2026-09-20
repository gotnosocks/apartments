"""Preserve eight manually reviewed descriptions and dated price-basis leads."""
import argparse
import hashlib
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

# Exact full texts reviewed, not a lexical classifier or automatic correction.
REVIEWS = {
    '00b7269e59e775bb3531155f451da74af26fec546691f59a0b56ec54f4083ae8': ('shared_amenity', 'Gross monthly rent is $9,110.'),
    '01a089ffbf5e404d248baa73ef1a792c6a1ea3a367b0b6f61968c253872ce763': ('shared_amenity', 'Gross monthly rent is $7,569.00.'),
    '01aa03934153504904ef8d736c471fae0730eff27bbf9852cda4c64fe408ee01': ('shared_amenity', 'Gross monthly rent is $5,225.'),
    '01e2e6ae6b7d05ed5205b9144e14f34dbab35ae7b4113b240b1649a1e1fcf9a8': ('shared_amenity', 'Net effective price shown including one month free on a 15 month lease. Gross monthly rent is $7,500.'),
    '01ea6eafd4b302c88f4844fcd4c64bfccce51b251ef346216290429664b55c0a': ('shared_amenity', 'Event Space'),
    '02019748db8901431b4682b8033b4465024eda3a9f9102437cf9f011e058eae4': ('appliance', 'additional commercial washer and dryer located in the basement'),
    '026715108b018415cd66b15f437a6a3898335ef1b8b7e8fa96ffd84254693d00': ('home_office', 'a cozy den which can be used as a bright bedroom or office space'),
    '02be9c1a2b5deb0aa8566157e68f5275ff3fa5ea4a51d77f770831c1353682ac': ('home_office', '5th floor facing tree lined middle of 16th street.'),
}
PRICE_LEADS = {'2834394': 9110, '2560481': 7569, '2362330': 5225, '2967520': 7500}


def run(groups, screen, output):
    groups, screen, output = map(Path, (groups, screen, output))
    bindings = {'groups': '49d393e968f3c0ae81e087b0c5f23c1087296621b65de40c46a2d6fcb324d29f',
                'screen': 'cd15f51866365e5f7ad68f4f517a031120e049c42bebc1edbe6da7b62c9c43d9'}
    for name, path in [('groups', groups), ('screen', screen)]:
        if digest(path/'complete.json') != bindings[name]:
            raise ValueError('Manual review input differs')
    _, gf = _verified_bundle(groups, retain={'groups.jsonl'})
    _, sf = _verified_bundle(screen, retain={'cases.jsonl'})
    cases = [json.loads(l) for l in sf['cases.jsonl'].decode().split('\n') if l]
    by_id = {c['source_row']['audit_id']: c for c in cases}
    selected = [json.loads(l) for l in gf['groups.jsonl'].decode().split('\n') if l]
    selected = [g for g in selected if g['description_sha256'] in REVIEWS]
    if len(selected) != len(REVIEWS):
        raise ValueError('Review membership differs')
    review, leads = [], {}
    for g in selected:
        kind, phrase = REVIEWS[g['description_sha256']]
        text = g['description']
        if hashlib.sha256(text.encode()).hexdigest() != g['description_sha256']:
            raise ValueError('Description differs')
        start = text.index(phrase)
        review.append({**g, 'manual_disposition': 'incidental_'+kind,
            'scope_exclusion_supported': False,
            'literal_evidence': {'start': start, 'end': start+len(phrase), 'literal': phrase}})
        for a in g['associations']:
            c = by_id[a['audit_id']]
            if hashlib.sha256(canonical(c['source_row']).encode()).hexdigest() != a['source_row_sha256']:
                raise ValueError('Associated analytical row differs')
            if a['source_listing_id'] in PRICE_LEADS:
                leads[a['audit_id']] = {**c,
                    'captured_description_gross_rent': PRICE_LEADS[a['source_listing_id']],
                    'historical_price_basis_confirmed': False, 'replacement_price': None,
                    'interpretation': 'Later-captured gross/concession wording needs historical event alignment; no automatic rent replacement.'}
    summary = {'reviewed_groups': len(review), 'price_basis_lead_observations': len(leads),
        'scope_exclusions': 0, 'remaining_groups_after_prior_batches': 498,
        'limitation': 'Full-text product-language review, not legal occupancy or historical price-basis certification.'}
    publish_bundle(output, {'review.jsonl': ''.join(canonical(r)+'\n' for r in review),
        'price-basis-leads.jsonl': ''.join(canonical(r)+'\n' for _, r in sorted(leads.items())),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': 'commercial-manual-batch-two-v1', 'input_manifests': bindings,
         'source_or_model_changes': False})
    _verified_bundle(output)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('groups', 'screen', 'output'):
        p.add_argument('--'+name, required=True)
    print(canonical(run(**vars(p.parse_args()))))
