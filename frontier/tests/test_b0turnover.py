import datetime as dt
import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0coop
from rentfrontier import b0turnover as bt
from rentfrontier.b0data import sha256

DAY = dt.date(2022, 1, 1)
# (building, unit_id, price day, on_day, other ads opened in the 730 days before the price
# day), with days as offsets from DAY and None for a missing unit_id or on_day.
ROWS = [
    ("b1", "1", 0, 0, 6),
    # Opened the day before row 0's price day: counted for row 0.
    ("b1", "2", -1, -1, 7),
    # Opened exactly 730 days before row 0's price day: counted for row 0.
    ("b1", "3", -730, -730, 1),
    # Opened 731 days before: not counted for row 0.
    ("b1", "4", -731, -731, 0),
    # Opened on row 0's price day: not counted for row 0.
    ("b1", "5", 0, 0, 7),
    # Row 0's own unit: not counted for row 0, counted for the others in b1.
    ("b1", "1", -10, -10, 6),
    # Unit "2" of another building: neither counted for b1 nor taken for b1's unit "2".
    ("b2", "2", -5, -5, 0),
    # Priced after row 0 but opened before it: counted for row 0.
    ("b1", "6", 100, -20, 7),
    # on_day after the price day, so the row opens on its price day.
    ("b1", "7", -50, 5, 4),
    # Rows without a unit_id are units of their own; the second opened before its price day,
    # so its own row sits in its window and is taken out.
    ("b1", None, -100, None, 3),
    ("b1", None, -200, -210, 2),
    ("nolot", "8", 0, 0, 0),
]

# (release, published), with 22v2 undated as in City Planning's archive. Each release can be
# read from a week after it is published.
RELEASES = [
    ("19v1", "2019-01-31"),
    ("20v1", "2020-01-05"),
    ("21v1", "2021-01-31"),
    ("22v2", None),
]
# (bbl, unitsres in each release in RELEASES' order), None where the lot is missing from it.
LOTS = [
    ("1000010001", ["00010", "00012", "00012", "00040"]),
    ("1000010002", ["00006", "00006", "", "00007"]),
    ("1000010003", [None, None, "00030", "00030"]),
    ("1000010004", ["00000", "00000", "00000", "00000"]),
]
REGISTRY = {
    "b1": "1000010001",
    "b2": "1000010002",
    "late": "1000010003",
    "zero": "1000010004",
}
# Units of ROWS' rows, by the release out at their price month: rows priced in December 2019
# or January 2020 read 19v1, since 20v1 is out from 2020-01-12; the rest read 21v1, never the
# undated 22v2.
ROW_UNITS = [12, 12, 10, 10, 12, 12, None, 12, 12, 12, 12, None]
# (building, price_at, release read, units, status)
UNIT_ROWS = [
    ("b1", "2019-06-10", "19v1", 10, "read"),
    ("b1", "2020-01-20", "19v1", 10, "read"),
    ("b1", "2020-02-03", "20v1", 12, "read"),
    # 22v2 has no publication date, so a 2023 row reads 21v1.
    ("b1", "2023-03-01", "21v1", 12, "read"),
    ("b2", "2019-05-01", "19v1", 6, "read"),
    ("b2", "2021-03-01", "21v1", None, "no units"),
    # The lot first appears in 21v1, which a row priced in 2020 never reads.
    ("late", "2020-06-01", "20v1", None, "lot not in release"),
    ("late", "2021-03-01", "21v1", 30, "read"),
    ("zero", "2020-06-01", "20v1", 0, "read"),
    ("nolot", "2020-06-01", "20v1", None, "no lot"),
    ("b1", "2018-12-01", None, None, "no release"),
]


def day(offset):
    return DAY + dt.timedelta(days=offset)


def frame(rows=ROWS):
    return pd.DataFrame(
        {
            "listing_id": [str(100 + i) for i in range(len(rows))],
            "building": [r[0] for r in rows],
            "unit_id": [r[1] for r in rows],
            "price_at": pd.to_datetime(
                [f"{day(r[2]).isoformat()}T12:00" for r in rows], utc=True
            ),
            "latest_ask": [3000.0 + i for i in range(len(rows))],
        }
    )


def ads_table(rows=ROWS):
    on = [None if r[3] is None else day(r[3]) for r in rows]
    return pa.table(
        {
            "listing_id": pa.array([str(100 + i) for i in range(len(rows))] + ["999"]),
            "on_day": pa.array([*on, dt.date(2020, 1, 1)], pa.date32()),
        }
    )


def release_table():
    lines = [
        (release, bbl, units[k], published)
        for bbl, units in LOTS
        for k, (release, published) in enumerate(RELEASES)
        if units[k] is not None
    ]
    return pa.table(
        {
            "bbl": pa.array([x[1] for x in lines], pa.large_string()),
            "unitsres": pa.array([x[2] for x in lines], pa.large_string()),
            "release": pa.array([x[0] for x in lines], pa.large_string()),
            "published": pa.array([x[3] for x in lines], pa.large_string()),
        }
    )


@pytest.fixture
def files(tmp_path):
    ads = tmp_path / "ads.parquet"
    pq.write_table(ads_table(), ads)
    releases = tmp_path / "plutoreleases.parquet"
    pq.write_table(release_table(), releases)
    registry = tmp_path / "registry.parquet"
    pd.DataFrame(
        {"building": list(REGISTRY), "bbl": list(REGISTRY.values())}
    ).to_parquet(registry)
    src = tmp_path / "src"
    src.mkdir()
    frame().to_parquet(src / "rows.parquet")
    frame().iloc[:0].to_parquet(src / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"ads": {"path": str(ads), "sha256": sha256(ads)}},
    }
    (src / "manifest.json").write_text(json.dumps(manifest))
    return src, ads, registry, releases


def opened(ads):
    f = frame()
    return bt.opening_days(f, bt.read_on_days(ads, set(f.listing_id)))


def brute_force(f, opened):
    """The count by a loop over every pair of rows."""
    price_day = bt.days(f.price_at)
    unit = bt.unit_keys(f)
    building = f.building.to_numpy()
    return np.array(
        [
            sum(
                building[j] == building[i]
                and unit[j] != unit[i]
                and price_day[i] - bt.WINDOW_DAYS <= opened[j] < price_day[i]
                for j in range(len(f))
            )
            for i in range(len(f))
        ]
    )


def test_counts_other_units_in_the_window_before_the_price_day(files):
    src, ads, registry, releases = files
    count = bt.other_ads(frame(), opened(ads))
    assert list(count) == [r[4] for r in ROWS]


def test_the_window_holds_730_days_and_ends_the_day_before(files):
    src, ads, registry, releases = files
    o = opened(ads)
    price_day = bt.days(frame().price_at)
    # Rows 2 and 3 opened 730 and 731 days before row 0's price day, row 4 on it.
    assert price_day[0] - o[2] == bt.WINDOW_DAYS
    assert price_day[0] - o[3] == bt.WINDOW_DAYS + 1
    assert o[4] == price_day[0]
    # Row 8's on_day comes after its price day, and row 9 has none.
    assert o[8] == price_day[8]
    assert o[9] == price_day[9]
    assert o[10] == price_day[10] - 10


def test_the_count_matches_a_loop_over_pairs(files):
    src, ads, registry, releases = files
    rng = np.random.default_rng(0)
    n = 400
    f = pd.DataFrame(
        {
            "listing_id": [str(i) for i in range(n)],
            "building": rng.choice(["a", "b", "c"], n),
            "unit_id": rng.choice(["1", "2", "3", "4", "5", None], n),
            "price_at": pd.to_datetime("2018-01-01", utc=True)
            + pd.to_timedelta(rng.integers(0, 2000, n), unit="D"),
        }
    )
    o = bt.days(f.price_at) - rng.integers(0, 60, n)
    assert (bt.other_ads(f, o) == brute_force(f, o)).all()


def test_the_same_unit_id_in_two_buildings_is_two_units():
    f = frame()
    keys = bt.unit_keys(f)
    assert keys[1] != keys[6]
    assert keys[0] == keys[5]
    assert keys[9] == "row:109" and keys[10] == "row:110"


def test_each_row_reads_the_units_of_the_release_out_at_its_month(files):
    src, ads, registry, releases = files
    lots = pd.Series(REGISTRY)
    f = pd.DataFrame(
        {
            "building": [r[0] for r in UNIT_ROWS],
            "price_at": pd.to_datetime([r[1] for r in UNIT_ROWS], utc=True),
        }
    )
    found = bt.units_asof(
        f, lots, b0coop.read_releases(releases, set(lots.values), "unitsres")
    )
    assert list(found.release) == [r[2] for r in UNIT_ROWS]
    assert list(found.status) == [r[4] for r in UNIT_ROWS]
    want = np.array([np.nan if r[3] is None else r[3] for r in UNIT_ROWS], float)
    np.testing.assert_array_equal(found.units.to_numpy(), want)


def test_a_later_release_is_never_read(files):
    src, ads, registry, releases = files
    lots = pd.Series(REGISTRY)
    table = b0coop.read_releases(releases, set(lots.values), "unitsres")
    f = frame()
    found = bt.units_asof(f, lots, table)
    published = pd.to_datetime(
        table.dropna(subset=["published"])
        .drop_duplicates("release")
        .set_index("release")
        .published
    )
    read = found.release.notna().to_numpy()
    month = b0coop.months(f.price_at)
    usable = published.reindex(found.release[read]).to_numpy() + np.timedelta64(
        bt.PLUTO_RELEASE_BUFFER_DAYS, "D"
    )
    assert (usable <= month[read]).all()
    assert "22v2" not in set(found.release.dropna())
    # Row 7 is priced in April 2022, after 22v2 came out, and reads 21v1's 12, not 40.
    assert found.units[7] == 12


def test_a_release_out_a_week_before_the_month_starts_is_read_that_month():
    lots = pd.Series({"b1": "1000010001"})
    # 21v2 comes out exactly `PLUTO_RELEASE_BUFFER_DAYS` days before 2021-06-01, so it is
    # usable on that day, and a row priced in June reads it.
    published = dt.date(2021, 6, 1) - dt.timedelta(days=bt.PLUTO_RELEASE_BUFFER_DAYS)
    releases = pd.DataFrame(
        {
            "release": ["21v1", "21v2"],
            "bbl": ["1000010001", "1000010001"],
            "unitsres": ["00012", "00015"],
            "published": ["2021-01-31", published.isoformat()],
        }
    )
    f = pd.DataFrame(
        {
            "building": ["b1", "b1", "b1"],
            "price_at": pd.to_datetime(
                ["2021-05-31T23:59", "2021-06-01T00:00", "2021-06-30T12:00"], utc=True
            ),
        }
    )
    found = bt.units_asof(f, lots, releases)
    assert list(found.release) == ["21v1", "21v2", "21v2"]
    assert list(found.units) == [12, 15, 15]


def test_the_dataset_gets_both_columns_and_a_manifest_entry(files, tmp_path):
    src, ads, registry, releases = files
    before = {f.name: sha256(f) for f in src.iterdir()}
    assert set(before) == {"rows.parquet", "set_aside.parquet", "manifest.json"}
    out = tmp_path / "out"
    manifest = bt.turnover(src, out, registry=registry, release_file=releases)
    rows = pd.read_parquet(out / "rows.parquet")
    assert list(rows.listing_id) == list(frame().listing_id)
    assert list(rows.columns) == [*frame().columns, bt.COUNT, bt.UNITS]
    assert bt.COUNT == "bld_opened_730" and bt.UNITS == "res_units_asof"
    assert rows[bt.COUNT].dtype == np.int32
    assert list(rows[bt.COUNT]) == [r[4] for r in ROWS]
    want = np.array([np.nan if u is None else u for u in ROW_UNITS], float)
    np.testing.assert_array_equal(rows[bt.UNITS].to_numpy(), want)
    # SRC's files stay as they were, and its other files are copied as they are.
    assert {f.name: sha256(f) for f in src.iterdir()} == before
    assert sha256(out / "set_aside.parquet") == before["set_aside.parquet"]
    entry = manifest["turnover"]
    assert entry["source"] == str(src)
    assert entry["source_rows_sha256"] == "abc"
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert entry["ads"] == {"path": str(ads), "sha256": sha256(ads)}
    assert entry["registry"] == {"path": str(registry), "sha256": sha256(registry)}
    assert entry["releases"] == {"path": str(releases), "sha256": sha256(releases)}
    assert set(entry["rule"]) == {bt.COUNT, bt.UNITS}
    assert (entry["window_days"], entry["buffer_days"]) == (730, 7)
    assert entry["rows"] == len(ROWS)
    assert entry["rows_by_status"] == {
        "read": 10,
        "no lot": 1,
        "no release": 0,
        "lot not in release": 0,
        "no units": 1,
    }
    assert entry["releases_read"] == {"19v1": 2, "21v1": 10}
    assert entry["rows_count_zero"] == 3
    assert entry["rows_units_zero"] == 0
    assert json.loads((out / "manifest.json").read_text()) == json.loads(
        json.dumps(manifest, default=str)
    )


def test_an_existing_out_is_refused(files, tmp_path):
    src, ads, registry, releases = files
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileExistsError):
        bt.turnover(src, out, registry=registry, release_file=releases)


def test_a_changed_ads_file_is_refused(files, tmp_path):
    src, ads, registry, releases = files
    pq.write_table(ads_table(ROWS[:-1]), ads)
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        bt.turnover(src, out, registry=registry, release_file=releases)
    assert not out.exists()
