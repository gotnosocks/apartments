from copy import deepcopy
import json

import pytest

from apartments import residual_scope_projection as contract
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import project_residual_scope as project
from .test_residual_scope_projection import CLOCK, decision_for, fixture


def inputs(tmp_path, monkeypatch, *, exclude_current=False):
    rows, original_decisions, _ = fixture()
    for row in rows:
        row["building"] = "same-building"
    index = 0 if exclude_current else 2
    original = next(
        d for d in original_decisions if d["audit_id"] == rows[index]["audit_id"]
    )
    decision = decision_for(rows[index], original["source_captures"])
    parent = tmp_path / "parent"
    products = {
        "observations.jsonl": "".join(canonical(r) + "\n" for r in rows),
        "summary.json": "{}\n",
        "quarantined.jsonl": "[]\n",
        "elevator-corrections.jsonl": "[]\n",
        "floor-label-projection.jsonl": "[]\n",
        "expanded-floor-projection.jsonl": "[]\n",
        "ancestor-policy.txt": "Keep this literal unchanged.\n",
    }
    pm = publish_bundle(
        parent,
        products,
        {"version": contract.PARENT, "interpreted_at": "2026-09-19T23:00:00Z"},
    )
    decisions = tmp_path / "decisions"
    publish_bundle(
        decisions,
        {"decisions.jsonl": canonical(decision) + "\n", "policy.json": "{}\n"},
        {
            "version": contract.DECISION_VERSION,
            "source_manifest_sha256": digest(parent / "complete.json"),
            "source_observations_sha256": pm["files"]["observations.jsonl"],
            "reviewed_at": CLOCK,
        },
    )
    calls = []

    # The contract itself remains real. The full ancestor chain has separate
    # integration fixtures; this test isolates publication and preservation.
    def lineage(manifest, kept, **sidecars):
        assert contract.parent_rows(
            manifest, kept, sidecars["residual_scope_changes"]
        ) == (pm, rows)
        assert all(
            name in sidecars
            for name in (
                "quarantined",
                "elevator_changes",
                "floor_label_changes",
                "expanded_floor_changes",
            )
        )
        calls.append(deepcopy(manifest))

    monkeypatch.setattr(project, "source_lineage", lineage)
    return parent, decisions, rows, calls


def test_publication_preserves_parent_sidecars_values_and_replays(
    tmp_path, monkeypatch
):
    parent, decisions, rows, calls = inputs(tmp_path, monkeypatch)
    target = tmp_path / "result"
    result = project.run(parent, decisions, target)
    assert (
        result["rows"] == 3
        and result["quarantined_rows"] == 1
        and result["current_rows"] == 1
    )
    assert [
        json.loads(l) for l in (target / "observations.jsonl").read_text().splitlines()
    ] == [rows[0], rows[1], rows[3]]
    for name in (
        "quarantined.jsonl",
        "floor-label-projection.jsonl",
        "expanded-floor-projection.jsonl",
        "elevator-corrections.jsonl",
        "ancestor-policy.txt",
    ):
        assert (target / name).read_bytes() == (parent / name).read_bytes()
    excluded = json.loads((target / contract.SIDECAR).read_text())
    assert excluded["source_index"] == 2 and excluded["observation"] == rows[2]
    fingerprint = digest(target / "complete.json")
    assert project.run(parent, decisions, target) == result
    assert digest(target / "complete.json") == fingerprint and len(calls) == 2


def test_experiment_rejects_current_membership_change_before_publication(
    tmp_path, monkeypatch
):
    parent, decisions, _, calls = inputs(tmp_path, monkeypatch, exclude_current=True)
    with pytest.raises(ValueError, match="preserves every captured-current"):
        project.run(parent, decisions, tmp_path / "result")
    assert not (tmp_path / "result").exists() and not calls


def test_tampered_decision_cannot_publish(tmp_path, monkeypatch):
    parent, decisions, _, calls = inputs(tmp_path, monkeypatch)
    (decisions / "decisions.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="Artifact integrity"):
        project.run(parent, decisions, tmp_path / "result")
    assert not (tmp_path / "result").exists() and not calls
