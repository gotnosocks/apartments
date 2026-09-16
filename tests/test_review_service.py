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
        """CREATE TABLE event_mentions AS SELECT 1::BIGINT snapshot_id,0 episode_index,0 event_index,'1' event_listing_id,'rental' event_category,'2020-01-01' event_date,0.0 price,'Listed' status,'{}' event_json"""
    )
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
