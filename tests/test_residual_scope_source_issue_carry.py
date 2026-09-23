from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "scope_issue_carry",
    Path(__file__).parents[1]
    / "docs/analysis/scripts/carry_residual_scope_source_issues.py",
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "row_changed",
        "row_missing",
        "capture_changed",
        "capture_missing",
        "typed",
        "clock",
        "reviewer",
    ],
)
def test_retained_annotations_require_exact_row_capture_and_review_equality(fault):
    row = {"audit_id": "a", "bedrooms": 1}
    capture = {"capture_id": "c", "description": "Literal phrase"}
    issues = [
        {
            "audit_id": "a",
            "captures": [
                {
                    "capture": capture,
                    "spans": [{"start": 0, "end": 7, "literal": "Literal"}],
                }
            ],
            "reviewed_at": "2026-09-19T23:00:00Z",
            "reviewer": "original reviewer",
        }
    ]
    original, retained = {"a": row}, {"a": deepcopy(row)}
    captures = {"a": [deepcopy(capture)]}
    if fault == "row_changed":
        retained["a"]["bedrooms"] = 2
    elif fault == "row_missing":
        retained.clear()
    elif fault == "capture_changed":
        captures["a"][0]["description"] += "!"
    elif fault == "capture_missing":
        captures.clear()
    elif fault == "typed":
        retained["a"]["bedrooms"] = True
    elif fault in ("clock", "reviewer"):
        issues.append(deepcopy(issues[0]))
        issues[1]["reviewed_at" if fault == "clock" else "reviewer"] = "changed"
    if fault:
        with pytest.raises(ValueError):
            m.verify_retained(issues, original, retained, captures)
    else:
        before = deepcopy((issues, original, retained, captures))
        assert m.verify_retained(issues, original, retained, captures) == (
            "2026-09-19T23:00:00Z",
            "original reviewer",
        )
        assert (issues, original, retained, captures) == before


def test_publication_reload_and_replay_preserve_annotations_and_linkage(
    tmp_path, monkeypatch
):
    """Real source-issue and linkage publishers; only verified evidence is mocked."""
    import json
    from apartments.corrections import canonical
    from apartments.research_pipeline import publish_bundle, digest, _verified_bundle

    reference, candidate, evidence, previous, output, linkage = [
        tmp_path / name
        for name in (
            "reference",
            "candidate",
            "evidence",
            "previous",
            "output",
            "linkage",
        )
    ]
    rows = [
        {
            "audit_id": f"a{i}",
            "unit_id": f"u{i}",
            "source_listing_id": str(i),
            "known_at": "2026-09-19T00:00:00Z",
            "furnished": None,
        }
        for i in range(3)
    ]
    captures = {
        r["audit_id"]: [
            {
                "capture_id": r["audit_id"],
                "description": "Literal\u2028phrase\u2029with separators",
                "known_at": "2026-09-19T00:00:00Z",
            }
        ]
        for r in rows
    }
    specs = [
        {
            "audit_id": rows[i % 3]["audit_id"],
            "kind": f"issue{i}",
            "message": f"Finding {i}",
            "temporal_scope": "Original captured advertisement only",
            "observed_fields": {"furnished": None},
            "literals": ["Literal\u2028phrase"],
        }
        for i in range(4)
    ]
    parent = publish_bundle(
        reference,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"version": m.residual_scope_projection.PARENT},
    )
    publish_bundle(
        candidate,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {
            "version": m.residual_scope_projection.VERSION,
            "source_manifest": parent,
            "source_manifest_sha256": digest(reference / "complete.json"),
        },
    )
    publish_bundle(
        evidence,
        {"capture-fixture.json": canonical(captures)},
        {"version": "verified-test-evidence"},
    )
    calls = []

    def verified(path, archive):
        assert path in (reference, candidate) and archive == evidence
        calls.append(path)
        return deepcopy(captures)

    monkeypatch.setattr(m.source_issues, "load_evidence", verified)
    monkeypatch.setattr(m.bayesian_evidence, "load_evidence", verified)
    m.source_issues.publish_source_issues(
        reference,
        evidence,
        specs,
        previous,
        reviewed_at="2026-09-19T23:00:00Z",
        reviewer="Original reviewer",
    )
    m.run(reference, candidate, evidence, previous, output, linkage)
    manifest, files = _verified_bundle(linkage, retain={"linkage.json"})
    result = json.loads(files["linkage.json"])
    assert result["independent_public_load_passed"]
    assert result["original_review_timing_preserved"]
    assert result["inputs"]["previous_issues"] == digest(previous / "complete.json")
    assert result["output_manifest_sha256"] == digest(output / "complete.json")
    assert (output / "issues.jsonl").read_bytes() == (
        previous / "issues.jsonl"
    ).read_bytes()
    assert len(calls) == 5
    before = {
        str(path): digest(path / "complete.json")
        for path in (reference, candidate, evidence, previous, output, linkage)
    }
    m.run(reference, candidate, evidence, previous, output, linkage)
    assert before == {
        str(path): digest(path / "complete.json")
        for path in (reference, candidate, evidence, previous, output, linkage)
    }
