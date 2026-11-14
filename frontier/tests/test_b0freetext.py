import json
import math

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0freetext as ft
from rentfrontier.b0data import sha256

NAN = math.nan
WEEK = 12 / 52
DAY = 12 / 365


@pytest.mark.parametrize(
    "text, months, lease, kind",
    [
        # Counts in numbers and words.
        (
            "Net effective rent based on 1 month free on a 12 month lease",
            1,
            12,
            "exact",
        ),
        ("TWO MONTHS FREE on a 14-month lease!", 2, 14, "exact"),
        ("Offering one (1) month free rent", 1, NAN, "exact"),
        ("2 FREE MONTHS with a 13 month lease", 2, 13, "exact"),
        ("Rent reflects a month free", 1, NAN, "exact"),
        ("Net rent shown with a free month on an 18 month term", 1, 18, "exact"),
        ("Free rent for the first 2 months", 2, NAN, "exact"),
        ("Rent concession of 1.5 months", 1.5, NAN, "exact"),
        ("Price is based off 1 month abatement on a 12 month lease", 1, 12, "exact"),
        ("421a tax abatement, 15 year abatement", NAN, NAN, None),
        ("Two complimentary months on a 16 month lease", 2, 16, "exact"),
        # Halves.
        ("1.5 months free on a 13 month lease", 1.5, 13, "exact"),
        ("1. 5 months free on a 13 month lease", 1.5, 13, "exact"),
        ("one and a half months free", 1.5, NAN, "exact"),
        ("a month and a half free on a one-year lease", 1.5, 12, "exact"),
        ("1 1/2 months free", 1.5, NAN, "exact"),
        ("half a month free", 0.5, NAN, "exact"),
        ("1/2 month free rent", 0.5, NAN, "exact"),
        ("Net effective on a 12-month lease with a 1/2 MONTH FREE", 0.5, 12, "exact"),
        ("Paying 1 month OP and .50 Free month on a 12 month term", 0.5, 12, "exact"),
        ("based on a gross rent of $3057.00 and 2.66 Months Free", 2.66, NAN, "exact"),
        # Weeks and days, unrounded.
        ("8 weeks free on a 12 month lease", 8 * WEEK, 12, "exact"),
        ("2 weeks free", 2 * WEEK, NAN, "exact"),
        ("30 days free rent", 30 * DAY, NAN, "exact"),
        # A month named by its place in the lease.
        ("First month free!", 1, NAN, "exact"),
        ("The last month is free on a 13 month lease", 1, 13, "exact"),
        ("13th month free", 1, NAN, "exact"),
        ("First and last month free", 2, NAN, "exact"),
        ("on a 14 month lease, with 13th and 14th month free", 2, 14, "exact"),
        ("FIRST TWO MONTHS OF LEASE AND LAST MONTH ARE FREE", 3, NAN, "exact"),
        ("Pay the first 11 months and the last month will be free", 1, NAN, "exact"),
        ("12 MONTH FREE on a 12 month lease", 1, 12, "exact"),
        ("13 months for the price of 12", 1, NAN, "exact"),
        # The text states the concession and leaves it out of the price.
        ("1 month free, not reflected in the price", 1, NAN, "exact"),
        ("Gross rent listed does not include 2 months free", 2, NAN, "exact"),
        # Conditions and "up to".
        ("1 month free if you sign by March 1", 1, NAN, "conditional"),
        (
            "2 months free for qualified applicants on a 12 month lease",
            2,
            12,
            "conditional",
        ),
        ("One month free on select units", 1, NAN, "conditional"),
        ("2 months free on 12 month leases signed before June", 2, 12, "conditional"),
        ("Up to 2 months free", 2, NAN, "up_to"),
        ("Offering 1-2 months free", 2, NAN, "up_to"),
        ("Limited time: 1 month free", 1, NAN, "exact"),
        # Denials, and texts with no count.
        ("No concessions, no fee", 0, NAN, "none"),
        ("Real rent, no free months", 0, NAN, "none"),
        (
            "1 month free on an 18 month lease (price does not reflect free month)",
            1,
            18,
            "exact",
        ),
        ("Net effective rent advertised", NAN, NAN, "unstated"),
        ("Not net effective, the gross rent", NAN, NAN, None),
        ("Feel free to call me, heat included", NAN, NAN, None),
        # Things given free that are not rent.
        ("6 months free parking", NAN, NAN, None),
        ("Gym membership: 3 months free", NAN, NAN, None),
        ("6 months of free weekly cleaning", NAN, NAN, None),
        ("6 month free on large storage unit", NAN, NAN, None),
        ("1 year free WiFi", NAN, NAN, None),
        ("Broker fee free, no fee apartment", NAN, NAN, None),
        ("Parking $200/month - 6 months free", NAN, NAN, None),
        ("FREE RENT FOR 12 MONTH LEASE", NAN, NAN, "unstated"),
        ("one month free plus free gym", 1, NAN, "exact"),
        ("Month-to-month free of charge", NAN, NAN, None),
        (None, NAN, NAN, None),
    ],
)
def test_parse(text, months, lease, kind):
    got = ft.parse(text)
    assert got[0] == pytest.approx(months, nan_ok=True)
    assert got[1] == pytest.approx(lease, nan_ok=True)
    assert got[2] == kind


def test_several_offers_choose_the_first_exact_one():
    text = (
        "Up to 3 months free on select units. 2 months free on a 12 month lease or "
        "3 months free when you sign a 24-month lease."
    )
    offers = ft.statements(text)
    assert [(o.months, o.kind) for o in offers] == [
        (3, "up_to"),
        (2, "exact"),
        (3, "exact"),
    ]
    # The first offer's sentence states no lease; each later offer takes the lease after it.
    assert math.isnan(offers[0].lease) and [o.lease for o in offers[1:]] == [12, 24]
    assert ft.parse(text) == (2, 12, "exact", 2)


def test_a_chosen_offer_with_no_lease_takes_a_same_count_offers_lease():
    text = "Net effective based on 2 months free. Offering 2 months free on a 16 month lease."
    assert ft.parse(text) == (2, 16, "exact", 1)


def test_the_offer_tied_to_the_price_comes_first():
    text = (
        "NO FEE AND 1.5 Months Free on 12-15 Month Lease!! *Net effective rent advertised "
        "based on 1 month free on the 12 month lease option."
    )
    assert [o.basis for o in ft.statements(text)] == [False, True]
    assert ft.parse(text) == (1, 12, "exact", 2)
    text = (
        "Advertised rent is with 8 weeks free on a 12-month lease. For 24-month leases, "
        "management is offering 12 weeks free, net effective $3,100."
    )
    assert [o.basis for o in ft.statements(text)] == [True, False]
    assert ft.parse(text)[0] == pytest.approx(8 * WEEK)
    text = "2 months free on 24 months. 1 MONTH FREE NET EFFECTIVE RENT LISTED"
    assert ft.parse(text)[0] == 1
    # A sentence saying the price leaves the offer out ties nothing to it.
    text = (
        "2 months free. 1 month free on a 24 month lease, not reflected in the price."
    )
    assert [o.basis for o in ft.statements(text)] == [False, False]
    assert ft.parse(text)[0] == 2


def test_a_conditional_offer_yields_to_an_exact_one():
    text = "2 months free if you sign by Friday! Otherwise 1 month free."
    months, _, kind, n = ft.parse(text)
    assert (months, kind, n) == (1, "exact", 2)


# (listing, collected_at, last_collected_at, description), one record each.
RECORDS = [
    # Listing 5's later record comes first; its earlier record offers more.
    ("5", 4.0, 4.0, "Sunny one bedroom. 1 month free on a 12 month lease."),
    ("1", 1.0, 1.0, "Two months free on a 14 month lease. Net effective rent shown."),
    ("2", 1.0, 1.0, "Up to 6 weeks free for qualified applicants."),
    ("3", 1.0, 1.0, "No concessions. The gross rent is shown."),
    ("4", 1.0, 1.0, "Net effective rent advertised, call for details."),
    ("5", 2.0, 2.0, "Sunny one bedroom. 3 months free on a 24 month lease."),
    ("6", 1.0, 1.0, "A quiet studio with free parking and a gym."),
    # The later record of listing 7 is chosen by last_collected_at.
    ("7", 3.0, 3.0, "1 month free"),
    ("7", 2.0, 5.0, "First and last month free if you move in by June 1"),
    ("8", 1.0, 1.0, None),
    # A record with neither time is no listing's latest.
    ("9", None, None, "2 months free"),
]


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": [int(r[0]) for r in RECORDS],
                "collected_at": [r[1] for r in RECORDS],
                "last_collected_at": [r[2] for r in RECORDS],
                "raw_listing_json": [
                    json.dumps({} if r[3] is None else {"description": r[3]})
                    for r in RECORDS
                ],
            }
        ),
        path,
        row_group_size=4,
    )
    rows = pd.DataFrame(
        {
            "listing_id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "latest_ask": [3000.0 + i for i in range(10)],
        }
    )
    d = tmp_path / "src"
    d.mkdir()
    rows.to_parquet(d / "rows.parquet")
    rows.iloc[:0].to_parquet(d / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"records": {"path": str(path), "sha256": sha256(path)}},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def test_free_text_adds_the_columns_and_leaves_src_alone(src, tmp_path):
    hashes = {f.name: sha256(f) for f in src.iterdir()}
    out = tmp_path / "out"
    manifest = ft.free_text(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    before = pd.read_parquet(src / "rows.parquet")
    added = ["months_free_text", "free_lease_months", "free_text_kind"]
    pd.testing.assert_frame_equal(rows.drop(columns=added), before)
    got = {
        lid: (m, lease, None if pd.isna(k) else k)
        for lid, m, lease, k in zip(rows.listing_id, *(rows[c] for c in added))
    }
    expect = {
        1: (2, 14, "exact"),
        2: (6 * WEEK, NAN, "up_to"),
        3: (0, NAN, "none"),
        4: (NAN, NAN, "unstated"),
        5: (1, 12, "exact"),  # its latest record
        6: (NAN, NAN, None),  # parking is not rent
        7: (2, NAN, "conditional"),
        8: (NAN, NAN, None),  # no description
        9: (NAN, NAN, None),  # its only record has no time
        10: (NAN, NAN, None),  # no record
    }
    for lid, (m, lease, kind) in expect.items():
        assert got[lid][0] == pytest.approx(m, nan_ok=True), lid
        assert got[lid][1] == pytest.approx(lease, nan_ok=True), lid
        assert got[lid][2] == kind, lid
    assert str(rows.free_text_kind.dtype) == "string"
    assert (out / "set_aside.parquet").exists()
    entry = manifest["free_text"]
    assert entry["source"] == str(src) and entry["source_rows_sha256"] == "abc"
    assert entry["listings_read"] == 8
    assert entry["rows_by_kind"] == {
        "exact": 2,
        "up_to": 1,
        "conditional": 1,
        "none": 1,
        "unstated": 1,
    }
    assert entry["rows_with_months"] == 4
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert json.loads((out / "manifest.json").read_text()) == json.loads(
        json.dumps(manifest, default=str)
    )
    assert {f.name: sha256(f) for f in src.iterdir()} == hashes
    with pytest.raises(FileExistsError):
        ft.free_text(src, out)


def test_free_text_refuses_records_that_changed(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        ft.free_text(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()
