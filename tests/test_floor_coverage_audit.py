import pytest

from models.floor_coverage_audit import family, hypotheses


@pytest.mark.parametrize('label,expected', [
    ('#906', {'numeric_hundreds': 9}), ('#1404', {'numeric_hundreds': 14}),
    ('#S15K', {'north_south_wing_prefix': 15}),
    ('#4FE', {'front_rear_suffix': 4}), ('#3RW', {'front_rear_suffix': 3}),
    ('11THFLOOR', {'explicit_ordinal_label': 11}),
    ('11THFL', {'explicit_ordinal_label': 11}),
    ('#1BEDS', {}), ('#1BR', {}), ('#PH9/10A', {}), ('#10215', {}),
    ('#001', {}), ('#15', {}), (None, {}), ('#0A', {}),
])
def test_review_hypotheses_preserve_unsupported_formats(label, expected):
    assert hypotheses(label) == expected


@pytest.mark.parametrize('label,expected', [
    ('#4', 'numeric_1_digits'), ('#31', 'numeric_2_digits'),
    ('#906', 'numeric_3_digits'), ('#1BEDS', 'digits_then_letters'),
    ('#N10Q', 'letter_prefix'), ('#PH9/10A', 'other_format'),
    (None, 'missing_label'), (' ', 'missing_label'),
])
def test_census_families_do_not_claim_floor_truth(label, expected):
    assert family(label) == expected
