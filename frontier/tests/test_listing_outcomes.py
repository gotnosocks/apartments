import json

import pandas as pd
import pytest

from rentfrontier import api_records, listing_outcomes


def _raw(changes, price, status, on, off):
    return json.dumps(
        {
            "status": status,
            "onMarketAt": on,
            "offMarketAt": off,
            "pricing": {
                "price": price,
                "priceChanges": [
                    {"changedAt": f"2026-0{i + 1}-01T00:00:00Z", "price": p}
                    for i, p in enumerate(changes)
                ],
            },
        }
    )


def test_record_outcomes_counts_cuts_and_days():
    got = listing_outcomes.record_outcomes(
        _raw(
            [5000, 4900, 4900, 4950, 4800], 4800, "RENTED", "2026-01-01", "2026-03-02"
        ),
        0.0,
    )
    assert got["first_ask"] == 5000 and got["final_ask"] == 4800
    assert (got["n_changes"], got["n_cuts"], got["n_raises"]) == (3, 2, 1)
    assert got["days_listed"] == 60 and not got["still_listed"]


def test_record_outcomes_counts_an_active_listing_to_its_capture():
    at = pd.Timestamp("2026-01-11", tz="UTC").timestamp()
    got = listing_outcomes.record_outcomes(
        _raw([3000], 3000, "ACTIVE", "2026-01-01", None), at
    )
    assert got["still_listed"] and got["days_listed"] == 10 and got["n_cuts"] == 0


def test_attach_matches_on_source_listing_id(tmp_path):
    table = pd.DataFrame(
        {"listing_id": ["7", "8"], **{c: [1, 2] for c in listing_outcomes.COLUMNS}}
    )
    table.to_parquet(tmp_path / "o.parquet")
    frame = pd.DataFrame({"source_listing_id": [8, 9]})
    got = listing_outcomes.attach(frame, str(tmp_path / "o.parquet"))
    assert got.final_ask.iloc[0] == 2 and pd.isna(got.final_ask.iloc[1])


def test_record_outcomes_leaves_a_stale_off_market_day_uncounted():
    got = listing_outcomes.record_outcomes(
        _raw([3000], 3000, "RENTED", "2026-02-01", "2026-01-01"), 0.0
    )
    assert got["days_listed"] is None


DAY = 86_400.0
OCT_1 = pd.Timestamp("2026-10-01", tz="UTC").timestamp()


def outcome(status, off=None):
    return {
        "status": status,
        "onMarketAt": "2026-10-01T00:00:00Z",
        "offMarketAt": off,
        "pricing": {"price": 3000, "priceChanges": []},
    }


def test_a_live_listings_days_run_to_its_records_last_fetch(records_catalog):
    """Listing 7 is still on the market, first fetched a day after it was listed and last
    fetched ten days after, so it counts ten days. Listing 8 left the market on Oct 5, and its
    days stop there."""
    records_catalog(
        [
            {
                "listing_id": 7,
                "collected_at": OCT_1 + DAY,
                "last_collected_at": OCT_1 + 10 * DAY,
                "record": outcome("ACTIVE"),
            },
            {
                "listing_id": 8,
                "collected_at": OCT_1 + DAY,
                "last_collected_at": OCT_1 + 10 * DAY,
                "record": outcome("OFF_MARKET", "2026-10-05T00:00:00Z"),
            },
        ]
    )
    table = listing_outcomes.build({"api": api_records.CRAWL}).set_index("listing_id")
    assert (table.loc["7"].days_listed, table.loc["7"].still_listed) == (10, True)
    assert (table.loc["8"].days_listed, table.loc["8"].still_listed) == (4, False)
    assert table.loc["7"].collected_at == OCT_1 + 10 * DAY


def test_main_names_the_records_file_it_read(records_catalog, tmp_path, monkeypatch):
    """`--crawl records` reads the catalog's records file, and provenance.json gives it under
    `records`. `--crawl page` stands for the page crawls, and a tag without a crawl stops."""
    line = records_catalog(
        [{"listing_id": 7, "collected_at": OCT_1, "record": outcome("ACTIVE")}]
    )
    monkeypatch.setattr(listing_outcomes, "EXTERNAL_ROOT", tmp_path / "external")
    monkeypatch.setattr(
        listing_outcomes, "_git", lambda *a: "" if a[0] == "status" else "abc1234def"
    )
    listing_outcomes.main(["--crawl", "records", "--tag", "api"])
    (prov,) = (tmp_path / "external").glob(
        "listing-outcomes/*-abc1234-api/provenance.json"
    )
    prov = json.loads(prov.read_text())
    assert prov["crawls"] == {"crawl": "records"}
    assert (prov["records"]["path"], prov["records"]["sha256"]) == (
        str(tmp_path / line["records"]["path"]),
        line["records"]["sha256"],
    )
    ads = prov["records"]["ads"]
    assert (ads["path"], ads["sha256"]) == (
        str(tmp_path / line["ads_file"]["path"]),
        line["ads_file"]["sha256"],
    )
    n = len(listing_outcomes.CRAWLS)
    assert listing_outcomes.parse(["--crawl", "page", "--crawl", "records"]) == (
        {**listing_outcomes.CRAWLS, f"crawl-{n}": "records"},
        "",
    )
    with pytest.raises(SystemExit):
        listing_outcomes.main(["--tag", "api"])


def test_the_later_capture_wins_across_page_crawls_and_records(
    records_catalog, tmp_path
):
    """Listing 7's record is fetched after its page capture, so its outcome comes from the
    record. Listing 8's page capture comes after its record, so the page capture stands. The ads
    file marks listing 9 `no_dated_own_active_event`, so the reader skips its record, and its
    earlier page capture stands."""
    page = tmp_path / "page"
    (page / "listing_observations").mkdir(parents=True)
    pd.DataFrame(
        {
            "listing_id": ["7", "8", "9"],
            "collected_at": [OCT_1 + 5 * DAY, OCT_1 + 20 * DAY, OCT_1 + 2 * DAY],
            "raw_listing_json": [
                json.dumps(outcome("ACTIVE")),
                json.dumps(outcome("RENTED", "2026-10-15T00:00:00Z")),
                json.dumps(outcome("ACTIVE")),
            ],
        }
    ).to_parquet(page / "listing_observations" / "part-0.parquet")
    rented = outcome("RENTED", "2026-10-09T00:00:00Z")
    rented["pricing"] = {
        "price": 2900,
        "priceChanges": [
            {"changedAt": "2026-10-01T00:00:00Z", "price": 3000},
            {"changedAt": "2026-10-06T00:00:00Z", "price": 2900},
        ],
    }
    records_catalog(
        [
            {
                "listing_id": 7,
                "collected_at": OCT_1 + DAY,
                "last_collected_at": OCT_1 + 10 * DAY,
                "record": rented,
            },
            {
                "listing_id": 8,
                "collected_at": OCT_1 + DAY,
                "last_collected_at": OCT_1 + 3 * DAY,
                "record": outcome("ACTIVE"),
            },
            {
                "listing_id": 9,
                "collected_at": OCT_1 + DAY,
                "last_collected_at": OCT_1 + 10 * DAY,
                "record": rented,
            },
        ],
        ads=[
            {"listing_id": "7"},
            {"listing_id": "8"},
            {"listing_id": "9", "exclusion_reasons": ["no_dated_own_active_event"]},
        ],
    )
    table = listing_outcomes.build(
        {"page": str(page), "api": api_records.CRAWL}
    ).set_index("listing_id")
    seven, eight, nine = (table.loc[i] for i in ("7", "8", "9"))
    assert (seven.status, seven.final_ask, seven.n_cuts, seven.days_listed) == (
        "RENTED",
        2900,
        1,
        8,
    )
    assert seven.collected_at == OCT_1 + 10 * DAY
    assert (eight.status, eight.days_listed, eight.collected_at) == (
        "RENTED",
        14,
        OCT_1 + 20 * DAY,
    )
    assert (nine.status, nine.still_listed, nine.collected_at) == (
        "ACTIVE",
        True,
        OCT_1 + 2 * DAY,
    )
