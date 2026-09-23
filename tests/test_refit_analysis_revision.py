import json

import numpy as np
import pandas as pd
import pytest

from apartments import robust_pricing
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle, _verified_bundle
from models import fit_robust_analysis as analysis, refit_analysis_revision as revision
from models import amenity_rent_model as amenities, minimal_rent_model as baseline


def test_quarantine_is_explicit_and_never_rewrites_source_price():
    rows = [
        {"audit_id": "a", "source_listing_id": "10", "asking_rent": 30000},
        {"audit_id": "b", "source_listing_id": "20", "asking_rent": 3000},
    ]
    edit = {
        "audit_id": "a",
        "source_listing_id": "10",
        "action": "quarantine",
        "reasons": ["commercial"],
        "evidence": ["source hash"],
        "author": "reviewer",
    }
    kept, excluded = revision.apply_decisions(rows, [edit])
    assert kept == [rows[1]] and excluded[0]["record"]["asking_rent"] == 30000
    assert rows[0]["asking_rent"] == 30000
    with pytest.raises(ValueError, match="Unknown/duplicate"):
        revision.apply_decisions(rows, [edit, edit])
    with pytest.raises(ValueError, match="matching identity"):
        revision.apply_decisions(rows, [{**edit, "source_listing_id": "wrong"}])


def test_real_revision_fit_exact_cohort_comparison_and_replay(tmp_path, monkeypatch):
    rows = []
    for period in pd.date_range("2017-01-01", "2019-12-01", freq="MS"):
        for unit in range(6):
            rent = 3000.0 + 100 * unit
            rows.append(
                dict(
                    period=period,
                    unit_id=f"u{unit}",
                    building=f"b{unit // 2}",
                    building_id=f"b{unit // 2}",
                    audit_id=f"{period}-{unit}",
                    source_listing_id=f"{period}-{unit}",
                    bedrooms=1.0,
                    bathrooms=1.0,
                    square_feet=600.0,
                    asking_rent=rent,
                    rent=rent,
                    log_rent=np.log(rent),
                    known_at="2020-01-01T00:00:00Z",
                )
            )
    data = pd.DataFrame(rows)
    monkeypatch.setattr(
        amenities,
        "load_analytical",
        lambda _: (data, {"as_of": "2020-01-01T00:00:00Z"}, {}),
    )
    capture = dict(
        unit_id="u0",
        building_id="b0",
        source="streeteasy",
        source_listing_id="current",
        capture_id="c",
        collected_at="2020-01-02T00:00:00Z",
        known_at="2020-01-02T01:00:00Z",
        listing_status="ACTIVE",
        rent=3900,
        bedrooms=1,
        bathrooms=1,
        price_basis="gross_advertised_rent",
    )
    source = tmp_path / "current"
    publish_bundle(
        source,
        {"candidates.jsonl": canonical(capture) + "\n"},
        {"snapshot_version": "bounded-refreshed-candidates-v1"},
    )
    parent = tmp_path / "parent"
    analysis.run(tmp_path, source, parent, as_of="2020-01-02T02:00:00Z")
    dm, _ = _verified_bundle(parent / "dataset")
    edits = [
        {
            "audit_id": r["audit_id"],
            "source_listing_id": r["source_listing_id"],
            "action": "quarantine",
            "reasons": ["fixture"],
            "author": "reviewer",
            "evidence": ["fixture"],
        }
        for r in rows[:6]
    ]
    decisions = tmp_path / "decisions"
    publish_bundle(
        decisions,
        {"decisions.jsonl": "".join(canonical(edit) + "\n" for edit in edits)},
        {"dataset_manifest": dm, "recorded_at": "2020-01-03T00:00:00Z"},
    )
    output = tmp_path / "revised"
    result = revision.run(parent / "model", parent / "dataset", decisions, output)
    model = robust_pricing.RobustPricingModel.load(output / "model")
    assert model.artifact["training"]["rows"] == 211
    assert model.artifact["training"]["start_month"] == "2017-02-01"
    assert model.artifact["training"]["knowledge_cutoff"] == "2020-01-03T00:00:00Z"
    report = json.loads((output / "comparison/report.json").read_text())
    assert report["quarantined_rows"] == 6 and report["retained_rows"] == 211
    assert report["matched_retained_cohort"]["parent"]["observations"] == 211
    assert report["matched_retained_cohort"]["revised"]["observations"] == 211
    assert report["current_captures"]["rows"] == 1

    def forbidden(*args, **kwargs):
        raise AssertionError("Completed revision must not refit")

    monkeypatch.setattr(baseline, "fit", forbidden)
    assert (
        revision.run(parent / "model", parent / "dataset", decisions, output) == result
    )
