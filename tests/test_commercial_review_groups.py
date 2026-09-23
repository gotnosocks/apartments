from copy import deepcopy
import hashlib

import pytest

from apartments.corrections import canonical
from docs.analysis.scripts.group_commercial_review import group_cases
from docs.analysis.scripts.screen_commercial_offer_language import matches


def case(audit, text="No solely commercial uses; residential live/work."):
    row = {
        "audit_id": audit,
        "unit_id": "unit-" + audit,
        "source_listing_id": audit,
        "building": "building",
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
    }
    sha = hashlib.sha256(text.encode()).hexdigest()
    capture = {
        **row,
        "capture_id": 1,
        "description": text,
        "description_sha256": sha,
        "raw_listing_sha256": "a" * 64,
        "source_collected_at": "2026-09-19T00:00:00Z",
    }
    return {
        "source_row": row,
        "source_row_sha256": hashlib.sha256(canonical(row).encode()).hexdigest(),
        "captures": [capture],
        "witnesses": [
            {"capture_id": 1, "description_sha256": sha, "matches": matches(text)}
        ],
    }


def test_identical_text_keeps_distinct_own_ad_associations_and_negation():
    groups = group_cases([case("a"), case("b")])
    assert len(groups) == 1
    assert {a["audit_id"] for a in groups[0]["associations"]} == {"a", "b"}
    assert groups[0]["description"].startswith("No solely")
    assert "scope" not in groups[0]


def test_nonmatching_capture_of_matched_row_is_not_lost():
    c = case("a")
    extra = case("a", "A sunny residence")["captures"][0]
    extra["capture_id"] = 2
    c["captures"].append(extra)
    groups = group_cases([c])
    assert len(groups) == 2
    assert sorted(len(g["associations"][0]["matches"]) for g in groups) == [0, 1]


@pytest.mark.parametrize(
    "mutation", ["duplicate", "hash", "span", "identity", "missing_capture"]
)
def test_rejects_corrupted_associations(mutation):
    c = case("a")
    if mutation == "duplicate":
        c["captures"].append(deepcopy(c["captures"][0]))
    if mutation == "hash":
        c["captures"][0]["description"] += "changed"
    if mutation == "span":
        c["witnesses"][0]["matches"][0]["start"] = 0
    if mutation == "identity":
        c["captures"][0]["unit_id"] = "other"
    if mutation == "missing_capture":
        c["captures"] = []
    with pytest.raises(ValueError):
        group_cases([c])
