"""The pipeline's records step serializes each API record as the granular export's parser does.

The pipeline's own venv lacks the page parser's dependencies, so this check runs here, with the
parser of `apartments.graphql_listing` beside the step's `serialize`.
"""

import importlib.util
import json
from pathlib import Path

import pyarrow.parquet as pq

from apartments.graphql_listing import listing_body, parse_capture

PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
FIXTURE = PIPELINE / "tests" / "fixture" / "export" / "ads"


def records():
    spec = importlib.util.spec_from_file_location(
        "pipeline_records", PIPELINE / "steps" / "records.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parsed(listing_id, record):
    building = {
        "id": record.get("buildingId"),
        "slug": "a-building",
        "page": "https://streeteasy.com/building/a-building",
    }
    url = f"https://streeteasy.com/rental/{listing_id}"
    row, _ = parse_capture(listing_body(listing_id, building, record), url)
    return row


def test_fixture_records_match_the_granular_parser():
    """Each of the fixture's 229 records comes out of `serialize` as the parser's
    `raw_listing_json` of the page the capture rewrite builds from it."""
    step = records()
    count = 0
    for path in sorted(FIXTURE.glob("*/*.parquet")):
        table = pq.read_table(path, columns=["listing_id", "outcome", "record"])
        for listing_id, outcome, text in zip(*(c.to_pylist() for c in table.columns)):
            if outcome != "record":
                continue
            row = parsed(listing_id, json.loads(text))
            assert (row["parse_status"], row["listing_id"], row["listing_type"]) == (
                "ok",
                str(listing_id),
                "rental",
            )
            assert step.serialize(text) == row["raw_listing_json"]
            count += 1
    assert count == 229


def test_floats_and_text_match_the_granular_parser():
    """A made-up record with integral and fractional floats in its prices and sizes, nested
    `__typename` keys and non-ASCII text comes out of `serialize` as the parser gives it."""
    record = {
        "__typename": "RentalListing",
        "id": "4000001",
        "buildingId": "17503",
        "description": "Café – sunny",
        "pricing": {
            "__typename": "Pricing",
            "price": 3050.0,
            "priceChanges": [
                {
                    "__typename": "PriceChange",
                    "changedAt": "2026-10-01",
                    "price": 3100.0,
                },
                {
                    "__typename": "PriceChange",
                    "changedAt": "2026-10-08",
                    "price": 3050.5,
                },
            ],
        },
        "propertyDetails": {"livingAreaSize": 750.0, "bathroomCount": 1.5},
    }
    text = json.dumps(record, sort_keys=True)
    # The record lacks fields a page needs, so the parser reads it as partial.
    row = parsed(4000001, record)
    assert row["parse_status"] == "partial"
    assert records().serialize(text) == row["raw_listing_json"]
