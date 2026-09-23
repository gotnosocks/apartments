import json

import numpy as np
import pandas as pd
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, publish_bundle
from models import outdoor_experiment as experiment, minimal_rent_model as baseline


def fixture(tmp_path):
    rows = []
    categories = []
    for period in pd.date_range("2020-01-01", "2022-12-01", freq="MS"):
        for unit in range(4):
            key = f"{period}-{unit}"
            rows.append(
                dict(
                    audit_id=key,
                    source_listing_id=key,
                    unit_id=f"u{unit}",
                    building=f"b{unit // 2}",
                    period=period.strftime("%Y-%m-%d"),
                    bedrooms=1.0,
                    bathrooms=1.0,
                    square_feet=600.0,
                    asking_rent=float(3000 * np.exp(0.02 * unit)),
                    analysis_price_basis="historical_initial_own_advertisement_ask",
                    advertised_ceiling_feet=10.0,
                    advertised_levels=None,
                    floor_through_mention=None,
                    skylight_mention=None,
                )
            )
            categories.append(
                dict(
                    audit_id=key,
                    source_listing_id=key,
                    unit_id=f"u{unit}",
                    private_outdoor_category="BALCONY" if unit % 2 else "TERRACE",
                    shared_outdoor_category=None,
                )
            )
    parent = {"dataset_version": "fixture"}
    interior = tmp_path / "interior"
    dm = publish_bundle(
        interior,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {
            "dataset_version": "advertised-interior-claims-v1",
            "parent_dataset_manifest": parent,
        },
    )
    audit = tmp_path / "audit"
    publish_bundle(
        audit,
        {"categories.jsonl": "".join(canonical(r) + "\n" for r in categories)},
        {
            "dataset_manifest": parent,
            "report": {"support": {"private": {"known_rows": 144}}},
        },
    )
    return interior, audit


def test_prepare_matched_fit_and_verified_replay(tmp_path, monkeypatch):
    interior, audit = fixture(tmp_path)
    dataset = tmp_path / "dataset"
    manifest = experiment.prepare(interior, audit, dataset)
    assert manifest["rows"] == 144
    assert experiment.prepare(interior, audit, dataset) == manifest
    old = experiment.records(
        _verified_bundle(interior, retain={"observations.jsonl"})[1][
            "observations.jsonl"
        ]
    )
    rows = experiment.records(
        _verified_bundle(dataset, retain={"observations.jsonl"})[1][
            "observations.jsonl"
        ]
    )
    assert [
        {k: v for k, v in r.items() if k not in experiment.FIELDS} for r in rows
    ] == old
    review = tmp_path / "review"
    publish_bundle(
        review,
        {"review.json": canonical({"decision": "proceed_exploratory"})},
        {"dataset_manifest": manifest},
    )
    output = tmp_path / "fit"
    grid = {"standard": experiment.SETTINGS_GRID["standard"]}
    result = experiment.run(dataset, review, output, settings_grid=grid)
    assert result["fits"] == 3
    for variant in experiment.VARIANTS:
        r = json.load(open(output / "standard" / variant / "result.json"))
        assert r["metrics"]["observations"] == 144
        assert r["serialization_maximum_log_difference"] == 0
    monkeypatch.setattr(
        baseline, "fit", lambda *a, **k: pytest.fail("Replay cannot refit")
    )
    assert experiment.run(dataset, review, output, settings_grid=grid) == result


def test_mismatched_source_rejected(tmp_path):
    interior, audit = fixture(tmp_path)
    bad = tmp_path / "bad"
    publish_bundle(bad, {"categories.jsonl": ""}, {"dataset_manifest": {"wrong": True}})
    with pytest.raises(ValueError, match="identical base cohort"):
        experiment.prepare(interior, bad, tmp_path / "out")
