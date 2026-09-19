"""Record reviewed exact-row elevator corrections and verify their dry-run effect.

All 109 literal capture denials in the bound replay were manually inspected.
The two opposing structured-code cases are masked, not adjudicated. This does
not publish a new model dataset or overwrite any prior analytical artifact.
"""
import json
import hashlib
from pathlib import Path

from apartments import corrections
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.cohort_spatial_features import verified_manifest, records

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT/'data/model/chelsea-reviewed-price-basis-complete-analysis-20260919'
AUDIT = ROOT/'data/model/chelsea-elevator-negation-replay-final-20260919'
LEDGER = ROOT/'config/reviews/chelsea-elevator-negation-20260919.jsonl'
OUTPUT = ROOT/'data/model/chelsea-elevator-reviewed-correction-preview-20260919'


def main():
    source_manifest, audit_manifest = verified_manifest(DATASET), verified_manifest(AUDIT)
    source_hash, audit_hash = digest(DATASET/'complete.json'), digest(AUDIT/'complete.json')
    if audit_manifest['dataset_manifest_sha256'] != source_hash:
        raise ValueError('Review belongs to a different analytical source')
    rows = {r['audit_id']: r for r in records(DATASET/'observations.jsonl')}
    candidates = list(records(AUDIT/'observations.jsonl'))
    captures = list(records(AUDIT/'captures.jsonl'))
    if (len(candidates) != 98 or len(captures) != 109 or
            sum(r['candidate_elevator'] is False for r in candidates) != 96 or
            sum(r['candidate_elevator'] is None for r in candidates) != 2):
        raise ValueError('Changed reviewed case inventory requires a new review')
    plans = {}
    for c in candidates:
        row = rows[c['audit_id']]
        bound = [e for e in captures if e['audit_id'] == c['audit_id']]
        expected = {(type(v).__name__, v) for v in row['capture_ids']}
        if ({(type(e['capture_id']).__name__, e['capture_id']) for e in bound} != expected
                or len(bound) != len(expected) or not c['all_captures_agree']
                or row['elevator'] is not True or row['source_listing_id'] != c['source_listing_id']
                or any(e['after']['value'] is not c['candidate_elevator'] for e in bound)):
            raise ValueError('Review needs every exact attached capture and agreed candidate')
        for e in bound:
            denials = [claim for claim in e['after']['claims'] if claim['value'] is False]
            if not denials or any(claim['method'] != 'description_pattern' or
                    e['description'][claim['start']:claim['end']] != claim['literal'] for claim in denials):
                raise ValueError('Missing literal denial')
        version = hashlib.sha256(canonical(row).encode()).hexdigest()
        edit = {'target': {'source': 'streeteasy', 'source_listing_id': row['source_listing_id'], 'version_id': version},
                'patch': [{'op': 'test', 'path': '/elevator', 'value': True},
                          {'op': 'replace', 'path': '/elevator', 'value': c['candidate_elevator']}],
                'validity': {'all_time': True}}
        corrections.validate_edit(edit)
        plans[version] = (row, edit)
    existing = corrections.Overlay(LEDGER).active if LEDGER.exists() else []
    if len({e['target']['version_id'] for e in existing}) != len(existing):
        raise ValueError('Repeated reviewed targets')
    for e in existing:
        if e['target']['version_id'] not in plans or {k: e[k] for k in ('target', 'patch', 'validity')} != plans[e['target']['version_id']][1]:
            raise ValueError('Unexpected existing review edit')
    done = {e['target']['version_id'] for e in existing}
    for version, (row, edit) in plans.items():
        if version in done: continue
        corrections.append(LEDGER, author='Codex source review', edit=edit,
            reason=('Correct non-elevator negation from every original advertisement capture. '
                    'Opposing structured/text assertions remain unknown; no facility change date or building-wide propagation.'),
            evidence=[str(AUDIT.relative_to(ROOT)), 'audit_manifest_sha256:'+audit_hash,
                      'source_manifest_sha256:'+source_hash, 'audit_id:'+row['audit_id']])
    # Use the last recorded knowledge clock for a deterministic preview.
    latest = corrections.Overlay(LEDGER).records[-1]['recorded_at']
    overlay = corrections.Overlay(LEDGER, as_of=latest)
    changes = []
    for version, (row, edit) in plans.items():
        updated, applied = overlay.apply(row, edit['target'])
        if len(applied) != 1 or {**updated, 'elevator': row['elevator']} != row:
            raise ValueError('Correction changed unrelated source fields')
        changes.append({'audit_id': row['audit_id'], 'unit_id': row['unit_id'], 'building': row['building'],
                        'before': row['elevator'], 'after': updated['elevator'], 'source_row_sha256': version,
                        'correction_id': applied[0]['id']})
    if digest(DATASET/'complete.json') != source_hash or digest(AUDIT/'complete.json') != audit_hash:
        raise ValueError('Bound source changed during review')
    summary = {'reviewed_rows': len(changes), 'negative_claim_rows': sum(c['after'] is False for c in changes),
        'conflict_mask_rows': sum(c['after'] is None for c in changes), 'captures': len(captures),
        'source_or_model_changed': False, 'ledger_sha256': digest(LEDGER), 'overlay': overlay.manifest}
    publish_bundle(OUTPUT, {'summary.json': canonical(summary)+'\n',
        'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes),
        'corrections.jsonl': LEDGER.read_text(), Path(__file__).name: Path(__file__).read_text()},
        {'version': 'reviewed-elevator-correction-preview-v1', 'dataset_manifest_sha256': source_hash,
         'source_audit_manifest_sha256': audit_hash})
    print(canonical({k: v for k, v in summary.items() if k != 'overlay'}))


if __name__ == '__main__': main()
