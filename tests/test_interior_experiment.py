import json

import numpy as np
import pandas as pd
import pytest

from apartments import interior_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, publish_bundle
from models import interior_experiment as experiment, minimal_rent_model as baseline


def fixture(tmp_path):
    rows = []
    captures = []
    for i, period in enumerate(pd.date_range("2020-01-01", "2022-12-01", freq="MS")):
        for unit in range(4):
            key = f"{i}:{unit}"
            height = 9 + unit
            row = dict(
                audit_id=key,
                source_listing_id=key,
                unit_id=f"u{unit}",
                building=f"b{unit // 2}",
                canonical_unit_url=f"unit:{unit}",
                capture_ids=[key],
                capture_id=None,
                period=period.strftime("%Y-%m-%d"),
                known_at="2023-01-01T00:00:00Z",
                bedrooms=1.0,
                bathrooms=1.0,
                square_feet=600.0,
                asking_rent=float(3000 * np.exp(0.02 * unit + 0.001 * i)),
                analysis_price_basis="historical_initial_own_advertisement_ask",
            )
            rows.append(row)
            text = f"This apartment has {height}-foot ceilings."
            captures.append(
                {
                    k: row[k]
                    for k in (
                        "audit_id",
                        "source_listing_id",
                        "unit_id",
                        "canonical_unit_url",
                        "known_at",
                        "period",
                    )
                }
                | {
                    "capture_id": key,
                    "description": text,
                    "findings": interior_evidence.screen(text),
                }
            )
    source = tmp_path / "source"
    dm = publish_bundle(
        source,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"version": "fixture"},
    )
    evidence = tmp_path / "evidence"
    publish_bundle(
        evidence,
        {"evidence.jsonl": "".join(canonical(c) + "\n" for c in captures)},
        {"dataset_manifest": dm},
    )
    return source, evidence, dm


def test_prepare_preserves_prices_and_exact_scope_then_real_fit_replay(
    tmp_path, monkeypatch
):
    source, evidence, dm = fixture(tmp_path)
    dataset = tmp_path / "dataset"
    projected = experiment.prepare(source, evidence, dataset)
    assert projected["rows"] == 144
    assert projected["support"]["advertised_ceiling_feet"]["known_rows"] == 144
    assert (
        projected["support"]["advertised_ceiling_feet"][
            "buildings_with_known_value_variation"
        ]
        == 2
    )
    assert experiment.prepare(source, evidence, dataset) == projected
    before = experiment.records(
        _verified_bundle(source, retain={"observations.jsonl"})[1]["observations.jsonl"]
    )
    after = experiment.records(
        _verified_bundle(dataset, retain={"observations.jsonl"})[1][
            "observations.jsonl"
        ]
    )
    assert [
        {k: v for k, v in row.items() if k not in experiment.FIELDS} for row in after
    ] == before
    review = tmp_path / "review"
    publish_bundle(
        review,
        {"review.json": canonical({"decision": "proceed_exploratory"})},
        {"dataset_manifest": projected},
    )
    output = tmp_path / "experiment"
    result = experiment.run(
        dataset,
        review,
        output,
        settings_grid={"standard": experiment.SETTINGS_GRID["standard"]},
    )
    assert result["fits"] == 3
    for variant in experiment.VARIANTS:
        saved = json.load(open(output / "standard" / variant / "result.json"))
        assert saved["metrics"]["observations"] == 144
        assert saved["serialization_maximum_log_difference"] == 0
    monkeypatch.setattr(
        baseline, "fit", lambda *a, **k: pytest.fail("Replay must not refit")
    )
    assert (
        experiment.run(
            dataset,
            review,
            output,
            settings_grid={"standard": experiment.SETTINGS_GRID["standard"]},
        )
        == result
    )


def test_source_and_review_binding_fail_closed(tmp_path):
    source, evidence, dm = fixture(tmp_path)
    wrong = tmp_path / "wrong"
    publish_bundle(wrong, {"evidence.jsonl": ""}, {"dataset_manifest": {"wrong": True}})
    with pytest.raises(ValueError, match="ancestor"):
        experiment.prepare(source, wrong, tmp_path / "out")
    dataset = tmp_path / "projected"
    experiment.prepare(source, evidence, dataset)
    review = tmp_path / "review"
    publish_bundle(
        review,
        {"review.json": canonical({"decision": "proceed_exploratory"})},
        {"dataset_manifest": dm},
    )
    with pytest.raises(ValueError, match="matching source review"):
        experiment.run(dataset, review, tmp_path / "fit")
