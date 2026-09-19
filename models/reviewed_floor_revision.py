"""Project source-reviewed floor masks through exact-version correction records."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from apartments import corrections
from apartments.corrections import Overlay, canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models.laundry_negation_revision import hashed, records

VERSION = 'reviewed-floor-conflict-projection-v1'
WITHHOLD = {'withhold_floor_due_to_scope', 'withhold_floor_due_to_source_conflict'}


def patch(value):
    return [{'op': 'test', 'path': '/advertised_floor', 'value': value},
            {'op': 'replace', 'path': '/advertised_floor', 'value': None}]


def validate_reviews(rows, originals, decisions):
    current = {r['audit_id']: r for r in rows}
    original = {r['audit_id']: r for r in originals}
    reviews = {r['audit_id']: r for r in decisions}
    if len(current) != len(rows) or len(original) != len(originals) or len(reviews) != len(decisions):
        raise ValueError('Duplicate analytical/review identity')
    for identity, review in reviews.items():
        row = current.get(identity)
        if row is None or row != original.get(identity):
            raise ValueError('Reviewed source row changed or is absent from the revised cohort')
        if (review['decision'] not in WITHHOLD | {'retain_explicit_floor_claim'}
                or review['status'] != 'review_complete_recommendation_not_yet_projected'
                or review['label_prefix_validated_as_floor'] is not False
                or any(row.get(k) is not None for k in ('listed_floor', 'physical_floor', 'floors_above_ground'))
                or row.get('advertised_floor') != review['explicit_floor']
                or any(row[k] != review[k] for k in ('unit_id', 'building', 'source_listing_id'))
                or instant(row['known_at']) > instant(review['interpreted_at'])):
            raise ValueError('Floor review scope, value, identity or clock differs')
        proposed = None if review['decision'] in WITHHOLD else review['explicit_floor']
        if review['proposed_analytical_floor'] != proposed:
            raise ValueError('Proposed floor contradicts the reviewed disposition')
        captures = row.get('capture_ids', []) + ([row['capture_id']] if row.get('capture_id') is not None else [])
        expected = {(type(c).__name__, c) for c in captures}
        observed = {(type(c['capture_id']).__name__, c['capture_id']) for c in review['captures']}
        if not expected or expected != observed or len(observed) != len(review['captures']):
            raise ValueError('Floor correction requires every exact reviewed capture')
        for capture in review['captures']:
            if (any(capture[k] != row[k] for k in ('audit_id', 'unit_id', 'source_listing_id'))
                    or instant(capture['known_at']) > instant(review['interpreted_at'])):
                raise ValueError('Floor capture identity or clock differs')
            for span in capture['review_spans']:
                if capture['description'][span['start']:span['end']] != span['literal']:
                    raise ValueError('Floor review literal span differs')
    return reviews


def assemble(rows, originals, decisions, overlay):
    reviews = validate_reviews(rows, originals, decisions)
    expected = {key for key, r in reviews.items() if r['decision'] in WITHHOLD}
    if not expected or len(overlay.active) != len(expected):
        raise ValueError('Every withheld observation needs exactly one active correction')
    for edit in overlay.active:
        if (set(edit['target']) != {'source', 'source_listing_id', 'version_id'}
                or edit['target']['source'] != 'streeteasy' or edit['validity'] != {'all_time': True}):
            raise ValueError('Exact source-row-version floor correction required')
    revised, changes, applied = [], [], set()
    for row in rows:
        updated, edits = overlay.apply(row, {'source': 'streeteasy',
            'source_listing_id': row['source_listing_id'], 'version_id': hashed(row)})
        if edits:
            review = reviews.get(row['audit_id'])
            if len(edits) != 1 or review is None or row['audit_id'] not in expected:
                raise ValueError('Correction targets an unreviewed or retained floor')
            edit = edits[0]
            if (edit['id'] in applied or edit['patch'] != patch(row['advertised_floor'])
                    or instant(edit['recorded_at']) < instant(review['interpreted_at'])):
                raise ValueError('Correction patch or review clock differs')
            change = {**edit, 'audit_id': row['audit_id'], 'unit_id': row['unit_id'],
                'source_row_sha256': hashed(row), 'review_decision_sha256': hashed(review),
                'before_advertised_floor': row['advertised_floor'], 'after_advertised_floor': None,
                'review_decision': review['decision'], 'review_interpreted_at': review['interpreted_at'],
                'captures': [{k: c[k] for k in ('capture_id', 'body_sha256', 'raw_listing_sha256',
                    'description_sha256', 'source_collected_at', 'known_at', 'review_spans')}
                    for c in review['captures']]}
            updated.setdefault('attribute_review_history', []).append(deepcopy(change))
            changes.append(change); applied.add(edit['id'])
        revised.append(updated)
    if ({r['audit_id'] for r in changes} != expected or applied != {r['id'] for r in overlay.active}):
        raise ValueError('Correction ledger does not match every exact reviewed source version')
    return revised, changes


def run(dataset, reviewed_source, review, ledger, as_of, output):
    dataset, reviewed_source, review, ledger = map(Path, (dataset, reviewed_source, review, ledger))
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl'})
    sm, sf = _verified_bundle(reviewed_source, retain={'observations.jsonl'})
    rm, rf = _verified_bundle(review, retain={'decisions.jsonl'})
    if (dm.get('version') != 'reviewed-laundry-negation-projection-v1'
            or sm.get('version') != 'reviewed-scope-composition-projection-v2'
            or rm.get('version') != 'unit-label-floor-conflict-review-v1'
            or rm['source_manifest_sha256'] != digest(reviewed_source/'complete.json')):
        raise ValueError('Reviewed floor source lineage differs')
    rows, decisions = records(df['observations.jsonl']), records(rf['decisions.jsonl'])
    if len(decisions) != rm['summary']['observations']:
        raise ValueError('Review coverage differs')
    overlay = Overlay(ledger, as_of=as_of)
    revised, changes = assemble(rows, records(sf['observations.jsonl']), decisions, overlay)
    summary = {'rows': len(rows), 'reviewed_rows': len(decisions), 'changed_rows': len(changes),
        'retained_reviewed_claims': len(decisions)-len(changes),
        'current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in rows),
        'changed_current_rows': sum(a != b for a, b in zip(rows, revised, strict=True)
            if a['analysis_price_basis'] == 'current_capture_gross_ask'),
        'policy': 'Mask only reviewed ambiguous/reference-scoped advertised floor claims. Exact source versions; all original labels, claims, captures, prices and source clocks preserved. No label-prefix floor, building offset, physical height or physical change date inferred.'}
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in revised),
        'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes),
        'review-decisions.jsonl': rf['decisions.jsonl'].decode(),
        'corrections.jsonl': ''.join(canonical(r)+'\n' for r in overlay.records),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text(),
        'corrections.py': Path(corrections.__file__).read_text()}
    if 'current-source-evidence.jsonl' in df:
        files['current-source-evidence.jsonl'] = df['current-source-evidence.jsonl'].decode()
    return publish_bundle(output, files, {'version': VERSION, 'source_manifest': dm,
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'reviewed_source_manifest_sha256': digest(reviewed_source/'complete.json'),
        'review_manifest_sha256': digest(review/'complete.json'), 'overlay': overlay.manifest, 'summary': summary})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'reviewed_source', 'review', 'ledger', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
