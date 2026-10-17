import json

import numpy as np
import pandas as pd

from rentfrontier import features, lister, run


def test_record_lister_reads_name_licence_and_source_type():
    raw = json.dumps(
        {
            "legacy": {
                "sourceGroupLabel": "Corcoran",
                "license": {"licenseType": "Limited Liability Broker"},
            },
            "listingSource": {"sourceType": "PARTNER"},
            "pricing": {"price": 4000},
        }
    )
    assert lister.record_lister(raw) == {
        "lister": "Corcoran",
        "licensed": True,
        "source_type": "PARTNER",
    }
    assert lister.record_lister("{}") == {
        "lister": None,
        "licensed": False,
        "source_type": None,
    }


def test_kind_puts_owner_then_brokerage_names_first():
    names = pd.Series(
        ["Compass", "Related Rentals", "Mirador Real Estate", "AJ Clarke", None, "X"]
    )
    source = pd.Series(["PARTNER", "FEED", "PARTNER", "PARTNER", None, "OWNER"])
    assert lister.kind(names, source).tolist() == [
        "brokerage",
        "management",
        "brokerage",
        "other",
        "other",
        "owner",
    ]


def test_earlier_counts_only_earlier_days_in_the_same_building():
    d = pd.DataFrame(
        {
            "listing_id": list("abcdef"),
            "building": ["b1", "b1", "b1", "b1", "b2", "b1"],
            "lister": ["A", "A", "B", "A", "A", None],
            "listed_at": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-02-01",
                    "2020-02-01",
                    "2020-03-01",
                    "2020-03-01",
                    "2020-04-01",
                ],
                utc=True,
            ),
        },
        index=[10, 11, 12, 13, 14, 15],
    )
    got = lister.earlier_counts(d)
    # b and c share a day, so neither counts the other.
    assert got.earlier.tolist() == [0, 1, 1, 3, 0, 4]
    assert got.earlier_same.tolist() == [0, 1, 0, 2, 0, 0]
    assert list(got.index) == [10, 11, 12, 13, 14, 15]


def test_own_agent_needs_half_of_five_earlier():
    earlier = pd.Series([4, 5, 5, 10])
    same = pd.Series([4, 3, 2, 5])
    assert lister.own_agent(earlier, same).tolist() == [
        "few_earlier",
        "own",
        "outside",
        "own",
    ]


def test_lister_v1_adds_kind_and_agent_against_brokerage_and_outside(
    monkeypatch, tmp_path
):
    snap = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3"],
            "kind": ["management", "brokerage", "owner"],
            "earlier": pd.array([9, 2, 6], dtype="Int64"),
            "earlier_same": pd.array([8, 2, 1], dtype="Int64"),
        }
    )
    path = tmp_path / "lister.parquet"
    snap.to_parquet(path)
    monkeypatch.setattr(features, "LISTER_FILE", str(path))
    frame = pd.DataFrame({"source_listing_id": [1, 2, 3, 4]})
    base = features.Features("b", [], [], np.zeros((4, 0)), np.zeros(0))
    monkeypatch.setitem(features.FEATURE_SETS, "toy", lambda f, t: base)
    got = features.lister_v1(frame, np.ones(4, bool), id="t", base="toy")
    cols = dict(zip(got.names, got.values.T.tolist()))
    # Listing 4 is missing: other kind, fewer than five earlier.
    assert cols == {
        "lister=management": [1, 0, 0, 0],
        "lister=other": [0, 0, 0, 1],
        "lister=owner": [0, 0, 1, 0],
        "building agent=few_earlier": [0, 1, 0, 1],
        "building agent=own": [1, 0, 0, 0],
    }
    assert got.groups == ["lister"] * 3 + ["building agent"] * 2


def test_nostuy_lister_set_is_registered_and_recorded(monkeypatch):
    f = features.FEATURE_SETS["nb6-nostuy-lister-v1"]
    assert f.func is features.lister_v1
    assert f.keywords == {"id": "nb6-nostuy-lister-v1", "base": "nb6-nostuy-v1"}
    assert "nb6-nostuy-lister-v1" in features.LISTER
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    sources = run.feature_sources("nb6-nostuy-lister-v1")
    assert sources["lister"]["path"] == features.LISTER_FILE
    assert "lister" not in run.feature_sources("nb6-nostuy-v1")


def history_record(lister_name, episodes):
    return {
        "id": "7",
        "legacy": {"sourceGroupLabel": lister_name},
        "propertyDetails": {},
        "propertyHistory": episodes,
    }


def test_record_first_listed_matches_the_granular_event_mentions():
    """A record's earliest listed day is the earliest day the granular parser gives an own
    ACTIVE rental event mention: an episode named by `listingId` or `id`, or by neither, and
    events with another status, no date or no dict left out."""
    from apartments.graphql_listing import listing_body, parse_capture

    episodes = [
        {
            "listingId": 9,
            "rentalEventsOfInterest": [{"status": "ACTIVE", "date": "2024-01-01"}],
        },
        {
            "id": "7",
            "rentalEventsOfInterest": [{"status": "ACTIVE", "date": "2026-03-02"}],
        },
        {
            "listingId": "7",
            "rentalEventsOfInterest": [
                {"status": "PENDING", "date": "2025-01-01"},
                {"status": "ACTIVE", "date": None},
                "ACTIVE",
                {"status": "ACTIVE", "date": "2026-03-01"},
            ],
        },
        {"rentalEventsOfInterest": [{"status": "ACTIVE", "date": "2026-04-01"}]},
        {"listingId": "7", "rentalEventsOfInterest": None},
        "an episode",
    ]
    for history in (episodes, episodes[3:], episodes[4:], None, {"a": 1}):
        record = history_record("A", history)
        building = {
            "id": "1",
            "slug": "a-building",
            "page": "https://streeteasy.com/building/a",
        }
        _, events = parse_capture(
            listing_body(7, building, record), "https://streeteasy.com/rental/7"
        )
        mentions = pd.DataFrame(
            events,
            columns=[
                "listing_id",
                "event_listing_id",
                "event_category",
                "status",
                "event_date",
            ],
        )
        own = mentions[
            mentions.listing_id.eq(mentions.event_listing_id)
            & mentions.event_category.eq("rental")
            & mentions.status.eq("ACTIVE")
        ].event_date.dropna()
        expected = own.min() if len(own) else None
        assert lister.record_first_listed(json.dumps(record), "7") == expected
    assert (
        lister.record_first_listed(json.dumps(history_record("A", episodes)), "7")
        == "2026-03-01"
    )


def test_lister_reads_the_records_file_and_the_ads_files_buildings(records_catalog):
    """Listing 7's first record has the later last fetch, so its lister comes from it, while its
    listed day is the earliest over both records. Listing 8 in the same building of the ads
    file was listed earlier by the same lister."""

    def own(day):
        return [
            {
                "listingId": "7",
                "rentalEventsOfInterest": [{"status": "ACTIVE", "date": day}],
            }
        ]

    eight = history_record(
        "A",
        [
            {
                "listingId": "8",
                "rentalEventsOfInterest": [{"status": "ACTIVE", "date": "2026-07-01"}],
            }
        ],
    )
    eight["id"] = "8"
    records_catalog(
        [
            {
                "listing_id": 7,
                "collected_at": 1.0,
                "last_collected_at": 9.0,
                "record": history_record("A", own("2026-09-01")),
            },
            {
                "listing_id": 7,
                "collected_at": 2.0,
                "last_collected_at": 3.0,
                "record": history_record("B", own("2026-08-15")),
            },
            {"listing_id": 8, "collected_at": 1.0, "record": eight},
        ],
        ads=[
            {"listing_id": "7", "building": "b"},
            {"listing_id": "8", "building": "b"},
        ],
    )
    table = lister.build({"api": lister.api_records.CRAWL}).set_index("listing_id")
    assert table.loc["7", "lister"] == "A"
    assert table.loc["7", "building"] == "b"
    assert table.loc["7", "listed_at"] == pd.Timestamp("2026-08-15", tz="UTC")
    assert (table.loc["7", "earlier"], table.loc["7", "earlier_same"]) == (1, 1)
    assert "collected_at" not in table


def test_main_lists_the_records_and_ads_files(records_catalog, tmp_path, monkeypatch):
    """`--crawl records` reads both files of the catalog's newest line, and provenance.json gives
    their paths and SHA-256. A tag without a crawl stops."""
    import pytest

    line = records_catalog(
        [{"listing_id": 7, "collected_at": 1.0, "record": history_record("A", [])}],
        ads=[{"listing_id": "7", "building": "b"}],
    )
    monkeypatch.setattr(lister, "EXTERNAL_ROOT", tmp_path / "external")
    monkeypatch.setattr(
        lister, "_git", lambda *a: "" if a[0] == "status" else "abc1234def"
    )
    lister.main(["--crawl", "records", "--tag", "api"])
    (prov,) = (tmp_path / "external").glob("lister/*-abc1234-api/provenance.json")
    sources = json.loads(prov.read_text())["sources"]
    assert sources == {
        "crawl": {
            "path": str(tmp_path / line["records"]["path"]),
            "sha256": line["records"]["sha256"],
        },
        "ads_file": {
            "path": str(tmp_path / line["ads_file"]["path"]),
            "sha256": line["ads_file"]["sha256"],
        },
    }
    with pytest.raises(SystemExit):
        lister.main(["--tag", "api"])
