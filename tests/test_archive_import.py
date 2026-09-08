import gzip
import json
import sqlite3

from apartments.archive_import import import_archive, normalize_listing
from apartments.db import connect


def listing_html():
    listing = {
        "id": "5116510",
        "daysOnMarket": 35,
        "status": "ACTIVE",
        "price": 4909,
        "propertyDetails": {
            "address": {
                "state": "NY", "street": "500 West 23rd Street",
                "city": "NEW YORK", "zipCode": "10011", "displayUnit": "#4C",
            },
            "roomCount": 2, "bedroomCount": 0, "fullBathroomCount": 1,
            "halfBathroomCount": 0, "livingAreaSize": 475,
            "amenities": {"list": ["DOORMAN"]},
            "features": {"list": ["DISHWASHER"]},
        },
        "propertyHistory": [{
            "listingId": "2300302",
            "sourceGroupLabel": "Equity Residential",
            "rentalEventsOfInterest": [
                {"date": "2015-01-31", "price": 3120, "status": "ACTIVE"},
                {"date": "2015-02-01", "price": 3315, "pricePercentChange": 6.25},
                {"date": "2015-02-02", "price": 3315, "status": "NO_LONGER_AVAILABLE"},
            ],
        }],
    }
    flight = '0:{"listing":' + json.dumps(listing, separators=(",", ":")) + "}"
    push = json.dumps([1, flight])
    return f"""<html><head>
      <link rel="canonical" href="https://streeteasy.com/rental/5116510">
      <script>self.__next_f.push({push})</script></head><body>
      <a data-testid="addressLink" href="/building/ten23-500-west-23rd-street-new_york">building</a>
      <div data-testid="address">500 West 23rd Street #4C</div>
      <div data-testid="priceInfo">$4,909 for rent</div>
      <div data-testid="propertyDetails">475 ft² Studio 1 bath</div>
    </body></html>""".encode()


def test_normalize_listing_reads_complete_embedded_history():
    item = normalize_listing(listing_html(), "https://streeteasy.com/rental/5116510", 1_700_000_000)
    assert item["source_listing_id"] == "ten23-500-west-23rd-street-new_york/4c"
    assert item["asking_rent"] == 4909
    assert item["attributes"] == {
        "square_feet": 475, "bedrooms": 0, "bathrooms": 1.0, "rooms": 2,
    }
    assert [event["date"] for event in item["price_history"]] == [
        "2015-01-31", "2015-02-01", "2015-02-02",
    ]
    assert item["price_history"][1]["event"] == "Price increased by 6%"


def test_normalize_listing_rejects_sale_history():
    body = listing_html().replace(b"rentalEventsOfInterest", b"saleEventsOfInterest")
    assert normalize_listing(body, "https://streeteasy.com/sale/5116510", 1_700_000_000) is None


def test_import_archive_is_incremental(tmp_path):
    archive = tmp_path / "archive"
    body_dir = archive / "bodies" / "aa"
    body_dir.mkdir(parents=True)
    body_path = body_dir / "capture.gz"
    with gzip.open(body_path, "wb") as stream:
        stream.write(listing_html())
    source = sqlite3.connect(archive / "archive.sqlite3")
    source.executescript("""
      CREATE TABLE snapshots(id INTEGER PRIMARY KEY, generation INTEGER, url TEXT, body_hash TEXT, observed REAL);
      CREATE TABLE bodies(hash TEXT PRIMARY KEY, path TEXT, size INTEGER, created REAL);
      CREATE TABLE frontier(generation INTEGER, url TEXT, kind TEXT);
    """)
    url = "https://streeteasy.com/rental/5116510"
    source.execute("INSERT INTO snapshots VALUES (1,1,?,?,?)", (url, "abc", 1_700_000_000))
    source.execute("INSERT INTO bodies VALUES ('abc','bodies/aa/capture.gz',1,0)")
    source.execute("INSERT INTO frontier VALUES (1,?,'listing')", (url,))
    source.commit()
    source.close()

    db_path = tmp_path / "apartments.duckdb"
    first = import_archive(archive, db_path)
    second = import_archive(archive, db_path)
    assert first["imported"] == 1
    assert first["events"] == 3
    assert second["imported"] == 0
    assert second["skipped"] == 1
    db = connect(db_path)
    assert db.execute("SELECT count(*) FROM listing_events").fetchone()[0] == 3
    assert db.execute("SELECT count(*) FROM captures").fetchone()[0] == 1
    db.close()
