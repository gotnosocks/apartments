"""Combine preserved historical descriptions with exact refreshed capture evidence."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from apartments import bayesian_evidence
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import current_source_review as reviewed
from . import refresh_analysis_cohort as refresh

VERSION = 'refreshed-fitted-description-archive-v1'


def assemble(parent_rows, rows, evidence, historical_mapping):
    history = lambda rr: [r for r in rr if r['analysis_price_basis'] == 'historical_initial_own_advertisement_ask']
    historical = history(rows)
    if history(parent_rows) != historical:
        raise ValueError('Reviewed historical rows changed during refresh')
    current = [r for r in rows if r['analysis_price_basis'] == 'current_capture_gross_ask']
    if len(historical)+len(current) != len(rows): raise ValueError('Unknown analytical price basis')
    by_id = {e['audit_id']: e for e in evidence}
    if len(by_id) != len(evidence) or by_id.keys() != {r['audit_id'] for r in current}:
        raise ValueError('Current evidence coverage differs')
    result = []
    for row in historical:
        captures = historical_mapping[row['audit_id']]
        if {(type(c['capture_id']).__name__, c['capture_id']) for c in captures} != {
                (type(c).__name__, c) for c in row['capture_ids']}:
            raise ValueError('Historical capture coverage differs')
        result.extend(captures)
    for row in current:
        e = by_id[row['audit_id']]
        if any(e.get(k) != row.get(k) for k in reviewed.IDENTITY):
            raise ValueError('Current description identity differs')
        if (any(e.get(k) != row.get(k) for k in ('collected_at', 'known_at'))
                or instant(e['collected_at']) > instant(e['known_at'])):
            raise ValueError('Current description knowledge clock differs')
        if row.get('capture_ids') not in (None, [], [row['capture_id']]):
            raise ValueError('Current description capture membership differs')
        if e['raw_listing_sha256'] != row['source_raw_sha256'] or e['body_sha256'] != row['refresh_provenance']['body_sha256']:
            raise ValueError('Current description source hashes differ')
        text = e['description']
        if text is not None and not isinstance(text, str): raise ValueError('Description must be literal text or null')
        result.append({**{k: e[k] for k in ('audit_id', 'capture_id', 'source_listing_id', 'unit_id',
                                          'body_sha256', 'raw_listing_sha256', 'known_at')},
            'source_collected_at': e['collected_at'], 'description_interpreted_at': None,
            'description': text, 'description_sha256': hashlib.sha256(text.encode()).hexdigest() if text is not None else None,
            'description_source': 'verified_current_own_listing', 'source_path': '/description'})
    return sorted(result, key=lambda r: (r['audit_id'], str(r['capture_id'])))


def run(parent, historical_evidence, refreshed, dataset, output):
    parent, historical_evidence, refreshed, dataset = map(Path, (parent, historical_evidence, refreshed, dataset))
    pm, pf = _verified_bundle(parent, retain={'observations.jsonl'})
    fm, _ = _verified_bundle(refreshed, retain=set())
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl'})
    if (pm.get('version') != refresh.PARENT_VERSION or fm.get('version') != refresh.VERSION
            or dm.get('version') != reviewed.VERSION
            or fm['parent_manifest_sha256'] != digest(parent/'complete.json')
            or fm['parent_observations_sha256'] != pm['files']['observations.jsonl']
            or dm['source_manifest_sha256'] != digest(refreshed/'complete.json')
            or dm['source_observations_sha256'] != fm['files']['observations.jsonl']
            or dm['files']['current-source-evidence.jsonl'] != fm['files']['current-source-evidence.jsonl']):
        raise ValueError('Reviewed refresh/source lineage differs')
    mapping = bayesian_evidence.load_evidence(parent, historical_evidence)
    records = assemble(refresh.records(pf['observations.jsonl']), refresh.records(df['observations.jsonl']),
                       refresh.records(df['current-source-evidence.jsonl']), mapping)
    del mapping, pf, df
    result = publish_bundle(output, {'evidence.jsonl': ''.join(canonical(r)+'\n' for r in records),
        Path(__file__).name: Path(__file__).read_text(),
        Path(bayesian_evidence.__file__).name: Path(bayesian_evidence.__file__).read_text()}, {
        'version': VERSION, 'dataset_manifest_sha256': digest(dataset/'complete.json'),
        'dataset_observations_sha256': dm['files']['observations.jsonl'],
        'parent_manifest_sha256': digest(parent/'complete.json'),
        'historical_evidence_manifest_sha256': digest(historical_evidence/'complete.json'),
        'refresh_manifest_sha256': digest(refreshed/'complete.json'),
        'captures': len(records), 'observations': len({r['audit_id'] for r in records}),
        'current_captures': sum(r['description_source'] == 'verified_current_own_listing' for r in records),
        'policy': 'Original historical literal evidence plus exact current captures. No cross-advertisement substitution, backfill, model fit or promotion.'})
    # Verify the consumer's full identity, capture coverage and knowledge-clock
    # contract before claiming this artifact is ready for attachment.
    del records
    bayesian_evidence.load_evidence(dataset, output)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('parent', 'historical_evidence', 'refreshed', 'dataset', 'output'):
        p.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    result = run(**vars(p.parse_args()))
    print(canonical({k: result[k] for k in ('version', 'captures', 'observations', 'current_captures')}))
