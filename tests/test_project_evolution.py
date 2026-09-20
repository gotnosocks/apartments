import json
from pathlib import Path

from apartments.project_evolution import (
    CATEGORIES,
    METRIC_DEFINITIONS,
    OBSERVATIONS,
    STATUSES,
    comparable_change,
    current_fit,
    current_selection,
    definitions,
    format_value,
    observations,
)


ROOT = Path(__file__).resolve().parents[1]


def test_metric_ledger_covers_all_pipeline_stages():
    assert {definition["stage"] for definition in METRIC_DEFINITIONS.values()} == set(CATEGORIES)
    assert set(item.status for item in OBSERVATIONS) <= set(STATUSES)
    assert len(METRIC_DEFINITIONS) >= 40
    assert len(OBSERVATIONS) >= 60


def test_every_metric_observation_has_a_definition_and_existing_evidence():
    for item in OBSERVATIONS:
        assert item.metric_id in METRIC_DEFINITIONS
        assert item.source
        assert all((ROOT / path).exists() for path in item.source), item
        assert item.value == item.value  # reject NaN without importing numpy


def test_stage_and_importance_filters_do_not_change_metric_identity():
    for category in CATEGORIES:
        stage_items = observations(stage=category)
        assert stage_items
        assert all(METRIC_DEFINITIONS[item.metric_id]["stage"] == category for item in stage_items)
    assert definitions("Data collection")
    assert definitions(importance="risk")


def test_comparable_changes_require_the_same_source_cohort_key():
    floor = comparable_change("transform.floor_coverage_pct")
    assert floor["comparable"] is True
    assert round(floor["delta"], 2) == 11.56

    rows = comparable_change("model.selected_rows")
    assert rows["comparable"] is False
    assert "Only one" in rows["reason"]


def test_metric_formatting_is_explicit():
    assert format_value("collection.building_roots", 1311) == "1,311"
    assert format_value("transform.floor_coverage_pct", 68.36) == "68.36%"
    assert format_value("model.max_rhat", 1.0039819) == "1.0040"
    assert format_value("model.current_fit_max_move_dollars", 13.21) == "$13.21"


def test_current_selection_and_fit_read_lightweight_saved_artifacts():
    selection = current_selection(ROOT)
    assert selection["available"] is True
    assert selection["model_family"] == "pymc_bayesian"
    cohort = json.loads((ROOT / "config/main-analysis.json").read_text())["cohort"]
    assert selection["rows"] == cohort["rows"]
    assert selection["units"] == cohort["units"]
    assert selection["buildings"] == cohort["buildings"]

    fit = current_fit(ROOT)
    assert fit["available"] is True
    assert fit["retained_draws"] == 24000
    assert fit["divergences"] == 0
    assert fit["max_rhat"] < 1.01
    assert fit["acceptable"] is True
