import json

import pandas as pd
import pytest

from rentfrontier import api_records, listing_outcomes

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
    n = len(listing_outcomes.CRAWLS)
    assert listing_outcomes.parse(["--crawl", "page", "--crawl", "records"]) == (
        {**listing_outcomes.CRAWLS, f"crawl-{n}": "records"},
        "",
    )
    with pytest.raises(SystemExit):
        listing_outcomes.main(["--tag", "api"])
