"""The analysis fit deliberately includes current asking-price observations."""

import json

import numpy as np
import pandas as pd
import pytest

from apartments import robust_pricing
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import amenity_rent_model as amenities, minimal_rent_model as baseline
from models import fit_robust_analysis as analysis
from models import residual_review


def historical():
    rows = []
    for period in pd.date_range("2017-01-01", "2019-12-01", freq="MS"):
        for unit in range(6):
            rent = 3000.0 + unit * 100
            rows.append(
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
                    rent=rent,
                    log_rent=np.log(rent),
                    known_at="2020-01-01T00:00:00Z",
                )
            )
    return pd.DataFrame(rows)


def capture(**changes):
    return {
        **dict(
            unit_id="u0",
            building_id="b0",
            source="streeteasy",
            source_listing_id="current-ad",
            capture_id="fresh-capture",
            collected_at="2020-01-02T00:00:00Z",
            known_at="2020-01-02T01:00:00Z",
            listing_status="ACTIVE",
            rent=3900.0,
            bedrooms=2.0,
            bathrooms=1.0,
            square_feet=600.0,
            price_basis="gross_advertised_rent",
        ),
        **changes,
    }


def test_refit_current_capture_preserves_past_attributes_and_replays(
    tmp_path, monkeypatch
):
    data = historical()
    monkeypatch.setattr(
        amenities,
        "load_analytical",
        lambda _: (data, {"as_of": "2020-01-01T00:00:00Z"}, {}),
    )
    source = tmp_path / "current"
    publish_bundle(
        source,
        {"candidates.jsonl": canonical(capture()) + "\n"},
        {"snapshot_version": "bounded-refreshed-candidates-v1"},
    )
    output = tmp_path / "analysis"
    kwargs = dict(as_of="2020-01-02T02:00:00Z")
    result = analysis.run(tmp_path, source, output, **kwargs)
    model = robust_pricing.RobustPricingModel.load(output / "model")
    assert (
        model.artifact["training"]["rows"] == 217
        and model.artifact["analysis"]["current_rows"] == 1
    )
    assert model.artifact["training"]["end_month"] == "2020-01-01"
    assert model.artifact["training"]["current_capture_ids"] == ["fresh-capture"]
    rows = [
        json.loads(s)
        for s in (output / "dataset/observations.jsonl").read_text().splitlines()
    ]
    unit = [r for r in rows if r["unit_id"] == "u0"]
    assert all(r["bedrooms"] == 1 for r in unit[:-1]) and unit[-1]["bedrooms"] == 2
    assert unit[-1]["analysis_price_basis"] == "current_capture_gross_ask"
    diagnostics = json.loads((output / "model/diagnostics.json").read_text())
    assert (
        diagnostics["parity_rows"] == 217
        and diagnostics["maximum_relative_difference"] < 1e-11
    )
    review = tmp_path / "review"
    reviewed = residual_review.run(
        output / "model", output / "dataset", review, top_units=2
    )
    assert (
        residual_review.run(output / "model", output / "dataset", review, top_units=2)
        == reviewed
    )
    summary = json.loads((review / "summary.json").read_text())
    assert summary["all"]["rows"] == 217 and summary["current"]["rows"] == 1

    def forbidden(*args, **kwargs):
        raise AssertionError("A completed analysis fit must be reused")

    monkeypatch.setattr(baseline, "fit", forbidden)
    assert analysis.run(tmp_path, source, output, **kwargs) == result
    with pytest.raises(ValueError, match="future"):
        analysis.run(tmp_path, source, tmp_path / "future", as_of="2099-01-01")


def test_inactive_stale_bad_layout_and_previous_month_excluded():
    accepted, excluded, _ = analysis.current_rows(
        [
            capture(listing_status="RENTED"),
            capture(
                unit_id="u1",
                source_listing_id="old",
                collected_at="2019-12-31T23:00:00Z",
            ),
            capture(unit_id="u2", source_listing_id="bad", bedrooms=1.5),
            capture(unit_id="u3", source_listing_id="valid"),
        ],
        as_of="2020-01-02T02:00:00Z",
        max_age_days=7,
    )
    assert [r["unit_id"] for r in accepted] == ["u3"]
    assert {r["reason"] for r in excluded} == {
        "latest_capture_not_confirmed_active",
        "capture_outside_current_analysis_month",
        "outside_analysis_rent_or_layout_support",
    }
