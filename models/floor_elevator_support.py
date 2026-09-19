"""Audit support for floor/elevator contrasts without fitting or imputing features."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apartments import pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_rent_model as amenity
from . import floor_label_research as labels

VERSION = 'floor-elevator-contrast-support-v2'


def count(rows):
    return {'rows': len(rows), 'units': len({r['unit_id'] for r in rows}),
            'buildings': len({r['building'] for r in rows})}


def summarize(rows):
    levels = sorted({r['floor'] for r in rows if r['floor'] is not None})
    groups = []
    for value, name in ((0., 'no_elevator'), (1., 'elevator'), (None, 'unknown_elevator')):
        chosen = [r for r in rows if r['elevator'] == value]
        known = [r for r in chosen if r['floor'] is not None]
        groups.append({'elevator': name, 'all': count(chosen), 'known_floor': count(known),
                       'floor_levels': sorted({r['floor'] for r in known})})
    contrasts = []
    for threshold in levels[:-1]:
        cells = []; within = []
        for value, name in ((0., 'no_elevator'), (1., 'elevator')):
            selected = [r for r in rows if r['elevator'] == value and r['floor'] is not None]
            low = [r for r in selected if r['floor'] <= threshold]
            high = [r for r in selected if r['floor'] > threshold]
            cells.append({'elevator': name, 'at_or_below': count(low), 'above': count(high)})
            within.append({'elevator': name,
                'buildings_on_both_sides': len({r['building'] for r in low} & {r['building'] for r in high}),
                'units_on_both_sides': len({r['unit_id'] for r in low} & {r['unit_id'] for r in high}),
                'building_ids_on_both_sides': sorted({r['building'] for r in low} & {r['building'] for r in high}),
                'unit_ids_on_both_sides': sorted({r['unit_id'] for r in low} & {r['unit_id'] for r in high})})
        # This diagnoses the naive product encoding, not a proposed unknown-value
        # policy. Unknown elevator evidence is explicitly counted separately.
        above = [r for r in rows if r['floor'] is not None and r['floor'] > threshold]
        contrasts.append({'threshold': threshold, 'cells': cells, 'within_group_support': within,
            'four_observed_cells_nonempty': all(c[s]['rows'] > 0 for c in cells for s in ('at_or_below', 'above')),
            'both_groups_have_within_building_floor_variation': all(w['buildings_on_both_sides'] > 0 for w in within),
            'above_threshold_unknown_elevator': count([r for r in above if r['elevator'] is None]),
            'naive_product_duplicates_floor_column': bool(above) and all(r['elevator'] == 1. for r in above)})
    variants = {}
    for row in rows:
        if row['elevator'] is not None:
            variants.setdefault(row['building'], set()).add(row['elevator'])
    return {'rows': len(rows), 'floor_levels': levels, 'elevator_groups': groups,
        'contradictory_or_changing_elevator_buildings': sum(len(v) > 1 for v in variants.values()),
        'thresholds': contrasts,
        'four_cell_thresholds': [r['threshold'] for r in contrasts if r['four_observed_cells_nonempty']],
        'within_building_supported_thresholds': [r['threshold'] for r in contrasts if r['both_groups_have_within_building_floor_variation']],
        'duplicate_interaction_thresholds': [r['threshold'] for r in contrasts if r['naive_product_duplicates_floor_column']]}


def ambiguity_sensitivity(rows):
    """Remove opposing-claim buildings only in a labelled support sensitivity."""
    variants = {}
    for row in rows:
        if row['elevator'] is not None:
            variants.setdefault(row['building'], set()).add(row['elevator'])
    ambiguous = {k for k, v in variants.items() if len(v) > 1}
    kept = [r for r in rows if r['building'] not in ambiguous]
    excluded = [r for r in rows if r['building'] in ambiguous]
    return {'policy': 'Support sensitivity excluding every building with both known positive and negative claims; not an adjudication or model-cohort edit.',
        'excluded_building_ids': sorted(ambiguous), 'excluded': count(excluded),
        'excluded_known_floor': count([r for r in excluded if r['floor'] is not None]),
        'support': summarize(kept)}


def run(dataset, label_audit, output):
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    source = [json.loads(s) for s in df['observations.jsonl'].decode().splitlines()]
    if len({r['audit_id'] for r in source}) != len(source):
        raise ValueError('Duplicate source observation')
    by_id = None
    if label_audit is not None:
        lm, lf = _verified_bundle(label_audit, retain={'observations.jsonl'})
        if (lm.get('version') != labels.VERSION
                or lm['summary']['source_manifest_sha256'] != digest(Path(dataset)/'complete.json')):
            raise ValueError('Label research belongs to a different source cohort')
        records = [json.loads(s) for s in lf['observations.jsonl'].decode().splitlines()]
        by_id = {r['audit_id']: r for r in records}
        if len(by_id) != len(records) or by_id.keys() != {r['audit_id'] for r in source}:
            raise ValueError('Floor-label audit coverage differs')
    explicit, inferred = [], []
    for row in source:
        normalized = amenity.feature_record(row)
        own = {k: row[k] for k in ('audit_id', 'unit_id', 'building')}
        own['elevator'] = pricing._boolean(normalized.get('elevator'))
        explicit.append({**own, 'floor': pricing._numeric_feature('listed_floor', normalized.get('listed_floor'))})
        if by_id is not None:
            label = by_id[row['audit_id']]
            if any(label[k] != row[k] for k in ('unit_id', 'building')):
                raise ValueError('Floor-label identity differs')
            inferred.append({**own, 'floor': label['candidate_floor']})
    reports = {'explicit_source_floor': summarize(explicit),
        'opposing_claim_building_sensitivity': ambiguity_sensitivity(explicit)}
    if by_id is not None:
        reports['unvalidated_label_candidate'] = summarize(inferred)
    reports['semantics'] = ('Support audit only, no model fit or inference integration. Label candidates and explicit claims are separate; neither is measured physical height. Empty cells and duplicate products prevent unrestricted interaction identification. Within-building overlap is necessary support, not sufficient adjustment or causal evidence. Repeated observations are not independent units. Conflicting elevator reports require source review.')
    return publish_bundle(output, {'support.json': canonical(reports)+'\n',
        'explicit-observations.jsonl': ''.join(canonical(r)+'\n' for r in explicit),
        Path(__file__).name: Path(__file__).read_text()}, {'version': VERSION,
        'dataset_manifest_sha256': digest(Path(dataset)/'complete.json'),
        'label_audit_manifest_sha256': digest(Path(label_audit)/'complete.json') if label_audit is not None else None,
        'implementation_sha256': {Path(m.__file__).name: digest(m.__file__) for m in (amenity, pricing)}})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'output'):
        p.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    p.add_argument('--label-audit', type=Path)
    print(canonical(run(**vars(p.parse_args()))))
