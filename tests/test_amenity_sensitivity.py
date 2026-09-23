"""Sensitivity must use exactly the reference cohort and preserve fitted artifacts."""

import json
import shutil

import numpy as np
import pandas as pd
import pytest

from models import amenity_ablation as ablation
from models import amenity_rent_model as model
from models import amenity_sensitivity as sensitivity
from models import minimal_rent_model as baseline


def sample():
    rows = []
    for year in (2017, 2018, 2019):
        for unit in range(30):
            rows.append(
                dict(
                    unit_id=f"u{unit}",
                    building=f"b{unit // 2}",
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


def test_prespecified_grid_separates_settings_and_preserves_defaults():
    original = dict(model.SETTINGS)
    specs = sensitivity.specifications(original)
    assert len(specs) == 10 and len({s["name"] for s in specs}) == 10
    assert original == model.SETTINGS
    assert {s["settings"]["building_penalty"] for s in specs} == {1, 10, 100}
    assert {s["unit_effect"] for s in specs} == {True, False}
    reference = next(s for s in specs if s["name"] == "building-10-units")
    assert reference["settings"] == original


def test_matched_reference_resume_and_source_rejection(tmp_path, monkeypatch):
    data = sample()
    monkeypatch.setattr(
        model, "load_analytical", lambda _: (data, {"fixture": True}, {})
    )
    reference = tmp_path / "reference"
    ablation.run(
        tmp_path / "input",
        reference,
        years=(2019,),
        cross_years=(2019,),
        folds=(0,),
        min_rows=1,
    )
    specs = sensitivity.specifications(model.SETTINGS)
    monkeypatch.setattr(sensitivity, "specifications", lambda _: [specs[1], specs[4]])
    root = tmp_path / "sensitivity"
    kwargs = dict(year=2019, building_fold=0, min_rows=1)
    result = sensitivity.run(tmp_path / "input", reference, root, **kwargs)
    report = json.loads((root / "summary" / "report.json").read_text())
    assert len(report["results"]) == 4
    fit = model.load_fit(root / "year-2019" / "building-10-units")
    test = data[data.period.dt.year.eq(2019)]
    stored = json.loads(
        (root / "year-2019" / "building-10-units" / "predictions.json").read_text()
    )
    assert np.allclose(np.exp(baseline.predict(fit, test)), stored)

    def forbidden(*args, **kwargs):
        raise AssertionError("Completed checkpoints must resume without fitting")

    monkeypatch.setattr(baseline, "fit", forbidden)
    assert sensitivity.run(tmp_path / "input", reference, root, **kwargs) == result
    assert sensitivity.verify_completed(root)["verified_grid_cells"] == 4
    # A checksummed fit from the same protocol but another setting is invalid.
    donor = root / "year-2019" / "building-10-units"
    recipient = root / "year-2019" / "building-10-no-units"
    shutil.rmtree(recipient)
    shutil.copytree(donor, recipient)
    with pytest.raises(ValueError, match="identity mismatch"):
        sensitivity.run(tmp_path / "input", reference, root, **kwargs)
    with pytest.raises(ValueError, match="identity mismatch"):
        sensitivity.verify_completed(root)
    monkeypatch.setattr(
        model, "load_analytical", lambda _: (data, {"fixture": False}, {})
    )
    with pytest.raises(ValueError, match="source changed"):
        sensitivity.run(tmp_path / "input", reference, tmp_path / "bad", **kwargs)


def test_centered_category_renaming_preserves_fitted_predictions():
    data = sample()
    renamed = data.copy()
    renamed["laundry_type"] = data.laundry_type.map(
        {"in_building": "zzz", "in_unit": "aaa"}
    )
    fits = [
        baseline.fit(
            frame,
            model.SETTINGS,
            iterations=20,
            unit_effect=False,
            encoder_class=ablation.encoder_class("full"),
        )
        for frame in (data, renamed)
    ]
    assert np.allclose(
        baseline.predict(fits[0], data),
        baseline.predict(fits[1], renamed),
        atol=1e-7,
        rtol=0,
    )
