"""Measure occurrence-level outdoor claims on the fixed reviewed cohort.

Publishes review evidence, not new model inputs or physical feature values.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path

from apartments import outdoor_evidence, outdoor_scope_v2 as outdoor_scope
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'cohort-outdoor-access-scope-v1'


def records(data):
    return [json.loads(s) for s in data.decode().split('\n') if s]


def run(dataset, evidence, output):
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    em, ef = _verified_bundle(evidence, retain={'evidence.jsonl'})
    if dm.get('dataset_version') != 'advertised-outdoor-types-v1' or dm['outdoor_audit_manifest'] != em:
        raise ValueError('Structured dataset and source evidence do not bind')
    rows = records(df['observations.jsonl'])
    by_id = {r['audit_id']:r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError('Duplicate analytical identity')
    grouped = defaultdict(list)
    for capture in records(ef['evidence.jsonl']):
        row = by_id.get(capture['audit_id'])
        if row is None:
            raise ValueError('Unbound outdoor capture')
        allowed = set(row.get('capture_ids') or []) | {row.get('capture_id')}
        if capture['unit_id'] != row['unit_id'] or capture['source_listing_id'] != str(row['source_listing_id']) or capture['capture_id'] not in allowed:
            raise ValueError('Outdoor scope capture identity mismatch')
        if instant(capture['source_collected_at']) > instant(row['known_at']):
            raise ValueError('Capture later than analytical knowledge clock')
        grouped[row['audit_id']].append(capture)
    measured, scope_rows, claim_counts, basis_counts = [], Counter(), Counter(), Counter()
    coexisting, conflicting = 0, 0
    for row in rows:
        result = outdoor_scope.measure(grouped.get(row['audit_id'], []))
        measured.append({k:row.get(k) for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent','private_outdoor_category','shared_outdoor_category')} | result)
        scope_rows.update(s for s, types in result['types_by_scope'].items() if types)
        claim_counts.update(c['scope'] for c in result['claims'])
        basis_counts.update(c['basis'] for c in result['claims'])
        coexisting += bool(result['private_and_shared_types'])
        conflicting += bool(result['positive_and_negative_types'])
    summary = {'rows':len(rows), 'rows_by_scope':dict(sorted(scope_rows.items())),
               'mentions_by_scope':dict(sorted(claim_counts.items())), 'mentions_by_basis':dict(sorted(basis_counts.items())),
               'rows_with_same_type_private_and_shared':coexisting, 'rows_with_same_type_positive_and_negative':conflicting,
               'status':'Source-claim measurement for review; no model inputs promoted.'}
    previous = _verified_bundle(output)[0] if (Path(output)/'complete.json').exists() else None
    interpreted_at = previous['interpreted_at'] if previous else datetime.now(UTC).isoformat()
    paths = [Path(__file__),Path(outdoor_scope.__file__),Path(outdoor_evidence.__file__)]
    return publish_bundle(output, {
        'measurements.jsonl':''.join(canonical(r)+'\n' for r in measured),
        'summary.json':canonical(summary)+'\n', **{p.name:p.read_text() for p in paths}},
        {'version':VERSION, 'dataset_manifest':dm, 'evidence_manifest':em, 'rows':len(rows),
         'interpreted_at':interpreted_at, 'summary':summary, 'implementation_sha256':{p.name:digest(p) for p in paths}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('dataset','evidence','output'):
        parser.add_argument('--'+key, type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(canonical(result['summary']))
