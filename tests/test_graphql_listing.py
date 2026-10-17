import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from apartments import granular_parse, graphql_listing
from apartments.granular_parse import parse_listing
from apartments.graphql_listing import (
    api_document,
    listing_body,
    parse_capture,
    parse_listing_json,
)

URL = "https://streeteasy.com/rental/4242"
BUILDING = {
    "id": "17503",
    "slug": "demo-500-west-43-street-new_york",
    "page": "https://streeteasy.com/building/demo-500-west-43-street-new_york",
}
UNIT = "https://streeteasy.com/building/demo-500-west-43-street-new_york/12b"


def page_listing():
    return {
        "id": "4242",
        "slug": "12b",
        "buildingId": "17503",
        "createdAt": "2026-09-01T12:00:00Z",
        "updatedAt": "2026-10-01T12:00:00Z",
        "pricing": {"price": 4100, "noFeeAmount": None},
        "propertyDetails": {
            "address": {"displayUnit": "#12B", "street": "500 West 43rd Street"},
            "bedroomCount": 1,
            "fullBathroomCount": 1,
            "halfBathroomCount": 1,
            "livingAreaSize": 700,
            "roomCount": 3,
            "features": {"list": ["Dishwasher"]},
            "amenities": {"list": ["Doorman"]},
        },
        "propertyHistory": [
            {
                "listingId": "4242",
                "rentalEventsOfInterest": [
                    {"date": "2026-09-01", "price": 4300, "status": "LISTED"},
                    {
                        "date": "2026-09-20",
                        "price": 4100,
                        "status": "PRICE_DECREASE",
                        "pricePercentChange": -5,
                    },
                ],
            },
            {
                "listingId": "3101",
                "rentalEventsOfInterest": [
                    {"date": "2024-05-01", "price": 3900, "status": "RENTED"}
                ],
            },
        ],
    }


def api_record(listing):
    """The listing as the API writes it: typed objects and floats for numbers."""

    def typed(value, name):
        if isinstance(value, dict):
            return {
                "__typename": name,
                **{k: typed(v, f"{name}_{k}") for k, v in value.items()},
            }
        if isinstance(value, list):
            return [typed(v, name) for v in value]
        if isinstance(value, int) and not isinstance(value, bool):
            return float(value)
        return value

    return typed(listing, "RentalListing")


def page_body(listing):
    payload = json.dumps(listing).replace('"', '\\"')
    return (
        f'<html><head><link rel="canonical" href="{UNIT}"></head><body>'
        f'<a data-testid="addressLink" href="{BUILDING["page"]}">x</a>'
        f'<script>self.__next_f.push([1,"a:{payload}\\n"])</script></body></html>'
    ).encode()


def test_api_body_parses_to_the_page_row_and_events():
    listing = page_listing()
    page_row, page_events = parse_listing(page_body(listing), URL)
    body = listing_body("4242", BUILDING, api_record(listing))
    api_row, api_events = parse_listing_json(body, URL)
    assert page_row["parse_status"] == "ok"
    assert page_row["canonical_unit_url"] == UNIT
    assert api_row == page_row
    assert api_events == page_events
    assert [e["status"] for e in api_events] == ["LISTED", "PRICE_DECREASE", "RENTED"]


def test_listing_body_bytes_repeat_for_an_unchanged_record():
    record = api_record(page_listing())
    first = listing_body(4242, BUILDING, record)
    assert first == listing_body("4242", BUILDING, json.loads(json.dumps(record)))
    assert api_document(first)["listing_id"] == "4242"


@pytest.mark.parametrize(
    "body",
    [
        b"<html></html>",
        b'{"source": "something-else"}',
        b"{not json",
        b"",
    ],
)
def test_api_document_rejects_other_bodies(body):
    assert api_document(body) is None


def test_parse_capture_sends_each_body_to_its_parser(monkeypatch):
    listing = page_listing()
    api = listing_body("4242", BUILDING, api_record(listing))
    page = page_body(listing)
    assert parse_capture(api, URL) == parse_listing_json(api, URL)
    calls = []

    def fake(body, url):
        calls.append(url)
        return {"parse_status": "patched"}, []

    monkeypatch.setattr(granular_parse, "parse_listing", fake)
    assert parse_capture(page, URL) == ({"parse_status": "patched"}, [])
    assert parse_capture(api, URL)[0]["parse_status"] == "ok"
    assert calls == [URL]


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        0,
        7,
        -6.0,
        2.5,
        "1,250 ft²",
        " $4,100 / month ",
        "none",
        "",
        [1, 2],
        {"b": 1, "a": "é"},
    ],
)
def test_helpers_give_the_page_parsers_values(value):
    assert graphql_listing._number(value) == granular_parse._number(value)
    assert graphql_listing._clean(value) == granular_parse._clean(value)
    assert graphql_listing._json(value) == granular_parse._json(value)
    key = graphql_listing._event_key("4242", "4241", "rental", 1, 2, value)
    assert key == granular_parse._event_key("4242", "4241", "rental", 1, 2, value)
    assert graphql_listing._occurrence_key(key, 1, 2) == granular_parse._occurrence_key(
        key, 1, 2
    )


def test_api_collection_loads_without_the_page_parser():
    """The collector, its export and the pipeline parse API ads with no page parser imported."""
    body = listing_body("4242", BUILDING, api_record(page_listing())).decode()
    program = f"""
import sys
from apartments.graphql_listing import parse_capture
import streeteasy_archive.graphql_export, streeteasy_archive.graphql_search
row, events = parse_capture({body!r}.encode(), {URL!r})
assert row["parse_status"] == "ok" and events
loaded = sorted(m for m in sys.modules if m.startswith("apartments.granular"))
assert loaded == [], loaded
"""
    src = Path(__file__).resolve().parents[1] / "src"
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        env={**os.environ, "PYTHONPATH": str(src)},
    )


def test_missing_slug_leaves_no_canonical_unit():
    record = api_record(page_listing())
    record["slug"] = None
    row, events = parse_listing_json(listing_body("4242", BUILDING, record), URL)
    assert row["parse_status"] == "ok" and len(events) == 3
    assert row["canonical_unit_url"] is None
    assert row["canonical_unit_error"] == "API record has no building slug or unit slug"


def test_building_id_mismatch_leaves_no_canonical_unit():
    record = api_record(page_listing())
    record["buildingId"] = "999"
    row, _ = parse_listing_json(listing_body("4242", BUILDING, record), URL)
    assert row["canonical_href"] is None and row["canonical_unit_url"] is None
    assert row["canonical_unit_error"].startswith("API record's buildingId differs")


def test_wrong_listing_id_fails_like_the_page_parser():
    body = listing_body("4242", BUILDING, api_record(page_listing()))
    row, events = parse_listing_json(body, "https://streeteasy.com/rental/99")
    page_row, _ = parse_listing(
        page_body(page_listing()), "https://streeteasy.com/rental/99"
    )
    assert events == []
    assert row["parse_status"] == page_row["parse_status"] == "failed"
    assert row["error"] == page_row["error"]
    assert row["listing_id"] == "99"
    assert row["canonical_unit_url"] == UNIT


def test_null_record_fails():
    row, events = parse_listing_json(listing_body("4242", BUILDING, None), URL)
    assert row["parse_status"] == "failed" and events == []
    assert row["error"] == "listing object not found"


def test_missing_history_is_partial():
    record = api_record(page_listing())
    record["propertyHistory"] = None
    row, events = parse_listing_json(listing_body("4242", BUILDING, record), URL)
    assert row["parse_status"] == "partial" and events == []


def test_normalize_drops_typenames_and_integral_floats():
    assert graphql_listing.normalize(
        {"__typename": "X", "a": [1.0, 1.5, {"__typename": "Y", "b": -6.0}]}
    ) == {"a": [1, 1.5, {"b": -6}]}


def test_export_building_copies_the_center_and_drops_typenames():
    record = {
        "__typename": "Building",
        "id": "17503",
        "slug": BUILDING["slug"],
        "floorCount": 30.0,
        "geoCenter": {"__typename": "LatLng", "latitude": 40.76, "longitude": -73.99},
    }
    data = {
        "json": graphql_listing.building_document(
            graphql_listing.building_body(17503, record)
        )
    }
    assert graphql_listing.export_building(data) == {
        "id": "17503",
        "slug": BUILDING["slug"],
        "floorCount": 30,
        "geoCenter": {"latitude": 40.76, "longitude": -73.99},
        "latitude": 40.76,
        "longitude": -73.99,
    }
    listing = {"json": api_document(listing_body("4242", BUILDING, {"id": "4242"}))}
    assert graphql_listing.export_building(listing) is None
    assert graphql_listing.export_building({"json": None}) is None
