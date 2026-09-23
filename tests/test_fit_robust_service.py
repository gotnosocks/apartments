"""A current refit must retain the validated specification and source clocks."""

import json

import numpy as np
import pandas as pd
import pytest

from apartments import robust_pricing
from models import amenity_rent_model as amenities
from models import minimal_rent_model as baseline
from models import rolling_rent_validation as rolling
from models import fit_robust_service as serving


def test_refit_parity_reuse_and_future_source_rejection(tmp_path, monkeypatch):
    records = []
    for period in pd.date_range("2017-01-01", "2019-12-01", freq="MS"):
        for unit in range(6):
            rent = 3000.0 + unit * 100
            records.append(
                dict(
                    period=period,
                    unit_id=f"u{unit}",
                    building=f"b{unit // 2}",
                    building_id=f"b{unit // 2}",
                    audit_id=f"{period}-{unit}",
                    source_listing_id=f"ad-{period}-{unit}",
                    bedrooms=1.0,
                    bathrooms=1.0,
                    square_feet=600.0,
                    asking_rent=rent,
                    log_rent=np.log(rent),
                    known_at="2020-01-01T00:00:00Z",
                )
            )
    data = pd.DataFrame(records)
    source = {"fixture": True, "as_of": "2020-01-01T00:00:00Z"}
    monkeypatch.setattr(amenities, "load_analytical", lambda _: (data, source, {}))
    validation = tmp_path / "validation"
    rolling.run(tmp_path, validation, start_year=2019, end_year=2019, min_rows=1)
    output = tmp_path / "serving"
    result = serving.run(tmp_path, validation, output, prediction_month="2020-01")
    model = robust_pricing.RobustPricingModel.load(output / "model")
    parity = json.loads((output / "model" / "parity.json").read_text())
    assert parity["rows"] == 216 and parity["maximum_relative_difference"] < 1e-11
    assert model.artifact["training"]["end_month"] == "2019-12-01"
    assert model.artifact["published_at"]

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Verified serving artifact must be reused without refitting"
        )

    monkeypatch.setattr(baseline, "fit", forbidden)
    assert (
        serving.run(tmp_path, validation, output, prediction_month="2020-01") == result
    )
    with pytest.raises(ValueError, match="month immediately before"):
        serving.run(
            tmp_path, validation, tmp_path / "stale", prediction_month="2020-02"
        )
    source["as_of"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="future"):
        serving.run(
            tmp_path, validation, tmp_path / "future", prediction_month="2020-01"
        )
