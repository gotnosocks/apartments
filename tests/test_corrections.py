"""Evidence-preserving correction overlays; all tests use small synthetic records."""

from copy import deepcopy
from datetime import UTC, datetime
import json

import pytest
from typer.testing import CliRunner

from apartments import corrections as c
from apartments.cli import app
from apartments.db import connect
from apartments.observation_dataset import export_observations, iter_observations
from apartments.temporal import retain_capture

RAW = {
    "source": "streeteasy",
    "source_listing_id": "b/4c",
    "building_slug": "b",
    "unit": "4C",
    "street_easy_rental_id": "123",
    "captured_at": "2026-09-07T12:00:00Z",
    "attributes": {"square_feet": 700, "bedrooms": 1, "bathrooms": 1},
    "home_features": ["DISHWASHER"],
    "archive_listing": {"createdAt": "2015-01-01"},
    "price_history": [{"date": "2015-01-01", "base_rent": 2000, "event": "Listed"}],
}
CTX = {
    "source": "streeteasy",
    "source_listing_id": "b/4c",
    "building_slug": "b",
    "unit": "4C",
    "episode_id": "123",
    "version_id": "v",
    "capture_id": "cap",
}


def edit(value=750, *, target=None, validity=None, patch=None, **extra):
    return {
        "target": target or {"source": "streeteasy", "episode_id": "123"},
        "validity": validity or {"all_time": True},
        "patch": patch
        or [{"op": "replace", "path": "/attributes/square_feet", "value": value}],
        **extra,
    }


@pytest.fixture
def ledger(tmp_path):
    p = tmp_path / "corrections.jsonl"
    p.touch()
    return p


def add(ledger, spec=None):
    return c.append(
        ledger,
        author="Ben",
        reason="Measured floor plan",
        evidence=["floorplan.pdf"],
        edit=spec or edit(),
    )


def test_independent_recorded_and_effective_time_with_revision_and_withdrawal(
    ledger, monkeypatch
):
    monkeypatch.setattr(c, "now", lambda: datetime(2026, 9, 16, tzinfo=UTC))
    spec = edit(validity={"from": "2015-01-01", "until": "2018-01-01"})
    first = add(ledger, spec)
    assert (
        c.Overlay(ledger, as_of="2026-09-15").apply(
            RAW, CTX, effective_at="2016-01-01"
        )[0]
        == RAW
    )
    overlay = c.Overlay(ledger)
    assert (
        overlay.apply(RAW, CTX, effective_at="2015-01-01")[0]["attributes"][
            "square_feet"
        ]
        == 750
    )
    assert overlay.apply(RAW, CTX, effective_at="2018-01-01")[0] == RAW
    assert overlay.apply(RAW, CTX, effective_at="2014-12-31")[0] == RAW
    with pytest.raises(c.CorrectionError, match="effective_at"):
        overlay.apply(RAW, CTX)
    monkeypatch.setattr(c, "now", lambda: datetime(2026, 9, 17, tzinfo=UTC))
    second = add(
        ledger, {**spec, "supersedes": first["id"], "patch": edit(760)["patch"]}
    )
    assert (
        c.Overlay(ledger, as_of="2026-09-16").apply(
            RAW, CTX, effective_at="2016-01-01"
        )[0]["attributes"]["square_feet"]
        == 750
    )
    assert (
        c.Overlay(ledger).apply(RAW, CTX, effective_at="2016-01-01")[0]["attributes"][
            "square_feet"
        ]
        == 760
    )
    monkeypatch.setattr(c, "now", lambda: datetime(2026, 9, 18, tzinfo=UTC))
    c.append(ledger, author="Ben", reason="Wrong plan", retracts=second["id"])
    assert c.Overlay(ledger).apply(RAW, CTX, effective_at="2016-01-01")[0] == RAW
    assert (
        len(c.Overlay(ledger).records) == 3
    )  # Original edit never resurrected/deleted.


@pytest.mark.parametrize(
    "target",
    [
        {"source": "streeteasy", "version_id": "v"},
        {"source": "streeteasy", "capture_id": "cap"},
        {"source": "streeteasy", "episode_id": "123"},
        {"source": "streeteasy", "source_listing_id": "b/4c"},
        {"source": "streeteasy", "building_slug": "b", "unit": "4C"},
    ],
)
def test_scope_uses_original_identity(target, ledger):
    add(ledger, edit(target=target))
    overlay = c.Overlay(ledger)
    assert overlay.apply(RAW, CTX)[0]["attributes"]["square_feet"] == 750
    assert overlay.apply(RAW, {**CTX, "source": "other"})[0] == RAW
    key = next(k for k in target if k != "source")
    assert overlay.apply(RAW, {**CTX, key: "other"})[0] == RAW


def test_arbitrary_nested_attributes_null_arrays_and_provenance(ledger):
    raw = deepcopy(RAW)
    patch = [
        {"op": "test", "path": "/attributes/square_feet", "value": 700},
        {"op": "replace", "path": "/attributes/square_feet", "value": None},
        {"op": "add", "path": "/attributes/physical_floor", "value": 12},
        {"op": "add", "path": "/attributes/advertised_floor", "value": 14},
        {"op": "add", "path": "/attributes/view", "value": {"courtyard": True}},
        {"op": "add", "path": "/attributes/a~1b~0c", "value": "escaped"},
        {"op": "add", "path": "/home_features/-", "value": "WASHER_DRYER"},
        {"op": "remove", "path": "/attributes/bedrooms"},
    ]
    rec = add(ledger, edit(patch=patch))
    result, evidence = c.Overlay(ledger).apply(raw, CTX)
    assert raw == RAW
    assert result["attributes"]["square_feet"] is None
    assert "bedrooms" not in result["attributes"]
    assert result["attributes"]["a/b~c"] == "escaped"
    assert result["attributes"]["physical_floor"] == 12
    assert result["attributes"]["advertised_floor"] == 14
    assert result["attributes"]["view"]["courtyard"] is True
    assert result["home_features"] == ["DISHWASHER", "WASHER_DRYER"]
    assert evidence[0]["id"] == rec["id"]
    assert evidence[0]["reason"] == "Measured floor plan"
    assert c.Overlay(ledger, enabled=False).apply(raw, CTX) == (RAW, [])


@pytest.mark.parametrize(
    "second",
    [
        [{"op": "replace", "path": "/attributes/square_feet", "value": 800}],
        [{"op": "replace", "path": "/attributes", "value": {}}],
        [
            {"op": "test", "path": "/attributes/square_feet", "value": 750},
            {"op": "add", "path": "/attributes/view", "value": "street"},
        ],
    ],
)
def test_overlapping_edits_fail_instead_of_implicit_priority(ledger, second):
    add(ledger)
    add(ledger, edit(target={"source": "streeteasy", "version_id": "v"}, patch=second))
    with pytest.raises(c.CorrectionError, match="Conflicting"):
        c.Overlay(ledger).apply(RAW, CTX)


def test_array_index_shifts_conflict(ledger):
    add(ledger, edit(patch=[{"op": "remove", "path": "/home_features/0"}]))
    add(
        ledger,
        edit(patch=[{"op": "add", "path": "/home_features/0", "value": "OTHER"}]),
    )
    with pytest.raises(c.CorrectionError, match="Conflicting"):
        c.Overlay(ledger).apply(RAW, CTX)


def test_disjoint_edits_and_failed_test_are_atomic(ledger):
    add(ledger)
    add(
        ledger,
        edit(patch=[{"op": "replace", "path": "/attributes/bedrooms", "value": 2}]),
    )
    assert c.Overlay(ledger).apply(RAW, CTX)[0]["attributes"] == {
        "square_feet": 750,
        "bedrooms": 2,
        "bathrooms": 1,
    }
    add(
        ledger,
        edit(
            patch=[
                {"op": "test", "path": "/attributes/bathrooms", "value": 2},
                {"op": "replace", "path": "/attributes/bathrooms", "value": 3},
            ]
        ),
    )
    with pytest.raises(c.CorrectionError, match="cannot apply"):
        c.Overlay(ledger).apply(RAW, CTX)
    assert RAW["attributes"]["bathrooms"] == 1


def test_changed_scope_requires_explicit_retraction(ledger):
    first = add(ledger)
    with pytest.raises(c.CorrectionError, match="preserve target"):
        add(
            ledger,
            edit(
                supersedes=first["id"],
                target={"source": "streeteasy", "building_slug": "b"},
            ),
        )
    assert len(c.Overlay(ledger).records) == 1


@pytest.mark.parametrize(
    "patch",
    [
        [{"op": "replace", "path": "/captured_at", "value": "1900-01-01"}],
        [{"op": "replace", "path": "", "value": {}}],
        [{"op": "add", "path": "/attributes/square_feet", "value": float("nan")}],
        [{"op": "replace", "path": "/attributes/x"}],
    ],
)
def test_invalid_or_metadata_edits_rejected(ledger, patch):
    with pytest.raises(ValueError):
        add(ledger, edit(patch=patch))
    assert ledger.read_text() == ""


def test_integrity_and_incomplete_tail_fail_closed(ledger):
    add(ledger)
    text = ledger.read_text()
    ledger.write_text(text.replace("750", "999"))
    with pytest.raises(c.CorrectionError, match="hash"):
        c.Overlay(ledger)
    ledger.write_text(text.rstrip("\n"))
    with pytest.raises(c.CorrectionError, match="Incomplete"):
        add(ledger)


def test_export_raw_preserved_selectors_and_clocks_independent(tmp_path, ledger):
    path = tmp_path / "db.duckdb"
    db = connect(path)
    version = retain_capture(db, "cap", RAW)
    before = db.execute(
        "SELECT version_id,structured_json,attributes_json,CAST(collected_at AS VARCHAR),CAST(recorded_at AS VARCHAR) FROM attribute_versions"
    ).fetchall()
    add(ledger, edit(target={"source": "streeteasy", "version_id": version}))
    overlay = c.Overlay(ledger)
    row = next(iter_observations(db, overlay))
    assert row["raw"] == RAW
    assert row["corrected"]["attributes"]["square_feet"] == 750
    assert row["observation"]["collected_at"].startswith("2026-09-07")
    assert list(iter_observations(db, overlay, collected_as_of="2016-01-01")) == []
    assert list(iter_observations(db, overlay, interpreted_as_of="2016-01-01")) == []
    assert (
        db.execute(
            "SELECT version_id,structured_json,attributes_json,CAST(collected_at AS VARCHAR),CAST(recorded_at AS VARCHAR) FROM attribute_versions"
        ).fetchall()
        == before
    )
    db.close()
    manifest = export_observations(path, tmp_path / "export", overlay)
    assert manifest["corrected_observations"] == 1
    assert manifest["overlay"]["ledger_prefix_sha256"] == overlay.records[-1]["hash"]
    frozen = c.Overlay(tmp_path / "export/corrections.jsonl", as_of=overlay.as_of)
    assert (
        frozen.apply(RAW, {**CTX, "version_id": version})[0]["attributes"][
            "square_feet"
        ]
        == 750
    )
    raw_manifest = export_observations(
        path, tmp_path / "raw", c.Overlay(ledger, enabled=False)
    )
    assert (
        raw_manifest["source_observations_sha256"]
        == manifest["source_observations_sha256"]
    )
    assert raw_manifest["observations_sha256"] != manifest["observations_sha256"]
    with pytest.raises(FileExistsError):
        export_observations(path, tmp_path / "export", overlay)


def test_failed_export_has_no_ready_manifest(tmp_path, ledger):
    path = tmp_path / "db.duckdb"
    db = connect(path)
    retain_capture(db, "cap", RAW)
    db.close()
    add(ledger, edit(validity={"from": "2015-01-01"}))
    with pytest.raises(c.CorrectionError, match="effective_at"):
        export_observations(path, tmp_path / "export", c.Overlay(ledger))
    assert not (tmp_path / "export/metadata.json").exists()


def test_cli_add_list_retract(tmp_path, ledger):
    runner = CliRunner()
    spec = tmp_path / "edit.json"
    spec.write_text(json.dumps(edit()))
    result = runner.invoke(
        app,
        [
            "corrections",
            "add",
            str(spec),
            "--ledger",
            str(ledger),
            "--author",
            "Ben",
            "--reason",
            "Test",
        ],
    )
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    result = runner.invoke(app, ["corrections", "list", "--ledger", str(ledger)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["manifest"]["active_ids"] == [record["id"]]
    result = runner.invoke(
        app,
        [
            "corrections",
            "retract",
            record["id"],
            "--ledger",
            str(ledger),
            "--author",
            "Ben",
            "--reason",
            "Test withdrawal",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not c.Overlay(ledger).active


def test_known_as_of_rejects_future_corrections(tmp_path, ledger):
    db = connect(tmp_path / "db.duckdb")
    retain_capture(db, "cap", RAW)
    add(ledger)
    with pytest.raises(c.CorrectionError, match="later knowledge"):
        list(iter_observations(db, c.Overlay(ledger), known_as_of="2026-01-01"))
    assert (
        list(
            iter_observations(
                db, c.Overlay(ledger, as_of="2026-01-01"), known_as_of="2026-01-01"
            )
        )
        == []
    )
    db.close()


def test_raw_nested_source_attributes_editable_but_episode_id_protected(ledger):
    add(
        ledger,
        edit(
            patch=[
                {
                    "op": "add",
                    "path": "/archive_listing/custom_attribute",
                    "value": {"courtyard": True},
                }
            ]
        ),
    )
    assert c.Overlay(ledger).apply(RAW, CTX)[0]["archive_listing"]["custom_attribute"][
        "courtyard"
    ]
    with pytest.raises(c.CorrectionError):
        add(
            ledger,
            edit(
                patch=[
                    {"op": "replace", "path": "/archive_listing/id", "value": "other"}
                ]
            ),
        )


def test_explicit_validity_required(ledger):
    spec = edit()
    del spec["validity"]
    with pytest.raises(c.CorrectionError):
        add(ledger, spec)
    with pytest.raises(c.CorrectionError):
        add(ledger, edit(validity={"all_time": 1}))
