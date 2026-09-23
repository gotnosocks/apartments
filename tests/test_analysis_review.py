import copy
import math

import pandas as pd
import pytest

from apartments import pricing, robust_pricing
from apartments.analysis_review import AnalysisWorkspace, bundle_signature
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import (
    amenity_ablation,
    amenity_rent_model,
    minimal_rent_model,
    residual_review,
)


@pytest.fixture(scope="module")
def source_fit():
    rows = []
    for period in pd.date_range("2024-01-01", "2024-06-01", freq="MS"):
        for i in range(12):
            rent = 2500 + 180 * i + 10 * period.month
            rows.append(
                dict(
                    audit_id=f"{period.month}-{i}",
                    unit_id=f"u{i}",
                    building=f"b{i // 3}",
                    building_id=f"b{i // 3}",
                    source_listing_id=str(period.month * 100 + i),
                    period=period.strftime("%Y-%m-%d"),
                    asking_rent=rent,
                    log_rent=math.log(rent),
                    bedrooms=i % 3,
                    bathrooms=1 + 0.5 * (i % 3),
                    square_feet=450 + 50 * i,
                    listed_floor=i + 1,
                    physical_floor=None,
                    elevator=bool(i % 2),
                    laundry_type=["in_building", "in_unit", None][i % 3],
                    doorman_type="full_time",
                    hvac_type=None,
                    pet_rules=None,
                    pet_policy="approval_required" if i % 2 else "not_allowed",
                    description="Source\u2028description",
                    capture_ids=[f"c{period.month}-{i}"],
                    known_at="2024-07-01T00:00:00Z",
                    collected_at="2024-06-30T00:00:00Z",
                    analysis_price_basis="historical_initial_own_advertisement_ask",
                )
            )
    train = pd.DataFrame(rows)
    train["period"] = pd.to_datetime(train.period)
    fit = minimal_rent_model.fit(
        train,
        amenity_rent_model.SETTINGS,
        iterations=20,
        encoder_class=amenity_ablation.encoder_class("full"),
    )
    artifact = {
        "version": robust_pricing.VERSION,
        "encoder": fit["encoder"].metadata(),
        "coefficients": fit["beta"].tolist(),
        "center": fit["center"],
        "training": {
            "knowledge_cutoff": "2024-07-01T00:00:00Z",
            "membership_sha256": "fixture-membership",
            "unit_buildings": {f"u{i}": f"b{i // 3}" for i in range(12)},
        },
    }
    return rows, artifact


@pytest.fixture
def workspace(tmp_path, source_fit):
    rows, artifact = copy.deepcopy(source_fit)
    dataset = tmp_path / "dataset"
    model_path = tmp_path / "model"
    residual_path = tmp_path / "residuals"
    dm = publish_bundle(
        dataset,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"dataset_version": "historical-plus-current-capture-analysis-v1"},
    )
    artifact["training"]["source_manifest"] = dm
    mm = publish_bundle(
        model_path,
        {"model.json": canonical(artifact) + "\n"},
        {
            "model_version": robust_pricing.VERSION,
            "runtime_sha256": digest(robust_pricing.__file__),
            "pricing_features_sha256": digest(pricing.__file__),
        },
    )
    model = robust_pricing.RobustPricingModel.load(model_path)
    residuals = [residual_review.residual(model, row) for row in rows]
    publish_bundle(
        residual_path,
        {
            "residuals.jsonl": "".join(canonical(r) + "\n" for r in residuals),
            "summary.json": "{}\n",
        },
        {
            "version": "fitted-residual-review-v1",
            "model_manifest": mm,
            "dataset_manifest": dm,
            "runtime_sha256": mm["runtime_sha256"],
            "pricing_features_sha256": mm["pricing_features_sha256"],
        },
    )
    return AnalysisWorkspace.load(model_path, dataset, residual_path), (
        model_path,
        dataset,
        residual_path,
    )


def test_detail_replays_components_history_and_normalizes_aliases(workspace):
    w, _ = workspace
    d = w.detail("1-0")
    assert math.exp(
        math.fsum(d["log_contributions_by_family"].values())
    ) == pytest.approx(d["residual"]["fitted_rent"])
    assert len(d["unit_history"]) == 6
    assert d["feature_values"]["pet_rules"] == "not_allowed"
    assert d["source_record"]["pet_rules"] is None
    assert d["source_record"]["description"] == "Source\u2028description"
    assert d["provenance"]["all_rows_in_fit"] is True


def test_supported_joint_contrast_matches_full_reencoding(workspace):
    w, _ = workspace
    changes = {
        "bedrooms": 1,
        "bathrooms": 1.5,
        "square_feet": 550,
        "laundry_type": "in_unit",
    }
    result = w.contrast("1-0", changes)
    source = w.detail("1-0")["source_record"]
    expected = w.model.predict({**source, **changes}, source["period"])
    assert result["show_estimate"] and result["status"] == "supported_association"
    assert result["estimate"]["changed_rent"] == pytest.approx(
        expected["predicted_rent"]
    )
    assert any("normalization" in s for s in result["warnings"])
    assert all(s["buildings_with_known_variation"] > 0 for s in result["support"])
    # Group effects and month are held fixed even with simultaneous layout edits.
    before = w.model.predict(source, source["period"])["log_components"]
    for key in before:
        if key.startswith(("building:", "unit:", "trend:", "season:")):
            assert expected["log_components"][key] == before[key]


def test_no_magnitude_zero_is_presented_for_unobserved_floor_or_reporting_change(
    workspace,
):
    w, _ = workspace
    result = w.contrast("1-0", {"physical_floor": 3})
    assert result["status"] == "unsupported" and not result["show_estimate"]
    assert result["support"][0]["known_rows"] == 0
    result = w.contrast("1-2", {"laundry_type": "in_unit"})
    assert result["status"] == "reporting_comparison" and not result["show_estimate"]
    # An unchanged unknown field does not invalidate a different supported edit.
    result = w.contrast("1-0", {"laundry_type": "in_unit", "physical_floor": None})
    assert result["show_estimate"]
    assert result["estimate"]["changes"] == {"laundry_type": "in_unit"}


def test_explicit_unknown_does_not_refill_from_raw_alias(workspace):
    w, _ = workspace
    result = w.contrast("1-0", {"pet_rules": None})
    assert not result["show_estimate"] and result["status"] == "reporting_comparison"
    assert result["estimate"]["status"] == "unknown_attribute_contrast"
    assert result["support"][0]["reference"] == "not_allowed"
    assert result["support"][0]["destination"] is None


def test_unsupported_joint_layout_and_numeric_extrapolation_are_visible(workspace):
    w, _ = workspace
    result = w.contrast("1-0", {"bedrooms": 1})
    assert not result["show_estimate"]
    assert any("combination" in s for s in result["warnings"])
    assert not w.contrast("1-0", {"square_feet": 1500})["show_estimate"]


@pytest.mark.parametrize(
    "changes",
    [
        {"building_id": "new"},
        {"bedrooms": 1.2},
        {"bathrooms": None},
        {"square_feet": float("nan")},
        {"elevator": "yes"},
        {"laundry_type": "invented"},
        {"bedrooms": 0},
    ],
)
def test_invalid_identity_layout_values_and_noop_rejected(workspace, changes):
    w, _ = workspace
    with pytest.raises(ValueError):
        w.contrast("1-0", changes)


def test_residual_mismatch_cache_invalidation_and_changed_bundle_fail_closed(workspace):
    w, paths = workspace
    wrong = copy.deepcopy(w.residuals)
    wrong[0]["asking_rent"] += 1
    with pytest.raises(ValueError, match="target or identity"):
        AnalysisWorkspace(w.model, w.rows, wrong, w.summary, w.manifests)
    wrong = copy.deepcopy(w.residuals)
    wrong[0]["asking_minus_fitted"] += 10
    with pytest.raises(ValueError, match="arithmetic"):
        AnalysisWorkspace(w.model, w.rows, wrong, w.summary, w.manifests)
    before = bundle_signature(*paths)
    file = paths[2] / "residuals.jsonl"
    file.write_text(file.read_text() + "\n")
    assert bundle_signature(*paths) != before
    with pytest.raises(ValueError):
        AnalysisWorkspace.load(*paths)


def test_same_length_different_residual_membership_rejected(workspace):
    w, _ = workspace
    wrong = copy.deepcopy(w.residuals)
    wrong[0]["audit_id"] = "another-row"
    with pytest.raises(ValueError, match="membership"):
        AnalysisWorkspace(w.model, w.rows, wrong, w.summary, w.manifests)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "wrong_ad",
        "future_capture",
        "future_recovery",
        "text_hash",
        "wrong_dataset",
    ],
)
def test_archived_descriptions_bind_identity_clock_and_exact_source_without_promoting_claims(
    workspace, tmp_path, fault
):
    w, _ = workspace
    capture = {
        "audit_id": "1-0",
        "unit_id": "u0",
        "source_listing_id": "wrong" if fault == "wrong_ad" else "100",
        "capture_id": "c1-0",
        "source_collected_at": "2024-08-01"
        if fault == "future_capture"
        else "2024-06-30",
        "description": "top-level fallback",
        "property_details": {
            "description": "Archived <b>private terrace</b>\u2028wording."
        },
        "extraction": {
            "experimental_inference": "must not be displayed as a physical fact"
        },
    }
    if fault == "future_recovery":
        capture["description_interpreted_at"] = "2024-08-01"
    if fault == "text_hash":
        capture["description_sha256"] = "invalid"
    path = tmp_path / "evidence"
    publish_bundle(
        path,
        {"evidence.jsonl": canonical(capture) + "\n"},
        {
            "version": "cohort-outdoor-evidence-v1",
            "dataset_manifest": {}
            if fault == "wrong_dataset"
            else w.manifests["dataset"],
        },
    )
    if fault:
        with pytest.raises(ValueError):
            w.attach_evidence(path)
        assert w.detail("1-0")["source_captures"] == []
    else:
        w.attach_evidence(path)
        detail = w.detail("1-0")
        shown = detail["source_captures"][0]
        assert shown["description"] == "Archived <b>private terrace</b>\u2028wording."
        assert shown["source_path"] == "/propertyDetails/description"
        assert "extraction" not in shown
        assert w.detail("1-1")["source_captures"] == []
