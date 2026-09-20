"""Rebind unchanged floor decisions after the exact 2938067 scope exclusion."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from apartments import residual_scope_projection
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_cohort_quarantine import sha


def rebase_cases(policy, before, after, new_source_hash):
    expected = [row for row in before if row['source_listing_id'] != '2938067']
    if len(expected) != len(before)-1 or canonical(expected) != canonical(after):
        raise ValueError('Expected only the exact location-conflict row removed')
    indexed = {row['audit_id']: row for row in after}
    if len(indexed) != len(after):
        raise ValueError('Duplicate source identity')
    for case in policy['cases']:
        row = indexed.get(case['audit_id'])
        if row is None or sha(row) != case['source_row_sha256']:
            raise ValueError('Reviewed floor row removed or changed')
    result = deepcopy(policy)
    result['source_manifest_sha256'] = new_source_hash
    return result


def run(reference, candidate, policy, output):
    reference, candidate, policy, output = map(Path, (reference, candidate, policy, output))
    if digest(policy/'complete.json') != 'b447545431c5ab427c2995d30fbe0bdd50b6c5d491b41fb5acd8d870c29057d2':
        raise ValueError('Expected original reviewed floor policy')
    _, pf = _verified_bundle(policy, retain={'policy.json', 'preserved-review-findings.jsonl'})
    original = json.loads(pf['policy.json'])
    if digest(reference/'complete.json') != original['source_manifest_sha256']:
        raise ValueError('Floor policy binds another reference')
    bundles = [_verified_bundle(path, retain={'observations.jsonl', residual_scope_projection.SIDECAR})
               for path in (reference, candidate)]
    parse = lambda data: [json.loads(s) for s in data.decode().split('\n') if s]
    restored = [residual_scope_projection.parent_rows(m, parse(f['observations.jsonl']),
                 parse(f[residual_scope_projection.SIDECAR])) for m, f in bundles]
    if canonical(restored[0]) != canonical(restored[1]):
        raise ValueError('Scope revisions do not share the exact original source')
    before, after = [parse(f['observations.jsonl']) for _, f in bundles]
    result = rebase_cases(original, before, after, digest(candidate/'complete.json'))
    assert len(result['cases']) == 24
    # The 17 preserved manual findings remain exactly bound too, including masks.
    index = {row['audit_id']: row for row in after}
    for finding in parse(pf['preserved-review-findings.jsonl']):
        row = finding['source_row']
        if index.get(row['audit_id']) != row:
            raise ValueError('Preserved floor review changed')
    publish_bundle(output, {'policy.json': canonical(result)+'\n',
        'preserved-review-findings.jsonl': pf['preserved-review-findings.jsonl'].decode(),
        'original-policy.json': pf['policy.json'].decode(),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': 'rebound-direct-floor-policy-v1', 'source_manifest_sha256': digest(candidate/'complete.json'),
         'reference_manifest_sha256': digest(reference/'complete.json'),
         'original_policy_manifest_sha256': digest(policy/'complete.json'),
         'review_manifest_sha256': original['review_manifest_sha256'],
         'cases_unchanged': 24, 'preserved_reviews_unchanged': 17, 'applied': False})
    _verified_bundle(output)
    print(canonical({'cases': 24, 'applied': False, 'manifest_sha256': digest(output/'complete.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'policy', 'output'):
        parser.add_argument('--'+name, required=True)
    run(**vars(parser.parse_args()))
