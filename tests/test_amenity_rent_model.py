"""Matched cohort, sparse feature, and honest temporal-validation invariants."""

import json

import numpy as np
import pandas as pd
import pytest

from models import amenity_rent_model as model
from models import minimal_rent_model as base
from apartments.research_pipeline import publish_bundle


def fixture():
    rows = []
    for year in range(2016, 2020):
        for month in (1, 4, 7, 10):
            for unit in range(20):
                rows.append(
                    {
                        "unit_id": f"u{unit}",
                        "building": f"b{unit % 5}",
                        "period": pd.Timestamp(year, month, 1),
                        "bedrooms": float(unit % 3),
                        "bathrooms": 1.0,
                        "square_feet": 500.0 + unit * 10,
                        "asking_rent": float(
                            np.exp(
                                8
                                + 0.2 * (unit % 3)
                                + 0.08 * (unit % 2)
                                + 0.02 * (year - 2016)
                            )
                        ),
                        "physical_floor": unit % 6 + 1,
                        "listed_floor": unit % 6 + 1,
                        "elevator": unit % 2 == 1,
                        "laundry_type": "in_unit" if unit % 2 else "none",
                        "doorman_type": None,
                        "hvac_type": "central_ac",
                        "window_exposures": {"south": True} if unit % 2 else None,
                    }
                )
    data = pd.DataFrame(rows)
    data["log_rent"] = np.log(data.asking_rent)
    return data


def test_sparse_extension_preserves_core_and_training_encoder():
    data = fixture()
    train = data[data.period < "2019-01-01"]
    encoder = model.AmenityEncoder(train, unit_effect=False)
    matrix = encoder.matrix(train)
    core = base.Encoder(train, unit_effect=False).matrix(train)
    assert np.allclose(matrix[:, : core.shape[1]].toarray(), core.toarray())
    assert encoder.penalty(model.SETTINGS).shape[1] == matrix.shape[1]
    before = encoder.metadata()
    future = data.iloc[:2].copy()
    future["laundry_type"] = "never_observed"
    future["physical_floor"] = 100
    future["building"] = "new-building"
    assert np.isfinite(encoder.matrix(future).data).all()
    assert encoder.metadata() == before
    assert "never_observed" not in encoder.amenity_categories["laundry_type"]


def test_interactions_recompute_and_partial_exposures_stay_unknown():
    data = fixture()
    enc = model.AmenityEncoder(data, unit_effect=False)
    row = data.iloc[:1].copy()
    row["physical_floor"] = 5
    row["elevator"] = False
    before = enc.matrix(row)
    row["elevator"] = True
    after = enc.matrix(row)
    start, _ = enc.offsets["amenities"]
    j = start + enc.amenity_features.index("physical_floor_x_elevator")
    expected = 5 / enc.amenity_numeric["physical_floor_x_elevator"]["scale"]
    assert float((after - before)[0, j]) == pytest.approx(expected)
    row["window_exposures"] = [{"south": True}]
    x = enc.matrix(row)
    j = start + enc.amenity_features.index("window_exposures.north.unknown")
    assert x[0, j] == 1


def test_robust_fit_converges_and_saved_design_roundtrips(tmp_path):
    data = fixture()
    fitted = base.fit(
        data,
        model.SETTINGS,
        unit_effect=False,
        iterations=12,
        encoder_class=model.AmenityEncoder,
    )
    assert fitted["robust_objective_relative_change"] < 1e-5
    original = base.predict(fitted, data)
    assert np.sqrt(np.mean((original - data.log_rent) ** 2)) < 0.03
    content = {
        "amenities": {
            "encoder": fitted["encoder"].metadata(),
            "beta": fitted["beta"].tolist(),
            "center": fitted["center"],
        }
    }
    publish_bundle(
        tmp_path,
        {"models.json": json.dumps(content, sort_keys=True)},
        {"version": model.VERSION},
    )
    loaded = model.load_fit(tmp_path)
    assert np.allclose(base.predict(loaded, data), original)


def test_paired_comparison_resamples_same_buildings():
    data = pd.DataFrame(
        {
            "building": ["a", "a", "b"],
            "asking_rent": [2000.0, 3000.0, 4000.0],
            "baseline_rent": [2200.0, 3300.0, 4400.0],
            "amenity_rent": [2000.0, 3000.0, 4000.0],
        }
    )
    result = model.paired_building_comparison(data, draws=100)
    assert result["difference"] == pytest.approx(-np.log(1.1))
    assert result["interval_95"][1] < 0
    assert result == model.paired_building_comparison(data, draws=100)


def test_dataframe_missing_values_do_not_become_category_levels_or_hide_aliases():
    row = model.feature_record(
        {
            "physical_floor": np.nan,
            "floors_above_ground": 5,
            "pet_policy": pd.NA,
            "period": "2024-01-01",
        }
    )
    assert row["physical_floor"] == 5
    assert row["pet_rules"] is None
    assert model.pricing._category(row["pet_rules"]) == "__unknown__"


def test_extracted_view_vocabulary_is_accepted_by_model():
    from apartments.attribute_evidence import extract_attribute_evidence

    attrs = extract_attribute_evidence(
        {"propertyDetails": {"features": {"views": ["CITY", "PARK"]}}}
    )["attributes"]
    raw = model.pricing._raw_features(
        {**attrs, "observed_at": "2024-01-01"}, "2020-01-01"
    )
    assert raw["view_exposures.park"] == 1
    assert raw["view_exposures.city"] == 1
    assert raw["view_exposures.courtyard"] is None


def test_category_contrast_matches_prediction_difference_and_rejects_unknown():
    from models.amenity_model_analysis import category_contrast

    data = fixture()
    fitted = base.fit(
        data,
        model.SETTINGS,
        unit_effect=False,
        iterations=12,
        encoder_class=model.AmenityEncoder,
    )
    reference = data.iloc[:1].copy()
    reference["laundry_type"] = "none"
    before = float(np.exp(base.predict(fitted, reference))[0])
    reference["laundry_type"] = "in_unit"
    after = float(np.exp(base.predict(fitted, reference))[0])
    contrast = category_contrast(
        fitted, "laundry_type", "none", "in_unit", baseline_rent=before
    )
    assert contrast["dollar_difference_at_reference"] == pytest.approx(after - before)
    with pytest.raises(ValueError, match="explicitly known"):
        category_contrast(fitted, "laundry_type", "__unknown__", "in_unit")
