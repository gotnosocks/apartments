from copy import deepcopy
import pytest
from models.source_movement_review import compare_details, select_cases


@pytest.mark.parametrize(
    "version,key,scope",
    [
        (
            "verified-bayesian-source-sensitivity-v1",
            "largest_distinct_unit_movements",
            "largest_common_distinct_unit_movements",
        ),
        (
            "reviewed-elevator-fit-comparison-v1",
            "largest_current_movements",
            "largest_current_distinct_unit_movements",
        ),
        (
            "reviewed-quarantine-fit-comparison-v1",
            "largest_current_movements",
            "largest_current_distinct_unit_movements",
        ),
    ],
)
def test_movement_selection_preserves_verified_order_and_distinct_units(
    version, key, scope
):
    cases = [
        {"unit_id": "a", "audit_id": "1"},
        {"unit_id": "a", "audit_id": "2"},
        {"unit_id": "b", "audit_id": "3"},
        {"unit_id": "c", "audit_id": "4"},
    ]
    chosen, actual_scope = select_cases(
        {"version": version, "residuals": {key: cases}}, 2
    )
    assert chosen == [cases[0], cases[2]] and actual_scope == scope


def test_unknown_or_empty_movement_report_is_refused():
    with pytest.raises(ValueError):
        select_cases({"version": "unknown"}, 3)
    with pytest.raises(ValueError):
        select_cases(
            {
                "version": "reviewed-quarantine-fit-comparison-v1",
                "residuals": {"largest_current_movements": []},
            },
            3,
        )


def test_expanded_floor_movement_selection_uses_all_cohort_distinct_units():
    cases = [
        {"unit_id": "a", "audit_id": "historical:1"},
        {"unit_id": "a", "audit_id": "current:2"},
        {"unit_id": "b", "audit_id": "historical:3"},
    ]
    report = {
        "version": "matched-expanded-floor-spline-fit-comparison-v1",
        "largest_distinct_unit_movements": cases,
    }
    chosen, scope = select_cases(report, 2)
    assert chosen == [cases[0], cases[2]]
    assert scope == "largest_common_distinct_unit_movements"


def detail():
    return {
        "audit_id": "a",
        "source_record": {
            "asking_rent": 5000,
            "source_listing_id": "ad",
            "unit_id": "u",
            "building": "b",
        },
        "mean_log_rent": 8.5,
        "contributions": [
            {"term": "intercept", "mean_log_contribution": 8.0},
            {"term": "building", "mean_log_contribution": 0.5},
        ],
        "grouped_contributions": {"intercept": 8.0, "building": 0.5},
        "fitted_median_rent": {"median": 4900, "lower_95": 4500, "upper_95": 5300},
        "contribution_diagnostics": {"acceptable": True},
    }


def test_decomposition_uses_additive_mean_log_changes_without_pairing_draws():
    a = detail()
    b = deepcopy(a)
    b["mean_log_rent"] = 8.6
    b["contributions"][1]["mean_log_contribution"] = 0.6
    b["grouped_contributions"]["building"] = 0.6
    r = compare_details(a, b)
    assert r["mean_log_rent_change"] == pytest.approx(0.1)
    assert r["term_changes"][0]["term"] == "building"
    assert r["reference_fitted_interval"] == r["candidate_fitted_interval"]


@pytest.mark.parametrize("damage", ["identity", "target", "sum", "terms"])
def test_invalid_comparisons_fail(damage):
    a = detail()
    b = deepcopy(a)
    if damage == "identity":
        b["audit_id"] = "different"
    if damage == "target":
        b["source_record"]["asking_rent"] = 6000
    if damage == "sum":
        b["mean_log_rent"] = 9
    if damage == "terms":
        b["contributions"][1]["term"] = "unit"
    with pytest.raises(ValueError):
        compare_details(a, b)
