"""Publish a source-bound reviewed quarantine without editing retained records."""
import argparse
import json
from pathlib import Path

from apartments import reviewed_cohort_quarantine as lineage
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

DECISION_VERSION = lineage.DECISION_VERSION


def rows(blob):
    return [json.loads(s) for s in blob.decode().split('\n') if s.strip()]


def project(source, decisions, reviewed_at):
    by_id = {d['audit_id']: d for d in decisions}
    if (not by_id or len(by_id) != len(decisions) or len({r['audit_id'] for r in source}) != len(source)
            or not by_id.keys() <= {r['audit_id'] for r in source}):
        raise ValueError('Duplicate or unknown quarantine identity')
    kept, quarantined = [], []
    for index, row in enumerate(source):
        decision = by_id.get(row['audit_id'])
        if decision is None: kept.append(row)
        else:
            lineage.validate_decision(row, decision, reviewed_at)
            quarantined.append({'source_index': index, 'observation': row, 'decision': decision})
    return kept, quarantined


def run(dataset, decisions, output):
    dataset, decisions = map(Path, (dataset, decisions))
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl'})
    dm, df = _verified_bundle(decisions, retain={'decisions.jsonl'})
    if (sm.get('version') != lineage.PARENT or dm.get('version') != DECISION_VERSION
            or dm.get('source_manifest_sha256') != digest(dataset/'complete.json')
            or dm.get('source_observations_sha256') != sm['files']['observations.jsonl']):
        raise ValueError('Quarantine decision/source binding differs')
    original = rows(sf['observations.jsonl'])
    kept, quarantined = project(original, rows(df['decisions.jsonl']), dm['reviewed_at'])
    metadata = {'version': lineage.VERSION, 'source_manifest': sm,
        'source_manifest_sha256': digest(dataset/'complete.json'), 'source_rows': len(original),
        'reviewed_at': dm['reviewed_at'], 'decisions_manifest': dm,
        'decisions_manifest_sha256': digest(decisions/'complete.json'),
        'decision_ids': sorted(item['decision']['decision_id'] for item in quarantined)}
    probe = {**metadata, 'files': {lineage.SIDECAR: lineage.records_hash(quarantined)}}
    if lineage.parent_rows(probe, kept, quarantined) != (sm, original):
        raise ValueError('Quarantine does not reconstruct the original source')
    summary = {'source_rows': len(original), 'rows': len(kept), 'quarantined_rows': len(quarantined),
        'units': len({r['unit_id'] for r in kept}), 'buildings': len({r['building'] for r in kept}),
        'current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in kept),
        'source_listing_ids': [r['observation']['source_listing_id'] for r in quarantined],
        'policy': 'Quarantine named historical advertisement observations only. Retained fields, raw records and current rows unchanged. No replacement prices or propagation across advertisements.'}
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in kept),
        lineage.SIDECAR: ''.join(canonical(r)+'\n' for r in quarantined),
        'summary.json': canonical(summary)+'\n', 'decisions.jsonl': df['decisions.jsonl'].decode(),
        'reviewed_cohort_quarantine.py': Path(lineage.__file__).read_text(),
        Path(__file__).name: Path(__file__).read_text()}
    if 'current-source-evidence.jsonl' in sf:
        files['current-source-evidence.jsonl'] = sf['current-source-evidence.jsonl'].decode()
    publish_bundle(output, files, {**metadata, 'summary': summary})
    print(canonical(summary), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'decisions', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
