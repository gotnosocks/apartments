"""Apply reviewed laundry-negation corrections using the dated patch ledger.

Only exact analytical row versions with corroborating evidence from every
capture are eligible. No physical facility change date is inferred.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from apartments import bayesian_evidence, corrections
from apartments.corrections import Overlay, canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'reviewed-laundry-negation-projection-v1'
SOURCE_VERSION = 'reviewed-capture-refreshed-analysis-v1'
AUDIT_VERSION = 'laundry-capture-source-audit-v1'
PATCH = [{'op': 'test', 'path': '/laundry_type', 'value': 'in_building'},
         {'op': 'replace', 'path': '/laundry_type', 'value': None}]


def hashed(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def records(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line.strip()]


def key(capture):
    value = capture['capture_id']
    return capture['audit_id'], type(value).__name__, value


def review_captures(row, captures, audit, recorded_at):
    expected = row.get('capture_ids', []) + ([row['capture_id']] if row.get('capture_id') is not None else [])
    expected = {(row['audit_id'], type(value).__name__, value) for value in expected}
    if not expected or {key(e) for e in captures} != expected or len(captures) != len(expected):
        raise ValueError('Every exact source capture must support the correction')
    if instant(recorded_at) < instant(row['known_at']):
        raise ValueError('Correction predates source knowledge')
    reviewed = []
    for evidence in captures:
        source = audit.get(key(evidence))
        if source is None:
            raise ValueError('Correction capture is absent from the laundry audit')
        for field in ('audit_id', 'unit_id', 'source_listing_id', 'body_sha256',
                      'raw_listing_sha256', 'description_sha256', 'source_collected_at',
                      'known_at', 'description_interpreted_at'):
            if source.get(field) != evidence.get(field):
                raise ValueError('Correction evidence binding differs: '+field)
        if (source['building'] != row['building'] or source['laundry_type'] != row['laundry_type']
                or source['replay_version'] != 'attribute-evidence-v4'
                or source['replayed_laundry_type'] is not None
                or source['structured_in_unit_claim'] or source['structured_in_building_claim']
                or instant(recorded_at) < instant(evidence['known_at'])):
            raise ValueError('Source does not support this bounded negation correction')
        assertions = source['laundry_assertions']
        if not assertions:
            raise ValueError('Literal scoped denial is required')
        text = evidence['description']
        for assertion in assertions:
            start, end = assertion.get('start'), assertion.get('end')
            if (assertion.get('attribute') != 'laundry_type' or assertion.get('value') != 'not:in_building'
                    or assertion.get('method') != 'description_pattern'
                    or assertion.get('source_path') != '/description'
                    or not isinstance(text, str) or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(text) or text[start:end] != assertion.get('literal')):
                raise ValueError('Correction requires exact scoped-denial spans')
        reviewed.append({'capture_id': evidence['capture_id'],
            'body_sha256': evidence['body_sha256'], 'raw_listing_sha256': evidence['raw_listing_sha256'],
            'description_sha256': evidence['description_sha256'],
            'source_collected_at': evidence['source_collected_at'], 'source_known_at': evidence['known_at'],
            'source_audit_row_sha256': hashed(source), 'assertions': deepcopy(assertions)})
    return reviewed


def assemble(rows, descriptions, audit_rows, overlay):
    audit = {key(r): r for r in audit_rows}
    if len(audit) != len(audit_rows) or len({r['audit_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate source/audit identity')
    if not overlay.active:
        raise ValueError('At least one active review correction is required')
    for edit in overlay.active:
        if (set(edit['target']) != {'source', 'source_listing_id', 'version_id'}
                or edit['target']['source'] != 'streeteasy' or edit['patch'] != PATCH
                or edit['validity'] != {'all_time': True}):
            raise ValueError('Only the bounded laundry patch on an exact row version is supported')
    result, changes, applied = [], [], set()
    for row in rows:
        context = {'source': 'streeteasy', 'source_listing_id': row['source_listing_id'],
                   'version_id': hashed(row)}
        updated, evidence = overlay.apply(row, context)
        if evidence:
            if len(evidence) != 1:
                raise ValueError('One active correction per exact row is required')
            edit = evidence[0]
            if edit['id'] in applied:
                raise ValueError('Correction matched more than one row')
            captures = review_captures(row, descriptions[row['audit_id']], audit, edit['recorded_at'])
            change = {**edit, 'audit_id': row['audit_id'], 'unit_id': row['unit_id'],
                'source_row_sha256': hashed(row), 'before_laundry_type': row['laundry_type'],
                'after_laundry_type': updated['laundry_type'], 'captures': captures}
            updated.setdefault('attribute_review_history', []).append(change)
            changes.append(change); applied.add(edit['id'])
        result.append(updated)
    if applied != {e['id'] for e in overlay.active}:
        raise ValueError('An active correction does not match this exact source row version')
    return result, changes


def run(dataset, descriptions, source_audit, ledger, as_of, output):
    dataset, descriptions, source_audit, ledger = map(Path, (dataset, descriptions, source_audit, ledger))
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl'})
    am, af = _verified_bundle(source_audit, retain={'captures.jsonl'})
    if dm.get('version') != SOURCE_VERSION or am.get('version') != AUDIT_VERSION:
        raise ValueError('Reviewed current cohort and laundry source audit required')
    literal = bayesian_evidence.load_evidence(dataset, descriptions)
    overlay = Overlay(ledger, as_of=as_of)
    rows = records(df['observations.jsonl'])
    revised, changes = assemble(rows, literal, records(af['captures.jsonl']), overlay)
    summary = {'rows': len(revised), 'changed_rows': len(changes),
        'reviewed_captures': sum(len(c['captures']) for c in changes),
        'current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in rows),
        'changed_current_rows': sum(a != b for a, b in zip(rows, revised)
                                    if a['analysis_price_basis'] == 'current_capture_gross_ask'),
        'policy': 'Exact analytical row versions only. Preserve prices, membership, source clocks and original categories in the review history. The ledger recorded_at dates corrected knowledge, not a physical laundry removal. Existing fitted datasets and selected model are unchanged.'}
    # The manifest retains both clocks: source known_at remains source knowledge;
    # correction knowledge is recorded_at in each row's attribute_review_history.
    paths = [Path(__file__), Path(corrections.__file__), Path(bayesian_evidence.__file__)]
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in revised),
        'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes),
        'corrections.jsonl': ''.join(canonical(r)+'\n' for r in overlay.records),
        'summary.json': canonical(summary)+'\n', **{p.name: p.read_text() for p in paths}}
    if 'current-source-evidence.jsonl' in df:
        files['current-source-evidence.jsonl'] = df['current-source-evidence.jsonl'].decode()
    return publish_bundle(output, files, {'version': VERSION, 'source_manifest': dm,
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'source_observations_sha256': dm['files']['observations.jsonl'],
        'descriptions_manifest_sha256': digest(descriptions/'complete.json'),
        'source_audit_manifest_sha256': digest(source_audit/'complete.json'),
        'overlay': overlay.manifest, 'summary': summary,
        'implementation_sha256': {p.name: digest(p) for p in paths}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'descriptions', 'source_audit', 'ledger', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
