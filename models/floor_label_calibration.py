"""Evaluate building-specific label mappings with whole-unit holdouts.

This is a source-measurement experiment, not a raw-data correction or rent fit.
"""
from collections import Counter, defaultdict


def mapping(references, *, minimum_units=4):
    units = {r['unit_id'] for r in references}
    levels = sorted({r['candidate_floor'] for r in references})
    offsets = {r['explicit_floor']-r['candidate_floor'] for r in references}
    if len(units) < minimum_units or len(levels) < 2 or len(offsets) != 1:
        return None
    return {'offset': offsets.pop(), 'units': len(units),
            'prefix_min': min(levels), 'prefix_max': max(levels), 'prefix_levels': levels}


def calibrate(records, reviewed_ids, blocked_buildings):
    """Learn only from reviewed claims; never discard inconvenient disagreements.

    A full mapping needs four reference units and two prefix levels. Whole-unit
    holdouts need three remaining units/two levels; tests outside the training
    prefix range are abstentions, never silently successful extrapolations.
    """
    ids = [r['audit_id'] for r in records]
    if len(set(ids)) != len(ids) or not set(reviewed_ids) <= set(ids):
        raise ValueError('Unique source rows and present reviewed references required')
    by_building = defaultdict(list)
    for row in records:
        by_building[row['building']].append(row)
    buildings, holdouts, candidates = [], [], []
    for building, rows in sorted(by_building.items()):
        comparable = [r for r in rows if r['explicit_floor'] is not None
                      and r['candidate_floor'] is not None]
        reviewed = [r for r in comparable if r['audit_id'] in reviewed_ids]
        rule = mapping(reviewed)
        # Existing unreviewed comparable claims remain veto evidence. They must
        # not disappear merely because the agreeing rows were selected to review.
        if rule and any(r['explicit_floor']-r['candidate_floor'] != rule['offset']
                        for r in comparable):
            rule = None
        if building in blocked_buildings:
            rule = None
        if not rule:
            continue
        reference_units = {r['unit_id'] for r in reviewed}
        buildings.append({'building': building, **rule, 'reference_rows': len(reviewed)})
        for unit in sorted(reference_units):
            train = [r for r in reviewed if r['unit_id'] != unit]
            held = [r for r in reviewed if r['unit_id'] == unit]
            fitted = mapping(train, minimum_units=3)
            if fitted is None:
                status = 'insufficient_other_unit_support'
            elif any(not fitted['prefix_min'] <= r['candidate_floor'] <= fitted['prefix_max'] for r in held):
                status = 'outside_other_units_prefix_range'
            else:
                status = ('agrees' if all(r['candidate_floor']+fitted['offset'] == r['explicit_floor']
                                        for r in held) else 'disagrees')
            holdouts.append({'building': building, 'unit_id': unit, 'status': status,
                'training_rule': fitted, 'held_audit_ids': sorted(r['audit_id'] for r in held)})
        for row in rows:
            prefix = row['candidate_floor']
            if (row['explicit_floor'] is None and prefix is not None
                    and not row.get('capture_label_conflict', False)
                    and row.get('unresolved_capture_labels', 0) == 0
                    and rule['prefix_min'] <= prefix <= rule['prefix_max']):
                candidates.append({k: row[k] for k in ('audit_id', 'unit_id', 'building')} | {
                    'prefix': prefix, 'inferred_floor_candidate': prefix+rule['offset'],
                    'reference_unit': row['unit_id'] in reference_units,
                    'interpretation': 'Reviewed building offset, interpolated within observed prefix range; inferred numbering, not verified apartment floor or physical height.'})
    return {'buildings': buildings, 'whole_unit_holdouts': holdouts,
            'holdout_counts': dict(Counter(r['status'] for r in holdouts)),
            'candidates': candidates,
            'policy': 'Four distinct reference units and two prefix levels; no extrapolation. Known conflict buildings excluded before fitting any rule. Whole-unit holdouts diagnose these selected rules, not corpus-wide accuracy or independent validation.'}
