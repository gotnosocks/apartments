import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from apartments.unit_spelling_aliases import (
    alias_rows,
    build,
    normalize_label,
    unit_key,
)

B = "https://streeteasy.com/building/10-downing-street-new_york/"


def unit(label, count=1):
    return {
        "unit_id": "unit:" + label,
        "canonical_unit_url": B + label,
        "listing_count": count,
    }


def test_normalization_ignores_case_punctuation_and_leading_zeros():
    assert normalize_label("005V") == normalize_label("5v") == "5v"
    assert normalize_label("4-b") == normalize_label("4b")
    assert normalize_label("ph03") == "ph3"
    assert normalize_label("0") == "0"
    assert normalize_label("3fl") != normalize_label("3")
    assert unit_key(B + "005v") == unit_key(B + "5v")
    assert unit_key("https://streeteasy.com/building/other/5v") != unit_key(B + "5v")
    assert unit_key("https://streeteasy.com/rental/123") is None


def test_groups_pick_the_best_supported_spelling_and_record_evidence():
    units = [unit("5v", 4), unit("005v", 1), unit("6a", 2)]
    memberships = [("111", "unit:005v"), ("222", "unit:5v")]
    # The /5v unit page lists advertisement 111, which the transform put under /005v.
    rows = alias_rows(units, memberships, [("111", B + "5v")])
    assert {r["canonical_unit_url"] for r in rows} == {B + "5v", B + "005v"}
    assert {r["representative_url"] for r in rows} == {B + "5v"}
    assert all(r["history_confirmed"] and r["group_size"] == 2 for r in rows)
    assert len({r["alias_group_id"] for r in rows}) == 1


def test_groups_without_history_evidence_are_unconfirmed():
    rows = alias_rows(
        [unit("1-2", 1), unit("12", 1)], [("1", "unit:1-2")], [("1", B + "1-2")]
    )
    assert rows and not any(r["history_confirmed"] for r in rows)


def write_dataset(root, units, members):
    tables = {"rental_units": units, "rental_unit_memberships": members}
    digests = {}
    for name, rows in tables.items():
        path = root / name / "derived.parquet"
        path.parent.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist(rows), path)
        import hashlib

        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "complete.json").write_text(
        json.dumps({"unit_association_rule": "canonical-url-v1"})
    )
    (root / "canonical-units.json").write_text(json.dumps({"output_sha256": digests}))


def test_build_writes_a_new_directory_and_never_overwrites(tmp_path):
    import sqlite3

    dataset = tmp_path / "dataset"
    units = [unit("5v", 3), unit("005v", 1)]
    members = [
        {"listing_id": "111", "unit_id": "unit:005v", "status": "associated"},
        {"listing_id": "222", "unit_id": "unit:5v", "status": "associated"},
    ]
    write_dataset(dataset, units, members)
    snapshot = tmp_path / "archive.sqlite3"
    with sqlite3.connect(snapshot) as db:
        db.execute("CREATE TABLE collection_memberships(listing_key, unit_url)")
        db.execute(
            "INSERT INTO collection_memberships VALUES('rental:111:detail', ?)",
            (B + "5v",),
        )
    manifest = build(dataset, tmp_path / "aliases", snapshot)
    assert manifest["counts"] == {
        "groups": 1,
        "history_confirmed_groups": 1,
        "units_in_groups": 2,
        "listings_in_groups": 4,
    }
    rows = pq.read_table(
        tmp_path / "aliases" / "unit_spelling_aliases.parquet"
    ).to_pylist()
    assert {r["representative_url"] for r in rows} == {B + "5v"}
    with pytest.raises(ValueError, match="already exists"):
        build(dataset, tmp_path / "aliases", snapshot)


def test_build_rejects_a_dataset_whose_tables_changed(tmp_path):
    dataset = tmp_path / "dataset"
    write_dataset(
        dataset,
        [unit("5v")],
        [{"listing_id": "1", "unit_id": "unit:5v", "status": "associated"}],
    )
    pq.write_table(
        pa.Table.from_pylist([unit("6a")]), dataset / "rental_units" / "derived.parquet"
    )
    with pytest.raises(ValueError, match="does not match"):
        build(dataset, tmp_path / "aliases")
