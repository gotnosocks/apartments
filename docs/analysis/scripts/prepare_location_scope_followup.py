"""Prepare ten cumulative exact-ad exclusions, adding verified location conflict 2938067."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_cohort_quarantine import sha


def run(output, policy_output):
    root = Path('data/model')
    old_policy_path = Path('config/reviews/chelsea-commercial-scope-followup-20260919.json')
    policy = json.loads(old_policy_path.read_text())
    prior = root/'chelsea-commercial-scope-followup-review-20260919'
    reviewed = root/'chelsea-2938067-location-review-20260920'
    source = root/'chelsea-expanded-label-floor-analysis-20260919'
    if (digest(prior/'complete.json') != policy['review_manifest_sha256']
            or digest(source/'complete.json') != policy['source_manifest_sha256']
            or digest(reviewed/'complete.json') != 'e69a5bd1af646ff887b564294ed13beaa4a3ff9189a4c34ce498828c1e890042'):
        raise ValueError('Reviewed scope lineage changed')
    _, pf = _verified_bundle(prior, retain={'queue.jsonl'})
    _, rf = _verified_bundle(reviewed, retain={'finding.json', 'reviewed-case.json', 'raw-witnesses.jsonl'})
    _, sf = _verified_bundle(source, retain={'observations.jsonl'})
    records = lambda data: [json.loads(s) for s in data.decode().split('\n') if s]
    finding, case = json.loads(rf['finding.json']), json.loads(rf['reviewed-case.json'])
    row = case['observation']
    matches = [r for r in records(sf['observations.jsonl']) if r['source_listing_id'] == '2938067']
    if len(matches) != 1 or matches[0] != row or sha(row) != finding['source_row_sha256']:
        raise ValueError('Location finding does not bind the original cumulative-policy base')
    witnesses = records(rf['raw-witnesses.jsonl'])
    if {w['capture_id'] for w in witnesses} != set(row['capture_ids']):
        raise ValueError('Location review capture membership differs')
    addresses = {json.loads(w['raw_listing_json'])['listingAddress'] for w in witnesses}
    if len(addresses) != 1:
        raise ValueError('Location review addresses disagree')
    queue = records(pf['queue.jsonl'])
    assert len(queue) == len(policy['cases']) == 9
    queue.append({**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
        'source_row_sha256': sha(row), 'kind': finding['finding_kind'], 'finding': finding['reason'],
        'applied_to_source_or_model': False,
        'literal_evidence': [{'capture_id': w['capture_id'], 'description_sha256': w['description_sha256'],
            'spans': [{'start': s['start'], 'end': s['end'], 'literal': s['text']} for s in w['literal_spans']]}
            for w in witnesses]})
    assert len({r['source_listing_id'] for r in queue}) == 10
    output, policy_output = Path(output), Path(policy_output)
    publish_bundle(output, {'queue.jsonl': ''.join(canonical(r)+'\n' for r in queue),
        'new-location-witnesses.jsonl': rf['raw-witnesses.jsonl'].decode(),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': 'cumulative-location-scope-review-v1', 'cases': 10, 'source_or_model_changes': False,
         'source_manifest_sha256': policy['source_manifest_sha256'],
         'prior_policy_sha256': digest(old_policy_path), 'prior_review_manifest_sha256': digest(prior/'complete.json'),
         'location_review_manifest_sha256': digest(reviewed/'complete.json')})
    prepared = deepcopy(policy)
    prepared['review_manifest_sha256'] = digest(output/'complete.json')
    prepared['cases'].append({'source_listing_id': '2938067', 'source_row_sha256': sha(row),
        'finding_kind': finding['finding_kind'], 'action': 'quarantine_location_conflict',
        'expected_listing_address': next(iter(addresses)), 'reason': finding['reason']})
    prepared['limits'] += ' Adds only the verified Park Slope/Manhattan location-conflict advertisement 2938067. No sibling exclusion, replacement address or price correction.'
    text = json.dumps(prepared, indent=2, ensure_ascii=False)+'\n'
    if policy_output.exists() and policy_output.read_text() != text:
        raise ValueError('Refusing to overwrite another prepared policy')
    policy_output.write_text(text)
    _verified_bundle(output)
    print(canonical({'cases': 10, 'applied': False, 'review_manifest_sha256': digest(output/'complete.json'),
                     'policy_sha256': digest(policy_output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--policy-output', required=True)
    run(**vars(parser.parse_args()))
