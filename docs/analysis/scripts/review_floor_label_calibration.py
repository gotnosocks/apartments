"""Reproduce the September 19 review of four local unit-number mappings."""
import json
from pathlib import Path
import re

from apartments import pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import amenity_rent_model as amenity
from models import floor_elevator_support as support
from models import floor_label_calibration as calibration


# Reviewed own-unit statements, not building height or video-only references.
REVIEWED_ADS = {
    '317-west-22-street-new_york': ['4333618', '2864102', '2717119', '3276791', '3051831',
        '3874120', '3204385', '4756979', '4773527', '2393389', '3623236'],
    '312-west-20-street-new_york': ['2817838', '4302119', '3783088', '4785723', '4125851',
        '5138225', '4169294', '3002487', '3042268'],
    '350-west-18-street-new_york': ['1719197', '2001591', '2094316', '1751773', '1643999',
        '1675087', '2059853', '2057195'],
    '152-west-20-street-new_york': ['3915964', '3688851', '4230838', '3751256', '4192324'],
}


def main():
    root = Path(__file__).resolve().parents[3]
    dataset = root/'data/model/chelsea-reviewed-scope-composition-projection-20260918'
    labels = root/'data/model/chelsea-unit-label-floor-audit-20260918'
    descriptions = root/'data/model/chelsea-analysis-descriptions-20260918'
    conflict_review = root/'data/model/chelsea-floor-label-conflict-review-20260918'
    output = root/'data/model/chelsea-floor-label-calibration-20260919'
    _, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    lm, lf = _verified_bundle(labels, retain={'observations.jsonl', 'captures.jsonl'})
    _, ef = _verified_bundle(descriptions, retain={'evidence.jsonl'})
    _, rf = _verified_bundle(conflict_review, retain={'review-policy.json'})
    policy = json.loads(rf['review-policy.json'])
    if (lm['summary']['source_manifest_sha256'] != digest(dataset/'complete.json')
            or policy['label_audit_manifest_sha256'] != digest(labels/'complete.json')
            or policy['descriptions_manifest_sha256'] != digest(descriptions/'complete.json')):
        raise ValueError('Review source bindings differ')
    source = {r['audit_id']: r for r in map(json.loads, df['observations.jsonl'].splitlines())}
    records = list(map(json.loads, lf['observations.jsonl'].splitlines()))
    by_id = {r['audit_id']: r for r in records}
    if by_id.keys() != source.keys():
        raise ValueError('Source and label audit coverage differs')
    ads = {ad: b for b, values in REVIEWED_ADS.items() for ad in values}
    selected = {identity for identity, r in source.items() if str(r['source_listing_id']) in ads}
    if {str(source[i]['source_listing_id']) for i in selected} != ads.keys():
        raise ValueError('Reviewed advertisement coverage differs')
    captures = {(r['audit_id'], r['capture_id']): r
                for r in map(json.loads, lf['captures.jsonl'].splitlines()) if r['audit_id'] in selected}
    evidence, seen = [], set()
    for e in map(json.loads, ef['evidence.jsonl'].splitlines()):
        if e['audit_id'] not in selected:
            continue
        identity = (e['audit_id'], e['capture_id'])
        reference = by_id[e['audit_id']]
        capture = captures[identity]
        if (reference['building'] != ads[str(e['source_listing_id'])]
                or e['unit_id'] != reference['unit_id']
                or e['raw_listing_sha256'] != capture['raw_listing_sha256']
                or identity in seen):
            raise ValueError('Reviewed capture identity differs')
        seen.add(identity)
        description = e['description'] or ''
        spans = []
        for match in re.finditer(r'\b([1-9][0-9]?)(?:st|nd|rd|th)\s+floor\b', description, re.I):
            if int(match[1]) != reference['explicit_floor']:
                raise ValueError('Review contains a different numbered-floor claim')
            start, end = max(0, match.start()-100), min(len(description), match.end()+100)
            spans.append({'start': start, 'end': end, 'text': description[start:end]})
        if not spans:
            raise ValueError('Reviewed explicit numbered-floor phrase is absent')
        evidence.append({**e, 'floor_spans': spans, 'label_capture': capture,
            'review': 'Own-apartment floor wording supports a local numbering hypothesis. Nearby media references and building-height descriptions were considered separately. Repeated copy is not independent unit evidence.'})
    if seen != captures.keys():
        raise ValueError('Every reference capture must have matching evidence')
    blocked = {by_id[c['audit_id']]['building'] for c in policy['cases']
               if c['interpretation'] != 'supported_local_offset'}
    result = calibration.calibrate(records, selected, blocked)
    inferred = {r['audit_id']: r for r in result.pop('candidates')}
    baseline, augmented = [], []
    withheld = {c['audit_id'] for c in policy['cases'] if c['decision'].startswith('withhold')}
    for identity, r in source.items():
        normalized = amenity.feature_record(r)
        floor = None if identity in withheld else pricing._numeric_feature('listed_floor', normalized.get('listed_floor'))
        base = {k: r[k] for k in ('audit_id', 'unit_id', 'building')}
        base.update(floor=floor, elevator=pricing._boolean(normalized.get('elevator')))
        baseline.append(base)
        augmented.append({**base, 'floor': floor if floor is not None else inferred.get(identity, {}).get('inferred_floor_candidate')})
    result.update(reference_rows=len(selected), reference_captures=len(evidence),
        blocked_buildings=sorted(blocked), additional_candidate_rows=len(inferred),
        additional_candidate_units=len({r['unit_id'] for r in inferred.values()}),
        new_reference_unseen_units=len({r['unit_id'] for r in inferred.values() if not r['reference_unit']}),
        cohort_rows=len(source), current_cohort=False,
        explicit_floor_after_review=support.summarize(baseline),
        explicit_plus_local_candidates=support.summarize(augmented),
        limitations='Selected historical/source cohort of 52,704 rows, not the refreshed 172-current cohort. Retrospective numbering review; no effective historical floor-change dates inferred. No rent model fit or analytical values changed.')
    publish_bundle(output, {'summary.json': canonical(result)+'\n',
        'candidates.jsonl': ''.join(canonical(r)+'\n' for _, r in sorted(inferred.items())),
        'reference-evidence.jsonl': ''.join(canonical(r)+'\n' for r in evidence),
        'reviewed-advertisements.json': canonical(REVIEWED_ADS)+'\n',
        Path(__file__).name: Path(__file__).read_text(),
        'floor_label_calibration.py': Path(calibration.__file__).read_text()},
        {'version': 'reviewed-local-floor-label-calibration-v1',
         'dataset_manifest_sha256': digest(dataset/'complete.json'),
         'label_manifest_sha256': digest(labels/'complete.json'),
         'descriptions_manifest_sha256': digest(descriptions/'complete.json'),
         'conflict_review_manifest_sha256': digest(conflict_review/'complete.json'),
         'support_implementation_sha256': {Path(m.__file__).name: digest(m.__file__) for m in (support, amenity, pricing)}})
    print(canonical({k: result[k] for k in ('buildings', 'reference_rows', 'reference_captures',
        'holdout_counts', 'additional_candidate_rows', 'additional_candidate_units', 'new_reference_unseen_units')}))


if __name__ == '__main__':
    main()
