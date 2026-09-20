"""Prepare exact reviewed floor additions; do not change analytical rows."""
import argparse
import hashlib
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(dataset, review, output):
    dataset, review, output = map(Path, (dataset, review, output))
    expected_source = '27ad22fd2e4814915c3411c792d0305c01a218be27a14d17ee9f5f7ba3fde359'
    expected_review = '8e604e097759247754d69d76149687980c93153ef66e67271035a544fabbac87'
    if digest(dataset/'complete.json') != expected_source or digest(review/'complete.json') != expected_review:
        raise ValueError('Prepared policy binds different reviewed inputs')
    _, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    _, rf = _verified_bundle(review, retain={'findings.jsonl', 'witnesses.jsonl'})
    rows = {r['audit_id']: r for r in map(json.loads, sf['observations.jsonl'].splitlines())}
    findings = [json.loads(l) for l in rf['findings.jsonl'].decode().split('\n') if l]
    witnesses = [json.loads(l) for l in rf['witnesses.jsonl'].decode().split('\n') if l]
    decisions, preserved = [], []
    for f in findings:
        row = f['source_row']
        if canonical(row) != canonical(rows[row['audit_id']]):
            raise ValueError('Reviewed source row changed')
        attached = [w for w in witnesses if w['capture']['audit_id'] == row['audit_id']]
        ids = lambda values: sorted(canonical(v) for v in values)
        if ids(w['capture']['capture_id'] for w in attached) != ids(row.get('capture_ids') or [row.get('capture_id')]):
            raise ValueError('Review must cover every attached capture exactly once')
        if f['disposition'] != 'previously_unknown_review_required' or f['existing_projection_status'] != 'unsupported_label_syntax':
            preserved.append(f)
            continue
        value = f['advertised_description_floor']
        if row['listed_floor'] is not None or any(w['complete_payload_floor'] != value for w in attached):
            raise ValueError('Proposed floor must be unknown with unanimous own-capture claims')
        decisions.append({'audit_id': row['audit_id'], 'source_listing_id': row['source_listing_id'],
            'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
            'action': 'add_explicit_advertised_floor', 'advertised_floor': value,
            'proposed_fields': {'listed_floor': value, 'advertised_floor': value},
            'witnesses': [{'capture_id': w['capture']['capture_id'],
                'raw_listing_sha256': w['capture']['raw_listing_sha256'],
                'description_sha256': w['capture']['description_sha256'],
                'source_collected_at': w['capture']['source_collected_at'],
                'claims': [e for e in w['after']['evidence'] if e['attribute'] == 'advertised_floor']}
                for w in attached],
            'temporal_scope': 'Captured own-advertisement description; preserves the parent retrospective attribute assumption, not a verified physical change date.'})
    if len(decisions) != 24 or len(preserved) != 17:
        raise ValueError('Expected 24 additions and 17 unchanged reviewed observations')
    policy = {'version': 'prepared-direct-floor-additions-v1', 'source_manifest_sha256': expected_source,
        'review_manifest_sha256': expected_review, 'applied': False,
        'cases': decisions, 'invariants': ['Keep all prices, identities, row order and nonfloor attributes unchanged.',
            'Preserve independent label proxies, physical-floor fields, masks and unresolved conflicts.',
            'Publish complete before/after values and exact inverse to the parent before model use.',
            'No other-advertisement propagation or building-wide numbering inference.']}
    publish_bundle(output, {'policy.json': canonical(policy)+'\n',
        'preserved-review-findings.jsonl': ''.join(canonical(r)+'\n' for r in preserved),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': policy['version'], 'source_manifest_sha256': expected_source,
         'review_manifest_sha256': expected_review, 'applied': False})
    _verified_bundle(output)
    print(canonical({'prepared_additions': len(decisions), 'preserved_observations': len(preserved), 'applied': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'review', 'output'):
        p.add_argument('--'+name, required=True)
    run(**vars(p.parse_args()))
