from copy import deepcopy
import hashlib
import json

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import research_scope_overlay as m


def fixture(ad="123", capture_id=1):
    row = {
        "audit_id": "audit:" + ad,
        "source_listing_id": ad,
        "unit_id": "unit:" + ad,
        "canonical_unit_url": "https://streeteasy.com/building/example/" + ad,
        "known_at": "2026-09-18T12:00:00+00:00",
        "asking_rent": 3500.0,
        "bedrooms": 2.0,
        "bathrooms": 1.0,
        "reported_full_bathrooms": 1,
        "reported_half_bathrooms": 0,
        "bathroom_count_evidence": {
            "capture_ids": [capture_id],
            "flags": ["existing_flag"],
        },
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
    }
    text = "The apartment has 2 FULL BATHS."
    capture = {k: row[k] for k in m.IDENTITY}
    capture.update(
        capture_id=capture_id,
        body_sha256="a" * 64,
        raw_listing_sha256="b" * 64,
        description=text,
        description_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_collected_at="2026-09-17T12:00:00+00:00",
        known_at=row["known_at"],
    )
    return row, capture


def decision(row, capture, action="mask_bathroom_composition"):
    e = deepcopy(capture)
    literal = "2 FULL BATHS"
    start = e["description"].index(literal)
    e["spans"] = [{"start": start, "end": start + len(literal), "literal": literal}]
    d = {k: row[k] for k in m.IDENTITY}
    d.update(
        action=action,
        reason="Reviewed source contradiction",
        interpreted_at="2026-09-18T13:00:00+00:00",
        source_projection_row_sha256=m.sha(row),
        evidence=[e],
    )
    d["decision_id"] = m.sha(d)
    return d


def reseal(d):
    d["decision_id"] = m.sha({k: v for k, v in d.items() if k != "decision_id"})


def test_mask_preserves_reported_values_price_other_fields_and_original_input():
    row, capture = fixture()
    before = deepcopy(row)
    d = decision(row, capture)
    result = m.apply_decision(row, d, {(row["audit_id"], "1"): capture})
    assert row == before
    assert all(result[k] == v for k, v in row.items() if k != "bathroom_count_evidence")
    assert result["bathroom_count_evidence"]["flags"] == ["existing_flag", m.MASK_FLAG]
    assert (
        result["research_review_history"][0]["before_bathroom_count_evidence"]
        == row["bathroom_count_evidence"]
    )


@pytest.mark.parametrize(
    "field,value", [("asking_rent", 999.0), ("unit_id", "different")]
)
def test_changed_target_or_identity_refused(field, value):
    row, capture = fixture()
    d = decision(row, capture)
    row[field] = value
    with pytest.raises(ValueError, match="binding mismatch"):
        m.apply_decision(row, d, {(row["audit_id"], "1"): capture})


@pytest.mark.parametrize(
    "mutation",
    [
        "capture_hash",
        "text",
        "clock",
        "span",
        "missing_capture",
        "duplicate_capture",
        "unknown_action",
    ],
)
def test_resealed_invalid_evidence_is_not_accepted(mutation):
    row, capture = fixture()
    d = decision(row, capture)
    if mutation == "capture_hash":
        d["evidence"][0]["body_sha256"] = "c" * 64
    if mutation == "text":
        d["evidence"][0]["description"] = "altered"
    if mutation == "clock":
        d["interpreted_at"] = "2020-01-01T00:00:00+00:00"
    if mutation == "span":
        d["evidence"][0]["spans"][0]["start"] += 1
    if mutation == "missing_capture":
        d["evidence"] = []
    if mutation == "duplicate_capture":
        d["evidence"] *= 2
    if mutation == "unknown_action":
        d["action"] = "repair_price"
    reseal(d)
    with pytest.raises(ValueError):
        m.apply_decision(row, d, {(row["audit_id"], "1"): capture})


def bundles(tmp_path, quarantine_current=False):
    a, ca = fixture("123", 1)
    b, cb = fixture("456", 2)
    c, cc = fixture("789", 3)
    c["analysis_price_basis"] = "current_capture_gross_ask"
    if quarantine_current:
        b["analysis_price_basis"] = "current_capture_gross_ask"
    src = tmp_path / "source"
    audit = tmp_path / "audit"
    ds = tmp_path / "decisions"
    publish_bundle(
        src,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in [a, b, c])},
        {"version": m.SOURCE_VERSION},
    )
    publish_bundle(
        audit,
        {"captures.jsonl": "".join(canonical(r) + "\n" for r in [ca, cb, cc])},
        {"version": "audit"},
    )
    dd = [decision(a, ca), decision(b, cb, "quarantine_nonresidential")]
    publish_bundle(
        ds,
        {"decisions.jsonl": "".join(canonical(d) + "\n" for d in dd)},
        {
            "version": m.DECISION_VERSION,
            "source_manifest_sha256": digest(src / "complete.json"),
            "source_observations_sha256": digest(src / "observations.jsonl"),
            "audit_manifest_sha256": digest(audit / "complete.json"),
        },
    )
    return src, ds, audit


def test_projection_replay_retains_quarantine_and_current_membership(tmp_path):
    src, ds, audit = bundles(tmp_path)
    out = tmp_path / "out"
    first = m.run(src, ds, audit, out)
    second = m.run(src, ds, audit, out)
    assert first == second
    assert first["summary"]["rows"] == 2 and first["summary"]["current_rows"] == 1
    assert (
        first["summary"]["masked_rows"] == 1
        and first["summary"]["quarantined_rows"] == 1
    )
    quarantined = json.loads((out / "quarantined.jsonl").read_text())
    assert quarantined["observation"]["asking_rent"] == 3500.0
    assert quarantined["observation"]["bathrooms"] == 1.0
    kept = m.rows((out / "observations.jsonl").read_bytes())
    assert [r["source_listing_id"] for r in kept] == ["123", "789"]


def test_current_capture_quarantine_requires_separate_policy(tmp_path):
    src, ds, audit = bundles(tmp_path, quarantine_current=True)
    with pytest.raises(ValueError, match="preserve the refreshed current cohort"):
        m.run(src, ds, audit, tmp_path / "out")
    assert not (tmp_path / "out" / "complete.json").exists()
