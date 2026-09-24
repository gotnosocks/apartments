"""Known-value block comparisons must preserve matched rows and missingness controls."""

import json
import shutil

import numpy as np
import pandas as pd
import pytest

from models import amenity_ablation as ablation
from models import amenity_feature_blocks as blocks
from models import amenity_rent_model as model
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
                    asking_rent=3000.0 + 150 * (unit % 3),
                    laundry_type=("in_building", "in_unit", None)[unit % 3],
                    window_exposures={"south": True} if unit % 2 else None,
                )
            )
    data = pd.DataFrame(rows)
    data["log_rent"] = np.log(data.asking_rent)
    return data


def test_positive_unknown_exposure_design_has_no_value_contrast():
    data = sample()
    enc = ablation.encoder_class("exposures")(data)
    support = blocks._exposure_support(data)
    assert support["window_exposures.south"] == {
        "positive": 45,
        "negative": 0,
        "unknown": 45,
    }
    assert blocks._exposure_zero_check(enc, data, data)["zero_value_design"]
    data.at[1, "window_exposures"] = {"south": False}
    enc = ablation.encoder_class("exposures")(data)
    assert not blocks._exposure_zero_check(enc, data, data)["zero_value_design"]


def test_matched_reference_reuse_exposure_equivalence_and_wrong_checkpoint(
    tmp_path, monkeypatch
):
    data = sample()
    monkeypatch.setattr(
        model, "load_analytical", lambda _: (data, {"fixture": True}, {})
    )
    reference = tmp_path / "reference"
    ablation.run(
        tmp_path / "input", reference, years=(2019,), folds=tuple(range(5)), min_rows=1
    )
    root = tmp_path / "blocks"
    kwargs = dict(
        year=2019,
        folds=tuple(range(5)),
        blocks=("laundry", "exposures"),
        min_rows=1,
        error_draws=20,
    )
    result = blocks.run(tmp_path / "input", reference, root, **kwargs)
    report = json.loads((root / "summary" / "report.json").read_text())
    assert report["pooled_building_holdouts"]["rows"] == len(data)
    for split in report["splits"]:
        assert split["block_fits"]["exposures"]["exposure_diagnostic"][
            "predictions_match_missingness"
        ]
        assert split["metrics"]["exposures"]["log_rmse"] == pytest.approx(
            split["metrics"]["missingness"]["log_rmse"], abs=1e-10
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("Completed and reference fits must not be repeated")

    monkeypatch.setattr(baseline, "fit", forbidden)
    assert blocks.run(tmp_path / "input", reference, root, **kwargs) == result
    donor = root / "building-0" / "laundry"
    recipient = root / "building-0" / "exposures"
    shutil.rmtree(recipient)
    shutil.copytree(donor, recipient)
    with pytest.raises(ValueError, match="split/block/membership"):
        blocks.run(tmp_path / "input", reference, root, **kwargs)


def test_changed_reference_row_membership_is_rejected(tmp_path, monkeypatch):
    data = sample()
    monkeypatch.setattr(
        model, "load_analytical", lambda _: (data, {"fixture": True}, {})
    )
    reference = tmp_path / "reference"
    ablation.run(tmp_path / "input", reference, years=(2019,), folds=(0,), min_rows=1)
    changed = data.copy()
    changed["audit_id"] = changed.audit_id + "-changed"
    monkeypatch.setattr(
        model, "load_analytical", lambda _: (changed, {"fixture": True}, {})
    )
    with pytest.raises(ValueError, match="membership changed"):
        blocks.run(
            tmp_path / "input",
            reference,
            tmp_path / "bad",
            year=2019,
            folds=(0,),
            min_rows=1,
        )
