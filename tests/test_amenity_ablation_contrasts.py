import json

import numpy as np
import pandas as pd
import pytest

from models import amenity_ablation as ablation
from models import amenity_ablation_contrasts as contrasts
from models import amenity_rent_model as model


def sample():
    rows = []
    for year in (2018, 2019):
        for unit in range(18):
            rows.append(
                dict(
                    unit_id=f"u{unit}",
                    building=f"b{unit // 3}",
                    audit_id=f"{year}-{unit}",
                    period=pd.Timestamp(year, 1, 1),
                    bedrooms=1.0,
                    bathrooms=1.0,
                    square_feet=600.0,
                    asking_rent=3000.0 + 100 * (unit % 3),
                    laundry_type=("in_building", "in_unit", None)[unit % 3],
                )
            )
    data = pd.DataFrame(rows)
    data["log_rent"] = np.log(data.asking_rent)
    return data


def test_centering_cancels_masks_apply_and_support_is_counted():
    data = sample()
    encoder = ablation.encoder_class("full")(data, unit_effect=False)
    beta = np.zeros(encoder.n_parameters)
    start = encoder.offsets["amenities"][0]
    names = encoder.amenity_features
    before = names.index("laundry_type=in_building")
    after = names.index("laundry_type=in_unit")
    beta[start + before] = 0.1
    beta[start + after] = 0.3
    fit = {"encoder": encoder, "beta": beta, "center": 8.0}
    result = contrasts.category_contrast(
        fit, data, "laundry_type", "in_building", "in_unit"
    )
    assert result["log_difference"] == pytest.approx(0.2)
    assert result["percent_difference"] == pytest.approx(100 * np.expm1(0.2))
    assert result["centering_cancellation_error"] < 1e-12
    assert result["support"]["in_unit"] == {
        "unit_months": 12,
        "units": 6,
        "buildings": 6,
    }
    assert result["buildings_with_both"] == 6
    assert result["units_with_both"] == 0
    encoder.amenity_active_columns[before] = False
    result = contrasts.category_contrast(
        fit, data, "laundry_type", "in_building", "in_unit"
    )
    assert result["log_difference"] == pytest.approx(0.3)


def test_unsupported_category_does_not_report_a_premium():
    data = sample()
    encoder = ablation.encoder_class("full")(data)
    fitted = {"encoder": encoder, "beta": np.zeros(encoder.n_parameters), "center": 8.0}
    result = contrasts.category_contrast(
        fitted, data, "pet_rules", "not_allowed", "approval_required"
    )
    assert result["status"] == "unsupported_category"
    assert result["percent_difference"] is None
    with pytest.raises(ValueError, match="known amenity values"):
        contrasts.category_contrast(
            fitted, data, "laundry_type", "__unknown__", "in_unit"
        )


def test_verified_replay_and_source_protocol_rejection(tmp_path, monkeypatch):
    source = {"fixture": True}
    monkeypatch.setattr(
        model, "load_analytical", lambda _: (sample(), source.copy(), {})
    )
    experiment = tmp_path / "fit"
    ablation.run(
        tmp_path / "input",
        experiment,
        years=(2019,),
        folds=(),
        unit_effect=False,
        min_rows=10,
    )
    output = tmp_path / "contrasts"
    manifest = contrasts.run(tmp_path / "input", experiment, output, split="year-2019")
    report = json.loads((output / "report.json").read_text())
    assert report["replay"]["verified"]
    assert report["replay"]["maximum_absolute_dollar_error"] < 1e-8
    assert report["training_rows"] == 18 and report["heldout_rows"] == 18
    assert (
        contrasts.run(tmp_path / "input", experiment, output, split="year-2019")
        == manifest
    )
    monkeypatch.setattr(
        model, "load_analytical", lambda _: (sample(), {"wrong_source": True}, {})
    )
    with pytest.raises(ValueError, match="source manifest"):
        contrasts.run(
            tmp_path / "input", experiment, tmp_path / "wrong", split="year-2019"
        )
    (experiment / "protocol.json").write_text(
        (experiment / "protocol.json").read_text() + "\n"
    )
    with pytest.raises(ValueError, match="protocol hash"):
        contrasts.run(
            tmp_path / "input",
            experiment,
            tmp_path / "wrong-protocol",
            split="year-2019",
        )
