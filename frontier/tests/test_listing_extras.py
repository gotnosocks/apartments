import json

import pyarrow as pa
import pyarrow.parquet as pq

from rentfrontier import api_records, listing_extras


def extras(changes, rooms):
    return {
        "status": "ACTIVE",
        "propertyDetails": {"roomCount": rooms},
        "pricing": {"priceChanges": [{"changedAt": d, "price": p} for d, p in changes]},
    }


def test_listing_extras_read_the_records_file_at_each_records_last_fetch(
    records_catalog, tmp_path
):
    """Listing 7's first record has the earlier first fetch and the later last fetch, so the
    builder keeps it, at its last fetch. Listing 8's page capture is older than its record, so
    the builder keeps the record."""
    records_catalog(
        [
            {
                "listing_id": 7,
                "collected_at": 1.0,
                "last_collected_at": 9.0,
                "record": extras([("2026-10-01", 3000)], 3),
            },
            {
                "listing_id": 7,
                "collected_at": 2.0,
                "last_collected_at": 3.0,
                "record": extras([("2026-10-02", 3100)], 4),
            },
            {"listing_id": 8, "collected_at": 5.0, "record": extras([], 2)},
        ]
    )
    page = tmp_path / "page" / "listing_observations"
    page.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "listing_id": [8],
                "listing_type": ["rental"],
                "collected_at": [4.0],
                "raw_listing_json": [json.dumps(extras([], 5))],
            }
        ),
        page / "part.parquet",
    )
    table = listing_extras.build(
        {"page": str(tmp_path / "page"), "api": api_records.CRAWL},
        api_records.records_file(),
    ).set_index("listing_id")
    assert table.loc["7"].collected_at == 9.0
    assert json.loads(table.loc["7"].price_changes) == [["2026-10-01", 3000]]
    assert table.loc["7"].room_count == 3
    assert (table.loc["8"].neighbourhood, table.loc["8"].room_count) == ("api", 2)


def test_main_lists_the_records_file_in_its_sources(
    records_catalog, tmp_path, monkeypatch
):
    """`--crawl records` reads the catalog's records file, and provenance.json gives its path
    and SHA-256, and those of the ads file on the same catalog line."""
    line = records_catalog(
        [{"listing_id": 7, "collected_at": 1.0, "record": extras([], 3)}]
    )
    monkeypatch.setattr(listing_extras, "EXTERNAL_ROOT", tmp_path / "external")
    monkeypatch.setattr(
        listing_extras, "_git", lambda *a: "" if a[0] == "status" else "abc1234def"
    )
    listing_extras.main(["--crawl", api_records.CRAWL, "--tag", "api"])
    (prov,) = (tmp_path / "external").glob(
        "listing-extras/*-abc1234-api/provenance.json"
    )
    sources = json.loads(prov.read_text())["sources"]
    assert sources["crawl"] == {
        "path": str(tmp_path / line["records"]["path"]),
        "sha256": line["records"]["sha256"],
    }
    assert sources["ads_file"] == {
        "path": str(tmp_path / line["ads_file"]["path"]),
        "sha256": line["ads_file"]["sha256"],
    }
