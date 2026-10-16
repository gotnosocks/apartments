import importlib.util
import json
import shutil
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
tests = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))


def record(listing_id, changes, plans=None):
    """A record of ad `listing_id` on the market from 2026-05-01, with a status change for each
    item of `changes` as in `market_record` and a floor plan for each key of `plans`. Without
    `plans` the record has no media."""
    ad = json.loads(tests.market_record(listing_id, changes))
    if plans is not None:
        ad["media"] = {"floorPlans": [{"key": key} for key in plans]}
    return json.dumps(ad, sort_keys=True)


def test_ads_cases(tmp_path, monkeypatch):
    """`analysis.ads` on these ads, each on the market from 2026-05-01:

    - ad 9000070 is paused and back on the market, and has two floor plans;
    - ad 9000071 goes from review to ACTIVE, and later through a brokerage review, with an
      empty list of floor plans;
    - ad 9000072 goes into contract and back on the market, then rents;
    - ad 9000073 had a break before 2026-05-01;
    - ad 9000074 goes into contract and back on the market at one instant, in the record's
      order;
    - ad 9000075 has an earlier answer listing changes off the market after it rents, which
      its later answer leaves out before its return;
    - ad 9000076 has an earlier answer ending it, which its later answer leaves out."""
    export = tmp_path / "export"
    shutil.copytree(tests.FIXTURE / "cases" / "export", export)
    records = [
        (
            9000070,
            record(
                9000070,
                [
                    ("2026-05-01", "ACTIVE"),
                    ("2026-05-10", "TEMPORARILY_OFF_MARKET"),
                    ("2026-05-20", "ACTIVE"),
                ],
                plans=["a.jpg", "b.jpg"],
            ),
        ),
        (
            9000071,
            record(
                9000071,
                [
                    ("2026-04-28", "DRAFT"),
                    ("2026-05-01", "IN_STREETEASY_REVIEW"),
                    ("2026-05-01", "ACTIVE", "11"),
                    ("2026-05-12", "IN_BROKERAGE_REVIEW"),
                    ("2026-05-13", "ACTIVE"),
                ],
                plans=[],
            ),
        ),
        (
            9000072,
            record(
                9000072,
                [
                    ("2026-05-01", "ACTIVE"),
                    ("2026-05-05", "IN_CONTRACT"),
                    ("2026-05-08", "ACTIVE"),
                    ("2026-05-30", "RENTED"),
                ],
            ),
        ),
        (
            9000073,
            record(
                9000073,
                [
                    ("2026-04-20", "ACTIVE"),
                    ("2026-04-25", "TEMPORARILY_OFF_MARKET"),
                    ("2026-05-01", "ACTIVE"),
                ],
            ),
        ),
        (
            9000074,
            record(
                9000074,
                [
                    ("2026-05-01", "ACTIVE"),
                    ("2026-05-10", "IN_CONTRACT"),
                    ("2026-05-10", "ACTIVE"),
                ],
            ),
        ),
    ]
    records += [
        (
            9000075,
            record(
                9000075,
                [
                    ("2026-05-01", "ACTIVE"),
                    ("2026-05-10", "RENTED", "11"),
                    ("2026-05-20", "ACTIVE"),
                ],
            ),
        ),
        (9000076, record(9000076, [("2026-05-01", "ACTIVE")])),
    ]
    earlier = [
        (
            9000075,
            record(
                9000075,
                [
                    ("2026-05-01", "ACTIVE"),
                    ("2026-05-10", "RENTED"),
                    ("2026-05-12", "NO_LONGER_AVAILABLE", "03"),
                    ("2026-05-13", "RENTED", "03"),
                ],
            ),
        ),
        (
            9000076,
            record(
                9000076,
                [("2026-05-01", "ACTIVE"), ("2026-05-15", "NO_LONGER_AVAILABLE")],
            ),
        ),
    ]
    tests.append_answers(export, tests.answers("listing_id", earlier, 30, "2026-09-01"))
    tests.append_answers(export, tests.answers("listing_id", records, 20, "2026-09-02"))
    ctx = tests.context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    got = ctx.fetchdf(
        """SELECT listing_id, regions, status, page_price, on_day::VARCHAR AS on_day,
        last_change, break_status, break_day::VARCHAR AS break_day,
        back_day::VARCHAR AS back_day, floor_plans, ledger_entries, in_rows
        FROM analysis.ads WHERE listing_id >= '9000070' ORDER BY listing_id"""
    )
    got = got.astype(object).where(got.notna(), None)
    for column in ("regions", "floor_plans", "ledger_entries"):
        got[column] = [None if v is None else list(v) for v in got[column]]
    on = ["cases"], 3000.0, "2026-05-01"
    assert got.values.tolist() == [
        ["9000070", *on[:1], "ACTIVE", *on[1:], "ACTIVE", "TEMPORARILY_OFF_MARKET"]
        + ["2026-05-10", "2026-05-20", ["a.jpg", "b.jpg"], [], False],
        ["9000071", *on[:1], "ACTIVE", *on[1:], "ACTIVE", None, None, None, []]
        + [[], False],
        ["9000072", *on[:1], "RENTED", *on[1:], "RENTED", None, None, None, None]
        + [[], False],
        ["9000073", *on[:1], "ACTIVE", *on[1:], "ACTIVE", None, None, None, None]
        + [[], False],
        ["9000074", *on[:1], "ACTIVE", *on[1:], "ACTIVE", "IN_CONTRACT", "2026-05-10"]
        + ["2026-05-10", None, [], False],
        ["9000075", *on[:1], "ACTIVE", *on[1:], "ACTIVE", "RENTED", "2026-05-10"]
        + ["2026-05-20", None, [], False],
        ["9000076", *on[:1], "ACTIVE", *on[1:], "ACTIVE", None, None, None, None]
        + [[], False],
    ]
    # Every ad with a record has a row, once.
    counts = ctx.fetchdf(
        """SELECT (SELECT count(*) FROM analysis.ads) AS ads,
        (SELECT count(DISTINCT listing_id) FROM analysis.ads) AS distinct_ads,
        (SELECT count(DISTINCT listing_id) FROM ads.answers WHERE outcome = 'record')
            AS with_records"""
    )
    assert counts.ads[0] == counts.distinct_ads[0] == counts.with_records[0]
