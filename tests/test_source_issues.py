"""Unresolved source notes remain literal, time-bound and independent of fits.

The evidence loader is mocked only at its verified boundary: these captures
stand in for exact, already validated archive records, as in source-review tests.
"""

from copy import deepcopy
import json

import pytest

from apartments import source_issues as m
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle

REVIEWED_AT = "2026-09-20T12:00:00+00:00"
REVIEWER = "Manual source review"


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    dataset, evidence, output = (
        tmp_path / name for name in ("dataset", "evidence", "issues")
    )
    rows = [
        {
            "audit_id": "historical:a",
            "unit_id": "u-a",
            "source_listing_id": 123,
            "known_at": "2026-09-19T12:00:00+00:00",
            "period": "2020-06-01",
            "asking_rent": 4040.0,
            "bedrooms": 1,
            "bathrooms": 1.5,
            "reported_full_bathrooms": 1,
            "reported_half_bathrooms": 1,
            "analysis_price_basis": "historical_initial_own_advertisement_ask",
            "bathroom_count_evidence": {"flags": [], "explicit": True},
        },
        {
            "audit_id": "current:b",
            "unit_id": "u-b",
            "source_listing_id": "456",
            "known_at": "2026-09-19T12:30:00+00:00",
            "period": "2026-09-19",
            "asking_rent": 5500.0,
            "bedrooms": 2,
            "bathrooms": 2.0,
            "analysis_price_basis": "current_capture_gross_ask",
        },
    ]
    text = "南向☀️ café\nNet $4,040\u2028Gross $4,446\u2029Net $4,040"
    captures = {
        "historical:a": [
            {
                "capture_id": 1,
                "audit_id": "historical:a",
                "unit_id": "u-a",
                "source_listing_id": 123,
                "source_collected_at": "2026-09-18T11:00:00+00:00",
                "known_at": "2026-09-19T13:00:00+00:00",
                "raw_sha256": "raw-a",
                "description": text,
            },
            {
                "capture_id": "second:a",
                "audit_id": "historical:a",
                "unit_id": "u-a",
                "source_listing_id": 123,
                "source_collected_at": "2026-09-18T12:00:00+00:00",
                "known_at": "2026-09-19T14:00:00+00:00",
                "raw_sha256": "raw-a2",
                "description": None,
            },
        ],
        "current:b": [
            {
                "capture_id": "current:2",
                "audit_id": "current:b",
                "unit_id": "u-b",
                "source_listing_id": "456",
                "source_collected_at": "2026-09-18T12:00:00+00:00",
                "known_at": "2026-09-19T12:30:00+00:00",
                "raw_sha256": "raw-b",
                "description": "Three bathrooms including an en suite.",
            }
        ],
    }
    specs = [
        {
            "audit_id": "historical:a",
            "kind": "advertised_price_basis_conflict",
            "message": "Headline ask is net; a separate gross quote needs a dated price policy.",
            "temporal_scope": "Source assertions were captured later than the historical price date; no effective-date claim.",
            "observed_fields": {
                "asking_rent": 4040.0,
                "analysis_price_basis": rows[0]["analysis_price_basis"],
            },
            "literals": ["Net $4,040", "Gross $4,446"],
        },
        {
            "audit_id": "current:b",
            "kind": "bathroom_count_conflict",
            "message": "Structured and prose bathroom counts disagree.",
            "temporal_scope": "Current captured advertisement only.",
            "observed_fields": {"bathrooms": 2.0},
            "literals": ["Three bathrooms"],
        },
    ]
    publish_bundle(
        dataset,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"version": "verified-fixture-source"},
    )
    publish_bundle(
        evidence,
        {
            "evidence.jsonl": "".join(
                canonical(c) + "\n" for cs in captures.values() for c in cs
            )
        },
        {"version": "verified-fixture-evidence"},
    )
    calls = []

    def verified(data, archive):
        assert data == dataset and archive == evidence
        calls.append((data, archive))
        return deepcopy(captures)

    monkeypatch.setattr(m, "load_evidence", verified)
    return {
        "dataset": dataset,
        "evidence": evidence,
        "output": output,
        "rows": rows,
        "captures": captures,
        "specifications": specs,
        "calls": calls,
    }


def publish(inputs, **kwargs):
    return m.publish_source_issues(
        inputs["dataset"],
        inputs["evidence"],
        kwargs.pop("specifications", inputs["specifications"]),
        inputs["output"],
        reviewed_at=kwargs.pop("reviewed_at", REVIEWED_AT),
        reviewer=kwargs.pop("reviewer", REVIEWER),
        **kwargs,
    )


def read(inputs):
    return m.load_source_issues(
        inputs["dataset"], inputs["output"], evidence=inputs["evidence"]
    )


def saved_issues(inputs):
    return [
        json.loads(line)
        for line in (inputs["output"] / "issues.jsonl").read_text().split("\n")
        if line
    ]


def reseal(inputs, values, *, reidentify=True, metadata=None):
    """Defeat only outer checksums so tests exercise actual semantic verification."""
    values = deepcopy(values)
    if reidentify:
        for value in values:
            value["issue_id"] = m._hash(
                {k: v for k, v in value.items() if k != "issue_id"}
            )
    path = inputs["output"]
    (path / "issues.jsonl").write_text("".join(canonical(v) + "\n" for v in values))
    manifest = json.loads((path / "complete.json").read_text())
    manifest["files"]["issues.jsonl"] = digest(path / "issues.jsonl")
    if metadata:
        manifest.update(metadata)
    (path / "complete.json").write_text(canonical(manifest) + "\n")


def snapshot(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}


def test_publish_load_and_replay_keep_source_and_evidence_immutable(inputs):
    before = {key: snapshot(inputs[key]) for key in ("dataset", "evidence")}
    original = deepcopy({k: inputs[k] for k in ("rows", "captures", "specifications")})
    notes = publish(inputs)
    assert set(notes) == {"historical:a", "current:b"}
    assert all(note["interpretation_limited"] for note in notes.values())
    assert read(inputs) == notes
    output = snapshot(inputs["output"])
    assert publish(inputs) == notes and snapshot(inputs["output"]) == output
    assert before == {key: snapshot(inputs[key]) for key in ("dataset", "evidence")}
    assert original == {k: inputs[k] for k in ("rows", "captures", "specifications")}
    assert len(inputs["calls"]) == 3
    for issue in saved_issues(inputs):
        row = next(
            row for row in inputs["rows"] if row["audit_id"] == issue["audit_id"]
        )
        assert issue["source_row_sha256"] == m._hash(row)
        assert issue["issue_id"] == m._hash(
            {k: v for k, v in issue.items() if k != "issue_id"}
        )
        assert issue["disposition"] == "unresolved"
        assert issue["reviewed_at"] == REVIEWED_AT and issue["reviewer"] == REVIEWER
        assert not {"valid_from", "valid_to", "corrected_value"} & issue.keys()
    notes["historical:a"]["issues"][0]["captures"][0]["capture"]["description"] = (
        "mutated caller copy"
    )
    assert (
        read(inputs)["historical:a"]["issues"][0]["captures"][0]["capture"][
            "description"
        ]
        != "mutated caller copy"
    )
    assert snapshot(inputs["output"]) == output


def test_spans_use_unicode_codepoints_preserve_lf_separators_and_all_captures(inputs):
    spec = deepcopy(inputs["specifications"][0])
    spec["literals"] = ["café\nNet $4,040\u2028Gross $4,446", "Net $4,040"]
    publish(inputs, specifications=[spec])
    issue = saved_issues(inputs)[0]
    assert [c["capture"] for c in issue["captures"]] == inputs["captures"][
        "historical:a"
    ]
    assert issue["captures"][1]["spans"] == []  # Missing description still retained.
    text = inputs["captures"]["historical:a"][0]["description"]
    spans = issue["captures"][0]["spans"]
    assert len(spans) == 3  # One cross-line phrase plus both repeated net quotes.
    assert all(text[v["start"] : v["end"]] == v["literal"] for v in spans)
    net = next(v for v in spans if v["literal"] == "Net $4,040")
    assert net["start"] == text.index("Net $4,040")
    assert net["start"] != len(text[: net["start"]].encode("utf-8"))
    # Non-ASCII JSONL with real U+2028/U+2029 separators remains one record.
    root = inputs["output"]
    values = saved_issues(inputs)
    (root / "issues.jsonl").write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values)
    )
    manifest = json.loads((root / "complete.json").read_text())
    manifest["files"]["issues.jsonl"] = digest(root / "issues.jsonl")
    (root / "complete.json").write_text(canonical(manifest) + "\n")
    assert (
        read(inputs)["historical:a"]["issues"][0]["captures"][0]["capture"][
            "description"
        ]
        == text
    )


@pytest.mark.parametrize(
    "fault",
    [
        "source_hash",
        "unknown_row",
        "unit",
        "typed_advertisement",
        "observed_price",
        "observed_type",
        "observed_missing",
        "observed_empty",
        "capture_drop",
        "capture_order",
        "capture_text",
        "capture_typed_id",
        "span_literal",
        "span_byte_offset",
        "span_boolean_offset",
        "span_duplicate",
        "span_empty",
        "disposition",
        "interpretation",
        "message",
        "temporal_scope",
        "reviewer",
    ],
)
def test_rehashed_semantic_tampering_is_rejected(inputs, fault):
    publish(inputs)
    values = saved_issues(inputs)
    issue = next(v for v in values if v["audit_id"] == "historical:a")
    if fault == "source_hash":
        issue["source_row_sha256"] = "0" * 64
    if fault == "unknown_row":
        issue["audit_id"] = "other"
    if fault == "unit":
        issue["unit_id"] = "another-unit"
    if fault == "typed_advertisement":
        issue["source_listing_id"] = 123.0
    if fault == "observed_price":
        issue["observed_fields"]["asking_rent"] = 4446.0
    if fault == "observed_type":
        issue["observed_fields"] = {"bedrooms": True}
    if fault == "observed_missing":
        issue["observed_fields"] = {"not_a_source_field": 1}
    if fault == "observed_empty":
        issue["observed_fields"] = {}
    if fault == "capture_drop":
        issue["captures"].pop()
    if fault == "capture_order":
        issue["captures"].reverse()
    if fault == "capture_text":
        issue["captures"][0]["capture"]["description"] += " new text"
    if fault == "capture_typed_id":
        issue["captures"][0]["capture"]["capture_id"] = True
    span = issue["captures"][0]["spans"][0] if issue["captures"][0]["spans"] else None
    if fault == "span_literal":
        span["literal"] = "invented quote"
    if fault == "span_byte_offset":
        text = issue["captures"][0]["capture"]["description"]
        span["start"] = len(text[: span["start"]].encode("utf-8"))
    if fault == "span_boolean_offset":
        span["start"] = True
    if fault == "span_duplicate":
        issue["captures"][0]["spans"].append(deepcopy(span))
    if fault == "span_empty":
        for capture in issue["captures"]:
            capture["spans"] = []
    if fault == "disposition":
        issue["disposition"] = "corrected"
    if fault == "interpretation":
        issue["interpretation_limited"] = False
    if fault == "message":
        issue["message"] = " "
    if fault == "temporal_scope":
        issue["temporal_scope"] = ""
    if fault == "reviewer":
        issue["reviewer"] = None
    reseal(inputs, values)
    with pytest.raises(ValueError):
        read(inputs)


@pytest.mark.parametrize(
    "clock",
    [
        "2026-09-19T11:59:59+00:00",
        "2026-09-19T13:59:59+00:00",
        "2026-09-20T12:00:00",
        "not-a-date",
    ],
)
def test_review_clock_cannot_precede_source_or_any_capture_or_omit_timezone(
    inputs, clock
):
    with pytest.raises(ValueError):
        publish(inputs, reviewed_at=clock)
    assert not inputs["output"].exists()


def test_review_at_latest_capture_knowledge_is_allowed_with_timezone_conversion(inputs):
    notes = publish(inputs, reviewed_at="2026-09-19T10:00:00-04:00")
    assert read(inputs) == notes


def test_rehashed_review_clock_still_checked_on_load(inputs):
    publish(inputs)
    values = saved_issues(inputs)
    values[0]["reviewed_at"] = "2019-01-01T00:00:00+00:00"
    reseal(inputs, values)
    with pytest.raises(ValueError, match="predates"):
        read(inputs)


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "dataset_manifest_sha256",
        "evidence_manifest_sha256",
        "source_observations_sha256",
        "issues",
        "observations",
    ],
)
def test_manifest_binding_and_coverage_tampering_rejected(inputs, fault):
    publish(inputs)
    values = saved_issues(inputs)
    reseal(
        inputs,
        values,
        metadata={fault: 999 if fault in ("issues", "observations") else "wrong"},
    )
    with pytest.raises(ValueError):
        read(inputs)


def test_duplicate_issues_rejected_at_publication_and_after_full_rehash(inputs):
    with pytest.raises(ValueError, match="distinct source issues"):
        publish(inputs, specifications=[inputs["specifications"][0]] * 2)
    publish(inputs)
    values = saved_issues(inputs)
    values.append(deepcopy(values[0]))
    reseal(inputs, values, metadata={"issues": len(values)})
    with pytest.raises(ValueError, match="coverage"):
        read(inputs)


def test_multiple_distinct_issues_on_one_observation_preserve_both_claims(inputs):
    first = deepcopy(inputs["specifications"][0])
    second = deepcopy(first)
    second.update(
        kind="lease_assignment_terms",
        message="Lease assignment terms need their own review.",
    )
    result = publish(inputs, specifications=[first, second])
    assert (
        set(result) == {"historical:a"} and len(result["historical:a"]["issues"]) == 2
    )
    assert (
        first["message"] in result["historical:a"]["message"]
        and second["message"] in result["historical:a"]["message"]
    )
    manifest = json.loads((inputs["output"] / "complete.json").read_text())
    assert (manifest["issues"], manifest["observations"]) == (2, 1)
    assert read(inputs) == result


@pytest.mark.parametrize("specifications", [[], [{"empty": "specification"}]])
def test_empty_or_malformed_specifications_cannot_publish(inputs, specifications):
    with pytest.raises((ValueError, KeyError)):
        publish(inputs, specifications=specifications)
    assert not inputs["output"].exists()


@pytest.mark.parametrize(
    "phrases", [[], [""], ["Net $4,040", "Net $4,040"], ["Never in these captures"]]
)
def test_literal_evidence_is_nonempty_distinct_and_present(inputs, phrases):
    spec = deepcopy(inputs["specifications"][0])
    spec["literals"] = phrases
    with pytest.raises(ValueError):
        publish(inputs, specifications=[spec])
    assert not inputs["output"].exists()


def test_changed_issue_definition_requires_new_output_and_preserves_original(inputs):
    publish(inputs)
    original = snapshot(inputs["output"])
    changed = deepcopy(inputs["specifications"])
    changed[0]["message"] = "A different finding."
    with pytest.raises(ValueError, match="Run identity changed"):
        publish(inputs, specifications=changed)
    assert snapshot(inputs["output"]) == original


def test_duplicate_source_rows_rejected(inputs):
    path = inputs["dataset"]
    rows = inputs["rows"] + [deepcopy(inputs["rows"][0])]
    (path / "observations.jsonl").write_text("".join(canonical(r) + "\n" for r in rows))
    manifest = json.loads((path / "complete.json").read_text())
    manifest["files"]["observations.jsonl"] = digest(path / "observations.jsonl")
    (path / "complete.json").write_text(canonical(manifest) + "\n")
    with pytest.raises(ValueError, match="Duplicate source observation"):
        publish(inputs)
    assert not inputs["output"].exists()


def test_load_retains_exact_issue_identifier_binding(inputs):
    publish(inputs)
    values = saved_issues(inputs)
    values[0]["message"] = "Edited without regenerating issue identity"
    reseal(inputs, values, reidentify=False)
    with pytest.raises(ValueError, match="identifier"):
        read(inputs)


def test_merge_notes_preserves_both_channels_and_returns_independent_copies():
    reviews = {
        "shared": {
            "kind": "bedroom_conflict",
            "message": "Original bedroom review.",
            "interpretation_limited": False,
            "issues": [{"id": "old"}],
            "extra": "kept",
        },
        "review-only": {
            "kind": "view",
            "message": "View review.",
            "interpretation_limited": False,
        },
    }
    issues = {
        "shared": {
            "kind": "price_basis",
            "message": "Net/gross source issue.",
            "interpretation_limited": True,
            "issues": [{"id": "new", "nested": {"value": 1}}],
        },
        "issue-only": {
            "kind": "bathrooms",
            "message": "Bath issue.",
            "interpretation_limited": True,
            "issues": [{"id": "bath"}],
        },
    }
    before = deepcopy((reviews, issues))
    merged = m.merge_notes(reviews, issues)
    assert set(merged) == {"shared", "review-only", "issue-only"}
    assert merged["shared"]["kind"] == "bedroom_conflict; price_basis"
    assert (
        merged["shared"]["message"]
        == "Original bedroom review.\n\nNet/gross source issue."
    )
    assert (
        merged["shared"]["interpretation_limited"] is True
        and merged["shared"]["extra"] == "kept"
    )
    assert [v["id"] for v in merged["shared"]["issues"]] == ["old", "new"]
    assert (
        merged["review-only"] == reviews["review-only"]
        and merged["issue-only"] == issues["issue-only"]
    )
    merged["shared"]["issues"][1]["nested"]["value"] = 99
    merged["issue-only"]["issues"][0]["id"] = "changed"
    assert (reviews, issues) == before


def test_missing_attached_capture_evidence_cannot_publish(inputs):
    inputs["captures"]["historical:a"] = []
    with pytest.raises(ValueError, match="absent from attached evidence"):
        publish(inputs)
    assert not inputs["output"].exists()


def test_rehashed_nonmapping_capture_entry_rejected_as_validation_error(inputs):
    publish(inputs)
    values = saved_issues(inputs)
    values[0]["captures"][0] = None
    reseal(inputs, values)
    with pytest.raises(ValueError, match="every exact attached capture"):
        read(inputs)
