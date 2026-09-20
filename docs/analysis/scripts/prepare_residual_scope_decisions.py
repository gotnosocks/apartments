"""Bind reviewed residual-tail scope decisions to all exact own captures."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import duckdb

from apartments import residual_scope_projection as contract
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical, instant, now
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def records(data):
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def run(dataset, evidence, review, policy, archive, reviewed_at, output):
    dataset, evidence, review, policy, archive, output = map(
        Path, (dataset, evidence, review, policy, archive, output))
    policy_bytes = policy.read_bytes()
    specification = json.loads(policy_bytes)
    if specification.get('version') != 'chelsea-residual-scope-policy-v1':
        raise ValueError('Unsupported manual scope policy')
    if not instant(reviewed_at) <= now():
        raise ValueError('Review clock is in the future')
    if (digest(dataset/'complete.json') != specification['source_manifest_sha256']
            or digest(review/'complete.json') != specification['review_manifest_sha256']):
        raise ValueError('Policy binds a different source or source review')
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl', 'expanded-floor-projection.jsonl'})
    rm, rf = _verified_bundle(review, retain={'queue.jsonl'})
    if (sm['version'] != contract.PARENT or instant(reviewed_at) < instant(sm['interpreted_at'])
            or rm.get('source_or_model_changes') is not False):
        raise ValueError('Wrong parent source or invalid review chronology')
    source = records(sf['observations.jsonl'])
    changes = records(sf['expanded-floor-projection.jsonl'])
    by_index = {c['source_index']: c for c in changes}
    plans = {c['source_listing_id']: c for c in specification['cases']}
    if not plans or len(plans) != len(specification['cases']):
        raise ValueError('Duplicate or empty manual policy')
    selected = {row['source_listing_id']: (i, row) for i, row in enumerate(source)
                if row['source_listing_id'] in plans}
    if selected.keys() != plans.keys() or sum(r['source_listing_id'] in plans for r in source) != len(plans):
        raise ValueError('Reviewed advertisements must each identify exactly one source row')
    findings = {r['source_listing_id']: r for r in records(rf['queue.jsonl'])}
    capture_map = load_evidence(dataset, evidence)
    decisions = []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for ad, plan in plans.items():
            index, row = selected[ad]
            finding = findings[ad]
            if (contract.sha(row) != plan['source_row_sha256']
                    or finding['source_row_sha256'] != plan['source_row_sha256']
                    or finding['audit_id'] != row['audit_id']
                    or finding['kind'] != plan['finding_kind']
                    or row['analysis_price_basis'] != 'historical_initial_own_advertisement_ask'):
                raise ValueError('Reviewed source version, finding or scope differs')
            spans = {(type(v['capture_id']).__name__, v['capture_id']): v
                     for v in finding['literal_evidence']}
            witnesses = []
            for capture in capture_map[row['audit_id']]:
                literal = spans[(type(capture['capture_id']).__name__, capture['capture_id'])]
                if capture['description_sha256'] != literal['description_sha256']:
                    raise ValueError('Reviewed description differs')
                matches = db.execute('SELECT raw_listing_json FROM read_parquet(?) WHERE snapshot_id=?',
                    [str(archive/'listing_observations/*.parquet'), capture['capture_id']]).fetchall()
                if len(matches) != 1:
                    raise ValueError('Expected exactly one own raw listing witness')
                raw = matches[0][0]
                if (hashlib.sha256(raw.encode()).hexdigest() != capture['raw_listing_sha256']
                        or json.loads(raw)['listingAddress'] != plan['expected_listing_address']):
                    raise ValueError('Raw listing hash or reviewed address differs')
                witnesses.append({**deepcopy(capture), 'spans': deepcopy(literal['spans']),
                                  'raw_listing_json': raw})
            decision = {key: row[key] for key in ('audit_id', 'unit_id', 'source_listing_id')}
            decision.update(action=plan['action'], reason=plan['reason'], reviewer='codex',
                reviewed_at=reviewed_at, source_row_sha256=contract.sha(row),
                source_captures=deepcopy(by_index[index]['original_change']['captures']),
                evidence=witnesses, temporal_scope=specification['temporal_scope'],
                policy_sha256=hashlib.sha256(policy_bytes).hexdigest(),
                source_review_manifest_sha256=digest(review/'complete.json'))
            decision['decision_id'] = contract.sha(decision)
            contract.validate_decision(row, decision, reviewed_at)
            decisions.append(decision)
    decisions.sort(key=contract.decision_sort_key)
    if policy.read_bytes() != policy_bytes or digest(dataset/'complete.json') != specification['source_manifest_sha256']:
        raise ValueError('Source/policy changed during preparation')
    publish_bundle(output, {'decisions.jsonl': ''.join(canonical(d)+'\n' for d in decisions),
        'policy.json': policy_bytes.decode(), Path(__file__).name: Path(__file__).read_text()},
        {'version': contract.DECISION_VERSION, 'reviewed_at': reviewed_at,
         'source_manifest_sha256': specification['source_manifest_sha256'],
         'source_observations_sha256': sm['files']['observations.jsonl'],
         'source_review_manifest_sha256': specification['review_manifest_sha256'],
         'evidence_manifest_sha256': digest(evidence/'complete.json'),
         'policy_sha256': hashlib.sha256(policy_bytes).hexdigest(), 'decisions': len(decisions)})
    return {'decisions': len(decisions), 'captures': sum(len(d['evidence']) for d in decisions),
            'source_listing_ids': sorted(plans), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'evidence', 'review', 'policy', 'archive', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--reviewed-at', required=True)
    print(canonical(run(**vars(parser.parse_args()))))
