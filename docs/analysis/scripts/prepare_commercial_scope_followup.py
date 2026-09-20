"""Assemble nine exact-ad scope findings for the existing decision verifier.

This prepares a cumulative policy against the original expanded-floor source.
It does not apply exclusions, change prices, or start another model fit.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def rows(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line]


def run(output, policy_output):
    root = Path('data/model')
    old_policy = json.loads(Path('config/reviews/chelsea-residual-scope-20260919.json').read_text())
    old = root/'chelsea-expanded-fit-residual-research-20260919'
    movement = root/'chelsea-residual-scope-movement-review-20260919'
    retail = root/'chelsea-retail-1466274-scope-review-20260919'
    if digest(old/'complete.json') != old_policy['review_manifest_sha256']:
        raise ValueError('Original policy review differs')
    if digest(movement/'complete.json') != '26a6949af94a168aa5f8f4a930dcb5b8b1dd10d0273209d91b0d09dd5069e70d':
        raise ValueError('Reviewed movement evidence differs')
    if digest(retail/'complete.json') != '4f9750a04278d471f29cae4586e8647d3b2fd0457b07035901d83f0fb78a8242':
        raise ValueError('Reviewed retail evidence differs')
    _, of = _verified_bundle(old, retain={'queue.jsonl'})
    _, mf = _verified_bundle(movement, retain={'queue.jsonl', 'raw-scope-witnesses.jsonl'})
    _, rf = _verified_bundle(retail, retain={'case.json', 'raw-witnesses.jsonl'})
    old_ids = {c['source_listing_id'] for c in old_policy['cases']}
    queue = [r for r in rows(of['queue.jsonl']) if r['source_listing_id'] in old_ids]
    new_ids = {'1543471', '2391701', '806884', '947730'}
    addresses = {}
    for witness in rows(mf['raw-scope-witnesses.jsonl']):
        ad = witness['source_listing_id']
        address = json.loads(witness['raw_listing_json'])['listingAddress']
        if ad in addresses and addresses[ad] != address:
            raise ValueError('Own address differs across captures')
        addresses[ad] = address
    for finding in rows(mf['queue.jsonl']):
        if finding['source_listing_id'] not in new_ids:
            continue
        finding = deepcopy(finding)
        if finding['kind'] != 'explicit_nonresidential':
            raise ValueError('Commercial policy cannot include ambiguous findings')
        for evidence in finding['literal_evidence']:
            for span in evidence['spans']:
                span['literal'] = span.pop('text')
        queue.append(finding)
    case = json.loads(rf['case.json'])
    retail_witnesses = rows(rf['raw-witnesses.jsonl'])
    row = case['source_row']
    assert row['source_listing_id'] == '1466274'
    retail_addresses = {json.loads(w['raw_listing_json'])['listingAddress'] for w in retail_witnesses}
    if retail_addresses != {'109 West 28th Street #RETAIL'}:
        raise ValueError('Retail identity differs')
    addresses['1466274'] = next(iter(retail_addresses))
    queue.append({**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
        'source_row_sha256': case['source_row_sha256'], 'kind': 'explicit_nonresidential',
        'finding': 'Explicit ground-floor retail space for short-term pop-up-store lease.',
        'literal_evidence': [{'capture_id': w['capture']['capture_id'],
            'description_sha256': w['capture']['description_sha256'], 'spans': w['literal_spans']}
            for w in retail_witnesses]})
    if len(queue) != 9 or len({r['source_listing_id'] for r in queue}) != 9:
        raise ValueError('Cumulative review must contain nine distinct advertisements')
    provenance = {str(p): digest(p/'complete.json') for p in (old, movement, retail)}
    for finding in queue:
        finding['applied_to_source_or_model'] = False
    publish_bundle(Path(output), {'queue.jsonl': ''.join(canonical(r)+'\n' for r in queue),
        'prior-reviews.json': canonical(provenance)+'\n',
        Path(__file__).name: Path(__file__).read_text()},
        {'version': 'cumulative-commercial-scope-review-v1', 'cases': 9,
         'source_or_model_changes': False, 'source_manifest_sha256': old_policy['source_manifest_sha256']})
    policy = deepcopy(old_policy)
    policy['review_manifest_sha256'] = digest(Path(output)/'complete.json')
    for finding in queue:
        ad = finding['source_listing_id']
        if ad in old_ids:
            continue
        policy['cases'].append({'source_listing_id': ad,
            'source_row_sha256': finding['source_row_sha256'],
            'finding_kind': 'explicit_nonresidential', 'action': 'quarantine_nonresidential',
            'expected_listing_address': addresses[ad],
            'reason': finding['finding']+' Quarantine only this exact offer from residential apartment analysis; preserve the source price and all other advertisements. No physical-use effective date or legal occupancy determination is inferred.'})
    policy['limits'] += ' Cumulative follow-up adds five manually confirmed commercial/event/retail offers. Broad lexical matches and mixed live/work offers are not automatic exclusions. Remaining screen adjudication is incomplete.'
    dest = Path(policy_output)
    payload = json.dumps(policy, indent=2, ensure_ascii=False)+'\n'
    if dest.exists() and dest.read_text() != payload:
        raise ValueError('Refusing to replace a different prepared policy')
    dest.write_text(payload)
    return {'review_manifest_sha256': policy['review_manifest_sha256'],
        'policy': str(dest), 'cases': 9, 'applied': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--policy-output', required=True)
    print(canonical(run(**vars(p.parse_args()))))
