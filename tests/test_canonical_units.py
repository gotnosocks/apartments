import pytest

from apartments.canonical_units import memberships
from apartments.unit_canonical import canonical_unit_id


def capture(sid, lid, page="a/4c", **extra):
    return {
        "snapshot_id": sid,
        "listing_id": lid,
        "canonical_unit_url": "https://streeteasy.com/building/" + page
        if page
        else None,
        "listing_type": "rental",
        **extra,
    }


def test_url_only_ignores_labels_latest_history_and_attributes():
    rows = [
        capture(1, "1", unit_label="Studio", latest="99", bedrooms=0),
        capture(2, "2", unit_label=None, latest=None, bedrooms=3),
        capture(3, "1"),
        capture(4, "3", "b/4c"),
        capture(5, "4", "a/4d"),
    ]
    result = {r["listing_id"]: r for r in memberships(rows)}
    assert result["1"]["unit_id"] == result["2"]["unit_id"]
    assert len({r["unit_id"] for r in result.values()}) == 3
    assert result["1"]["capture_count"] == 2
    assert memberships(list(reversed(rows))) == list(result.values())
    assert canonical_unit_id(rows[0]["canonical_unit_url"]) == result["1"]["unit_id"]
    # Adding a later rental advertisement does not change the unit identity.
    assert memberships([capture(6, "999")])[0]["unit_id"] == result["1"]["unit_id"]


def test_conflicting_captures_never_bridge_distinct_units():
    result = memberships(
        [
            capture(1, "1"),
            capture(2, "1", "a/4d"),
            capture(3, "2"),
            capture(4, "3", "a/4d"),
            capture(5, "4", "b/1"),
            capture(6, "5", None),
        ]
    )
    assert {r["listing_id"] for r in result if r["unit_id"]} == {"4"}
    assert all(r["reason"] for r in result if not r["unit_id"])
    with pytest.raises(ValueError):
        canonical_unit_id("https://streeteasy.com/rental/1")
