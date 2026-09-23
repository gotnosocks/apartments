"""Temporal validation, sampling, interactions and preference economics invariants."""

import math

import pytest

from apartments.pricing import PricingModel, fit_pricing_model, rank_apartments


def sample():
    rows = []
    for month in range(1, 11):
        for unit in range(12):
            beds = unit % 4
            physical = unit % 6 + 1
            elevator = unit % 2 == 0
            rows.append(
                {
                    "unit_id": str(unit),
                    "building_id": str(unit % 3),
                    "observed_at": f"2025-{month:02d}-10T10:00:00Z",
                    "bedrooms": beds,
                    "bathrooms": 1 + unit % 2,
                    "physical_floor": physical,
                    "advertised_floor": physical + (physical > 4),
                    "elevator": elevator,
                    "laundry_type": "in_unit" if unit % 3 else "none",
                    "window_exposures": ["south"] if unit % 2 else None,
                    "rent": math.exp(
                        7.5 + 0.2 * beds + 0.04 * physical * elevator + 0.005 * month
                    ),
                }
            )
    return rows


def test_chronological_encoder_and_fit_ignore_future_targets_and_categories(tmp_path):
    rows = sample()
    model = fit_pricing_model(rows)
    changed = [dict(r) for r in rows]
    for row in changed:
        if row["observed_at"] >= "2025-09":
            row.update(
                rent=1000000, square_feet=10000000, building_id="future-building"
            )
    future = fit_pricing_model(changed)
    assert future.encoder == model.encoder
    assert future.coefficients == model.coefficients
    assert model.report["train_end"] < "2025-09"
    assert model.report["holdout"]["rows"] == 24
    assert model.report["holdout"]["rmse_log"] < 0.03
    model.save(tmp_path / "pricing.json")
    loaded = PricingModel.load(tmp_path / "pricing.json")
    assert loaded.predict(rows[0]) == model.predict(rows[0])
    assert sum(model.decomposition(rows[0]).values()) == pytest.approx(
        model.predict(rows[0])["log_rent"]
    )
    unseen = dict(rows[0], building_id="never-seen")
    assert "building_id" in model.predict(unseen)["unseen_categories"]


def test_unit_month_selection_resists_capture_frequency_and_orders():
    rows = sample()
    duplicated = rows + rows[:20] * 10
    model = fit_pricing_model(rows)
    duplicate_model = fit_pricing_model(reversed(duplicated))
    assert model.coefficients == duplicate_model.coefficients
    assert (
        duplicate_model.report["selection"]["exclusions"][
            "superseded_unit_month_capture"
        ]
        == 200
    )
    conflict = dict(rows[0], rent=9000)
    with pytest.raises(ValueError, match="Conflicting simultaneous"):
        fit_pricing_model(rows + [conflict])


def test_floor_interaction_unknown_and_aliases():
    model = fit_pricing_model(sample())
    # Isolate the interaction coefficient to verify counterfactual recomputation.
    model.coefficients = [0.0] * len(model.coefficients)
    model.coefficients[0] = math.log(3000)
    feature = "physical_floor_x_elevator"
    index = model.encoder["features"].index(feature)
    model.coefficients[index] = 0.1 * model.encoder["numeric"][feature]["scale"]
    base = {"observed_at": "2025-01-01", "physical_floor": 5, "elevator": False}
    effect = model.marginal_contributions(base, {"elevator": True})
    assert effect["percent_change"] == pytest.approx(100 * (math.exp(0.5) - 1))
    unknown = dict(base, physical_floor=None, advertised_floor=14)
    assert "physical_floor.unknown" in model.decomposition(unknown)
    assert "physical_floor" not in model.decomposition(unknown)
    assert "listed_floor" in model.decomposition(unknown)
    assert "window_exposures.south.unknown" in model.decomposition(unknown)


def test_empty_invalid_and_short_windows():
    with pytest.raises(ValueError, match="two observation months"):
        fit_pricing_model([])
    with pytest.raises(ValueError, match="two observation months"):
        fit_pricing_model(sample()[:12])
    model = fit_pricing_model(sample()[:12], holdout_fraction=0)
    assert model.report["validation_mode"] == "descriptive_no_holdout"
    assert model.report["holdout"] == {"rows": 0}
    assert model.report["training_median_baseline_holdout_mae"] is None
    with pytest.raises(ValueError, match="training unit-months"):
        fit_pricing_model([], holdout_fraction=0)
    for options in (
        {"ridge": 0},
        {"holdout_fraction": 1},
        {"holdout_fraction": float("nan")},
    ):
        with pytest.raises(ValueError):
            fit_pricing_model(sample(), **options)
    rows = sample() + [
        {"rent": -1},
        {"rent": 10},
        {"rent": 10, "unit_id": "x", "observed_at": "bad"},
    ]
    exclusions = fit_pricing_model(rows).report["selection"]["exclusions"]
    assert (
        exclusions["invalid_rent"]
        == exclusions["missing_unit_id"]
        == exclusions["invalid_observation_time"]
        == 1
    )


def test_preference_frontier_negative_preferences_unknowns_and_duplicate_ties():
    rows = [
        {"unit_id": "a", "rent": 3000, "bedrooms": 1, "physical_floor": 2},
        {"unit_id": "b", "rent": 3000, "bedrooms": 1, "physical_floor": 5},
        {"unit_id": "c", "rent": 3200, "bedrooms": 2, "physical_floor": 2},
        {"unit_id": "d", "rent": 2000, "bedrooms": None, "physical_floor": 1},
    ]
    ranking = rank_apartments(rows, {"bedrooms": 500, "physical_floor": -20})
    by_id = {r["record"]["unit_id"]: r for r in ranking}
    assert ranking[0]["record"]["unit_id"] == "c"
    assert by_id["a"]["pareto_efficient"]
    assert not by_id["b"]["pareto_efficient"]
    assert not by_id["d"]["eligible"]
    assert ranking[-1]["unknown_preferences"] == ["bedrooms"]
    assert ranking[0]["monthly_surplus"] == -2240
    zero = rank_apartments(rows, {"bedrooms": 500}, unknown_policy="zero")
    assert zero[0]["record"]["unit_id"] == "d"
    ties = rank_apartments([rows[0], rows[0]], {"bedrooms": 500})
    assert all(r["pareto_efficient"] for r in ties)


def test_indicator_preferences_and_boolean_unknown():
    rows = [
        {
            "rent": 3000,
            "laundry_type": "in_unit",
            "elevator": True,
            "window_exposures": ["south"],
        },
        {
            "rent": 3000,
            "laundry_type": "none",
            "elevator": False,
            "window_exposures": [],
        },
    ]
    ranking = rank_apartments(
        rows,
        {"laundry_type=in_unit": 150, "elevator": 200, "window_exposures.south": 100},
    )
    assert ranking[0]["monthly_surplus"] == -2550
    assert ranking[0]["pareto_efficient"] and not ranking[1]["pareto_efficient"]
    assert not rank_apartments(
        [dict(rows[0], elevator="unspecified")], {"elevator": 200}
    )[0]["eligible"]


def test_support_warnings_audited_exclusions_and_preference_typos():
    rows = sample()
    extras = [
        dict(rows[0], unit_id="f", furnished=True),
        dict(rows[0], unit_id="s", short_term=True),
        dict(rows[0], unit_id="c", concession=True),
    ]
    model = fit_pricing_model(rows + extras)
    assert model.report["selection"]["exclusions"] == {
        "excluded_furnished": 1,
        "excluded_short_term": 1,
        "excluded_concession": 1,
    }
    support = model.report["feature_support"]["numeric"]["square_feet"]
    assert support["known_rows"] == 0 and support["missing_rows"] == 96
    effect = model.marginal_contributions(
        rows[0], {"square_feet": 900, "laundry_type": "future"}
    )
    assert len(effect["warnings"]) == 2
    assert "not identified" in effect["warnings"][0]
    with pytest.raises(ValueError, match="Unknown or unsupported"):
        rank_apartments(rows, {"bedroms": 100})
    with pytest.raises(ValueError, match="Unknown or unsupported"):
        rank_apartments(rows, {"window_exposures.souht": 100})
    alias = rank_apartments(
        [{"rent": 2000, "pet_policy": "allowed"}], {"pet_policy=allowed": 100}
    )
    assert alias[0]["monthly_surplus"] == -1900


@pytest.mark.parametrize(
    "field,value,preference",
    [
        ("doorman_type", "unspecified", "doorman_type=full_time"),
        ("laundry_type", "unknown", "laundry_type=in_unit"),
        ("laundry_type", "", "laundry_type=in_unit"),
        ("window_exposures", ["souht"], "window_exposures.south"),
        ("window_exposures", [None], "window_exposures.south"),
        ("window_exposures", [""], "window_exposures.south"),
        ("bedrooms", -1, "bedrooms"),
        ("square_feet", 0, "square_feet"),
        ("bathrooms", 0, "bathrooms"),
    ],
)
def test_ranking_rejects_unknown_and_invalid_feature_evidence(field, value, preference):
    row = {"rent": 3000, field: value}
    result = rank_apartments([row], {preference: 100})[0]
    assert not result["eligible"]
    assert result["unknown_preferences"] == [preference]


def test_partial_directional_evidence_preserves_unknowns_in_encoding_and_search():
    from apartments.pricing import _raw_features

    row = {
        "rent": 3000,
        "observed_at": "2025-01-01",
        "window_exposures": {"south": True, "west": False},
    }
    features = _raw_features(row, "2025-01-01")
    assert features["window_exposures.south"] == 1
    assert features["window_exposures.west"] == 0
    assert features["window_exposures.north"] is None
    assert rank_apartments([row], {"window_exposures.south": 100})[0]["eligible"]
    assert not rank_apartments([row], {"window_exposures.north": -100})[0]["eligible"]
    # A caller may explicitly provide a complete exposure set.
    complete = dict(row, window_exposures=["south"])
    assert rank_apartments([complete], {"window_exposures.north": -100})[0]["eligible"]
    with pytest.raises(ValueError, match="unsupported preference"):
        rank_apartments([row], {"laundry_type=unknown": 100})


def test_short_temporal_coverage_freezes_time_effects_and_future_extrapolation():
    rows = sample()[:12]
    for i, row in enumerate(rows):
        row["observed_at"] = f"2025-01-10T{10 + i // 6:02d}:{i % 6:02d}:00Z"
    model = fit_pricing_model(rows, holdout_fraction=0)
    for feature in ("trend_years", "season_sin", "season_cos"):
        support = model.report["feature_support"]["numeric"][feature]
        assert not support["enabled"]
        assert "frozen" in support["support_warning"].lower()
        assert model.coefficients[model.encoder["features"].index(feature)] == 0
    assert (
        model.predict(rows[0])["predicted_rent"]
        == model.predict(dict(rows[0], observed_at="2028-09-01"))["predicted_rent"]
    )
    assert (
        len(
            model.marginal_contributions(rows[0], {"observed_at": "2028-09-01"})[
                "warnings"
            ]
        )
        == 3
    )


def test_temporal_support_enables_trend_and_full_year_seasonality():
    rows = sample()
    for month in (11, 12):
        rows.extend(
            dict(r, observed_at=f"2025-{month:02d}-10T10:00:00Z") for r in sample()[:12]
        )
    model = fit_pricing_model(rows, holdout_fraction=0)
    assert all(
        model.encoder["numeric"][f]["enabled"]
        for f in ("trend_years", "season_sin", "season_cos")
    )
