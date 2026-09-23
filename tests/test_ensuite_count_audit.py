import pytest
from models.ensuite_count_audit import screen, select, STRATA


def test_screen_retains_exact_offsets_and_does_not_assign_counts():
    text = (
        "Two closets and an en-suite bath.\u2028Both bedrooms have their own bathrooms."
    )
    findings = screen(text)
    assert {"numeric_phrase", "distributed_access"} <= {f["family"] for f in findings}
    for f in findings:
        assert text[f["start"] : f["end"]] == f["literal"]
        assert text[f["context_start"] : f["context_end"]] == f["context"]
        assert "count" not in f and "ensuite_count" not in f


def test_negative_and_nonbath_objects_remain_review_candidates():
    text = "No shortage of closets and an en-suite bath. En-suite laundry. Could convert bedroom with en-suite bath."
    findings = screen(text)
    assert {"negated_ensuite", "ambiguous_subject", "planned_ensuite"} <= {
        f["family"] for f in findings
    }
    assert all("count_status" not in f for f in findings)


def test_distributed_bathroom_finishes_are_not_automatically_access_counts():
    findings = screen("Both bathrooms have marble floors.")
    assert findings[0]["family"] == "distributed_access"
    assert list(findings[0]) == [
        "family",
        "start",
        "end",
        "literal",
        "context_start",
        "context_end",
        "context",
    ]


def test_selection_excludes_prior_units_and_is_deterministic():
    candidates = []
    for index, (_, families) in enumerate(STRATA):
        for n in range(3):
            candidates.append(
                {
                    "audit_id": f"a{index}{n}",
                    "capture_id": n,
                    "unit_id": f"u{index}{n}",
                    "count_candidates": [{"family": families[0]}],
                }
            )
    excluded = {"u00"}
    chosen = select(candidates, excluded, per_stratum=2)
    assert len(chosen) == len({c["unit_id"] for c in chosen}) == 10
    assert not ({c["unit_id"] for c in chosen} & excluded)
    assert chosen == select(list(reversed(candidates)), excluded, per_stratum=2)
    with pytest.raises(ValueError, match="Insufficient"):
        select(candidates, excluded, per_stratum=4)


def test_unknown_and_absent_text_produce_no_physical_negative():
    assert screen(None) == []
    assert screen("Sunny apartment.") == []


def test_source_bound_bundle_replays_with_json_normalized_selection_metadata(tmp_path):
    import hashlib
    from apartments.corrections import canonical
    from apartments.research_pipeline import publish_bundle
    from models.ensuite_count_audit import run

    examples = [
        "En-suite laundry.",
        "Two en-suite bathrooms.",
        "Each bedroom has a bathroom.",
        "Primary bedroom has an en-suite bathroom.",
        "A hall bathroom.",
    ]
    captures = []
    counts = []
    for index, text in enumerate(examples):
        for n in range(6):
            identity = f"{index}:{n}"
            c = {
                "audit_id": identity,
                "capture_id": identity,
                "unit_id": identity,
                "source_listing_id": identity,
                "canonical_unit_url": identity,
                "description": text,
                "description_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "raw_listing_sha256": "raw:" + identity,
                "body_sha256": "body:" + identity,
            }
            captures.append(c)
            counts.append(
                {
                    "audit_id": identity,
                    "bedrooms": 2,
                    "analysis_bathrooms": 2,
                    "reported_full_bathrooms": 2,
                    "reported_half_bathrooms": 0,
                    "status": "consistent_explicit_counts",
                }
            )
    descriptions = tmp_path / "descriptions"
    dm = publish_bundle(
        descriptions,
        {"evidence.jsonl": "".join(canonical(c) + "\n" for c in captures)},
        {"version": "fixture"},
    )
    audit = tmp_path / "audit"
    bm = publish_bundle(
        audit,
        {
            "captures.jsonl": "".join(
                canonical({**c, "bathroom_fields": {}}) + "\n" for c in captures
            ),
            "reported-counts.jsonl": "".join(canonical(c) + "\n" for c in counts),
        },
        {"description_manifest": dm},
    )
    prior = tmp_path / "prior"
    publish_bundle(
        prior,
        {"review.jsonl": canonical({"unit_id": "excluded"}) + "\n"},
        {"audit_manifest": bm},
    )
    output = tmp_path / "output"
    manifest = run(descriptions, audit, prior, output)
    assert manifest["summary"]["review_cases"] == 30
    assert run(descriptions, audit, prior, output) == manifest
