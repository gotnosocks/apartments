import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0coop
from rentfrontier.b0data import sha256

# (release, published), with 22v2 undated as in City Planning's archive. Each release can be
# read from a week after it is published.
RELEASES = [
    ("19v1", "2019-01-31"),
    ("20v1", "2020-01-05"),
    ("21v1", "2021-01-31"),
    ("22v2", None),
]
# (bbl, class in each release in RELEASES' order), None where the lot is missing from it.
LOTS = [
    ("1000010001", ["D7", "D4", "D4", "R4"]),
    ("1000010002", ["C6", "R4", "R4", "R4"]),
    ("1000010003", [None, None, "C6", "C6"]),
    ("1000010004", ["", "D7", "D7", "D7"]),
]
REGISTRY = {
    "coop-a": "1000010001",
    "condo-b": "1000010002",
    "late": "1000010003",
    "blank": "1000010004",
}
# (building, unit_id, price_at, release read, coop, condo, status)
ROWS = [
    ("coop-a", "1", "2019-06-10", "19v1", False, False, "read"),
    # 20v1 is out from 2020-01-12, after January's first day.
    ("coop-a", "1", "2020-01-20", "19v1", False, False, "read"),
    ("coop-a", "2", "2020-02-03", "20v1", True, False, "read"),
    # 22v2 has no publication date, so a 2023 row reads 21v1.
    ("coop-a", "2", "2023-03-01", "21v1", True, False, "read"),
    ("condo-b", "3", "2019-05-01", "19v1", True, False, "read"),
    ("condo-b", "3", "2020-03-01", "20v1", False, True, "read"),
    # The lot first appears in 21v1, which a row priced in 2020 never reads.
    ("late", None, "2020-06-01", "20v1", False, False, "lot not in release"),
    ("late", "4", "2021-03-01", "21v1", True, False, "read"),
    ("blank", "5", "2019-06-01", "19v1", False, False, "no class"),
    ("nolot", "6", "2020-06-01", "20v1", False, False, "no lot"),
    ("coop-a", "1", "2018-12-01", None, False, False, "no release"),
]


def frame():
    return pd.DataFrame(
        {
            "listing_id": [str(i) for i in range(len(ROWS))],
            "building": [r[0] for r in ROWS],
            "unit_id": [r[1] for r in ROWS],
            "price_at": pd.to_datetime([r[2] for r in ROWS], utc=True),
            "latest_ask": [3000.0 + i for i in range(len(ROWS))],
        }
    )


def release_table():
    lines = [
        (release, bbl, cls[k], published)
        for bbl, cls in LOTS
        for k, (release, published) in enumerate(RELEASES)
        if cls[k] is not None
    ]
    return pa.table(
        {
            "bbl": pa.array([x[1] for x in lines], pa.large_string()),
            "bldgclass": pa.array([x[2] for x in lines], pa.large_string()),
            "release": pa.array([x[0] for x in lines], pa.large_string()),
            "published": pa.array([x[3] for x in lines], pa.large_string()),
        }
    )


@pytest.fixture
def files(tmp_path):
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
    (src / "manifest.json").write_text(json.dumps({"rows_sha256": "abc"}))
    return src, registry, releases


def test_tenure_sorts_classes_as_building_attrs_does():
    cls = ["R4", "R9", "RR", "C6", "C8", "D0", "D4", "CB", "DB", "C7", "D7", "A8", ""]
    condo, coop = b0coop.tenure(np.array([*cls, None], dtype=object))
    assert list(condo) == [True] * 3 + [False] * 11
    assert list(coop) == [False] * 3 + [True] * 4 + [False] * 7


def test_month_is_the_first_day_in_utc():
    at = pd.Series(pd.to_datetime(["2020-01-31T23:30", "2020-02-01T00:10"], utc=True))
    assert list(b0coop.months(at)) == list(
        pd.to_datetime(["2020-01-01", "2020-02-01"]).to_numpy()
    )


def test_each_row_reads_the_release_out_at_its_month(files):
    src, registry, releases = files
    lots = pd.Series(REGISTRY)
    found = b0coop.classes(
        frame(), lots, b0coop.read_releases(releases, set(lots.values))
    )
    assert list(found.release) == [r[3] for r in ROWS]
    assert list(found.status) == [r[6] for r in ROWS]
    condo, coop = b0coop.tenure(found.bldgclass.to_numpy())
    assert list(coop) == [r[4] for r in ROWS]
    assert list(condo) == [r[5] for r in ROWS]


def test_a_later_release_is_never_read(files):
    src, registry, releases = files
    lots = pd.Series(REGISTRY)
    table = b0coop.read_releases(releases, set(lots.values))
    found = b0coop.classes(frame(), lots, table)
    published = pd.to_datetime(
        table.dropna(subset=["published"])
        .drop_duplicates("release")
        .set_index("release")
        .published
    )
    read = found.release.notna().to_numpy()
    month = b0coop.months(frame().price_at)
    usable = published.reindex(found.release[read]).to_numpy() + np.timedelta64(
        b0coop.PLUTO_RELEASE_BUFFER_DAYS, "D"
    )
    assert (usable <= month[read]).all()
    assert "22v2" not in set(found.release.dropna())


def test_the_dataset_gets_both_columns_and_a_manifest_entry(files, tmp_path):
    src, registry, releases = files
    before = sha256(src / "rows.parquet")
    out = tmp_path / "out"
    manifest = b0coop.coop(src, out, registry=registry, release_file=releases)
    rows = pd.read_parquet(out / "rows.parquet")
    assert list(rows.listing_id) == list(frame().listing_id)
    assert list(rows.coop) == [r[4] for r in ROWS]
    assert list(rows.condo) == [r[5] for r in ROWS]
    assert (out / "set_aside.parquet").exists()
    assert sha256(src / "rows.parquet") == before
    entry = manifest["coop"]
    assert entry["source"] == str(src)
    assert entry["source_rows_sha256"] == "abc"
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert entry["registry"] == {"path": str(registry), "sha256": sha256(registry)}
    assert entry["releases"] == {"path": str(releases), "sha256": sha256(releases)}
    assert entry["coop_classes"] == ["C6", "C8", "D0", "D4"]
    assert entry["rows_by_status"] == {
        "read": 7,
        "no lot": 1,
        "no release": 1,
        "lot not in release": 1,
        "no class": 1,
    }
    assert entry["releases_read"] == {"19v1": 4, "20v1": 4, "21v1": 2}
    assert (entry["rows_coop"], entry["units_coop"], entry["buildings_coop"]) == (
        4,
        3,
        3,
    )
    assert (entry["rows_condo"], entry["units_condo"], entry["buildings_condo"]) == (
        1,
        1,
        1,
    )
    assert json.loads((out / "manifest.json").read_text()) == json.loads(
        json.dumps(manifest, default=str)
    )


def test_an_existing_out_is_refused(files, tmp_path):
    src, registry, releases = files
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileExistsError):
        b0coop.coop(src, out, registry=registry, release_file=releases)
