import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import api_records


def _rows(price):
    return [
        {
            "listing_id": 7,
            "collected_at": 100.0,
            "last_collected_at": 250.0,
            "response_id": 41,
            "record": {"id": "7", "pricing": {"price": price}},
        }
    ]


def test_the_newest_complete_clean_line_names_the_file(records_catalog, tmp_path):
    line = records_catalog(_rows(3000))
    catalog = tmp_path / "catalog.ndjson"
    dirty = dict(line, code={"clean": False}, records=dict(line["records"], sha256="0"))
    with open(catalog, "a") as f:
        f.write(json.dumps(dirty) + "\n")
        f.write(json.dumps(dict(line, records={"path": "x"}))[:40])
    source = api_records.records_file()
    assert source["path"] == str(tmp_path / line["records"]["path"])
    assert (source["sha256"], source["rows"]) == (line["records"]["sha256"], 1)


def test_a_changed_records_file_stops(records_catalog, tmp_path):
    line = records_catalog(_rows(3000))
    path = tmp_path / line["records"]["path"]
    path.write_bytes(path.read_bytes() + b"\0")
    with pytest.raises(ValueError, match="differs from the pipeline's catalog"):
        api_records.records_file()


def test_a_build_without_a_records_file_stops(records_catalog, tmp_path):
    line = records_catalog(_rows(3000))
    with open(tmp_path / "catalog.ndjson", "a") as f:
        f.write(json.dumps({k: v for k, v in line.items() if k != "records"}) + "\n")
    with pytest.raises(ValueError, match="has no records"):
        api_records.records_file()


def test_captures_take_the_granular_names(records_catalog):
    records_catalog(_rows(3000))
    got = list(
        api_records.captures(
            api_records.records_file(),
            [
                "listing_id",
                "listing_type",
                "collected_at",
                "snapshot_id",
                "raw_listing_json",
            ],
        )
    )
    assert got == [
        {
            "listing_id": "7",
            "listing_type": "rental",
            "collected_at": 250.0,
            "snapshot_id": 41,
            "raw_listing_json": '{"id":"7","pricing":{"price":3000}}',
        }
    ]


def test_observations_read_a_granular_folder_or_the_records_file(
    records_catalog, tmp_path
):
    records_catalog(_rows(3000))
    folder = tmp_path / "granular" / "listing_observations"
    (folder / "part=b").mkdir(parents=True)
    (folder / "part=a").mkdir()
    for part, ids in (("b", ["3"]), ("a", ["1", "2"])):
        table = pa.table({"listing_id": ids, "collected_at": [1.0] * len(ids)})
        pq.write_table(table, folder / f"part={part}" / "0.parquet")
    got = api_records.observations(str(tmp_path / "granular"), ["listing_id"])
    assert [r["listing_id"] for r in got] == ["1", "2", "3"]
    got = api_records.observations(api_records.CRAWL, ["listing_id", "collected_at"])
    assert list(got) == [{"listing_id": "7", "collected_at": 250.0}]
