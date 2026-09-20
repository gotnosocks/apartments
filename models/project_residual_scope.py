"""Publish a reversible residual-driven scope revision with unchanged kept rows."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from apartments import residual_scope_projection as contract
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_source_lineage import source_lineage


def records(data):
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def run(dataset, decisions, output):
    dataset, decisions, output = map(Path, (dataset, decisions, output))
    parent_hash, decisions_hash = digest(dataset/'complete.json'), digest(decisions/'complete.json')
    parent_manifest = json.loads((dataset/'complete.json').read_text())
    parent, files = _verified_bundle(dataset, retain=set(parent_manifest['files']))
    dm, df = _verified_bundle(decisions, retain={'decisions.jsonl', 'policy.json'})
    if (parent['version'] != contract.PARENT or dm['version'] != contract.DECISION_VERSION
            or dm['source_manifest_sha256'] != parent_hash
            or dm['source_observations_sha256'] != parent['files']['observations.jsonl']):
        raise ValueError('Scope decisions bind a different parent source')
    before, edits = records(files['observations.jsonl']), records(df['decisions.jsonl'])
    by_id = {(type(d['audit_id']).__name__, d['audit_id']): d for d in edits}
    if len(by_id) != len(edits) or not edits:
        raise ValueError('Duplicate or empty scope decisions')
    kept, excluded = [], []
    for index, row in enumerate(before):
        decision = by_id.pop((type(row['audit_id']).__name__, row['audit_id']), None)
        if decision is None:
            kept.append(deepcopy(row))
        else:
            contract.validate_decision(row, decision, dm['reviewed_at'])
            excluded.append({'source_index': index, 'observation': deepcopy(row), 'decision': decision})
    if by_id:
        raise ValueError('Scope decision absent from source')
    current = lambda rows: [r for r in rows if r['analysis_price_basis'] == 'current_capture_gross_ask']
    if current(kept) != current(before):
        raise ValueError('This experiment preserves every captured-current observation')
    summary = {'source_rows': len(before), 'rows': len(kept), 'quarantined_rows': len(excluded),
        'units': len({r['unit_id'] for r in kept}), 'buildings': len({r['building'] for r in kept}),
        'current_rows': len(current(kept)), 'retained_values_unchanged': True,
        'scope': 'Exact reviewed advertisements only; no price/attribute repairs or other-ad propagation.'}
    metadata = {'version': contract.VERSION, 'source_manifest': parent,
        'source_manifest_sha256': parent_hash, 'decisions_manifest': dm,
        'decisions_manifest_sha256': decisions_hash, 'source_rows': len(before),
        'reviewed_at': dm['reviewed_at'], 'decision_ids': sorted(d['decision_id'] for d in edits),
        'summary': summary, 'implementation_sha256': digest(__file__)}
    products = {name: value.decode() for name, value in files.items()
                if name not in {'observations.jsonl', 'summary.json'}}
    if {'parent-summary.json', contract.SIDECAR, 'residual-scope-decisions.jsonl'} & products.keys():
        raise ValueError('Scope revision cannot overwrite ancestor artifacts')
    products.update({'observations.jsonl': ''.join(canonical(r)+'\n' for r in kept),
        contract.SIDECAR: ''.join(canonical(r)+'\n' for r in excluded),
        'residual-scope-decisions.jsonl': df['decisions.jsonl'].decode(),
        'residual-scope-policy.json': df['policy.json'].decode(),
        'parent-summary.json': files['summary.json'].decode(), 'summary.json': canonical(summary)+'\n',
        Path(__file__).name: Path(__file__).read_text(),
        Path(contract.__file__).name: Path(contract.__file__).read_text()})
    prospective = {**metadata, 'files': {k: hashlib.sha256(v.encode()).hexdigest()
                                       for k, v in products.items()}}
    if contract.parent_rows(prospective, kept, excluded) != (parent, before):
        raise ValueError('Scope revision does not restore exact parent rows')
    # Verify the entire older provenance chain, not just the new outer wrapper.
    source_lineage(prospective, kept, residual_scope_changes=excluded,
        quarantined=records(files['quarantined.jsonl']),
        elevator_changes=records(files['elevator-corrections.jsonl']),
        floor_label_changes=records(files['floor-label-projection.jsonl']),
        expanded_floor_changes=records(files['expanded-floor-projection.jsonl']))
    if digest(dataset/'complete.json') != parent_hash or digest(decisions/'complete.json') != decisions_hash:
        raise ValueError('Source or decisions changed during projection')
    publish_bundle(output, products, metadata)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'decisions', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
