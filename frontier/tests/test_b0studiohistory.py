import json

import numpy as np
import pandas as pd
import pytest

from rentfrontier import b0studiohistory as sh

START = pd.Timestamp("2024-06-01")


def day(n):
    return (START + pd.Timedelta(days=n)).date()


def case(others, rooms=6, heldout=False, page="p"):
    """A studio row `s` listed on day 0 on unit page `page`, with the page's other ads
    `others` as (listing id, day, bedrooms), and a plain one-bedroom row `r` elsewhere."""
    frame = pd.DataFrame(
        {
            "listing_id": ["s", "r"],
            "building": ["b1", "b2"],
            "unit_id": ["u1", "u2"],
            "bedrooms": [0.0, 1.0],
        }
    )
    ads = pd.DataFrame(
        [("s", page, day(0), 0.0), ("r", "q", day(0), 1.0)]
        + [(lid, page, day(n), b) for lid, n, b in others],
        columns=["listing_id", "unit_id", "on_day", "bedrooms"],
    )
    codes = pd.DataFrame({"listing_id": ["s", "r"], "rooms": [rooms, 3]})
    return frame, ads, codes, np.array([heldout, False])


def studio(others, **kw):
    """`evidence`'s row for `s`, or None when step 1 leaves it unmarked, and the recoded
    bedrooms of `s`."""
    frame, ads, codes, held = case(others, **kw)
    table = sh.evidence(frame, ads, codes, held)
    out = sh.recode(frame, ads, codes, held, rule=sh.RULE)
    assert out.bedrooms.iloc[1] == 1.0
    row = table.loc["s"] if "s" in table.index else None
    return row, out.bedrooms.iloc[0]


@pytest.mark.parametrize(
    "n, marked", [(730, True), (-730, True), (731, False), (-731, False)]
)
def test_the_window_holds_730_days_on_each_side(n, marked):
    row, bedrooms = studio([("a", n, 1.0)])
    assert (row is not None) == marked
    assert bedrooms == (1.0 if marked else 0.0)


def test_an_ad_before_or_after_the_studio_ad_recodes_it():
    row, bedrooms = studio([("a", -100, 2.0)])
    assert bedrooms == 2.0 and row.outcome == sh.RECODED and row.days == 100
    row, bedrooms = studio([("a", 100, 3.0)])
    assert bedrooms == 3.0 and row.nearest == ("a",)


def test_studio_ads_on_the_page_are_no_evidence():
    row, bedrooms = studio([("a", 10, 0.0), ("c", 20, np.nan)])
    assert row is None and bedrooms == 0.0


@pytest.mark.parametrize("rooms", [4, 21])
def test_rooms_outside_five_to_twenty_leave_the_row_alone(rooms):
    row, bedrooms = studio([("a", 10, 1.0)], rooms=rooms)
    assert row is None and bedrooms == 0.0


def test_missing_room_counts_leave_the_row_alone():
    frame, ads, codes, held = case([("a", 10, 1.0)])
    for missing in (codes[codes.listing_id != "s"], codes.assign(rooms=[np.nan, 3])):
        assert sh.evidence(frame, ads, missing, held).empty
        out = sh.recode(frame, ads, missing, held, rule=sh.RULE)
        pd.testing.assert_frame_equal(out, frame)


def test_a_unit_without_other_ads_leaves_the_row_alone():
    row, bedrooms = studio([])
    assert row is None and bedrooms == 0.0
    # Ads without a unit page never pair with each other.
    row, bedrooms = studio([("a", 10, 1.0)], page=None)
    assert row is None and bedrooms == 0.0


def test_the_nearest_ad_decides_between_disagreeing_ads():
    row, bedrooms = studio([("a", -10, 1.0), ("c", -400, 3.0), ("d", 300, 2.0)])
    assert bedrooms == 1.0
    assert row.disagree and row.ads_near == 3 and row.ads_kept == 3
    assert row.nearest_bedrooms == (1.0,)


def test_a_tie_at_the_nearest_distance_keeps_the_studio_unless_the_ads_agree():
    row, bedrooms = studio([("a", -50, 1.0), ("c", 50, 2.0)])
    assert bedrooms == 0.0 and row.outcome == sh.TIE
    assert row.nearest == ("a", "c") and row.nearest_bedrooms == (1.0, 2.0)
    row, bedrooms = studio([("a", -50, 2.0), ("c", 50, 2.0), ("d", 400, 1.0)])
    assert bedrooms == 2.0 and row.outcome == sh.RECODED


def test_a_heldout_row_reads_only_earlier_ads():
    row, bedrooms = studio([("a", -100, 1.0), ("c", 10, 3.0)], heldout=True)
    assert bedrooms == 1.0 and row.ads_near == 2 and row.ads_kept == 1
    row, bedrooms = studio([("a", -100, 1.0), ("c", 10, 3.0)])
    assert bedrooms == 3.0
    for later in (10, 0):
        row, bedrooms = studio([("a", later, 2.0)], heldout=True)
        assert bedrooms == 0.0 and row.outcome == sh.NO_EARLIER_AD and row.ads_kept == 0


@pytest.mark.parametrize("ad_bedrooms", [5.0, 6.0])
def test_a_count_at_or_above_the_rooms_keeps_the_studio(ad_bedrooms):
    row, bedrooms = studio([("a", 10, ad_bedrooms)], rooms=5)
    assert bedrooms == 0.0 and row.outcome == sh.AT_ROOMS
    assert row.chosen == ad_bedrooms and np.isnan(row.bedrooms)
    row, bedrooms = studio([("a", 10, 4.0)], rooms=5)
    assert bedrooms == 4.0 and row.outcome == sh.RECODED
    frame, ads, codes, held = case([("a", 10, ad_bedrooms)], rooms=5)
    c = sh.counts(sh.evidence(frame, ads, codes, held))
    assert c["recoded"]["rows"] == 0 and c["unchanged"][sh.AT_ROOMS]["rows"] == 1


def test_a_studio_row_with_missing_bedrooms_is_left_alone():
    frame, ads, codes, held = case([("a", 10, 2.0)])
    frame = frame.assign(bedrooms=[np.nan, 1.0])
    assert sh.evidence(frame, ads, codes, held).empty
    out = sh.recode(frame, ads, codes, held, rule=sh.RULE)
    pd.testing.assert_frame_equal(out, frame)


def test_a_row_absent_from_the_ads_file_is_left_alone():
    frame, ads, codes, held = case([("a", 10, 2.0)])
    ads = ads[ads.listing_id != "s"]
    assert sh.evidence(frame, ads, codes, held).empty
    out = sh.recode(frame, ads, codes, held, rule=sh.RULE)
    pd.testing.assert_frame_equal(out, frame)


def test_repeated_listing_ids_are_refused():
    frame, ads, codes, held = case([("a", 10, 2.0)])
    twice = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="rows repeat"):
        sh.evidence(twice, ads, codes, np.zeros(3, dtype=bool))
    with pytest.raises(ValueError, match="ads repeat"):
        sh.recode(frame, pd.concat([ads, ads.iloc[-1:]]), codes, held, rule=sh.RULE)


def test_the_rule_is_off_by_default():
    frame, ads, codes, held = case([("a", 10, 1.0)])
    assert sh.recode(frame, ads, codes, held) is frame
    assert frame.bedrooms.tolist() == [0.0, 1.0]
    with pytest.raises(ValueError):
        sh.recode(frame, ads, codes, held, rule="studio-history-h2")


def test_counts_split_rows_by_outcome():
    frame = pd.DataFrame(
        {
            "listing_id": ["s1", "s2", "s3", "s4"],
            "building": ["b1", "b1", "b2", "b3"],
            "unit_id": ["u1", "u1", "u2", None],
            "bedrooms": [0.0, 0.0, 0.0, 0.0],
        }
    )
    ads = pd.DataFrame(
        [
            ("s1", "p1", day(0), 0.0),
            ("s2", "p1", day(40), 0.0),
            ("a1", "p1", day(-20), 2.0),
            ("s3", "p2", day(0), 0.0),
            ("a2", "p2", day(5), 1.0),
            ("s4", "p3", day(0), 0.0),
            ("a3", "p3", day(-5), 1.0),
            ("a4", "p3", day(5), 3.0),
        ],
        columns=["listing_id", "unit_id", "on_day", "bedrooms"],
    )
    codes = pd.DataFrame({"listing_id": frame.listing_id, "rooms": 5})
    held = np.array([False, False, True, False])
    table = sh.evidence(frame, ads, codes, held)
    assert table.index.tolist() == ["s1", "s2", "s3", "s4"]
    assert table.outcome.tolist() == [sh.RECODED, sh.RECODED, sh.NO_EARLIER_AD, sh.TIE]
    c = sh.counts(table)
    assert c["marked"] == {
        "rows": 4,
        "training": 3,
        "heldout": 1,
        "units": 3,
        "buildings": 3,
    }
    assert c["recoded"]["rows"] == 2 and c["recoded"]["units"] == 1
    assert c["recoded"]["bedrooms"] == {"2": 2}
    assert c["unchanged"][sh.NO_EARLIER_AD]["heldout"] == 1
    assert c["unchanged"][sh.TIE]["rows"] == 1


def write_source(tmp_path, frame, ads):
    src = tmp_path / "src"
    src.mkdir()
    frame.to_parquet(src / "rows.parquet")
    frame.iloc[:0].to_parquet(src / "set_aside.parquet")
    ads.to_parquet(tmp_path / "ads.parquet")
    build = {"ads": {"path": str(tmp_path / "ads.parquet")}}
    build["ads"]["sha256"] = sh.sha256(tmp_path / "ads.parquet")
    (src / "manifest.json").write_text(
        json.dumps({"rows": len(frame), "rows_sha256": "abc", "build": build})
    )
    return src


def test_run_counts_without_out_and_writes_a_copy_with_it(tmp_path):
    frame, ads, codes, _ = case([("a", -30, 2.0)])
    frame = frame.assign(
        audit_id=[1, 2],
        price_at=pd.Timestamp("2024-06-01", tz="UTC"),
        asking_rent=3000.0,
    )
    codes.to_parquet(tmp_path / "codes.parquet")
    src = write_source(tmp_path, frame, ads)
    before = (src / "rows.parquet").read_bytes()
    entry = sh.run(src, None, tmp_path / "codes.parquet")
    assert entry["rule"] == sh.RULE and entry["source_rows_sha256"] == "abc"
    assert entry["recoded"]["bedrooms"] == {"2": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "ads.parquet",
        "codes.parquet",
        "src",
    ]
    out = tmp_path / "out"
    written = sh.run(src, out, tmp_path / "codes.parquet")
    assert (src / "rows.parquet").read_bytes() == before
    rows = pd.read_parquet(out / "rows.parquet")
    assert rows.bedrooms.tolist() == [2.0, 1.0]
    assert list(rows.columns) == list(frame.columns)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["rows_sha256"] == sh.sha256(out / "rows.parquet")
    assert manifest["studio_history"] == written
    table = pd.read_parquet(out / "recoded.parquet")
    assert table.listing_id.tolist() == ["s"] and list(table.nearest[0]) == ["a"]
    assert (out / "set_aside.parquet").exists()
    with pytest.raises(FileExistsError):
        sh.run(src, out, tmp_path / "codes.parquet")


def test_run_refuses_an_ads_file_that_changed(tmp_path):
    frame, ads, codes, _ = case([("a", -30, 2.0)])
    src = write_source(tmp_path, frame, ads)
    ads.iloc[:1].to_parquet(tmp_path / "ads.parquet")
    with pytest.raises(SystemExit):
        sh.run(src, None, tmp_path / "codes.parquet")
