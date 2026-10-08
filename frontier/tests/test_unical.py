import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest
from rentfrontier import features, unical

ARCHIVE = """<html><body><script>var x = "Fall 1999 - Summer 2000";</script>
<a>Fall 2012 - Summer 2013</a><a>Fall 2013 - Summer 2014</a>
<h2>Fall 2012 - Summer 2013</h2>
<p>Fall 2012 classes begin</p><p>Tuesday, September 4</p>
<p>Spring Semester Final Exams</p><p>Wednesday, May 15 -</p><p>Tuesday, May 21</p>
<p>Commencement</p><p>Wednesday, May 22</p>
<h2>Fall 2013 - Summer 2014</h2>
<p>Residence Hall Move-in</p><p>Sunday, August 25</p>
<p>Fall 2013 Classes Begin</p><p>Tuesday, September 3, 2013</p>
</body></html>"""


def test_archive_page_reads_events_under_their_year():
    got = unical.key_dates(unical.archive_events(ARCHIVE))
    assert got == {
        (2012, "fall_start"): dt.date(2012, 9, 4),
        (2012, "spring_exams"): dt.date(2013, 5, 15),
        (2012, "commencement"): dt.date(2013, 5, 22),
        (2013, "movein"): dt.date(2013, 8, 25),
        (2013, "fall_start"): dt.date(2013, 9, 3),
    }


def test_feed_skips_early_move_in_and_takes_the_first_exam_day():
    items = {
        "data": [
            {
                "title": "NYU Early Quarantine Move-in Days",
                "date_iso": "2021-08-18T00:00:00-04:00",
            },
            {"title": "NYU Move-in Days", "date_iso": "2021-08-28T00:00:00-04:00"},
            {"title": "NYU Move-in Days", "date_iso": "2021-08-27T00:00:00-04:00"},
            {"title": "Fall 2021 Classes Begin", "date_utc": "2021-09-02 04:00:00"},
            {"title": "Final Exam Period", "date_iso": "2021-12-16T00:00:00-05:00"},
            {"title": "Final Exam Period", "date_iso": "2022-05-12T00:00:00-04:00"},
            {"title": "Final Exam Period", "date_iso": "2022-05-11T00:00:00-04:00"},
        ]
    }
    assert unical.key_dates(unical.feed_events(items)) == {
        (2021, "movein"): dt.date(2021, 8, 27),
        (2021, "fall_start"): dt.date(2021, 9, 2),
        (2021, "spring_exams"): dt.date(2022, 5, 11),
    }


def test_build_keeps_the_first_source_and_records_conflicts(tmp_path):
    (tmp_path / "a.html").write_text(ARCHIVE)
    feed = [{"title": "Fall 2013 classes begin", "date_utc": "2013-09-04 04:00:00"}]
    (tmp_path / "b.json").write_text(json.dumps(feed))
    pd.DataFrame(
        {
            "file": ["a.html", "b.json"],
            "school": "NYU",
            "parser": ["nyu-archive", "nyu-feed"],
            "url": ["u-a", "u-b"],
            "fetched": "2026-10-08",
        }
    ).to_csv(tmp_path / "sources.tsv", sep="\t", index=False)
    table, provenance = unical.build(tmp_path)
    assert len(table) == 5
    start = [p for p in provenance if (p["year"], p["event"]) == (2013, "fall_start")]
    assert start == [
        {
            "school": "NYU",
            "year": 2013,
            "event": "fall_start",
            "date": "2013-09-03",
            "source": "u-a",
            "conflicts": [{"date": "2013-09-04", "source": "u-b"}],
        }
    ]


CALENDAR = pd.DataFrame(
    [
        ("NYU", 2011, "spring_exams", "2012-05-14"),
        ("NYU", 2012, "fall_start", "2012-09-04"),
        ("NYU", 2012, "spring_exams", "2013-05-15"),
        ("NYU", 2013, "movein", "2013-08-25"),
        ("NYU", 2013, "fall_start", "2013-09-03"),
        ("NYU", 2013, "spring_exams", "2014-05-14"),
    ],
    columns=["school", "year", "event", "date"],
)


def test_windows_edges_and_move_in_stand_in():
    days = [
        "2013-07-13",  # a day before 6 weeks before move-in
        "2013-07-14",
        "2013-08-24",
        "2013-08-25",  # move-in
        "2013-09-02",
        "2013-09-03",  # classes begin: in neither
        "2013-05-01",  # spring finals 2013-05-15 less 14 days
        "2013-05-28",
        "2013-05-29",
        "2012-08-26",  # 2012 has no move-in: 9 days before classes
        "2012-08-25",
    ]
    at = pd.Series(pd.to_datetime(days) + pd.Timedelta(hours=15))
    got = unical.windows(at, CALENDAR).astype(int).to_numpy().tolist()
    assert got == [
        [0, 0, 0],
        [1, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [0, 1, 0],
        [0, 0, 0],
        [0, 0, 1],
        [0, 0, 1],
        [0, 0, 0],
        [0, 1, 0],
        [1, 0, 0],
    ]


def test_windows_refuse_a_year_the_calendar_lacks():
    with pytest.raises(ValueError, match="2014"):
        unical.windows(pd.Series(pd.to_datetime(["2014-08-01"])), CALENDAR)


def test_near_campus_within_800_m_of_either():
    near = unical.near_campus(
        [40.7295, 40.7400, 40.7465, np.nan], [-73.9973, -73.9937, -74.0010, np.nan]
    )
    assert near.tolist() == [True, True, False, False]


def test_unical_set_is_on_point_in_time_pluto():
    assert features.FEATURE_SETS["nb5-unical-v1"].keywords["base"] == "nb5-plutoasof-v3"
    assert features.NB4_SETS["nb5-unical-v1"] == "nb5-plutoasof-v3"
    assert "nb5-unical-v1" in features.PLUTO_RELEASED_SETS
    assert "nb5-unical-v1" in features.UNICAL
