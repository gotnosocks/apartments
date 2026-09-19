"""Describe concentration and within-building/unit overlap for the exact split."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from apartments import laundry_floor_split as split
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(dataset, output):
    dataset = Path(dataset)
    manifest, _ = _verified_bundle(dataset)
    if manifest['version'] != split.VERSION:
        raise ValueError('Expected bounded same-floor split')
    buildings = defaultdict(Counter)
    units = defaultdict(lambda: defaultdict(set))
    unit_categories = defaultdict(set)
    periods = defaultdict(list)
    current = Counter()
    changed = set()
    for line in (dataset/'observations.jsonl').open():
        row = json.loads(line)
        category = row['laundry_type'] or 'unknown'
        building, unit = row['building'], row['unit_id']
        buildings[building][category] += 1
        units[building][category].add(unit)
        unit_categories[unit].add(category)
        if row['analysis_price_basis'] == 'current_capture_gross_ask': current[category] += 1
        if category == 'on_floor':
            if split.FIELD not in row: raise ValueError('Unbound on-floor observation')
            changed.add(row['audit_id'])
            periods[building].append(row['period'])
    if changed != set(manifest['changed_audit_ids']):
        raise ValueError('Split observation coverage differs')
    tables = []
    for building, counts in buildings.items():
        if not counts['on_floor']: continue
        known = units[building]
        tables.append({'building': building, 'rows_by_category': dict(counts),
            'units_by_category': {k: len(v) for k, v in known.items()},
            'on_floor_period_range': [min(periods[building]), max(periods[building])],
            'repeated_units_on_floor_and_generic': len(known['on_floor'] & known['in_building']),
            'stable_on_floor_units': sum(unit_categories[u] == {'on_floor'} for u in known['on_floor']),
            'stable_generic_units': sum(unit_categories[u] == {'in_building'} for u in known['in_building'])})
    tables.sort(key=lambda r: (-r['rows_by_category']['on_floor'], r['building']))
    result = {'version': 'bounded-laundry-floor-support-audit-v1',
        'on_floor_rows': len(changed), 'on_floor_buildings': len(tables),
        'on_floor_units': sum(r['units_by_category']['on_floor'] for r in tables),
        'buildings_with_generic_shared_laundry': sum(bool(r['rows_by_category'].get('in_building')) for r in tables),
        'buildings_with_distinct_stable_units_both_categories': sum(bool(r['stable_on_floor_units'] and r['stable_generic_units']) for r in tables),
        'units_with_both_categories': sum(r['repeated_units_on_floor_and_generic'] for r in tables),
        'largest_building_row_share': tables[0]['rows_by_category']['on_floor']/len(changed),
        'largest_three_buildings_row_share': sum(r['rows_by_category']['on_floor'] for r in tables[:3])/len(changed),
        'current_rows_by_category': dict(current),
        'interpretation': 'Coverage of reported categories, not independent observations or causal contrasts. A unit can change its wording or facilities. Period ranges date price observations, not facility validity.'}
    if digest(dataset/'observations.jsonl') != manifest['files']['observations.jsonl']:
        raise ValueError('Source changed during audit')
    publish_bundle(output, {'summary.json': canonical(result)+'\n',
        'buildings.jsonl': ''.join(canonical(r)+'\n' for r in tables), Path(__file__).name: Path(__file__).read_text()},
        {'version': result['version'], 'source_manifest_sha256': digest(dataset/'complete.json')})
    print(canonical({'summary': result, 'largest_buildings': tables[:5]}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
