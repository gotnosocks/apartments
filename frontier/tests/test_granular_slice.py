import json
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import granular_slice


def source(tmp_path, ads):
    """A granular transform with ads (listing, building, unit, snapshot) and
    the collector archive that gives each ad region "r"."""
    root = tmp_path / "granular"
    tables = {
        "listing_observations": [
            {
                "snapshot_id": s,
                "listing_id": li,
                "listing_type": "rental",
                "building_slug": b,
            }
            for li, b, _, s in ads
        ],
        "building_observations": [
            {"snapshot_id": 1000 + i, "building_slug": b}
            for i, b in enumerate(sorted({b for _, b, _, _ in ads}))
        ],
        "rental_unit_memberships": [
            {"listing_id": li, "unit_id": u} for li, _, u, _ in ads
        ],
        "event_mentions": [
            {"snapshot_id": s, "event_listing_id": li, "event_index": 0}
            for li, _, _, s in ads
        ],
    }
    for name, rows in tables.items():
        (root / name).mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist(rows), root / name / "part-0.parquet")
    (root / "complete.json").write_text(
        json.dumps({"unit_association_rule": "canonical-url-v1", "finished_at": 5.0})
    )
    archive = tmp_path / "archive.sqlite3"
    with sqlite3.connect(archive) as db:
        db.execute(
            "CREATE TABLE graphql_search_members(generation, region, listing_id)"
        )
        db.executemany(
            "INSERT INTO graphql_search_members VALUES (1, 'r', ?)",
            [(int(li),) for li, _, _, _ in ads],
        )
    return root, archive


def test_slices_keep_buildings_whole(tmp_path):
    ads = [
        ("1", "a", "u1", 1),
        ("2", "a", "u1", 2),
        ("3", "b", "u2", 3),
        ("4", "c", "u3", 4),
    ]
    root, archive = source(tmp_path, ads)
    slices = granular_slice.plan(root, archive, max_ads=2)
    assert dict(zip(slices.building_slug, slices.slice)) == {
        "a": "r-01",
        "b": "r-02",
        "c": "r-02",
    }
    report = granular_slice.write(root, slices, tmp_path / "out")
    assert report["r-01"] == {
        "listing_observations": 2,
        "building_observations": 1,
        "rental_unit_memberships": 2,
        "event_mentions": 2,
    }
    complete = json.loads((tmp_path / "out/r-02/complete.json").read_text())
    assert complete["finished_at"] == 5.0
    assert complete["unit_association_rule"] == "canonical-url-v1"
    events = pq.read_table(tmp_path / "out/r-02/event_mentions").to_pylist()
    assert sorted(e["event_listing_id"] for e in events) == ["3", "4"]


def test_a_unit_split_across_slices_is_refused(tmp_path):
    root, archive = source(tmp_path, [("1", "a", "u1", 1), ("2", "b", "u1", 2)])
    slices = granular_slice.plan(root, archive, max_ads=1)
    with pytest.raises(SystemExit, match="two slices"):
        granular_slice.write(root, slices, tmp_path / "out")
