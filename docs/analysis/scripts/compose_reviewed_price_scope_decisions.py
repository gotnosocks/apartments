"""Combine the closed net-quote review with the previously reviewed short-term ad."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from apartments import reviewed_cohort_quarantine as q
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def records(blob):
    return [json.loads(s) for s in blob.decode().split('\n') if s]


def run(dataset, recommendations, prior_scope, reviewed_at, output):
    dataset, recommendations, prior_scope = map(Path, (dataset, recommendations, prior_scope))
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    rm, rf = _verified_bundle(recommendations, retain={'proposed-quarantines.jsonl', 'findings.jsonl'})
    pm, pf = _verified_bundle(prior_scope, retain={'decisions.jsonl'})
    parent_hash = digest(dataset/'complete.json')
    if (sm['version'] != q.PARENT or rm['version'] != 'reviewed-rent-basis-recommendations-v1'
            or pm['version'] != q.DECISION_VERSION or any(m['source_manifest_sha256'] != parent_hash
            or m['source_observations_sha256'] != sm['files']['observations.jsonl'] for m in (rm, pm))):
        raise ValueError('Reviewed decisions do not share the exact source parent')
    rows = {r['audit_id']: r for r in records(sf['observations.jsonl'])}
    proposed = records(rf['proposed-quarantines.jsonl'])
    prior = records(pf['decisions.jsonl'])
    short_term = [d for d in prior if d['source_listing_id'] == '970866'
                  and d['action'] == 'quarantine_explicit_short_term_offer']
    if (len(proposed) != 164 or len(short_term) != 1
            or '2675026' not in {d['source_listing_id'] for d in proposed}
            or '2532848' in {d['source_listing_id'] for d in proposed}):
        raise ValueError('Closed reviewed batch or retained exception differs')
    inputs = [(d, digest(recommendations/'complete.json')) for d in proposed]
    inputs += [(d, digest(prior_scope/'complete.json')) for d in short_term]
    if len({d['audit_id'] for d, _ in inputs}) != 165: raise ValueError('Overlapping review identities')
    decisions, upstream = [], []
    for original, origin in inputs:
        row = rows[original['audit_id']]
        q.validate_decision(row, original, original['reviewed_at'])
        if instant(reviewed_at) < instant(original['reviewed_at']): raise ValueError('Composition precedes review')
        decision = deepcopy(original)
        decision.pop('decision_id')
        decision.update(reviewed_at=reviewed_at, recommendation_only=False,
            source_review_record={'decision_id': original['decision_id'], 'reviewed_at': original['reviewed_at'],
                                  'manifest_sha256': origin})
        decision['decision_id'] = q.sha(decision)
        q.validate_decision(row, decision, reviewed_at)
        decisions.append(decision)
        upstream.append({'origin_manifest_sha256': origin, 'review_record': original})
    decisions.sort(key=lambda d: d['audit_id'])
    publish_bundle(output, {'decisions.jsonl': ''.join(canonical(d)+'\n' for d in decisions),
        'upstream-reviewed-decisions.jsonl': ''.join(canonical(d)+'\n' for d in upstream),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': q.DECISION_VERSION, 'reviewed_at': reviewed_at,
         'source_manifest_sha256': parent_hash, 'source_observations_sha256': sm['files']['observations.jsonl'],
         'recommendations_manifest_sha256': digest(recommendations/'complete.json'),
         'prior_scope_manifest_sha256': digest(prior_scope/'complete.json'),
         'policy': '164 manually reviewed unresolved gross-price-basis exclusions plus one previously reviewed short-term advertisement. '
                   'The overlapping net-price ad 2675026 appears once. Ad 2532848 is retained. Original review records and clocks are preserved.'})
    print(canonical({'decisions': len(decisions), 'net_basis': len(proposed), 'short_term': len(short_term)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'recommendations', 'prior_scope', 'output'): parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--reviewed-at', required=True)
    run(**vars(parser.parse_args()))
