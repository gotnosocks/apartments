"""Measure laundry category overlap within buildings and repeatedly listed units."""
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models.laundry_source_audit import records


def main():
    root = Path(__file__).resolve().parents[3]
    base = root/'data/model'
    measured = base/'chelsea-full-cohort-laundry-v3-20260919'
    dataset = base/'chelsea-reviewed-floor-masked-analysis-20260918'
    mm, mf = _verified_bundle(measured, retain={'observations.jsonl', 'captures.jsonl'})
    _, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    assert mm['dataset_manifest_sha256'] == digest(dataset/'complete.json')
    source = {r['audit_id']: r for r in records(sf['observations.jsonl'])}
    rows = records(mf['observations.jsonl'])
    assert len(rows) == len(source) and {r['audit_id'] for r in rows} == source.keys()
    units, buildings, by_building = defaultdict(set), defaultdict(set), defaultdict(list)
    changes = Counter()
    for row in rows:
        original = source[row['audit_id']]
        assert all(row[k] == original[k] for k in ('unit_id', 'building', 'analysis_price_basis'))
        category = row['candidate_category'] or 'unknown'
        units[row['unit_id']].add(category)
        buildings[row['building']].add(category)
        by_building[row['building']].append(row)
        changes[(row['old_laundry_type'] or 'unknown', category)] += 1
    categories = ('none', 'in_building', 'on_floor', 'in_unit')
    pairs = []
    for left, right in combinations(categories, 2):
        pair = {left, right}
        common = sorted(b for b, values in buildings.items() if pair <= values)
        varying = sorted(u for u, values in units.items() if pair <= values)
        stable = {}
        for b in common:
            names = {r['unit_id'] for r in by_building[b]}
            sides = {c: sorted(u for u in names if units[u] == {c}) for c in pair}
            if all(sides.values()):
                stable[b] = sides
        pairs.append({'left': left, 'right': right, 'buildings_with_both_reported_categories': len(common),
            'units_observed_in_both_categories': len(varying),
            'buildings_with_distinct_units_consistently_in_each_category': len(stable),
            'shared_buildings': common, 'varying_units': varying, 'stable_unit_buildings': stable})
    floor_units = {u for u, values in units.items() if 'on_floor' in values}
    floor_only = {u for u in floor_units if units[u] == {'on_floor'}}
    by_floor_building = []
    for b, group in by_building.items():
        if 'on_floor' not in buildings[b]:
            continue
        by_floor_building.append({'building': b,
            'observation_counts': dict(Counter(r['candidate_category'] or 'unknown' for r in group)),
            'unit_counts': {c: len({r['unit_id'] for r in group if (r['candidate_category'] or 'unknown') == c})
                            for c in (*categories, 'unknown')}})
    by_floor_building.sort(key=lambda r: (-r['unit_counts']['on_floor'], r['building']))
    # Literal witnesses show whether a category change is a contradictory claim
    # or merely an additional location detail. Do not infer installation dates.
    target = next(p for p in pairs if {p['left'], p['right']} == {'in_building', 'on_floor'})
    selected_units = target['varying_units'][:8]
    selected_rows = []
    for unit in selected_units:
        for category in ('in_building', 'on_floor'):
            pool = [r for r in rows if r['unit_id'] == unit and r['candidate_category'] == category]
            chosen = min(pool, key=lambda r: (source[r['audit_id']]['period'], r['audit_id']))
            selected_rows.append(chosen)
    captures = defaultdict(list)
    selected_ids = {r['audit_id'] for r in selected_rows}
    for capture in records(mf['captures.jsonl']):
        if capture['audit_id'] in selected_ids:
            captures[capture['audit_id']].append(capture)
    witnesses = [{**r, 'period': source[r['audit_id']]['period'],
                  'asking_rent': source[r['audit_id']]['asking_rent'],
                  'captures': captures[r['audit_id']]} for r in selected_rows]
    summary = {'version': 'laundry-category-overlap-audit-v1', 'rows': len(rows),
        'units': len(units), 'buildings': len(buildings),
        'units_with_on_floor_category': len(floor_units),
        'units_consistently_on_floor_across_all_observations': len(floor_only),
        'on_floor_units_with_other_recorded_categories': len(floor_units-floor_only),
        'pair_overlap': [{k: v for k, v in p.items() if k not in ('shared_buildings', 'varying_units', 'stable_unit_buildings')} for p in pairs],
        'category_transition_counts': [{'accepted_category': a, 'candidate_category': b, 'observations': n}
                                       for (a, b), n in sorted(changes.items())],
        'model_inputs_changed': False,
        'interpretation': 'Reported in-building laundry does not establish that facilities are on a different floor. Repeated-unit category changes may reflect copy specificity or equipment changes; this audit does not distinguish them. Stable-unit support is a descriptive check, not randomized or causal identification.'}
    publish_bundle(base/'chelsea-laundry-category-overlap-20260919', {
        'summary.json': canonical(summary)+'\n', 'pair-support.json': canonical(pairs)+'\n',
        'on-floor-buildings.jsonl': ''.join(canonical(r)+'\n' for r in by_floor_building),
        'within-unit-witnesses.jsonl': ''.join(canonical(r)+'\n' for r in witnesses),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': summary['version'], 'measurement_manifest_sha256': digest(measured/'complete.json'),
         'source_manifest_sha256': digest(dataset/'complete.json')})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    main()
