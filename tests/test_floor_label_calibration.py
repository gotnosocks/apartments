from models.floor_label_calibration import calibrate


def row(unit, prefix, explicit, audit=None, building='b'):
    return dict(audit_id=audit or unit, unit_id=unit, building=building,
                candidate_floor=prefix, explicit_floor=explicit,
                capture_label_conflict=False, unresolved_capture_labels=0)


def test_whole_unit_holdouts_abstain_at_unsupported_endpoints():
    rows = [row(str(i), i, i+1) for i in range(1, 5)]
    result = calibrate(rows, {r['audit_id'] for r in rows}, set())
    assert result['buildings'][0]['offset'] == 1
    assert result['holdout_counts'] == {'agrees': 2, 'outside_other_units_prefix_range': 2}
    for h in result['whole_unit_holdouts']:
        assert h['training_rule']['units'] == 3


def test_repeated_ads_do_not_create_independent_unit_support():
    rows = [row('same-unit', i, i, audit=str(i)) for i in range(1, 6)]
    assert not calibrate(rows, {r['audit_id'] for r in rows}, set())['buildings']


def test_conflict_evidence_cannot_be_hidden_by_review_selection_or_masking():
    rows = [row(str(i), i, i) for i in range(1, 5)]
    reviewed = {r['audit_id'] for r in rows}
    assert not calibrate(rows+[row('bad', 3, 9)], reviewed, set())['buildings']
    assert not calibrate(rows, reviewed, {'b'})['buildings']


def test_candidates_require_interpolation_and_consistent_capture_labels():
    rows = [row(str(i), i, i+1) for i in range(1, 5)]
    reviewed = {r['audit_id'] for r in rows}
    rows += [row('new', 2, None), row('outside', 9, None), row('ambiguous', 2, None)]
    rows[-1]['unresolved_capture_labels'] = 1
    result = calibrate(rows, reviewed, set())
    assert [(r['unit_id'], r['inferred_floor_candidate']) for r in result['candidates']] == [('new', 3)]
