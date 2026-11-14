import datetime as dt
import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0amenitycarry as ac
from rentfrontier.b0data import sha256

H, C = "feat:HARDWOOD_FLOORS", "views:CITY"
# (building, unit_id, price_at, on_day, own codes, carried codes, earlier ads read). "S" is
# states_features, and "-" marks a listing with no line in the codes file.
ROWS = [
    ("b1", "1", "2020-01-10T12:00", "2020-01-10", "HS", "HS", 0),
    ("b1", "1", "2020-06-01T12:00", "2020-06-01", "CS", "HCS", 1),
    ("b1", "1", "2021-01-05T12:00", "2021-01-05", "", "HCS", 2),
    # Placed after the row above on the same day, so it opened on the same day: not read.
    ("b1", "2", "2020-03-01T09:00", "2020-03-01", "CS", "CS", 0),
    ("b1", "2", "2020-03-01T15:00", "2020-03-01", "", "", 0),
    # The same unit_id in another building is another unit.
    ("b2", "1", "2023-01-01T12:00", "2023-01-01", "", "", 0),
    # on_day after the price day is capped at the price day, 2020-05-10.
    ("b1", "3", "2020-05-10T12:00", "2020-09-01", "HS", "HS", 0),
    # Placed after the row above, but opened on 2020-05-01, before it: not read.
    ("b1", "3", "2020-05-20T12:00", "2020-05-01", "", "", 0),
    # No on_day, so the row opens on its price day and reads both ads above.
    ("b1", "3", "2020-10-01T12:00", None, "", "HS", 2),
    # Rows without a unit_id keep their own codes.
    ("b1", None, "2021-06-01T12:00", "2021-06-01", "", "", 0),
    ("b1", None, "2021-01-01T12:00", "2021-01-01", "HS", "HS", 0),
    ("b1", "1", "2022-01-01T12:00", "2022-01-01", "-", "HCS", 3),
]
CODES = {"H": H, "C": C, "S": ac.STATED}


def frame(rows=ROWS):
    return pd.DataFrame(
        {
            "listing_id": [str(100 + i) for i in range(len(rows))],
            "audit_id": [f"a{i:03d}" for i in range(len(rows))],
            "building": [r[0] for r in rows],
            "unit_id": [r[1] for r in rows],
            "price_at": pd.to_datetime([r[2] for r in rows], utc=True),
            "latest_ask": [3000.0 + i for i in range(len(rows))],
        }
    )


def codes_table(rows=ROWS):
    have = [(str(100 + i), r[4]) for i, r in enumerate(rows) if r[4] != "-"]
    # The dishwasher is one of the design's duplicates and the gym a building code, so
    # neither is carried.
    return pd.DataFrame(
        {
            "listing_id": [x[0] for x in have],
            "collected_at": 1.76e9,
            H: [int("H" in x[1]) for x in have],
            "feat:DISHWASHER": 1,
            C: [int("C" in x[1]) for x in have],
            "amen:GYM": 1,
            ac.STATED: [int("S" in x[1]) for x in have],
        }
    )


def ads_table(rows=ROWS):
    on = [None if r[3] is None else dt.date.fromisoformat(r[3]) for r in rows]
    return pa.table(
        {
            "listing_id": pa.array([str(100 + i) for i in range(len(rows))] + ["999"]),
            "on_day": pa.array([*on, dt.date(2020, 1, 1)], pa.date32()),
            "status": pa.array(["RENTED"] * (len(rows) + 1)),
        }
    )


def write_src(tmp_path, rows=ROWS):
    codes = tmp_path / "listing-codes.parquet"
    codes_table(rows).to_parquet(codes)
    ads = tmp_path / "ads.parquet"
    pq.write_table(ads_table(rows), ads)
    src = tmp_path / "src"
    src.mkdir()
    frame(rows).to_parquet(src / "rows.parquet")
    frame(rows).iloc[:0].to_parquet(src / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"ads": {"path": str(ads), "sha256": sha256(ads)}},
    }
    (src / "manifest.json").write_text(json.dumps(manifest))
    return src, codes, ads


def carried(tmp_path, rows=ROWS):
    src, codes, ads = write_src(tmp_path, rows)
    f = frame(rows)
    table, names = ac.read_codes(codes, set(f.listing_id))
    own = ac.masks(f, table, names)
    opened = ac.opening_days(f, ac.read_on_days(ads, set(f.listing_id)))
    return f, names, own, opened, *ac.carry(f, own, opened)


def bits(mask, names):
    return "".join(
        k for k, v in CODES.items() if v in names and mask >> names.index(v) & 1
    )


def test_only_unit_codes_the_design_can_read_are_carried(tmp_path):
    f, names, *_ = carried(tmp_path)
    assert names == [H, C]


def test_opening_day_is_on_day_capped_at_the_price_day(tmp_path):
    f, names, own, opened, *_ = carried(tmp_path)
    day = pd.to_datetime([r[2][:10] for r in ROWS]).to_numpy().astype("datetime64[D]")
    on = [r[3] or r[2][:10] for r in ROWS]
    want = np.minimum(
        day, pd.to_datetime(on).to_numpy().astype("datetime64[D]")
    ).astype(np.int64)
    assert list(opened) == list(want)
    assert opened[6] == np.datetime64("2020-05-10", "D").astype(np.int64)


def test_each_row_takes_the_union_of_its_own_and_earlier_ads_codes(tmp_path):
    f, names, own, opened, union, count, pairs = carried(tmp_path)
    names_s = [*names, ac.STATED]
    assert [bits(m, names_s) for m in own] == [r[4].strip("-") for r in ROWS]
    assert [bits(m, names_s) for m in union] == [r[5] for r in ROWS]
    assert list(count) == [r[6] for r in ROWS]
    assert pairs == {"pairs_read": 8, "pairs_opened_same_day_or_later": 2}


def test_a_later_ad_is_never_read():
    rng = np.random.default_rng(0)
    n = 400
    f = pd.DataFrame(
        {
            "listing_id": [str(i) for i in range(n)],
            "audit_id": [f"{rng.integers(1000):04d}" for _ in range(n)],
            "building": rng.choice(["x", "y"], n),
            "unit_id": pd.Series(rng.choice(["1", "2", "3", None], n), dtype=object),
            # Coarse times, so many rows share a price day.
            "price_at": pd.to_datetime("2020-01-01", utc=True)
            + pd.to_timedelta(rng.integers(0, 40, n) * 12, unit="h"),
        }
    )
    own = rng.integers(0, 1 << 6, n)
    opened = ac.days(f.price_at) - rng.integers(0, 4, n)
    union, count, _ = ac.carry(f, own, opened)
    unit = list(zip(f.building, f.unit_id))
    place = list(zip(f.price_at.to_numpy(), f.audit_id, range(n)))
    for i in range(n):
        want, k = own[i], 0
        for j in range(n):
            same = unit[i][1] is not None and unit[i] == unit[j]
            if same and place[j] < place[i] and opened[j] < opened[i]:
                want |= own[j]
                k += 1
        assert union[i] == want
        assert count[i] == k


def test_the_dataset_gets_the_columns_and_a_manifest_entry(tmp_path):
    src, codes, ads = write_src(tmp_path)
    before = sha256(src / "rows.parquet")
    out = tmp_path / "out"
    manifest = ac.amenity_carry(src, out, codes_file=codes)
    rows = pd.read_parquet(out / "rows.parquet")
    assert list(rows.listing_id) == list(frame().listing_id)
    added = [c for c in rows.columns if c.startswith(ac.PREFIX)]
    assert added == [
        f"carry:{H}",
        f"carry:{C}",
        "carry:states_features",
        "carry:earlier_ads",
    ]
    for k, name in CODES.items():
        assert list(rows[f"carry:{name}"]) == [int(k in r[5]) for r in ROWS]
    assert list(rows["carry:earlier_ads"]) == [r[6] for r in ROWS]
    assert (out / "set_aside.parquet").exists()
    assert sha256(src / "rows.parquet") == before
    entry = manifest["amenity_carry"]
    assert entry["source"] == str(src)
    assert entry["source_rows_sha256"] == "abc"
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert entry["codes"] == {"path": str(codes), "sha256": sha256(codes)}
    assert entry["ads"] == {"path": str(ads), "sha256": sha256(ads)}
    assert entry["codes_carried"] == [H, C, ac.STATED]
    assert entry["rows_own"] == {H: 3, C: 2, ac.STATED: 5}
    assert entry["rows_carried"] == {H: 7, C: 4, ac.STATED: 8}
    assert entry["rows_gaining"] == {H: 4, C: 2, ac.STATED: 3}
    assert entry["rows_gaining_any"] == 4
    assert entry["rows_with_earlier_ads"] == 4
    assert entry["pairs_read"] == 8
    assert json.loads((out / "manifest.json").read_text()) == json.loads(
        json.dumps(manifest, default=str)
    )


def test_an_ads_file_that_changed_is_refused(tmp_path):
    src, codes, ads = write_src(tmp_path)
    pq.write_table(ads_table()[:3], ads)
    with pytest.raises(SystemExit):
        ac.amenity_carry(src, tmp_path / "out", codes_file=codes)
    assert not (tmp_path / "out").exists()


def test_an_existing_out_is_refused(tmp_path):
    src, codes, ads = write_src(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileExistsError):
        ac.amenity_carry(src, out, codes_file=codes)
