"""Outdoor comparisons separate advertised type from whether space is reported."""

import json

import numpy as np
import pandas as pd
import pytest

from models import amenity_rent_model as amenities
from models import interior_model as interior
from models import minimal_rent_model as baseline
from models import outdoor_model as outdoor


def sample():
    rows = []
    private = ["BALCONY", "TERRACE", "GARDEN", "unspecified", None, "BALCONY+TERRACE"]
    shared = ["ROOF_DECK", "GARDEN", None]
    for month in range(1, 5):
        for unit in range(60):
            category = private[(unit + month) % len(private)]
            height = [9.0, 11.0, None][unit % 3]
            log_rent = np.log(3000) + {"TERRACE": 0.1, "GARDEN": 0.2, None: -0.03}.get(
                category, 0.0
            )
            rows.append(
                dict(
                    unit_id=f"u{unit}",
                    building=f"b{unit // 6}",
                    period=pd.Timestamp(2024, month, 1),
                    bedrooms=1.0,
                    bathrooms=1.0,
                    square_feet=650.0,
                    asking_rent=np.exp(log_rent),
                    log_rent=log_rent,
                    advertised_ceiling_feet=height,
                    advertised_levels=2.0 if unit % 2 else None,
                    floor_through_mention=1.0 if unit % 3 else None,
                    skylight_mention=None,
                    private_outdoor_category=category,
                    shared_outdoor_category=shared[(unit + month // 2) % 3],
                )
            )
    return pd.DataFrame(rows)


def outdoor_columns(encoder, data):
    start, stop = encoder.offsets["outdoor"]
    return dict(
        zip(encoder.outdoor_features, encoder.matrix(data).toarray()[:, start:stop].T)
    )


def test_interior_variant_exact_matrix_and_penalty():
    data = sample()
    original = interior.encoder_class("values")(data)
    extended = outdoor.encoder_class("interior")(data)
    settings = {**amenities.SETTINGS, "interior_penalty": 3.0, "outdoor_penalty": 7.0}
    assert np.array_equal(
        original.matrix(data).toarray(), extended.matrix(data).toarray()
    )
    assert np.array_equal(
        original.penalty(settings).toarray(), extended.penalty(settings).toarray()
    )
    assert extended.interior_variant == "values"


def test_known_centering_separates_values_and_unknown_reporting():
    data = sample()
    encoder = outdoor.encoder_class("types")(data)
    columns = outdoor_columns(encoder, data)
    for field in outdoor.FIELDS:
        known = data[field].notna()
        types = [
            columns[f"{field}={value}"] for value in encoder.outdoor_categories[field]
        ]
        assert np.allclose(np.sum(types, axis=0), 0.0)
        for values in types:
            assert np.mean(values[known]) == pytest.approx(0.0, abs=1e-14)
            assert (values[~known] == 0.0).all()
        assert np.array_equal(columns[field + ".unknown"], ~known)
    changed = data.iloc[:3].copy()
    changed["private_outdoor_category"] = ["BALCONY", "TERRACE", None]
    types = outdoor_columns(encoder, changed)
    assert (
        types["private_outdoor_category=BALCONY"][0]
        != types["private_outdoor_category=BALCONY"][1]
    )
    reporting = outdoor_columns(outdoor.encoder_class("reporting")(data), changed)
    assert reporting["private_outdoor_category.unknown"].tolist() == [0.0, 0.0, 1.0]


def test_rare_pool_and_unseen_category_use_training_only():
    data = sample()
    data.loc[:3, "private_outdoor_category"] = "PATIO"
    data.loc[4:8, "private_outdoor_category"] = "ROOF_DECK"
    encoder = outdoor.encoder_class("types")(data)
    field = "private_outdoor_category"
    assert encoder.outdoor_category_counts[field]["PATIO"] == 4
    assert encoder.outdoor_category_mapping[field]["PATIO"] == "__rare__"
    assert encoder.outdoor_category_mapping[field]["ROOF_DECK"] == "__rare__"
    assert encoder.outdoor_category_centers[field]["__rare__"] == pytest.approx(
        9 / data[field].notna().sum()
    )
    probe = pd.concat([data.iloc[:1]] * 4, ignore_index=True)
    probe[field] = ["PATIO", "ROOF_DECK", "COURTYARD", None]
    columns = outdoor_columns(encoder, probe)
    for name, values in columns.items():
        if name.startswith(field + "="):
            assert values[0] == values[1]
            assert values[2] == values[3] == 0.0
    assert columns[field + ".unknown"].tolist() == [0.0, 0.0, 0.0, 1.0]
    # Hundreds of scoring observations cannot promote a training-rare category.
    encoder.matrix(pd.concat([probe.iloc[:1]] * 100, ignore_index=True))
    assert encoder.outdoor_category_mapping[field]["PATIO"] == "__rare__"


def test_single_known_category_cannot_identify_presence_premium():
    data = sample()
    data["private_outdoor_category"] = [
        "BALCONY" if i % 2 else None for i in range(len(data))
    ]
    encoder = outdoor.encoder_class("types")(data)
    columns = outdoor_columns(encoder, data)
    assert (columns["private_outdoor_category=BALCONY"] == 0).all()
    assert columns["private_outdoor_category.unknown"].sum() == len(data) // 2


@pytest.mark.parametrize("variant", outdoor.VARIANTS)
def test_real_fit_roundtrip_penalties_and_contrast_prediction(variant):
    data = sample()
    settings = {**amenities.SETTINGS, "interior_penalty": 3.0, "outdoor_penalty": 2.0}
    fitted = baseline.fit(
        data, settings, iterations=20, encoder_class=outdoor.encoder_class(variant)
    )
    assert fitted["robust_objective_relative_change"] < 1e-7
    encoder = fitted["encoder"]
    penalty = encoder.penalty(settings)
    assert penalty.shape[1] == encoder.matrix(data).shape[1] == encoder.n_parameters
    diagonal = np.asarray(penalty.power(2).sum(axis=0)).ravel()
    for family, amount in [("amenities", 10.0), ("interior", 3.0), ("outdoor", 2.0)]:
        start, stop = encoder.offsets[family]
        assert np.allclose(diagonal[start:stop], amount)
    fallback = np.asarray(
        encoder.penalty(amenities.SETTINGS).power(2).sum(axis=0)
    ).ravel()
    start, stop = encoder.offsets["outdoor"]
    assert np.allclose(fallback[start:stop], 10.0)
    saved = json.loads(
        json.dumps(
            {
                "encoder": encoder.metadata(),
                "beta": fitted["beta"].tolist(),
                "center": fitted["center"],
            }
        )
    )
    loaded = outdoor.load_saved(saved)
    assert json.loads(json.dumps(loaded["encoder"].metadata())) == saved["encoder"]
    probe = data.iloc[:3].copy()
    probe["private_outdoor_category"] = ["COURTYARD", "BALCONY", None]
    assert np.array_equal(
        baseline.predict(loaded, probe), baseline.predict(fitted, probe)
    )
    assert np.array_equal(
        encoder.penalty(settings).toarray(),
        loaded["encoder"].penalty(settings).toarray(),
    )
    contrasts = outdoor.category_contrasts(loaded)
    assert all(item["supported"] == (variant == "types") for item in contrasts)
    if variant == "types":
        for contrast in contrasts:
            before = probe.iloc[:1].copy()
            after = before.copy()
            before[contrast["field"]] = contrast["before"]
            after[contrast["field"]] = contrast["after"]
            actual = (
                baseline.predict(loaded, after)[0] - baseline.predict(loaded, before)[0]
            )
            assert actual == pytest.approx(contrast["log_rent_change"])
        assert 0.07 < contrasts[0]["log_rent_change"] < 0.12
        assert 0.16 < contrasts[1]["log_rent_change"] < 0.22


def test_rare_contrast_not_reported_and_bad_inputs_rejected():
    data = sample()
    data.loc[data.private_outdoor_category.eq("GARDEN"), "private_outdoor_category"] = (
        None
    )
    data.loc[0, "private_outdoor_category"] = "GARDEN"
    encoder = outdoor.encoder_class("types")(data)
    fitted = {"encoder": encoder, "beta": np.zeros(encoder.n_parameters), "center": 0.0}
    contrasts = outdoor.category_contrasts(fitted)
    assert contrasts[0]["supported"]
    assert not contrasts[1]["supported"]
    assert contrasts[1]["log_rent_change"] is None
    assert contrasts[1]["support"]["GARDEN"] == 1
    for value in [
        "",
        "balcony",
        "TERRACE+BALCONY",
        "BALCONY+BALCONY",
        "__rare__",
        1.0,
        np.inf,
        ["BALCONY"],
    ]:
        bad = data.copy()
        bad["private_outdoor_category"] = bad.private_outdoor_category.astype(object)
        bad.at[0, "private_outdoor_category"] = value
        with pytest.raises(ValueError, match="outdoor category"):
            outdoor.encoder_class("types")(bad)
    with pytest.raises(ValueError, match="Unknown outdoor"):
        outdoor.encoder_class("other")
    with pytest.raises(ValueError, match="version"):
        outdoor.load_saved({"encoder": {"model_version": "other"}})
    with pytest.raises(ValueError, match="coefficients"):
        outdoor.load_saved({"encoder": encoder.metadata(), "beta": [], "center": 0.0})
    with pytest.raises(ValueError, match="outdoor penalty"):
        encoder.penalty({**amenities.SETTINGS, "outdoor_penalty": -1.0})


def test_missing_columns_and_nullable_values_are_unknown():
    data = sample()
    data = data.drop(columns=list(outdoor.FIELDS))
    encoder = outdoor.encoder_class("types")(data)
    assert all(
        (values == 1).all() for values in outdoor_columns(encoder, data).values()
    )
    assert encoder.outdoor_categories == {field: [] for field in outdoor.FIELDS}
    data["private_outdoor_category"] = pd.Series([pd.NA] * len(data), dtype="string")
    assert all(
        (values == 1).all() for values in outdoor_columns(encoder, data).values()
    )
