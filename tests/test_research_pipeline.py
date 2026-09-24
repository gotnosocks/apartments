"""End-to-end artifact and provenance contracts, with no network or production writes."""

import json

import pytest
from typer.testing import CliRunner

from apartments.analytical import build_dataset
from apartments.cli import app
from apartments.research_pipeline import (
    fit_dataset,
    publish_bundle,
    rank_candidates,
    read_bundle,
)


def captures():
    for month in range(1, 5):
        for unit in range(12):
            at = f"2026-{month:02d}-01T12:00:00Z"
            yield {
                "observation": {
                    "version_id": f"v{month}-{unit}",
                    "capture_id": f"c{month}-{unit}",
                    "source": "streeteasy",
                    "source_listing_id": f"b/{unit}",
                    "building_slug": "b",
                    "unit": str(unit),
                    "collected_at": at,
                    "recorded_at": at,
                },
                "raw": {
                    "status": "ACTIVE",
                    "asking_rent": 2500 + unit * 130 + month * 25,
                    "attributes": {
                        "bedrooms": unit % 3,
                        "bathrooms": 1,
                        "elevator": bool(unit % 2),
                    },
                },
                "provenance": {},
            }


def test_end_to_end_idempotent_analytics_model_and_frontier(tmp_path):
    dataset, fit, ranking = (tmp_path / name for name in ("dataset", "fit", "ranking"))
    source = build_dataset(captures(), dataset, as_of="2026-05-01")
    assert (
        build_dataset(reversed(list(captures())), dataset, as_of="2026-05-01") == source
    )
    manifest = fit_dataset(dataset, fit)
    assert fit_dataset(dataset, fit) == manifest
    report = json.loads((fit / "report.json").read_text())
    assert report["holdout"]["rows"] == 12
    assert report["train_end"] < report["holdout_end"]
    candidates, prefs = tmp_path / "candidates.jsonl", tmp_path / "prefs.json"
    rows = [
        dict(
            unit_id="a", rent=3000, bedrooms=1, elevator=False, observed_at="2026-05-01"
        ),
        dict(
            unit_id="b", rent=3100, bedrooms=1, elevator=True, observed_at="2026-05-01"
        ),
        dict(
            unit_id="c", rent=3300, bedrooms=1, elevator=True, observed_at="2026-05-01"
        ),
    ]
    candidates.write_text("".join(json.dumps(r) + "\n" for r in rows))
    prefs.write_text('{"elevator":200}')
    result = rank_candidates(candidates, prefs, ranking, budget=3200, model_bundle=fit)
    assert result["frontier"] == 2 and result["over_budget"] == 1
    ranked = [
        json.loads(line)
        for line in (ranking / "rankings.jsonl").read_text().splitlines()
    ]
    assert ranked[0]["record"]["unit_id"] == "b"
    assert "asking_minus_predicted" in ranked[0]["market_comparison"]
    assert read_bundle(ranking) == result
    assert (
        rank_candidates(candidates, prefs, ranking, budget=3200, model_bundle=fit)
        == result
    )


def test_tampered_or_unfinished_analytical_bundle_cannot_train(tmp_path):
    dataset = tmp_path / "dataset"
    build_dataset(captures(), dataset, as_of="2026-05-01")
    (dataset / "observations.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="integrity"):
        fit_dataset(dataset, tmp_path / "fit")
    assert not (tmp_path / "fit").exists()
    (dataset / "complete.json").unlink()
    with pytest.raises(FileNotFoundError):
        fit_dataset(dataset, tmp_path / "fit")


def test_publication_refuses_changed_settings_and_symlink_artifacts(tmp_path):
    root = tmp_path / "run"
    publish_bundle(root, {"rows.jsonl": "{}\n"}, {"version": 1})
    with pytest.raises(ValueError, match="identity"):
        publish_bundle(root, {"rows.jsonl": "{}\n"}, {"version": 2})
    outside = tmp_path / "outside"
    outside.write_text("{}\n")
    (root / "rows.jsonl").unlink()
    (root / "rows.jsonl").symlink_to(outside)
    with pytest.raises(ValueError, match="Invalid artifact"):
        read_bundle(root)


def test_rank_cli_and_invalid_preference_fail_without_publishing(tmp_path):
    candidates, preferences = tmp_path / "input.jsonl", tmp_path / "prefs.json"
    candidates.write_text('{"rent":2500,"bedrooms":1}\n')
    preferences.write_text('{"bedrooms":500}')
    result = CliRunner().invoke(
        app,
        ["rank-apartments", str(candidates), str(preferences), str(tmp_path / "out")],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["frontier"] == 1
    preferences.write_text('{"bedroooms":500}')
    with pytest.raises(ValueError):
        rank_candidates(candidates, preferences, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_verified_bytes_are_the_actual_training_input(tmp_path, monkeypatch):
    from apartments import research_pipeline as pipeline

    source = tmp_path / "source"
    build_dataset(captures(), source, as_of="2026-05-01")
    original = pipeline._verified_bundle

    def swap_after_verification(root, retain=()):
        result = original(root, retain)
        (source / "observations.jsonl").write_text('{"rent":999999}\n')
        return result

    monkeypatch.setattr(pipeline, "_verified_bundle", swap_after_verification)
    pipeline.fit_dataset(source, tmp_path / "fit")
    report = json.loads((tmp_path / "fit" / "report.json").read_text())
    assert report["training"]["rows"] == 36


def test_normalized_rental_flags_survive_analytical_model_boundary(tmp_path):
    rows = list(captures())
    for row in rows:
        if row["observation"]["unit"] == "0":
            row["raw"]["attributes"]["furnished"] = True
    dataset = tmp_path / "dataset"
    build_dataset(rows, dataset, as_of="2026-05-01")
    fit_dataset(dataset, tmp_path / "fit")
    report = json.loads((tmp_path / "fit" / "report.json").read_text())
    assert report["selection"]["exclusions"]["excluded_furnished"] == 4
    assert report["training"]["rows"] == 33
    observed = [
        json.loads(line)
        for line in (dataset / "observations.jsonl").read_text().splitlines()
    ]
    assert any(r["furnished"] is None for r in observed)


def test_literal_unicode_separators_are_not_jsonl_boundaries(tmp_path):
    text = "north\u2028south\u2029east\u0085west"
    candidates, prefs = tmp_path / "candidates.jsonl", tmp_path / "preferences.json"
    candidates.write_text(
        json.dumps(
            {"rent": 2500, "bedrooms": 1, "description": text}, ensure_ascii=False
        )
        + "\n"
    )
    prefs.write_text('{"bedrooms":100}')
    assert (
        rank_candidates(candidates, prefs, tmp_path / "ranked")["input_candidates"] == 1
    )
    source = tmp_path / "source"
    build_dataset(captures(), source, as_of="2026-05-01")
    manifest = read_bundle(source)
    rows = [
        json.loads(line)
        for line in (source / "observations.jsonl").read_text().split("\n")
        if line.strip()
    ]
    for row in rows:
        row["description"] = text
    enriched = tmp_path / "enriched"
    publish_bundle(
        enriched,
        {
            "observations.jsonl": "".join(
                json.dumps(row, ensure_ascii=False) + "\n" for row in rows
            )
        },
        {"dataset_version": manifest["dataset_version"]},
    )
    fit_dataset(enriched, tmp_path / "fit")
