"""Split accepted shared laundry by reported same-floor access for an experiment.

This does not replace the accepted encoder, change unknown/private assignments,
infer facilities from silence, or claim a physical amenity premium.
"""
import argparse
from copy import deepcopy
from pathlib import Path

from apartments import laundry_floor_split as split
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from .laundry_source_audit import identity, records


def assemble(rows, captures, measurement_hash, interpreted_at):
    by_row = {r['audit_id']: [] for r in rows}
    if len(by_row) != len(rows) or len({identity(c) for c in captures}) != len(captures):
        raise ValueError('Duplicate laundry source or capture identity')
    for capture in captures:
        if capture['audit_id'] not in by_row:
            raise ValueError('Unknown laundry observation')
        by_row[capture['audit_id']].append(capture)
    revised, changes = [], []
    for row in rows:
        group = by_row[row['audit_id']]
        if split.FIELD in row:
            raise ValueError('Laundry floor evidence already exists')
        if not group or {(type(c['capture_id']).__name__, c['capture_id']) for c in group} != split.capture_ids(row):
            raise ValueError('Incomplete attached laundry captures')
        if any(any(c[k] != row[k] for k in ('audit_id', 'unit_id', 'building', 'source_listing_id', 'laundry_type')) for c in group):
            raise ValueError('Laundry measurement source identity or category differs')
        updated = deepcopy(row)
        eligible = row['laundry_type'] == 'in_building' and all(
            c['measurement']['most_convenient_reported_option'] == 'on_floor'
            and c['measurement']['states']['shared_same_floor'] is True
            and not c['measurement']['conflicts'] and not c['measurement']['installation_review_required'] for c in group)
        if eligible:
            evidence = {'before': 'in_building', 'after': 'on_floor',
                'source_row_sha256': split.hashed(row), 'measurement_manifest_sha256': measurement_hash,
                'interpreted_at': interpreted_at, 'captures': [
                    {**{k: c[k] for k in ('audit_id', 'capture_id', 'unit_id', 'source_listing_id', 'body_sha256',
                        'raw_listing_sha256', 'description_sha256', 'source_collected_at', 'known_at')},
                     'source_category': c['measurement']['most_convenient_reported_option'],
                     'same_floor_claims': [e for e in c['measurement']['claims'] if e['scope'] == 'shared_same_floor' and e['present'] is True]}
                    for c in group]}
            split.validate_evidence(row, evidence, measurement_hash, interpreted_at)
            updated['laundry_type'] = 'on_floor'
            updated[split.FIELD] = evidence
            changes.append({'audit_id': row['audit_id'], 'unit_id': row['unit_id'], 'building': row['building'], 'evidence': evidence})
        revised.append(updated)
    return revised, changes


def run(dataset, measurement, interpreted_at, output):
    dataset, measurement = Path(dataset), Path(measurement)
    instant(interpreted_at)
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl'})
    mm, mf = _verified_bundle(measurement, retain={'captures.jsonl', 'summary.json'})
    if (dm.get('version') != split.PARENT or mm.get('version') != 'full-cohort-scoped-laundry-measurement-v1'
            or mm.get('dataset_manifest_sha256') != digest(dataset/'complete.json')):
        raise ValueError('Laundry split source/measurement binding differs')
    rows = records(df['observations.jsonl'])
    revised, changes = assemble(rows, records(mf['captures.jsonl']), digest(measurement/'complete.json'), interpreted_at)
    metadata = {'version': split.VERSION, 'source_manifest': dm, 'source_manifest_sha256': digest(dataset/'complete.json'),
        'measurement_manifest_sha256': digest(measurement/'complete.json'), 'interpreted_at': interpreted_at,
        'changed_audit_ids': [c['audit_id'] for c in changes]}
    parent, reconstructed = split.parent_rows(metadata, revised)
    if parent != dm or reconstructed != rows:
        raise ValueError('Laundry split does not reconstruct the exact source')
    summary = {'rows': len(rows), 'changed_rows': len(changes),
        'changed_units': len({c['unit_id'] for c in changes}), 'changed_buildings': len({c['building'] for c in changes}),
        'changed_current_rows': sum(a != b for a, b in zip(rows, revised, strict=True) if a['analysis_price_basis'] == 'current_capture_gross_ask'),
        'policy': 'Split only accepted in-building laundry when every attached capture reports shared same-floor access. All other categories, source clocks, prices and nonlaundry fields are unchanged. Experimental reported-detail association, not different-floor versus same-floor access or a physical amenity premium.'}
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in revised),
        'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes), 'summary.json': canonical(summary)+'\n',
        Path(__file__).name: Path(__file__).read_text(), 'laundry_floor_split.py': Path(split.__file__).read_text()}
    if 'current-source-evidence.jsonl' in df:
        files['current-source-evidence.jsonl'] = df['current-source-evidence.jsonl'].decode()
    publish_bundle(output, files, {**metadata, 'summary': summary})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'measurement', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--interpreted-at', required=True)
    print(canonical(run(**vars(parser.parse_args()))), flush=True)
