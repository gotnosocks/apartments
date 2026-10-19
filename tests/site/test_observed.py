"""The Hoboken and Jersey City listings: observed values from the pipeline, no estimates."""

import datetime as dt
import json

from apartments.site import build, observed

NJ = {
    "regions": "VARCHAR[]",
    "neighbourhood": "VARCHAR",
    "unit_id": "VARCHAR",
    "page": "VARCHAR",
    "building": "VARCHAR",
    "price_at": "TIMESTAMPTZ",
    "period": "DATE",
    "latest_ask": "DOUBLE",
    "latest_gross": "DOUBLE",
    "months_free": "DOUBLE",
    "lease_term": "DOUBLE",
}
SEEN = dt.datetime(2026, 10, 5, tzinfo=dt.UTC)


def ad(listing_id, regions, ask=3000.0, status="ACTIVE", fetched=SEEN, **values):
    return {
        "listing_id": listing_id,
        "unit_id": f"unit:{listing_id}",
        "building": "50-washington-street-hoboken",
        "page": f"https://streeteasy.com/building/50-washington-street-hoboken/{listing_id[-1]}a",
        "response_id": 1,
        "fetched": fetched,
        "status": status,
        "page_price": ask,
        "bedrooms": 1.0,
        "bathrooms": 1.0,
        "square_feet": 650.0,
        "regions": regions,
        "neighbourhood": "Hoboken",
        "price_at": fetched,
        "period": fetched.date().replace(day=1),
        "latest_ask": ask,
        "latest_gross": ask,
        **values,
    }


def write(pipeline, ads):
    return pipeline.write(ads, ad_columns={}, row_columns=NJ)


def reads(tmp_path, verdicts):
    path = tmp_path / "reads.jsonl"
    path.write_text(
        "".join(json.dumps({"listing_id": i, "verdict": v}) + "\n" for i, v in verdicts)
    )
    return path


def test_rows_keep_nj_ads_and_leave_out_nyc_and_read_non_apartments(
    pipeline, tmp_path, build_clock
):
    files = write(
        pipeline,
        [
            ad("1001", ["nj-jersey-city-hoboken"]),
            ad("1002", ["nj-jersey-city-hoboken"], ask=900.0),
            ad(
                "1003",
                ["nj-jersey-city-hoboken"],
                status="RENTED",
                fetched=SEEN - dt.timedelta(days=60),
            ),
            ad("2001", ["manhattan"], neighbourhood="Chelsea"),
        ],
    )
    rows, status = observed.rows(
        files, reads=reads(tmp_path, [("1002", "ROOM_SHARE"), ("1001", "OK")])
    )
    by_id = {r["listing_id"]: r for r in rows}
    assert set(by_id) == {"1001", "1003"}
    assert by_id["1001"]["is_current"] == 1
    assert by_id["1003"]["is_current"] == 0
    assert by_id["1001"]["ask"] == 3000.0
    assert by_id["1001"]["building_name"] == "50 Washington Street Hoboken"
    assert by_id["1001"]["listing_url"] == "https://streeteasy.com/rental/1001"
    assert status["left_out"] == {"ROOM_SHARE": 1}
    assert status["rows"] == 2 and status["current"] == 1


def test_rows_without_a_regions_column(pipeline):
    files = pipeline.write([ad("1001", None)])
    assert observed.rows(files)[0] == []


def test_page_shows_nj_listings_without_estimates(
    pipeline, tmp_path, bundle, monkeypatch, research_file
):
    from apartments.site.web import create_app

    write(
        pipeline,
        [
            ad("1001", ["nj-jersey-city-hoboken"], ask=3100.0),
            ad("1002", ["nj-jersey-city-hoboken"], ask=950.0),
            ad("1004", ["nj-jersey-city-hoboken"], ask=4200.0, bedrooms=2.0),
        ],
    )
    monkeypatch.setattr(observed, "READS", reads(tmp_path, [("1002", "ROOM_SHARE")]))
    root = tmp_path / "site"
    build.build(bundle, root, scope="Chelsea")
    app = create_app(
        root, allowed_hosts=["thelio.example.ts.net"], research_data=research_file
    )
    app.config["TESTING"] = True
    client = app.test_client()
    page = client.get("/new-jersey").get_data(as_text=True)
    assert "50 Washington Street Hoboken" in page
    assert "$3,100" in page and "$4,200" in page
    assert "$950" not in page
    assert "1 room share." in page
    assert "Estimate" not in page.split("<main", 1)[1].split("</main>")[0].replace(
        "Estimate an apartment", ""
    ).replace("Estimates", "")
    two = client.get("/new-jersey?beds=2").get_data(as_text=True)
    assert "$4,200" in two and "$3,100" not in two
    csv_text = client.get("/new-jersey.csv?sort=ask").get_data(as_text=True)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("listing_id,neighbourhood")
    assert [line.split(",")[0] for line in lines[1:]] == ["1001", "1004"]
    listings = client.get("/listings").get_data(as_text=True)
    assert "50 Washington Street Hoboken" not in listings


def test_the_recorded_reads_leave_out_ads():
    """The reads file ships with the repo, so a deploy hides the read non-apartments."""
    assert observed.READS.is_file()
    assert set(observed.hidden().values()) <= set(observed.HIDDEN)
    assert len(observed.hidden()) > 0
