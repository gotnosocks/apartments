import json

import duckdb
import pytest

from apartments.review_ledger import ReviewConflict
from apartments.review_service import ReviewService


@pytest.fixture
def service(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "complete.json").write_text("{}")
    db = duckdb.connect()
    for table in ("listing_observations", "event_mentions"):
        (root / table).mkdir()
    db.execute(
        """CREATE TABLE listing_observations AS SELECT 1::BIGINT snapshot_id,'https://streeteasy.com/rental/1' url,'1' listing_id,'rental' listing_type,'a' building_slug,'4C' unit_label,1.0::DOUBLE bedrooms,1.0::DOUBLE bathrooms,NULL::DOUBLE square_feet,3.0::DOUBLE room_count,1000.0::DOUBLE collected_at,'[]' features_json,'{}' amenities_json,'{\"price\":4000}' pricing_json,'{\"id\":1,\"nested\":{}}' raw_listing_json"""
    )
    db.execute(
        "INSERT INTO listing_observations SELECT * REPLACE(2 AS snapshot_id,'2' AS listing_id,NULL AS unit_label) FROM listing_observations WHERE snapshot_id=1"
    )
    db.execute(
        "INSERT INTO listing_observations SELECT * REPLACE(3 AS snapshot_id,'sale' AS listing_type) FROM listing_observations WHERE snapshot_id=1"
    )
    db.execute(
        "INSERT INTO listing_observations SELECT * REPLACE(4 AS snapshot_id,url||'/media_gallery' AS url) FROM listing_observations WHERE snapshot_id=1"
    )
    db.execute(
        """CREATE TABLE event_mentions AS SELECT 1::BIGINT snapshot_id,0 episode_index,0 event_index,'1' event_listing_id,'rental' event_category,'2020-01-01' event_date,0.0::DOUBLE price,'Listed' status,'{}' event_json"""
    )
    history = [{"listingId": "1", "rentalEventsOfInterest": [
        {"date": "2020-01-01", "price": 0, "status": "Listed"},
        {"date": "2020-01-01", "price": 13750, "status": "ACTIVE"},
    ]}]
    db.execute("UPDATE listing_observations SET raw_listing_json=?", [
        json.dumps({"id": 1, "nested": {}, "propertyHistory": history})
    ])
    db.execute("UPDATE event_mentions SET event_json=?", [json.dumps(history[0]["rentalEventsOfInterest"][0])])
    db.execute("INSERT INTO event_mentions SELECT * REPLACE(1 AS event_index,13750 AS price,'ACTIVE' AS status,? AS event_json) FROM event_mentions WHERE event_index=0", [json.dumps(history[0]["rentalEventsOfInterest"][1])])
    db.execute("INSERT INTO event_mentions SELECT * REPLACE(2 AS snapshot_id) FROM event_mentions")
    for table in ("listing_observations", "event_mentions"):
        db.execute(
            f"COPY {table} TO '{root / table / 'part.parquet'}' (FORMAT PARQUET)"
        )
    db.close()
    svc = ReviewService(root, tmp_path / "state")
    yield svc
    svc.close()


def apply(svc, preview):
    return svc.apply_preview(
        {"token": preview["token"], "author": "test", "reason": "verified"}
    )


def test_scope_progress_and_parameterized_selection(service):
    s = service
    assert s.overview()["rental_observations"] == 2
    assert s.observations({"search": "' OR 1=1 --"})["total"] == 0
    assert s.observations({"issue": "unit_missing"})["total"] == 1
    assert s.observations({"review_status": "unreviewed"})["total"] == 2
    s.review(
        {"snapshot_id": 1, "stage": "identity", "decision": "confirmed", "author": "a"}
    )
    assert s.overview()["stages"][0]["progress"] == {
        "confirmed": 1,
        "needs_attention": 0,
        "unreviewed": 1,
    }
    assert (
        s.observations({"review_status": "unreviewed"})["rows"][0]["snapshot_id"] == 2
    )
    assert s.observations({"review_status": "confirmed"})["total"] == 1
    assert s.observation({"snapshot_id": 2})["reviews"] == []
    with pytest.raises(ValueError):
        s.observation({"snapshot_id": 3})


def test_preview_apply_retry_retract_and_source_immutable(service):
    s = service
    before = s.observation({"snapshot_id": 1})["raw"]
    p = s.preview({"issue": "all", "field": "square_feet", "value": 800}, True)
    assert p["count"] == 2
    assert s.ledger.events() == []
    e = apply(s, p)
    assert apply(s, p)["id"] == e["id"]
    assert len(s.ledger.events()) == 1
    assert s.observation({"snapshot_id": 1})["corrected"]["square_feet"] == 800
    assert s.observation({"snapshot_id": 1})["raw"] == before
    s.retract({"id": e["id"], "author": "a", "reason": "undo"})
    assert s.observation({"snapshot_id": 1})["corrected"] == before


def test_stale_preview_and_dependent_retraction(service):
    s = service
    p = s.preview(
        {
            "snapshot_id": 1,
            "patch": [{"op": "add", "path": "/new_attribute", "value": {}}],
        }
    )
    first = apply(s, p)
    p2 = s.preview(
        {
            "snapshot_id": 1,
            "patch": [
                {"op": "add", "path": "/new_attribute/value", "value": "courtyard"}
            ],
        }
    )
    apply(s, p2)
    with pytest.raises(ValueError, match="dependent"):
        s.retract({"id": first["id"], "author": "a", "reason": "undo"})
    p3 = s.preview(
        {
            "snapshot_id": 1,
            "patch": [{"op": "replace", "path": "/bedrooms", "value": 2}],
        }
    )
    s.review(
        {"snapshot_id": 2, "stage": "identity", "decision": "confirmed", "author": "a"}
    )
    with pytest.raises(ReviewConflict):
        apply(s, p3)


def test_invalid_patch_and_parser_issue_do_not_edit_data(service):
    s = service
    with pytest.raises(ValueError):
        s.preview(
            {
                "snapshot_id": 1,
                "patch": [{"op": "replace", "path": "/bedrooms", "value": "two"}],
            }
        )
    with pytest.raises(ValueError):
        s.preview(
            {
                "snapshot_id": 1,
                "patch": [
                    {"op": "replace", "path": "/bedrooms", "value": float("nan")}
                ],
            }
        )
    with pytest.raises(ValueError):
        s.preview(
            {
                "snapshot_id": 1,
                "patch": [{"op": "replace", "path": "/not_here", "value": 2}],
            }
        )
    issue = s.parser_issue(
        {
            "issue": "unit_missing",
            "field": "unit_label",
            "note": "extraction class",
            "author": "a",
        }
    )
    assert issue["snapshot_ids"] == [2]
    assert (
        s.observation({"snapshot_id": 2})["raw"]
        == s.observation({"snapshot_id": 2})["corrected"]
    )


def test_selected_identity_confirmation_and_retry(service):
    s = service
    before = s.observation({"snapshot_id": 2})["raw"]
    args = {"stage": "identity", "snapshot_ids": [2], "author": "Ben",
            "ledger_revision": s.observations({})["ledger_revision"], "request_id": "selected-1"}
    assert s.identity_confirm(args)["count"] == 1
    assert s.identity_confirm(args)["count"] == 1
    assert len(s.ledger.events()) == 1
    assert s.observation({"snapshot_id": 2})["corrected"] == before
    assert s.observation({"snapshot_id": 2})["raw"] == before
    assert s.observations({"stage": "identity", "review_status": "unreviewed"})["rows"][0]["snapshot_id"] == 1
    assert s.observations({"stage": "prices", "review_status": "unreviewed"})["total"] == 2
    with pytest.raises(ReviewConflict):
        s.identity_confirm({**args, "snapshot_ids": [1]})


def test_selected_identity_batch_previous_decisions_and_stale_list(service):
    s = service
    args = {"stage": "identity", "snapshot_ids": [1, 2], "author": "Ben",
            "ledger_revision": s.ledger.revision(), "request_id": "selected-2"}
    s.review({"snapshot_id": 1, "stage": "identity", "decision": "needs_attention", "author": "a"})
    with pytest.raises(ReviewConflict):
        s.identity_confirm(args)
    assert len(s.ledger.events()) == 1
    args["ledger_revision"] = s.ledger.revision()
    assert s.identity_confirm(args)["count"] == 2
    assert s.overview()["stages"][0]["progress"]["confirmed"] == 2
    assert len(s.observation({"snapshot_id": 1})["reviews"]) == 2
    assert s.ledger.activity()["corrections"] == []


@pytest.mark.parametrize("changes", [
    {"snapshot_ids": []}, {"snapshot_ids": [1, 1]}, {"snapshot_ids": [1, 3]},
    {"snapshot_ids": [4]}, {"snapshot_ids": [True]}, {"snapshot_ids": "1"},
    {"stage": "prices"}, {"author": " "}, {"request_id": None},
])
def test_selected_identity_rejects_invalid_requests(service, changes):
    args = {"stage": "identity", "snapshot_ids": [1], "author": "Ben",
            "ledger_revision": service.ledger.revision(), "request_id": "selected-3"}
    with pytest.raises(ValueError):
        service.identity_confirm({**args, **changes})
    assert service.ledger.events() == []


def test_list_issue_counts_follow_filters_and_reviews(service):
    s = service
    s.db.execute("INSERT INTO rental SELECT * REPLACE(5 AS snapshot_id,'b' AS building_slug) FROM rental WHERE snapshot_id=2")
    filters = {"stage": "identity", "building": "a", "issue": "unit_missing", "review_status": "unreviewed"}
    page = s.observations(filters)
    assert page["total"] == page["issue_counts"]["unit_missing"] == 1
    assert page["issue_counts"]["all"] == 2
    assert page["issue_counts"]["unit_generic"] == 0
    assert s.observations({**filters, "search": "4C"})["issue_counts"] == {
        "all": 1, "unit_missing": 0, "unit_generic": 0,
    }
    s.review({"snapshot_id": 2, "stage": "identity", "decision": "confirmed", "author": "Ben"})
    page = s.observations(filters)
    assert page["total"] == page["issue_counts"]["unit_missing"] == 0
    assert page["issue_counts"]["all"] == 1
    page = s.observations({**filters, "review_status": "confirmed"})
    assert page["total"] == page["issue_counts"]["all"] == 1
    assert s.observations({**filters, "building": "b"})["issue_counts"]["unit_missing"] == 1
    assert s.observations({"stage": "prices", "building": "a", "review_status": "unreviewed"})["issue_counts"]["all"] == 2
    assert s.observations({"building": "does-not-exist"})["issue_counts"] == {
        "all": 0, "unit_missing": 0, "unit_generic": 0,
    }


def test_list_page_clamps_after_last_page_is_reviewed(service):
    s = service
    filters = {"stage": "identity", "review_status": "unreviewed", "limit": 1, "offset": 1}
    assert s.observations(filters)["offset"] == 1
    s.review({"snapshot_id": 2, "stage": "identity", "decision": "confirmed", "author": "Ben"})
    page = s.observations(filters)
    assert page["total"] == 1
    assert page["offset"] == 0
    assert len(page["rows"]) == 1


def price_preview(service, **changes):
    return service.event_price_preview({"snapshot_id": 1, "episode_index": 0,
        "event_index": 0, "expected_price": 0, "price": 13750, **changes})


def test_single_history_price_overlay_scope_retry_and_retraction(service):
    s = service
    raw = s.observation({"snapshot_id": 1})["raw"]
    original_events = s.events({"snapshot_id": 1})["events"]
    p = price_preview(s)
    assert p["event"]["before"] == 0
    assert p["event"]["after"] == 13750
    assert p["affected_count"] == 1
    assert s.ledger.events() == []
    e = apply(s, p)
    assert apply(s, p)["id"] == e["id"]
    events = s.events({"snapshot_id": 1})["events"]
    assert events[0]["price"] == 13750
    assert events[0]["raw_price"] == 0
    assert events[0]["price_corrected"] is True
    assert events[1] == original_events[1]  # Same date, different occurrence.
    assert s.events({"snapshot_id": 2})["events"][0]["price"] == 0
    detail = s.observation({"snapshot_id": 1})
    assert detail["raw"] == raw
    assert detail["corrected"]["asking_price"] == raw["asking_price"]
    assert detail["events"][0]["price"] == 13750
    s.retract({"id": e["id"], "author": "test", "reason": "undo"})
    assert s.events({"snapshot_id": 1})["events"] == original_events


def test_history_price_unknown_pagination_and_stale_preview(service):
    s = service
    p = price_preview(s, event_index=1, expected_price=13750, price=None)
    apply(s, p)
    event = s.events({"snapshot_id": 1, "offset": 1, "limit": 1})["events"][0]
    assert event["price"] is None
    assert event["raw_price"] == 13750
    with pytest.raises(ReviewConflict):
        price_preview(s, event_index=1, expected_price=13750, price=14000)
    p = price_preview(s)
    s.review({"snapshot_id": 2, "stage": "prices", "decision": "confirmed", "author": "a"})
    with pytest.raises(ReviewConflict):
        apply(s, p)


@pytest.mark.parametrize("changes", [
    {"price": 0}, {"price": -1}, {"price": True}, {"price": "13750"},
    {"price": float("nan")}, {"price": float("inf")},
    {"snapshot_id": 3}, {"episode_index": 10}, {"event_index": 10},
    {"event_index": -1}, {"event_index": True},
])
def test_invalid_history_price_edits(service, changes):
    with pytest.raises(ValueError):
        price_preview(service, **changes)
    assert service.ledger.events() == []


def test_history_structure_correction_blocks_ambiguous_price_edit(service):
    s = service
    p = s.preview({"snapshot_id": 1, "patch": [{"op": "remove",
        "path": "/archive_listing/propertyHistory/0/rentalEventsOfInterest/0"}]})
    apply(s, p)
    assert s.events({"snapshot_id": 1})["events"][0]["price_editable"] is False
    with pytest.raises(ValueError, match="History structure changed"):
        price_preview(s)
