import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import sqlmesh.core.console
from sqlmesh import Context
from sqlmesh.core.console import TerminalConsole
from sqlmesh.utils.errors import PlanError

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixture"


def context(
    monkeypatch,
    state,
    export=FIXTURE / "export",
    rows=FIXTURE / "rows.parquet",
    project=PROJECT,
):
    monkeypatch.setenv("PIPELINE_EXPORT", str(export))
    monkeypatch.setenv("PIPELINE_ROWS", str(rows))
    monkeypatch.setenv("PIPELINE_STATE", str(state))
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    return Context(paths=str(project))


def latest_ask(ctx):
    frame = ctx.fetchdf("SELECT * FROM analysis.latest_ask ORDER BY ordinal")
    return frame.reset_index(drop=True)


def changed(plan):
    """The names of the models a plan builds again, directly changed or below a change."""
    ids = set(plan.directly_modified).union(*plan.indirectly_modified.values())
    return sorted(i.name.replace('"', "").removeprefix("pipeline.") for i in ids)


def copy_export(tmp_path, keep=None):
    """Copy the fixture export, keeping only the manifest lines `keep` accepts."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "export", export)
    lines = (export / "manifest.ndjson").read_text().splitlines(keepends=True)
    (export / "manifest.ndjson").write_text(
        "".join(line for line in lines if keep is None or keep(json.loads(line)))
    )
    return export


def append_answers(export, answers):
    """Write `answers` as a new ads file of run 5 and list it in the manifest."""
    first, last = answers.response_id.min(), answers.response_id.max()
    path = Path("ads/run-0005") / f"responses-{first:07d}-{last:07d}.parquet"
    (export / path).parent.mkdir(parents=True)
    db = duckdb.connect(config={"TimeZone": "UTC"})
    db.register("answers", answers)
    db.execute(
        f"""COPY (SELECT listing_id::BIGINT AS listing_id, fetched::TIMESTAMPTZ AS fetched,
        response_id::BIGINT AS response_id, run::INTEGER AS run, region, generation::INTEGER
        AS generation, outcome, record_sha256, record FROM answers ORDER BY response_id)
        TO '{export / path}' (FORMAT parquet)"""
    )
    line = {
        "first": int(first),
        "last": int(last),
        "path": str(path),
        "rows": len(answers),
        "run": 5,
        "sha256": hashlib.sha256((export / path).read_bytes()).hexdigest(),
        "table": "ads",
        "written": "2026-10-23T12:00:00Z",
    }
    with open(export / "manifest.ndjson", "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def test_latest_ask_matches_rentfrontier(tmp_path, monkeypatch):
    ctx = context(monkeypatch, tmp_path / "state")
    ctx.plan(auto_apply=True, no_prompts=True)
    expected = pd.read_parquet(FIXTURE / "latest-ask.parquet")
    pd.testing.assert_frame_equal(latest_ask(ctx), expected)
    assert set(expected.how) == {
        "latest",
        "latest, nearer building",
        "first, nearer building",
        "page price",
        "page price, digit",
    }
    # Four of 1,176 changes fail the placeholder check.
    kept = ctx.fetchdf("SELECT count(*) AS n FROM ads.kept_changes").n[0]
    assert kept == len(ctx.fetchdf("SELECT * FROM ads.price_changes")) - 4


def test_latest_ask_cases(tmp_path, monkeypatch):
    """The made-up ads of make_cases.py: several rows of one ad, a record collected before its
    row, an ad without answers, a missing latest answer and rows without group keys."""
    cases = FIXTURE / "cases"
    ctx = context(
        monkeypatch, tmp_path / "state", cases / "export", cases / "rows.parquet"
    )
    ctx.plan(auto_apply=True, no_prompts=True)
    expected = pd.read_parquet(cases / "latest-ask.parquet")
    pd.testing.assert_frame_equal(latest_ask(ctx), expected)
    assert set(expected.how) == {
        "latest",
        "page price",
        "own ask, captured before the row",
        "uncaptured",
        "first, nearer building",
    }


def test_new_export_file_rebuilds_only_downstream(tmp_path, monkeypatch):
    export = copy_export(tmp_path, keep=lambda line: line["run"] < 4)
    context(monkeypatch, tmp_path / "state", export).plan(
        auto_apply=True, no_prompts=True
    )
    cache = tmp_path / "state" / "attributes"
    before = {path.name for path in cache.glob("*/*.parquet")}
    export = copy_export(tmp_path / "full")
    ctx = context(monkeypatch, tmp_path / "state", export)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == [
        "ads.answers",
        "ads.attributes",
        "ads.events",
        "ads.exclusions",
        "ads.first_ask",
        "ads.history_events",
        "ads.kept_changes",
        "ads.latest_record",
        "ads.price_changes",
        "ads.record_attributes",
        "analysis.latest_ask",
        "analysis.latest_change",
        "raw.ads",
    ]
    # The second build parsed only records missing from runs 2 and 3.
    added = [path for path in cache.glob("*/*.parquet") if path.name not in before]
    parsed = pd.concat(pd.read_parquet(path) for path in added).record_sha256
    db = duckdb.connect()
    new = db.execute(
        """SELECT DISTINCT record_sha256 FROM read_parquet(?) WHERE outcome = 'record'
        EXCEPT SELECT record_sha256 FROM read_parquet(?)""",
        [
            [str(path) for path in (export / "ads").glob("run-0004/*.parquet")],
            [str(path) for path in (export / "ads").glob("run-000[23]/*.parquet")],
        ],
    ).df()
    assert len(new) and sorted(parsed) == sorted(new.record_sha256)
    pd.testing.assert_frame_equal(
        latest_ask(ctx), pd.read_parquet(FIXTURE / "latest-ask.parquet")
    )
    again = (
        context(monkeypatch, tmp_path / "state", export).plan_builder("prod").build()
    )
    assert not again.has_changes and not again.new_snapshots


def test_code_change_starts_a_new_cache_folder(tmp_path, monkeypatch):
    """A change to the projection's code gives ads.record_attributes a new code version, and the
    build parses every record again into a new folder."""
    project = tmp_path / "project"
    shutil.copytree(
        PROJECT,
        project,
        ignore=shutil.ignore_patterns(".venv", "tests", "logs", "__pycache__"),
    )
    (tmp_path / "src").symlink_to(PROJECT.parent / "src")
    export = copy_export(tmp_path, keep=lambda line: line["run"] == 2)
    context(monkeypatch, tmp_path / "state", export, project=project).plan(
        auto_apply=True, no_prompts=True
    )
    cache = tmp_path / "state" / "attributes"
    (old,) = cache.iterdir()
    code = project / "steps" / "attributes.py"
    code.write_text(code.read_text() + "\n# A change to the projection's code.\n")
    ctx = context(monkeypatch, tmp_path / "state", export, project=project)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert "ads.record_attributes" in changed(plan)
    (new,) = set(cache.iterdir()) - {old}

    def parsed(folder):
        return sorted(
            pd.concat(map(pd.read_parquet, folder.glob("*.parquet"))).record_sha256
        )

    assert parsed(new) == parsed(old) and len(parsed(new))


def test_rewritten_export_file_rebuilds(tmp_path, monkeypatch):
    """A file written again under its old path gets a new hash in the manifest, and the plan
    builds the ads models again."""
    export = copy_export(tmp_path)
    context(monkeypatch, tmp_path / "state", export).plan(
        auto_apply=True, no_prompts=True
    )
    lines = [json.loads(line) for line in open(export / "manifest.ndjson")]
    path = export / lines[0]["path"]
    db = duckdb.connect()
    db.execute(
        f"COPY (SELECT * FROM '{path}') TO '{path}.new' (FORMAT parquet, COMPRESSION gzip)"
    )
    Path(f"{path}.new").replace(path)
    lines[0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (export / "manifest.ndjson").write_text(
        "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines)
    )
    ctx = context(monkeypatch, tmp_path / "state", export)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert "raw.ads" in changed(plan) and "analysis.latest_ask" in changed(plan)
    pd.testing.assert_frame_equal(
        latest_ask(ctx), pd.read_parquet(FIXTURE / "latest-ask.parquet")
    )


def test_later_answer_replaces_an_earlier_one(tmp_path, monkeypatch):
    """A newer answer for an ad replaces its earlier one, and an older answer changes nothing."""
    expected = pd.read_parquet(FIXTURE / "latest-ask.parquet")
    rows = pd.read_parquet(FIXTURE / "rows.parquet").merge(
        expected, on=["ordinal", "audit_id"]
    )
    once = rows.groupby("source_listing_id").filter(lambda r: len(r) == 1)
    steady = once[(once.how == "latest") & (once.latest_ask == once.first_ask)]
    steady = steady.set_index("source_listing_id").latest_ask
    db = duckdb.connect(config={"TimeZone": "UTC"})
    answers = db.execute(
        "SELECT * FROM read_parquet(?) ORDER BY listing_id",
        [str(FIXTURE / "export/ads/*/*.parquet")],
    ).df()
    answers = answers[answers.listing_id.astype(str).isin(steady.index)]
    relisted, stale = answers.iloc[0], answers.iloc[1]
    price = float(round(steady[str(relisted.listing_id)] * 1.05))
    first = answers.response_id.max() + 1

    def answer(old, days, response_id, price, status):
        """A copy of an answer, `days` later, with a price change to `price` on Oct 20."""
        record = json.loads(old.record)
        record.update(status=status, offMarketAt=None)
        record["pricing"]["price"] = price
        record["pricing"]["priceChanges"].append(
            {"changedAt": "2026-10-20T12:00:00Z", "price": price}
        )
        text = json.dumps(record, sort_keys=True)
        return {
            **old,
            "fetched": old.fetched + pd.Timedelta(days=days),
            "response_id": response_id,
            "run": 5,
            "record": text,
            "record_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }

    export = copy_export(tmp_path)
    append_answers(
        export,
        pd.DataFrame(
            [
                answer(relisted, 8, first, price, "ACTIVE"),
                answer(stale, -8, first + 1, 99999.0, "ACTIVE"),
            ]
        ),
    )
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    got = latest_ask(ctx)
    moved = expected.ordinal.isin(
        rows.ordinal[rows.source_listing_id == str(relisted.listing_id)]
    )
    assert got.latest_ask[moved].tolist() == [price]
    assert got.how[moved].tolist() == ["latest"]
    pd.testing.assert_frame_equal(got[~moved], expected[~moved])


def test_ads_match_the_rows(tmp_path, monkeypatch):
    """Each analysis row's price date, asking rent and bedroom count are its ad's first day,
    first ask and bedroom count, and the ad has no reason for exclusion. The current chain kept
    every ad of the fixture."""
    ctx = context(monkeypatch, tmp_path / "state")
    ctx.plan(auto_apply=True, no_prompts=True)
    rows = ctx.fetchdf(
        """SELECT coalesce(r.price_at = f.first_day::TIMESTAMPTZ, false) AS same_day,
        coalesce(f.prices = [r.asking_rent], false) AS same_ask,
        coalesce(e.rent = r.asking_rent AND e.reasons = [], false) AS kept,
        coalesce(a.bedrooms = r.bedrooms::DOUBLE, false) AS same_bedrooms
        FROM raw.analysis_rows r
        LEFT JOIN ads.first_ask f ON f.listing_id = r.source_listing_id
        LEFT JOIN ads.exclusions e ON e.listing_id = r.source_listing_id
        LEFT JOIN ads.attributes a ON a.listing_id = r.source_listing_id"""
    )
    assert len(rows) == 229 and rows.all().all()
    assert ctx.fetchdf("SELECT count(*) AS n FROM ads.exclusions").n[0] == 229


def test_repeated_answer_adds_only_its_fetch(tmp_path, monkeypatch):
    """A later answer with the same record reports no event besides its own fetch."""
    export = copy_export(tmp_path)
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    key = ["listing_id", "source", "kind", "day", "at", "price"]
    before = ctx.fetchdf("SELECT * FROM ads.events")
    db = duckdb.connect(config={"TimeZone": "UTC"})
    answers = db.execute(
        "SELECT * FROM read_parquet(?) ORDER BY response_id",
        [str(FIXTURE / "export/ads/*/*.parquet")],
    ).df()
    # An answer whose history lists another ad's events too.
    pick = ctx.fetchdf(
        """SELECT listing_id, response_id FROM ads.answers a WHERE EXISTS (
        SELECT 1 FROM ads.history_events e
        WHERE e.history = a.history AND e.listing_id <> a.listing_id)
        ORDER BY response_id, listing_id LIMIT 1"""
    )
    ad, response = int(pick.listing_id[0]), int(pick.response_id[0])
    old = answers[(answers.listing_id == ad) & (answers.response_id == response)]
    history = ctx.fetchdf(
        f"""SELECT DISTINCT listing_id::VARCHAR AS listing_id, kind, day, price
        FROM ads.history_events WHERE history = (SELECT history FROM ads.answers
        WHERE listing_id = {ad} AND response_id = {response})"""
    )
    assert (history.listing_id != str(ad)).any()
    expected = pd.concat(
        [
            before[
                (before.listing_id == str(ad)) & before.source.isin(["status", "price"])
            ],
            before[before.source == "history"].merge(history),
        ]
    )[key]
    again = old.assign(
        fetched=old.fetched + pd.Timedelta(days=8),
        response_id=answers.response_id.max() + 1,
        run=5,
    )
    append_answers(export, again)
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    after = ctx.fetchdf("SELECT * FROM ads.events")
    both = after.merge(before, on=key, how="outer", indicator=True)
    added = both[both._merge == "left_only"]
    assert len(added) == 1 and len(both) == len(after) == len(before) + 1
    assert added.source.tolist() == ["fetch"]
    assert added.listing_id.tolist() == [str(old.listing_id.iloc[0])]
    both = both[both._merge == "both"]
    assert (both.first_seen_x == both.first_seen_y).all()
    assert (both.first_response_id_x == both.first_response_id_y).all()
    seen = both[both.answers_x != both.answers_y]
    check = seen[key].merge(expected, how="outer", indicator=True)
    assert len(check) == len(seen) == len(expected) and (check._merge == "both").all()
    assert (seen.last_seen_x == again.fetched.iloc[0]).all()
    assert (seen.answers_x == seen.answers_y + 1).all()
    rest = both[both.answers_x == both.answers_y]
    assert (rest.last_seen_x == rest.last_seen_y).all()


def history_record(listing_id, history):
    return json.dumps(
        {
            "id": str(listing_id),
            "status": "ACTIVE",
            "onMarketAt": "2026-05-01",
            "createdAt": "2026-05-01T09:00:00.000-04:00",
            "offMarketAt": None,
            "pricing": {
                "price": 3000,
                "priceChanges": [
                    {"changedAt": "2026-05-01T10:00:00.000-04:00", "price": 3000}
                ],
            },
            "statusChanges": [
                {"changedAt": "2026-05-01T10:00:00.000-04:00", "status": "ACTIVE"}
            ],
            "propertyHistory": history,
        },
        sort_keys=True,
    )


def test_event_log_cases(tmp_path, monkeypatch):
    """The made-up ads of make_cases.py, which have no histories and a missing answer, and four
    answers with histories: an empty one, one listing an event twice and an ACTIVE change
    without a price, a later one with an added event, and the same history from a sibling."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)

    def active(day, price):
        return {
            "__typename": "RentalStatusChangeOfInterest",
            "date": day,
            "price": price,
            "status": "ACTIVE",
        }

    rented = {
        "__typename": "RentalStatusChangeOfInterest",
        "date": "2026-06-01",
        "status": "RENTED",
    }
    first = [
        {
            "listingId": "9000011",
            "rentalEventsOfInterest": [
                active("2026-05-01", 3000),
                active("2026-05-01", 3000),
                active("2026-05-01", None),
            ],
        },
        {
            "id": "9000012",
            "listingId": None,
            "rentalEventsOfInterest": [active("2026-04-01", 2900)],
        },
    ]
    later = [
        {
            **first[0],
            "rentalEventsOfInterest": first[0]["rentalEventsOfInterest"] + [rented],
        },
        first[1],
    ]
    records = [
        (9000010, "2026-09-02", history_record(9000010, [])),
        (9000011, "2026-09-03", history_record(9000011, first)),
        (9000011, "2026-09-10", history_record(9000011, later)),
        (9000012, "2026-09-11", history_record(9000012, later)),
    ]
    append_answers(
        export,
        pd.DataFrame(
            {
                "listing_id": [r[0] for r in records],
                "fetched": pd.to_datetime([f"{r[1]}T12:00:00Z" for r in records]),
                "response_id": [8, 9, 10, 11],
                "run": 5,
                "region": "cases",
                "generation": 1,
                "outcome": "record",
                "record_sha256": [
                    hashlib.sha256(r[2].encode()).hexdigest() for r in records
                ],
                "record": [r[2] for r in records],
            }
        ),
    )
    ctx = context(
        monkeypatch, tmp_path / "state", export, FIXTURE / "cases" / "rows.parquet"
    )
    ctx.plan(auto_apply=True, no_prompts=True)
    missing = ctx.fetchdf(
        "SELECT listing_id, price FROM ads.events WHERE kind = 'MISSING'"
    )
    assert missing.listing_id.tolist() == ["9000005"] and missing.price.isna().all()
    events = ctx.fetchdf(
        """SELECT listing_id, kind, day::VARCHAR AS day, price, own, first_seen::DATE::VARCHAR
        AS first_seen, last_seen::DATE::VARCHAR AS last_seen, first_response_id, answers,
        own_first_seen::DATE::VARCHAR AS own_first_seen, own_first_response_id
        FROM ads.events WHERE source = 'history'
        ORDER BY listing_id, day, kind, price NULLS LAST"""
    )
    assert events.astype(object).where(events.notna(), None).values.tolist() == [
        [
            "9000011",
            "ACTIVE",
            "2026-05-01",
            3000.0,
            True,
            "2026-09-03",
            "2026-09-11",
            9,
            3,
            "2026-09-03",
            9,
        ],
        [
            "9000011",
            "ACTIVE",
            "2026-05-01",
            None,
            True,
            "2026-09-03",
            "2026-09-11",
            9,
            3,
            "2026-09-03",
            9,
        ],
        [
            "9000011",
            "RENTED",
            "2026-06-01",
            None,
            True,
            "2026-09-10",
            "2026-09-11",
            10,
            2,
            "2026-09-10",
            10,
        ],
        [
            "9000012",
            "ACTIVE",
            "2026-04-01",
            2900.0,
            True,
            "2026-09-03",
            "2026-09-11",
            9,
            3,
            "2026-09-11",
            11,
        ],
    ]
    first_ask = ctx.fetchdf(
        """SELECT listing_id, first_day::VARCHAR AS first_day, prices, missing_price,
        first_seen::DATE::VARCHAR AS first_seen, first_response_id
        FROM ads.first_ask ORDER BY listing_id"""
    )
    assert [[*r[:2], list(r[2]), *r[3:]] for r in first_ask.values.tolist()] == [
        ["9000011", "2026-05-01", [3000.0], True, "2026-09-03", 9],
        ["9000012", "2026-04-01", [2900.0], False, "2026-09-11", 11],
    ]


def ad_record(listing_id, active, beds=1, pricing=None, description=None, details=True):
    """A record of ad `listing_id`, with an ACTIVE event in its own history for each (day,
    price) pair of `active`, `beds` bedrooms and one bathroom. Without `details` the record
    lacks propertyDetails, and a dict in `details` updates them."""
    record = json.loads(
        history_record(
            listing_id,
            [
                {
                    "listingId": str(listing_id),
                    "rentalEventsOfInterest": [
                        {
                            "__typename": "RentalStatusChangeOfInterest",
                            "date": day,
                            "price": price,
                            "status": "ACTIVE",
                        }
                        for day, price in active
                    ],
                }
            ],
        )
    )
    record["pricing"].update(pricing or {})
    record["description"] = description
    record["propertyDetails"] = (
        {"bedroomCount": beds, "fullBathroomCount": 1} if details else None
    )
    if isinstance(details, dict):
        record["propertyDetails"].update(details)
    return json.dumps(record, sort_keys=True)


def test_exclusion_cases(tmp_path, monkeypatch):
    """The made-up ads here cover each reason in ads.exclusions and the edges of its ranges.
    Ads 9000020 and 9000032 have no reason, ad 9000031's record lacks propertyDetails, and one
    of ad 9000032's records carries another ad's `id`. Ad 9000034 has two records with the same
    values, and ads 9000043 to 9000045 have two records with different values."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    may = [("2026-05-01", 3000)]
    records = [
        (9000020, ad_record(9000020, may)),
        (9000021, ad_record(9000021, may + [("2026-09-20", 3100)])),
        (9000022, ad_record(9000022, [("2009-12-31", 3000)])),
        (9000023, ad_record(9000023, may + [("2026-05-01", 3100)])),
        (9000024, ad_record(9000024, may + [("2026-05-01", None)])),
        (9000025, ad_record(9000025, may)),
        (9000025, ad_record(9000025, may, beds=2)),
        (9000026, ad_record(9000026, may, description="It comes furnished.")),
        (9000027, ad_record(9000027, may, pricing={"leaseTermMonths": 3})),
        (9000028, ad_record(9000028, may, pricing={"monthsFree": 1})),
        (9000029, ad_record(9000029, [("2026-05-01", 600)])),
        (9000030, ad_record(9000030, may, beds=6)),
        (9000031, ad_record(9000031, may, details=False)),
        (9000032, ad_record(9000032, may)),
        (9000032, ad_record(9000020, may, beds=2)),
        (9000033, ad_record(9000033, [])),
        (9000034, ad_record(9000034, may)),
        (9000034, ad_record(9000034, may, description="A bright one bedroom.")),
        (9000035, ad_record(9000035, [("2026-05-01", 750)])),
        (9000036, ad_record(9000036, [("2026-05-01", 50000)])),
        (9000037, ad_record(9000037, [("2026-05-01", 749)])),
        (9000038, ad_record(9000038, [("2026-05-01", 50001)])),
        (9000039, ad_record(9000039, may, beds=0)),
        (9000040, ad_record(9000040, may, beds=5)),
        (
            9000041,
            ad_record(
                9000041,
                may,
                details={"fullBathroomCount": None, "halfBathroomCount": 1},
            ),
        ),
        (
            9000042,
            ad_record(
                9000042, may, details={"fullBathroomCount": None, "bathroomCount": 1.25}
            ),
        ),
        (9000043, ad_record(9000043, may, details={"livingAreaSize": 500})),
        (9000043, ad_record(9000043, may, details={"livingAreaSize": 600})),
        (
            9000044,
            ad_record(
                9000044, may, details={"amenities": {"list": ["FULL_TIME_DOORMAN"]}}
            ),
        ),
        (
            9000044,
            ad_record(
                9000044, may, details={"amenities": {"list": ["PART_TIME_DOORMAN"]}}
            ),
        ),
        (9000045, ad_record(9000045, may, pricing={"leaseTermMonths": 12})),
        (9000045, ad_record(9000045, may, pricing={"leaseTermMonths": 3})),
        (
            9000046,
            ad_record(9000046, may, details={"features": {"list": ["FURNISHED"]}}),
        ),
    ]
    append_answers(
        export,
        pd.DataFrame(
            {
                "listing_id": [r[0] for r in records],
                "fetched": pd.Timestamp("2026-09-02T12:00:00Z")
                + pd.to_timedelta(range(len(records)), unit="min"),
                "response_id": range(20, 20 + len(records)),
                "run": 5,
                "region": "cases",
                "generation": 1,
                "outcome": "record",
                "record_sha256": [
                    hashlib.sha256(r[1].encode()).hexdigest() for r in records
                ],
                "record": [r[1] for r in records],
            }
        ),
    )
    ctx = context(
        monkeypatch, tmp_path / "state", export, FIXTURE / "cases" / "rows.parquet"
    )
    ctx.plan(auto_apply=True, no_prompts=True)
    got = ctx.fetchdf(
        """SELECT e.listing_id, e.reasons, e.rent, a.bedrooms, a.conflicts, a.records
        FROM ads.exclusions e LEFT JOIN ads.attributes a USING (listing_id)
        WHERE e.listing_id >= '9000020' ORDER BY e.listing_id"""
    )
    got = [
        [r[0], list(r[1]), r[2], r[3], None if r[4] is None else list(r[4]), r[5]]
        for r in got.astype(object).where(got.notna(), None).values.tolist()
    ]
    layout = "invalid_or_missing_layout"
    ask = "invalid_or_extreme_initial_ask"
    assert got == [
        ["9000020", [], 3000.0, 1.0, [], 1],
        ["9000021", ["future_own_active_event"], 3000.0, 1.0, [], 1],
        ["9000022", ["outside_date_window"], 3000.0, 1.0, [], 1],
        ["9000023", ["conflicting_or_missing_initial_prices", ask], None, 1.0, [], 1],
        ["9000024", ["conflicting_or_missing_initial_prices"], 3000.0, 1.0, [], 1],
        [
            "9000025",
            ["conflicting_layout_within_advertisement", layout],
            3000.0,
            None,
            ["bedrooms"],
            2,
        ],
        ["9000026", ["excluded_furnished"], 3000.0, 1.0, [], 1],
        ["9000027", ["excluded_short_term"], 3000.0, 1.0, [], 1],
        ["9000028", ["excluded_concession"], 3000.0, 1.0, [], 1],
        ["9000029", [ask], 600.0, 1.0, [], 1],
        ["9000030", [layout], 3000.0, 6.0, [], 1],
        ["9000031", ["no_dated_own_active_event"], 3000.0, None, None, None],
        ["9000032", [], 3000.0, 1.0, [], 1],
        ["9000033", ["no_dated_own_active_event"], None, 1.0, [], 1],
        ["9000034", [], 3000.0, 1.0, [], 2],
        ["9000035", [], 750.0, 1.0, [], 1],
        ["9000036", [], 50000.0, 1.0, [], 1],
        ["9000037", [ask], 749.0, 1.0, [], 1],
        ["9000038", [ask], 50001.0, 1.0, [], 1],
        ["9000039", [], 3000.0, 0.0, [], 1],
        ["9000040", [], 3000.0, 5.0, [], 1],
        ["9000041", [layout], 3000.0, 1.0, [], 1],
        ["9000042", [layout], 3000.0, 1.0, [], 1],
        [
            "9000043",
            ["conflicting_layout_within_advertisement"],
            3000.0,
            1.0,
            ["square_feet"],
            2,
        ],
        ["9000044", [], 3000.0, 1.0, ["doorman_type"], 2],
        ["9000045", ["excluded_short_term"], 3000.0, 1.0, [], 2],
        ["9000046", ["excluded_furnished"], 3000.0, 1.0, [], 1],
    ]
    flags = ctx.fetchdf(
        """SELECT listing_id, bathrooms, short_term, furnished FROM ads.attributes
        WHERE listing_id IN ('9000020', '9000041', '9000042', '9000045', '9000046')
        ORDER BY listing_id"""
    )
    assert flags.astype(object).where(flags.notna(), None).values.tolist() == [
        ["9000020", 1.0, None, None],
        ["9000041", 0.5, None, None],
        ["9000042", 1.25, None, None],
        ["9000045", 1.0, True, None],
        ["9000046", 1.0, None, True],
    ]
    unparsed = ctx.fetchdf(
        "SELECT id FROM ads.record_attributes WHERE NOT parsed AND id >= '9000020'"
    )
    assert unparsed.id.tolist() == ["9000031"]


class Failures(TerminalConsole):
    """A console that also keeps the errors of the models that failed."""

    failed = ()

    def log_failed_models(self, errors):
        self.failed = errors
        super().log_failed_models(errors)


def test_failed_audit_leaves_the_built_tables(tmp_path, monkeypatch):
    context(monkeypatch, tmp_path / "state").plan(auto_apply=True, no_prompts=True)
    rows = pd.read_parquet(FIXTURE / "rows.parquet")
    pd.concat([rows, rows.iloc[[0]]]).to_parquet(tmp_path / "rows.parquet", index=False)
    console = Failures()
    monkeypatch.setattr(sqlmesh.core.console, "_CONSOLE", console)
    ctx = context(monkeypatch, tmp_path / "state", rows=tmp_path / "rows.parquet")
    with pytest.raises(PlanError):
        ctx.plan(auto_apply=True, no_prompts=True)
    assert [(e.node.snapshot_name, str(e.__cause__)) for e in console.failed] == [
        ('"pipeline"."analysis"."latest_change"', "Audits failed: unique_values")
    ]
    pd.testing.assert_frame_equal(
        latest_ask(ctx), pd.read_parquet(FIXTURE / "latest-ask.parquet")
    )


def test_every_row_audit_catches_a_lost_row(tmp_path, monkeypatch):
    project = tmp_path / "project"
    shutil.copytree(
        PROJECT,
        project,
        ignore=shutil.ignore_patterns(".venv", "tests", "logs", "__pycache__"),
    )
    (tmp_path / "src").symlink_to(PROJECT.parent / "src")
    model = project / "models" / "analysis" / "latest_ask.sql"
    lost = "FROM s4 WHERE ordinal > (SELECT min(ordinal) FROM s4)"
    model.write_text(model.read_text().replace("FROM s4", lost))
    console = Failures()
    monkeypatch.setattr(sqlmesh.core.console, "_CONSOLE", console)
    ctx = context(monkeypatch, tmp_path / "state", project=project)
    with pytest.raises(PlanError):
        ctx.plan(auto_apply=True, no_prompts=True)
    assert [(e.node.snapshot_name, str(e.__cause__)) for e in console.failed] == [
        ('"pipeline"."analysis"."latest_ask"', "Audits failed: every_row")
    ]


@pytest.fixture
def config(tmp_path, monkeypatch):
    """The pipeline's config module, reading its manifest from an empty folder."""
    monkeypatch.setenv("PIPELINE_EXPORT", str(FIXTURE / "export"))
    monkeypatch.setenv("PIPELINE_ROWS", str(FIXTURE / "rows.parquet"))
    monkeypatch.setenv("PIPELINE_STATE", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("config", PROJECT / "config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "EXPORT", tmp_path / "export")
    (tmp_path / "export").mkdir()
    return module


def test_attributes_code_covers_its_imports(config):
    """The code version of ads.record_attributes covers steps.attributes and every module it
    loads from src."""
    script = (
        "import sys; sys.path[:0] = sys.argv[1:]; import steps.attributes; "
        "print(*(m.__file__ for n, m in sys.modules.items() "
        "if n.split('.')[0] in ('apartments', 'steps') and m.__file__))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", script, str(config.PIPELINE), str(config.SRC)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert sorted(loaded) == sorted(str(path) for path in config.ATTRIBUTES_CODE)


def test_exported_reads_whole_lines(config):
    manifest = config.EXPORT / "manifest.ndjson"

    def write(*entries, cut=None):
        text = "".join(
            json.dumps({"path": path, "sha256": sha, "table": table}) + "\n"
            for path, sha, table in entries
        )
        manifest.write_text(text + (cut or ""))

    write(("ads/b", "2", "ads"), ("ads/a", "1", "ads"), ("other/c", "3", "other"))
    paths, version = config.exported("ads")
    assert paths == [str(config.EXPORT / "ads/a"), str(config.EXPORT / "ads/b")]
    # The exporter's cut-off last line and a repeated line change nothing.
    cut = json.dumps({"path": "ads/d", "sha256": "4", "table": "ads"})
    write(("ads/a", "1", "ads"), ("ads/b", "2", "ads"), ("ads/a", "1", "ads"), cut=cut)
    assert config.exported("ads") == (paths, version)
    # A manifest written again gives a rewritten file its new hash.
    write(("ads/a", "1", "ads"), ("ads/b", "5", "ads"))
    assert config.exported("ads")[0] == paths
    assert config.exported("ads")[1] != version
    write(("ads/a", "1", "ads"), ("ads/a", "5", "ads"))
    with pytest.raises(ValueError, match="two hashes"):
        config.exported("ads")
    write(("other/c", "3", "other"))
    with pytest.raises(ValueError, match="lists no ads files"):
        config.exported("ads")
