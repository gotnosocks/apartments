import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
import sqlmesh.core.console
from apartments.canonical_units import memberships
from apartments.graphql_listing import canonical_link
from apartments.unit_canonical import unit_page
from sqlmesh import Context
from sqlmesh.core.console import TerminalConsole
from sqlmesh.utils.errors import PlanError
from sqlmesh.utils.metaprogramming import ExecutableKind
from sqlglot import exp

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixture"


def context(
    monkeypatch, state, export=FIXTURE / "export", project=PROJECT, ledger=None
):
    """A context on `export` and `state`. Without `ledger`, the corrections ledger is an empty
    folder beside the state. The helper makes the ledger's folder when it is missing."""
    ledger = ledger or state.parent / "ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PIPELINE_EXPORT", str(export))
    monkeypatch.setenv("PIPELINE_STATE", str(state))
    monkeypatch.setenv("PIPELINE_LEDGER", str(ledger))
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    return Context(paths=str(project))


def latest_ask(ctx):
    frame = ctx.fetchdf("SELECT * FROM analysis.latest_ask ORDER BY listing_id")
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


def append_answers(export, answers, table="ads"):
    """Write `answers` as a new file of run 5 of `table` and list it in the manifest."""
    first, last = answers.response_id.min(), answers.response_id.max()
    path = Path(table) / "run-0005" / f"responses-{first:07d}-{last:07d}.parquet"
    (export / path).parent.mkdir(parents=True, exist_ok=True)
    key = (
        "listing_id::BIGINT AS listing_id"
        if table == "ads"
        else "building_id::VARCHAR AS building_id"
    )
    db = duckdb.connect(config={"TimeZone": "UTC"})
    db.register("answers", answers)
    db.execute(
        f"""COPY (SELECT {key}, fetched::TIMESTAMPTZ AS fetched,
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
        "table": table,
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
    """analysis.latest_ask gives these made-up rows the latest asks `rentfrontier.latest_ask`
    chooses for them:

    - ad 9000120 changes its price after its first day. Its page price equals its first
      change, so the page price counts for nothing. Ad 9000130 changes its price only before
      its first day.
    - ad 9000121 has no price changes and a page price of $3,100. Ad 9000131 has no price
      changes either, and its page price equals its first ask, so its own ask stands.
    - ad 9000122 more than doubles its ask. The building's other one-bedrooms ask $3,000, so its
      first ask stands.
    - ad 9000123 drops below half its first ask, to near the building's two-bedrooms, so its
      latest ask stands.
    - ad 9000127 asks $12,500, and its page price of $1,250 lies nearer the two-bedrooms. Ad
      9000126 asks $800, and its page price of $8,000 lies nearer the one-bedrooms.
    - ad 9000128's latest answer is missing, so its earlier record stands. Ad 9000132's first
      record lists a rise to $3,400 in June, and its later record leaves the rise out, so its
      ask stays at $3,000.
    - ad 9000129 goes off the market and then rises to a placeholder of $10,000, which drops
      out.
    - ad 9000133 asks $30,000 and corrects the typo to $3,000 on its last day on the market.
      The placeholder check drops the correction, and the page price of $3,000 lies nearer the
      one-bedrooms.
    - ad 9000134 drops to a placeholder of $300 on its last day on the market. The page price of
      $300 enters the digit step, and the ask of $3,000 lies nearer the one-bedrooms."""
    monkeypatch.syspath_prepend(str(PROJECT.parent / "frontier" / "src"))
    from rentfrontier import latest_ask as chain

    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    tower = json.dumps({"id": "900020", "slug": "900020-case-street-new_york"})
    append_answers(
        export,
        answers("building_id", [("900020", tower)], 40, "2026-09-01T12:00Z"),
        "buildings",
    )

    def ad(listing_id, changes, price, ask=3000, beds=1, **values):
        """A record of ad `listing_id` in building 900020, first asking `ask` on May 1, with a
        price change for each (day, price) of `changes`, the page price `price` and `values`
        over its top-level fields."""
        pricing = {
            "price": price,
            "priceChanges": [
                {"changedAt": f"{day}T10:00:00.000-04:00", "price": p}
                for day, p in changes
            ],
        }
        text = row_record(
            listing_id,
            may,
            f"l{listing_id}",
            None,
            "900020",
            beds,
            ask=ask,
            pricing=pricing,
        )
        return listing_id, json.dumps({**json.loads(text), **values}, sort_keys=True)

    may, june, july = "2026-05-01", "2026-06-01", "2026-07-01"
    records = [
        ad(9000120, [(may, 3000), (june, 3200)], 3000),
        ad(9000130, [("2026-04-20", 2900)], 2900),
        ad(9000121, [], 3100),
        ad(9000131, [], 3000),
        ad(9000122, [(may, 3000), (june, 7000)], 7000),
        ad(9000123, [(may, 3000), (june, 1250)], 1250, beds=2),
        ad(9000124, [(may, 1200)], 1200, ask=1200, beds=2),
        ad(9000125, [(may, 1300)], 1300, ask=1300, beds=2),
        ad(9000127, [(may, 12500)], 1250, ask=12500, beds=2),
        ad(9000126, [(may, 800)], 8000, ask=800),
        ad(9000128, [(may, 3000), (july, 3300)], 3300),
        (9000128, None),
        ad(9000132, [(may, 3000), (june, 3400)], 3400),
        ad(9000132, [(may, 3000)], 3000),
        ad(
            9000129,
            [(may, 3000), ("2026-07-15", 10000)],
            10000,
            status="OFF_MARKET",
            offMarketAt=july,
        ),
        ad(
            9000133,
            [(may, 30000), (july, 3000)],
            3000,
            ask=30000,
            status="OFF_MARKET",
            offMarketAt=july,
        ),
        ad(
            9000134,
            [(may, 3000), (july, 300)],
            300,
            status="OFF_MARKET",
            offMarketAt=july,
        ),
    ]
    new = answers("listing_id", records, 20, "2026-09-02T12:00Z")
    append_answers(export, new)
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)

    # The chain's choice, over the same rows and each ad's latest record.
    rows = ctx.fetchdf(
        """SELECT listing_id AS audit_id, listing_id AS source_listing_id, price_at,
        asking_rent, building, bedrooms FROM analysis.rows ORDER BY listing_id"""
    )
    rows["log_rent"] = np.log(rows.asking_rent)
    table = pd.DataFrame(
        [
            {
                "listing_id": str(a.listing_id),
                "collected_at": a.fetched.timestamp(),
                **chain.record_latest(a.record),
            }
            for a in new.itertuples()
            if a.record
        ]
    )
    table = table.sort_values(["collected_at", "listing_id"])
    table = table.drop_duplicates("listing_id", keep="last").set_index("listing_id")
    expected = chain.choose(rows, table).rename(columns={"audit_id": "listing_id"})
    got = latest_ask(ctx)
    pd.testing.assert_frame_equal(got.drop(columns="price_at"), expected)
    assert got.set_index("listing_id").how["9000133"] == "page price, digit"
    assert dict(zip(got.listing_id, got.latest_ask)) == {
        "9000120": 3200,
        "9000121": 3100,
        "9000122": 3000,
        "9000123": 1250,
        "9000124": 1200,
        "9000125": 1300,
        "9000126": 8000,
        "9000127": 1250,
        "9000128": 3300,
        "9000129": 3000,
        "9000130": 2900,
        "9000131": 3000,
        "9000132": 3000,
        "9000133": 3000,
        "9000134": 3000,
    }
    assert set(got.how) == {
        "latest",
        "own ask, captured before the row",
        "page price",
        "first, nearer building",
        "latest, nearer building",
        "page price, digit",
    }


def test_ask_check_cases(tmp_path, monkeypatch):
    """analysis.ask_check lists these made-up rows of building 900030 for review, and
    analysis.rows keeps them:

    - ad 9000145 asks $31,000. The building's other one-bedrooms ask $2,900 to $3,200 and one
      asks $16,500, so their median is $3,050.
    - ad 9000154 asks $1,250. The building's other three-bedrooms ask $11,800 to $12,500, and
      ad 9000159 asks $26,000, so their median is $12,200.

    The check doesn't list these rows:

    - ad 9000146 asks $16,500, 5.4 times the median of the other one-bedrooms.
    - ad 9000149 asks $40,000, ten times the building's other two-bedrooms, but they are only
      two.
    - ad 9000158 asks $40,000, 20 times the building's other studios.
    - ad 9000159 asks $26,000 as a studio, 13 times the other studios. A ledger set makes it a
      three-bedroom, and it asks 2.2 times the other three-bedrooms.

    Each ad gives its ask in every record, so the latest-ask steps keep it. A second ledger file
    then gives ad 9000145 an ask set to $3,100, made on its recorded ask, and ad 9000154 an ask
    set made on an ask of $1,200. The first applies: the row asks $3,100, and the check stops
    listing it. The second goes stale, and the row keeps its ask and its place on the list. The
    ads file keeps each ad's ask from before the ledger."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    tower = json.dumps({"id": "900030", "slug": "900030-case-street-new_york"})
    append_answers(
        export,
        answers("building_id", [("900030", tower)], 40, "2026-09-01T12:00Z"),
        "buildings",
    )

    def ad(listing_id, unit, ask, beds):
        """A record of ad `listing_id` for `unit` of building 900030, asking `ask` from May 1,
        with `ask` as its page price."""
        pricing = {
            "price": ask,
            "priceChanges": [
                {"changedAt": "2026-05-01T10:00:00.000-04:00", "price": ask}
            ],
        }
        text = row_record(
            listing_id,
            "2026-05-01",
            unit,
            building="900030",
            beds=beds,
            ask=ask,
            pricing=pricing,
        )
        return listing_id, text

    asks = {
        1: [3000, 3100, 2900, 3200, 3000, 31000, 16500],
        2: [4000, 4100, 40000],
        3: [12000, 12500, 11800, 12200, 1250],
        0: [2000, 2100, 1900, 40000, 26000],
    }
    records, ids = [], {}
    for beds, prices in asks.items():
        for i, price in enumerate(prices):
            listing_id = 9000140 + len(records)
            ids[(beds, price)] = str(listing_id)
            records.append(ad(listing_id, f"{i + 1}{'sabc'[beds]}", price, beds))
    assert ids[(1, 31000)] == "9000145" and ids[(0, 26000)] == "9000159"
    append_answers(export, answers("listing_id", records, 20, "2026-09-02T12:00Z"))
    entry = {
        "decided": "2026-10-16",
        "evidence": [
            {"kind": "other_ad", "listing_id": "123", "detail": "the same unit"}
        ],
        "change": "set",
        "listing_id": ids[(0, 26000)],
        "set": {"bedrooms": 3},
        "when": {"bedrooms": 0},
    }
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "2026-10-16.ndjson").write_text(json.dumps(entry) + "\n")
    ctx = context(monkeypatch, tmp_path / "state", export, ledger=ledger)
    ctx.plan(auto_apply=True, no_prompts=True)

    flagged = ctx.fetchdf(
        """SELECT listing_id, latest_ask, peer_ask, peer_rows, round(ratio, 4) AS ratio
        FROM analysis.ask_check ORDER BY listing_id"""
    )
    assert flagged.to_dict("records") == [
        {
            "listing_id": ids[(1, 31000)],
            "latest_ask": 31000,
            "peer_ask": 3050,
            "peer_rows": 6,
            "ratio": 10.1639,
        },
        {
            "listing_id": ids[(3, 1250)],
            "latest_ask": 1250,
            "peer_ask": 12200,
            "peer_rows": 5,
            "ratio": 0.1025,
        },
    ]
    rows = set(ctx.fetchdf("SELECT listing_id FROM analysis.rows").listing_id)
    assert {str(listing_id) for listing_id, _ in records} <= rows
    ads = ctx.fetchdf(
        """SELECT listing_id, ask_check, in_rows FROM analysis.ads
        WHERE listing_id IN (SELECT listing_id FROM analysis.kept)"""
    ).set_index("listing_id")
    assert ads.loc[ids[(1, 31000)]].ask_check == {
        "peer_ask": 3050,
        "peer_rows": 6,
        "ratio": 31000 / 3050,
    }
    assert ads.ask_check.isna().sum() == len(ads) - 2
    assert ads.in_rows.all()

    other_ad = {
        "kind": "other_ad",
        "listing_id": "123",
        "detail": "the same unit a month earlier",
    }
    asks = [
        (ids[(1, 31000)], 3100, 31000),
        (ids[(3, 1250)], 12500, 1200),
    ]
    sets = [
        {
            **entry,
            "evidence": [{**other_ad, "ask": ask}],
            "listing_id": listing_id,
            "set": {"latest_ask": ask},
            "when": {"period": "2026-05", "latest_ask": recorded},
        }
        for listing_id, ask, recorded in asks
    ]
    (ledger / "2026-10-17.ndjson").write_text(
        "".join(json.dumps(line) + "\n" for line in sets)
    )
    ctx = context(monkeypatch, tmp_path / "state", export, ledger=ledger)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == [
        "analysis.ads",
        "analysis.ask_check",
        "analysis.rows",
        "ledger.entries",
        "ledger.status",
    ]
    status = ctx.fetchdf(
        """SELECT listing_id, field, status, differs FROM ledger.status
        WHERE file = '2026-10-17.ndjson' ORDER BY listing_id"""
    )
    assert status.values.tolist() == [
        [ids[(1, 31000)], "latest_ask", "live", ""],
        [ids[(3, 1250)], "latest_ask", "stale", "latest_ask"],
    ]
    rows = ctx.fetchdf(
        f"""SELECT r.listing_id, r.asking_rent, r.latest_ask, a.latest_ask AS ads_ask
        FROM analysis.rows r JOIN analysis.ads a USING (listing_id)
        WHERE r.listing_id IN {(ids[(1, 31000)], ids[(3, 1250)])} ORDER BY r.listing_id"""
    )
    assert rows.values.tolist() == [
        [ids[(1, 31000)], 31000, 3100, 31000],
        [ids[(3, 1250)], 1250, 1250, 1250],
    ]
    flagged = ctx.fetchdf("SELECT listing_id FROM analysis.ask_check")
    assert flagged.listing_id.tolist() == [ids[(3, 1250)]]


def test_new_export_file_rebuilds_only_downstream(tmp_path, monkeypatch):
    export = copy_export(
        tmp_path, keep=lambda line: line["run"] < 4 or line["table"] == "buildings"
    )
    context(monkeypatch, tmp_path / "state", export).plan(
        auto_apply=True, no_prompts=True
    )
    cache = tmp_path / "state" / "attributes"
    before = {path.name for path in cache.glob("*/*.parquet")}
    # The full manifest goes over the partial one in the same folder. With the same export path
    # and buildings lines, raw.buildings keeps its fingerprint.
    shutil.copy(FIXTURE / "export" / "manifest.ndjson", export / "manifest.ndjson")
    ctx = context(monkeypatch, tmp_path / "state", export)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == [
        "ads.answer_events",
        "ads.answers",
        "ads.attributes",
        "ads.breaks",
        "ads.changes",
        "ads.events",
        "ads.exclusions",
        "ads.first_ask",
        "ads.history_events",
        "ads.history_reports",
        "ads.identity",
        "ads.kept_changes",
        "ads.latest_record",
        "ads.market",
        "ads.placed",
        "ads.price_changes",
        "ads.record_attributes",
        "ads.regions",
        "ads.reported",
        "ads.touched",
        "analysis.ads",
        "analysis.ask_check",
        "analysis.building_certificates",
        "analysis.candidates",
        "analysis.kept",
        "analysis.latest_ask",
        "analysis.latest_change",
        "analysis.lot_facts",
        "analysis.lot_landmarks",
        "analysis.rows",
        "ledger.status",
        "ledger.unit_status",
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


def test_new_buildings_file_rebuilds_only_what_reads_buildings(tmp_path, monkeypatch):
    def early(line):
        return line["table"] == "ads" or line["run"] < 4

    export = copy_export(tmp_path, keep=early)
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    # Run 4 holds the only answer for building 82192, so its 49 ads have no page yet.
    assert ctx.fetchdf("SELECT count(page) AS n FROM ads.identity").n[0] == 180
    shutil.copy(FIXTURE / "export" / "manifest.ndjson", export / "manifest.ndjson")
    ctx = context(monkeypatch, tmp_path / "state", export)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == [
        "ads.identity",
        "ads.placed",
        "analysis.ads",
        "analysis.ask_check",
        "analysis.building_certificates",
        "analysis.candidates",
        "analysis.kept",
        "analysis.latest_ask",
        "analysis.latest_change",
        "analysis.lot_facts",
        "analysis.lot_landmarks",
        "analysis.rows",
        "buildings.details",
        "buildings.footprint_link",
        "buildings.latest_record",
        "buildings.lot_releases",
        "buildings.lots",
        "buildings.pad_link",
        "ledger.status",
        "ledger.unit_status",
        "raw.buildings",
    ]
    assert ctx.fetchdf("SELECT count(page) AS n FROM ads.identity").n[0] == 229


def test_new_city_file_rebuilds_only_its_view(tmp_path, monkeypatch):
    """A file added to the city archive changes the view of its table and the view of refused
    rows, and the load unpacks only that file."""
    city = tmp_path / "city"
    shutil.copytree(FIXTURE / "city", city)
    lines = (city / "manifest.ndjson").read_text().splitlines(keepends=True)
    (city / "manifest.ndjson").write_text(
        "".join(line for line in lines if json.loads(line)["source"] != "landmarks")
    )
    monkeypatch.setenv("PIPELINE_CITY", str(city))
    monkeypatch.setenv("PIPELINE_CITY_CACHE", str(tmp_path / "cache"))
    ctx = context(monkeypatch, tmp_path / "state")
    ctx.plan(auto_apply=True, no_prompts=True)
    # With no file in the archive, the view has the added columns and no rows.
    landmarks = ctx.fetchdf("SELECT * FROM city.landmarks")
    assert list(landmarks) == [
        "release",
        "published",
        "file",
        "member",
        "record",
        "encoding",
    ]
    assert landmarks.empty
    before = set((tmp_path / "cache").glob("*/*"))
    (city / "manifest.ndjson").write_text("".join(lines))
    ctx = context(monkeypatch, tmp_path / "state")
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == ["analysis.lot_landmarks", "city.landmarks", "city.rejects"]
    (added,) = {
        path for path in (tmp_path / "cache").glob("*/*") if path.is_dir()
    } - before
    assert sorted(path.name for path in added.iterdir()) == [
        "landmarks-0.parquet",
        "rejects.parquet",
    ]
    assert ctx.fetchdf("SELECT count(*) AS n FROM city.landmarks").n[0] == 29


def test_pad_street_fields(render_context):
    """The view of PAD's street names cuts each record into fields, and leaves out the header
    record and the records of type S. The fixture's 26c dictionary has 276 records of other
    types."""
    view = render_context.render("city.pad_streets").sql(dialect="duckdb")
    streets = duckdb.sql(f"SELECT * FROM ({view}) WHERE release = '26c'")
    rows = streets.df()
    assert len(rows) == 276
    assert set(rows.gft) == {" ", "N", "B", "X", "G"}
    (broadway,) = rows[rows.stname == "BROADWAY".ljust(32)].itertuples()
    assert (
        broadway.boro,
        broadway.primary_flag,
        broadway.principal_flag,
        broadway.b10sc,
        broadway.sc5,
        broadway.lgc,
        broadway.spv,
        broadway.numeric_ind,
        broadway.gft,
        broadway.len_full_name,
        broadway.full_stname,
        broadway.stn20,
        broadway.ht_name_type_code,
    ) == (
        "1",
        "P",
        "F",
        "11361001010",
        "13610",
        "01",
        "010",
        " ",
        " ",
        "08",
        "BROADWAY".ljust(32),
        " " * 20,
        " ",
    )


def test_code_change_starts_a_new_cache_folder(tmp_path, monkeypatch):
    """A change to the projection's code gives ads.record_attributes a new code version, and the
    build parses every record again into a new folder. A build stops when the venv loads code
    other than the code config.py hashed."""
    project = tmp_path / "project"
    shutil.copytree(
        PROJECT,
        project,
        ignore=shutil.ignore_patterns(".venv", "tests", "logs", "__pycache__"),
    )
    (tmp_path / "src").symlink_to(PROJECT.parent / "src")
    export = copy_export(tmp_path, keep=lambda line: line["run"] == 2)
    ctx = context(monkeypatch, tmp_path / "state", export, project=project)
    ctx.plan(auto_apply=True, no_prompts=True)
    ctx.close()
    cache = tmp_path / "state" / "attributes"
    (old,) = cache.iterdir()
    code = project / "steps" / "attributes.py"
    line = '"bedrooms": number(details.get("bedroomCount")),'
    assert code.read_text().count(line) == 1
    code.write_text(code.read_text().replace(line, '"bedrooms": 9,'))
    # The venv's editable install loads the unchanged steps.attributes of this repo.
    console = Failures()
    monkeypatch.setattr(sqlmesh.core.console, "_CONSOLE", console)
    ctx = context(monkeypatch, tmp_path / "state", export, project=project)
    with pytest.raises(PlanError):
        ctx.plan(auto_apply=True, no_prompts=True)
    ctx.close()
    message = (
        f"the build loaded steps.attributes from {PROJECT / 'steps' / 'attributes.py'}, "
        "which differs from the file config.py hashed; run `uv sync` in the pipeline "
        "folder of the checkout to build"
    )
    # SQLMesh gives the model's error as a traceback, which ends in the error's message.
    assert [
        (e.node.snapshot_name, str(e.__cause__).strip().endswith(message))
        for e in console.failed
    ] == [('"pipeline"."ads"."record_attributes"', True)]
    assert list(cache.iterdir()) == [old]
    # A fresh process with the copy first on its path loads the changed code.
    build = subprocess.run(
        [Path(sys.executable).parent / "sqlmesh", "-p", project, "plan"]
        + ["--auto-apply", "--no-prompts"],
        env={**os.environ, "PYTHONPATH": f"{project}{os.pathsep}{tmp_path / 'src'}"},
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    (new,) = set(cache.iterdir()) - {old}

    def parsed(folder):
        return pd.concat(map(pd.read_parquet, folder.glob("*.parquet")))

    old, new = parsed(old), parsed(new)
    assert sorted(new.record_sha256) == sorted(old.record_sha256)
    assert len(set(old[old.parsed].bedrooms)) > 1
    assert set(new[new.parsed].bedrooms) == {"9"}


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


def test_fingerprints_hold_across_hash_seeds(tmp_path, render_context):
    """Each model has the same fingerprint in processes with different hash seeds. The text of a
    set of strings changes with the seed, so a model reading one would get a new fingerprint in
    each new build process, and the build would rebuild it and everything below it."""
    # SQLMesh fingerprints a model's Python values by their text. The test parses each value's
    # text and lists the values holding a set, or text Python can't parse, such as an object's
    # address.
    unstable = []
    for model in render_context.models.values():
        for name, value in model.python_env.items():
            if value.kind != ExecutableKind.VALUE:
                continue
            try:
                tree = ast.parse(value.payload, mode="eval")
            except SyntaxError:
                unstable.append((model.name, name))
                continue
            if any(
                isinstance(node, (ast.Set, ast.SetComp))
                or isinstance(node, ast.Call)
                and getattr(node.func, "id", None) in ("set", "frozenset")
                for node in ast.walk(tree)
            ):
                unstable.append((model.name, name))
    assert unstable == []

    # Each process gets its own state, since a second load would read the SQL models from the
    # first one's cache.
    script = (
        "import json, sys; from sqlmesh import Context; "
        "print(json.dumps({s.name: s.fingerprint.to_identifier() "
        "for s in Context(paths=sys.argv[1]).snapshots.values()}))"
    )
    (tmp_path / "ledger").mkdir()

    def load(seed):
        return subprocess.Popen(
            [sys.executable, "-c", script, str(PROJECT)],
            env=os.environ
            | {
                "PYTHONHASHSEED": str(seed),
                "PIPELINE_EXPORT": str(FIXTURE / "export"),
                "PIPELINE_STATE": str(tmp_path / f"state-{seed}"),
                "PIPELINE_LEDGER": str(tmp_path / "ledger"),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def fingerprints(loading):
        out, err = loading.communicate()
        assert loading.returncode == 0, err
        return json.loads(out.splitlines()[-1])

    # Both processes load the project at once.
    first, second = map(fingerprints, [load(1), load(2)])
    assert len(first) == len(render_context.models)
    assert first == second


def test_later_answer_replaces_an_earlier_one(tmp_path, monkeypatch):
    """A newer answer for an ad replaces its earlier one, and an older answer changes nothing."""
    expected = pd.read_parquet(FIXTURE / "latest-ask.parquet")
    steady = expected[
        (expected.how == "latest") & (expected.latest_ask == expected.first_ask)
    ]
    steady = steady.set_index("listing_id").latest_ask
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
    moved = expected.listing_id == str(relisted.listing_id)
    assert got.latest_ask[moved].tolist() == [price]
    assert got.how[moved].tolist() == ["latest"]
    pd.testing.assert_frame_equal(got[~moved], expected[~moved])


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
    ctx = context(monkeypatch, tmp_path / "state", export)
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


def ad_record(
    listing_id,
    active,
    beds=1,
    pricing=None,
    description=None,
    details=True,
    status="ACTIVE",
):
    """A record of ad `listing_id` with status `status`, with an ACTIVE event in its own
    history for each (day, price) pair of `active`, `beds` bedrooms and one bathroom. Without
    `details` the record lacks propertyDetails, and a dict in `details` updates them."""
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
    record["status"] = status
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
    values, and ads 9000043 to 9000045 have two records with different values.
    Ads 9000047 to 9000050 cover the cut at an ad's last ACTIVE answer. Ad 9000047's RENTED
    record comes after its ACTIVE one and stays out. Ad 9000048's record off the market comes
    between two ACTIVE ones and merges. Ad 9000049 has no ACTIVE record, so all its records
    merge. Ad 9000050's DELISTED record states a concession and two bedrooms after its ACTIVE
    record. The concession counts and the bedrooms stay out."""
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
        (9000047, ad_record(9000047, may)),
        (9000047, ad_record(9000047, may, beds=2, status="RENTED")),
        (9000048, ad_record(9000048, may, details={"livingAreaSize": 500})),
        (
            9000048,
            ad_record(
                9000048,
                may,
                details={"livingAreaSize": 600},
                status="TEMPORARILY_OFF_MARKET",
            ),
        ),
        (9000048, ad_record(9000048, may, details={"livingAreaSize": 500})),
        (9000049, ad_record(9000049, may, status="DELISTED")),
        (9000049, ad_record(9000049, may, beds=2, status="DELISTED")),
        (9000050, ad_record(9000050, may)),
        (
            9000050,
            ad_record(
                9000050, may, beds=2, pricing={"monthsFree": 1}, status="DELISTED"
            ),
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
    ctx = context(monkeypatch, tmp_path / "state", export)
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
        ["9000047", [], 3000.0, 1.0, [], 1],
        [
            "9000048",
            ["conflicting_layout_within_advertisement"],
            3000.0,
            1.0,
            ["square_feet"],
            2,
        ],
        [
            "9000049",
            ["conflicting_layout_within_advertisement", layout],
            3000.0,
            None,
            ["bedrooms"],
            2,
        ],
        ["9000050", ["excluded_concession"], 3000.0, 1.0, [], 1],
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


def market_record(listing_id, changes, days=None, rented=None):
    """A record of ad `listing_id` with a status change for each (day, status) pair of
    `changes`, at 10:00 New York time or at the hour a third item gives, and its daysOnMarket
    and rentedPrice."""
    record = json.loads(history_record(listing_id, None))
    record["statusChanges"] = [
        {
            "changedAt": f"{day}T{hour[0] if hour else '10'}:00:00.000-04:00",
            "status": status,
        }
        for day, status, *hour in changes
    ]
    record["status"] = changes[-1][1] if changes else "DRAFT"
    record["daysOnMarket"] = days
    record["pricing"]["rentedPrice"] = rented
    return json.dumps(record, sort_keys=True)


def test_market_cases(tmp_path, monkeypatch):
    """Ad 9000050 goes into contract and back on the market before it rents, ad 9000051 is
    paused and back on the market, ad 9000052 never goes on it, and ad 9000053 has no status
    changes. Ad 9000054 has two answers, and the later one ends it. Ad 9000055 lists two pairs
    of changes at a shared instant, in an order other than the alphabet's. Ad 9000056 has two
    answers, and the later one leaves out the earlier one's ending, so the ad stays on the
    market. Ad 9000051's latest answer has no record, and ad 9000053's latest record has no
    daysOnMarket."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    back = [
        ("2026-05-01", "ACTIVE"),
        ("2026-05-11", "IN_CONTRACT"),
        ("2026-05-15", "ACTIVE"),
        ("2026-05-15", "ACTIVE", "16"),
        ("2026-05-20", "RENTED"),
    ]
    paused = [
        ("2026-08-10", "ACTIVE"),
        ("2026-08-15", "TEMPORARILY_OFF_MARKET"),
        ("2026-08-20", "ACTIVE"),
    ]
    records = [
        (9000050, market_record(9000050, back, days=15, rented=2950)),
        (9000051, market_record(9000051, paused, days=18)),
        (
            9000052,
            market_record(
                9000052, [("2026-05-01", "DRAFT"), ("2026-05-03", "DELISTED")], days=0
            ),
        ),
        (9000053, market_record(9000053, [], days=7)),
        (9000053, market_record(9000053, [])),
        (9000054, market_record(9000054, [("2026-07-01", "ACTIVE")], days=30)),
        (
            9000054,
            market_record(
                9000054,
                [("2026-07-01", "ACTIVE"), ("2026-07-31", "NO_LONGER_AVAILABLE")],
                days=31,
            ),
        ),
        (
            9000055,
            market_record(
                9000055,
                [
                    ("2026-06-01", "DRAFT"),
                    ("2026-06-02", "IN_STREETEASY_REVIEW"),
                    ("2026-06-02", "ACTIVE"),
                    ("2026-06-02", "ACTIVE", "15"),
                    ("2026-06-12", "RENTED"),
                    ("2026-06-12", "NO_LONGER_AVAILABLE"),
                ],
                days=10,
            ),
        ),
        (
            9000056,
            market_record(
                9000056,
                [("2026-08-01", "ACTIVE"), ("2026-08-20", "NO_LONGER_AVAILABLE")],
                days=19,
            ),
        ),
        (9000056, market_record(9000056, [("2026-08-01", "ACTIVE")], days=32)),
        (9000051, None),
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
                "outcome": ["missing" if r[1] is None else "record" for r in records],
                "record_sha256": [
                    r[1] and hashlib.sha256(r[1].encode()).hexdigest() for r in records
                ],
                "record": [r[1] for r in records],
            }
        ),
    )
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    got = ctx.fetchdf(
        """SELECT listing_id, as_of::VARCHAR, status, on_day::VARCHAR, off_day::VARCHAR,
        active_days, active_spans, ending, ending_day::VARCHAR, record_days_on_market,
        rented_price FROM ads.market WHERE listing_id >= '9000050' ORDER BY listing_id"""
    )
    got = got.astype(object).where(got.notna(), None).values.tolist()
    day = "2026-09-02"
    assert got == [
        ["9000050", day, "RENTED", "2026-05-01", "2026-05-20", 15, 2]
        + ["RENTED", "2026-05-20", 15, 2950.0],
        ["9000051", day, "ACTIVE", "2026-08-10", None, 18, 2, None, None, 18, None],
        ["9000052", day, "DELISTED", None, None, 0, 0]
        + ["DELISTED", "2026-05-03", 0, None],
        ["9000053", day, "DRAFT", None, None, 0, 0, None, None, None, None],
        ["9000054", day, "NO_LONGER_AVAILABLE", "2026-07-01", "2026-07-31", 30, 1]
        + ["NO_LONGER_AVAILABLE", "2026-07-31", 31, None],
        ["9000055", day, "NO_LONGER_AVAILABLE", "2026-06-02", "2026-06-12", 10, 1]
        + ["NO_LONGER_AVAILABLE", "2026-06-12", 10, None],
        ["9000056", day, "ACTIVE", "2026-08-01", None, 32, 1, None, None, 32, None],
    ]


def answers(key, records, first, fetched):
    """A frame of run-5 answers: each of `records` is a key and a record, or None for a missing
    answer, with response IDs from `first` and a minute apart from `fetched`."""
    return pd.DataFrame(
        {
            key: [r[0] for r in records],
            "fetched": pd.Timestamp(fetched)
            + pd.to_timedelta(range(len(records)), unit="min"),
            "response_id": range(first, first + len(records)),
            "run": 5,
            "region": "cases",
            "generation": 1,
            "outcome": ["missing" if r[1] is None else "record" for r in records],
            "record_sha256": [
                r[1] and hashlib.sha256(r[1].encode()).hexdigest() for r in records
            ],
            "record": [r[1] for r in records],
        }
    )


def identity_record(listing_id, building=None, slug=None):
    """An ad record with the building ID and unit slug given, leaving out each one not given."""
    record = {"id": str(listing_id), "status": "ACTIVE"}
    if building is not None:
        record["buildingId"] = building
    if slug is not None:
        record["slug"] = slug
    return json.dumps(record, sort_keys=True)


def test_identity_cases(tmp_path, monkeypatch):
    """ads.identity gives each ad the unit page and unit that the current chain's
    `canonical_units.memberships` gives it, on these cases:

    - ads 9000060 and 9000061 give the same page, so they share a unit.
    - ad 9000062 gives two pages, and ad 9000063 gives the second of them, so neither gets a
      unit.
    - ads 9000064, 9000065 and 9000066 give an empty unit slug, none, and one with a '/'.
    - ad 9000067 names a building missing from the export.
    - ad 9000068 names a building that a later answer renames.
    - ad 9000069's latest answer is missing, so its record stands.
    - ad 9000070's building slug holds a '|', as one slug in the full export does.
    - ad 9000071's latest record names no building.
    - the case fixture's own ads name no building.

    Building 900001's latest answer is missing, so its record stands."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    tower = "1-case-street-new_york"
    buildings = [
        ("900002", json.dumps({"id": "900002", "slug": "2-old-name-new_york"})),
        ("900002", json.dumps({"id": "900002", "slug": "2-new-name-new_york"})),
        ("900003", json.dumps({"id": "900003", "slug": "111|2-case-street-new_york"})),
        ("900001", None),
    ]
    append_answers(
        export, answers("building_id", buildings, 40, "2026-09-01T12:00Z"), "buildings"
    )
    records = [
        (9000060, identity_record(9000060, "900001", "4a")),
        (9000060, identity_record(9000060, "900001", "4a")),
        (9000061, identity_record(9000061, "900001", "4a")),
        (9000062, identity_record(9000062, "900001", "5b")),
        (9000062, identity_record(9000062, "900001", "5c")),
        (9000063, identity_record(9000063, "900001", "5c")),
        (9000064, identity_record(9000064, "900001", "")),
        (9000065, identity_record(9000065, "900001")),
        (9000066, identity_record(9000066, "900001", "6/a")),
        (9000067, identity_record(9000067, "999999", "7a")),
        (9000068, identity_record(9000068, "900002", "8a")),
        (9000069, identity_record(9000069, "900001", "9a")),
        (9000069, None),
        (9000070, identity_record(9000070, "900003", "10a")),
        (9000071, identity_record(9000071, "900001", "11a")),
        (9000071, identity_record(9000071, None, "11a")),
    ]
    append_answers(export, answers("listing_id", records, 20, "2026-09-02T12:00Z"))
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)

    # The chain's functions, with each record's building slug taken from the latest record of
    # its building, as ads.identity takes it.
    latest = {}
    for building_id, raw in ctx.fetchdf(
        """SELECT building_id, record FROM raw.buildings WHERE outcome = 'record'
        ORDER BY fetched, response_id"""
    ).values:
        latest[building_id] = json.loads(raw)
    captures = []
    for listing_id, raw in ctx.fetchdf(
        """SELECT listing_id::VARCHAR, record FROM raw.ads WHERE outcome = 'record'
        ORDER BY fetched, response_id"""
    ).values:
        record = json.loads(raw)
        href = canonical_link(latest.get(str(record.get("buildingId"))), record)
        captures.append(
            {"listing_id": listing_id, "canonical_unit_url": href and unit_page(href)}
        )
    expected = {
        m["listing_id"]: (m["canonical_unit_url"], m["unit_id"])
        for m in memberships(captures)
    }
    got = ctx.fetchdf(
        "SELECT listing_id, page, unit_id, building, reasons FROM ads.identity"
    )
    got = got.astype(object).where(got.notna(), None).set_index("listing_id")
    assert {i: (r.page, r.unit_id) for i, r in got.iterrows()} == expected
    assert all((r.unit_id is None) == (len(r.reasons) == 2) for _, r in got.iterrows())

    page = "https://streeteasy.com/building/{}/{}".format
    assert (
        got.unit_id["9000060"]
        == got.unit_id["9000061"]
        == (f"unit:{uuid.uuid5(uuid.NAMESPACE_URL, page(tower, '4a'))}")
    )
    assert got.page["9000063"] == page(tower, "5c")
    assert got.loc[["9000062", "9000063", "9000064", "9000065"], "unit_id"].isna().all()
    assert got.loc[["9000066", "9000067", "9000071", "9000001"], "unit_id"].isna().all()
    assert got.page["9000068"] == page("2-new-name-new_york", "8a")
    assert got.page["9000070"] == page("111|2-case-street-new_york", "10a")
    assert got.unit_id["9000069"] is not None and got.unit_id["9000070"] is not None
    assert got.building["9000060"] == tower and got.building["9000071"] is None


def chain_cohort():
    """The chain's `rentfrontier.cohort` module, loaded from its file."""
    path = PROJECT.parent / "frontier" / "src" / "rentfrontier" / "cohort.py"
    spec = importlib.util.spec_from_file_location("cohort", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The fixture's ads with a pet fee in the description and no other pet policy. The chain gives
# them none, and `steps.attributes` reads the fee as pets allowed.
PET_FEE_ADS = ("4771575",)


def test_rows_match_the_chain(tmp_path, monkeypatch):
    """analysis.rows gives the fixture's ads the rows the chain's analysis datasets give them,
    with the same values in every column the pipeline rebuilds, apart from the pet policy of
    the ads in PET_FEE_ADS."""
    ctx = context(monkeypatch, tmp_path / "state")
    ctx.plan(auto_apply=True, no_prompts=True)
    ours = """SELECT listing_id, price_at, period, unit_id, page, building, asking_rent,
        bedrooms, bathrooms, full_baths, half_baths, square_feet, listed_floor,
        label_derived_floor, floor_status, building_floor_count, advertised_floor,
        physical_floor, floors_above_ground, elevator, laundry_type, doorman_type, hvac_type,
        pet_policy, view_exposures::VARCHAR, window_exposures::VARCHAR, neighbourhood
        FROM analysis.rows"""
    chain = f"""SELECT source_listing_id, price_at, period, unit_id, canonical_unit_url,
        building, asking_rent, bedrooms, bathrooms, reported_full_bathrooms,
        reported_half_bathrooms, square_feet, listed_floor, label_derived_floor,
        floor_label_provenance ->> 'status',
        (floor_label_provenance ->> 'building_floor_count')::BIGINT, advertised_floor,
        physical_floor, floors_above_ground, elevator, laundry_type, doorman_type, hvac_type,
        CASE WHEN source_listing_id IN {PET_FEE_ADS} AND pet_policy IS NULL
            THEN 'allowed_restrictions_unknown' ELSE pet_policy END,
        view_exposures::VARCHAR, window_exposures::VARCHAR, neighbourhood
        FROM '{FIXTURE / "chain-rows.parquet"}'"""
    assert ctx.fetchdf(f"SELECT count(*) AS n FROM ({chain})").n[0] == 229
    assert ctx.fetchdf(f"SELECT count(*) AS n FROM ({ours})").n[0] == 229
    assert ctx.fetchdf(f"{ours} EXCEPT {chain}").empty
    assert ctx.fetchdf(f"{chain} EXCEPT {ours}").empty


def row_record(
    listing_id,
    day,
    unit,
    label=None,
    building="900010",
    beds=1,
    details=None,
    ask=3000,
    **kw,
):
    """A record of ad `listing_id` for unit `unit` of `building`, first asking `ask` on `day`,
    with the unit label `label` and `details` updating its propertyDetails."""
    record = json.loads(
        ad_record(listing_id, [(day, ask)], beds, details=details or True, **kw)
    )
    record["buildingId"] = building
    record["slug"] = unit
    if label is not None:
        record["propertyDetails"]["address"] = {"displayUnit": label}
    return json.dumps(record, sort_keys=True)


def test_row_cases(tmp_path, monkeypatch):
    """analysis.candidates and ads.reported give these made-up ads the floors, bathroom counts
    and unit-month fates of the chain's `rentfrontier.cohort`:

    - ads 9000080 and 9000081 list unit 1a in May, and the later one stands.
    - ads 900009 and 9000082 list unit 2b on the same day, and 900009 stands, as it comes
      later in text order.
    - ads 9000083 and 9000084 give unit 3c two bedroom counts in June, so neither stands.
      Ad 9000085 lists the unit again in July. Ads 9000109 and 9000110 give unit 4e two
      bathroom counts in June, so neither stands.
    - ads 9000086 to 9000097 and 9000108 cover the label rules, whitespace and '#' around a
      label, a label above the building's floor count, a two-digit label in a building without
      a count, two labels that disagree, an explicit floor and a missing label.
    - ads 9000098 to 9000103 cover the bathroom counts, and ads 9000104 to 9000107 the edges of
      the square-foot range.

    Building 900011 has no floor count, and its later answer renames its area. Building
    900012's first answer gives a floor count of 0 and its second gives 20.5."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)

    def building(building_id, **values):
        record = {"id": building_id, "slug": f"{building_id}-case-street-new_york"}
        return building_id, json.dumps({**record, **values}, sort_keys=True)

    buildings = [
        building("900010", floorCount=6, area={"name": "Case Hill"}),
        building("900011", area={"name": "Old Flats"}),
        building("900011", area={"name": "Case Flats"}),
        building("900012", floorCount=0),
        building("900012", floorCount=20.5, area={"name": "Case Hill"}),
    ]
    append_answers(
        export, answers("building_id", buildings, 40, "2026-09-01T12:00Z"), "buildings"
    )
    may, june, july = "2026-05-01", "2026-06-03", "2026-07-01"
    one = [
        (9000080, row_record(9000080, may, "1a", "1A")),
        (9000081, row_record(9000081, "2026-05-20", "1a", "1A")),
        (9000082, row_record(9000082, june, "2b", "#2B")),
        (900009, row_record(900009, june, "2b", "#2B")),
        (9000083, row_record(9000083, "2026-06-10", "3c", "3C")),
        (9000084, row_record(9000084, "2026-06-12", "3c", "3C", beds=2)),
        (9000085, row_record(9000085, july, "3c", "3C", beds=2)),
        (9000109, row_record(9000109, june, "4e", "4E")),
        (
            9000110,
            row_record(9000110, june, "4e", "4E", details={"fullBathroomCount": 2}),
        ),
        (9000086, row_record(9000086, may, "4d", "  # 4d\t")),
        (9000087, row_record(9000087, may, "1205", "1205", "900012")),
        (9000088, row_record(9000088, may, "n3a", "N3A")),
        (9000089, row_record(9000089, may, "5re", "5RE")),
        (9000090, row_record(9000090, may, "3rdfloor", "3rdFloor")),
        (9000091, row_record(9000091, may, "ph", "PH")),
        (9000092, row_record(9000092, may, "12a", "12A")),
        (9000093, row_record(9000093, may, "12a", "12A", "900011")),
        (9000094, row_record(9000094, may, "9a", "9A", "900011")),
        (9000095, row_record(9000095, may, "6a", "6A")),
        (9000095, row_record(9000095, may, "6a", "7A")),
        (
            9000096,
            row_record(
                9000096, may, "7a", "7A", description="This third-floor apartment."
            ),
        ),
        (9000097, row_record(9000097, may, "8a")),
        (9000108, row_record(9000108, may, "8h", "#")),
    ]
    baths = [
        (9000098, {"fullBathroomCount": 2, "halfBathroomCount": 1}),
        (9000098, {"fullBathroomCount": 2, "halfBathroomCount": 1}),
        (9000099, {"halfBathroomCount": 1}),
        (9000099, {"halfBathroomCount": 0}),
        (9000100, {"halfBathroomCount": -1}),
        (9000101, {"halfBathroomCount": 0.5}),
        (9000102, {"halfBathroomCount": True}),
        (9000103, {"fullBathroomCount": 2.0}),
        (9000104, {"livingAreaSize": 149}),
        (9000105, {"livingAreaSize": 150}),
        (9000106, {"livingAreaSize": 6000}),
        (9000107, {"livingAreaSize": 6001}),
    ]
    records = one + [
        (i, row_record(i, may, f"u{i}", "2A", details=d)) for i, d in baths
    ]
    append_answers(export, answers("listing_id", records, 20, "2026-09-02T12:00Z"))
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)

    def frame(sql):
        got = ctx.fetchdf(sql)
        return got.astype(object).where(got.notna(), None).set_index("listing_id")

    # The chain's functions on each ad's labels and bathroom counts.
    cohort = chain_cohort()
    values = {}
    for listing_id, raw in ctx.fetchdf(
        """SELECT listing_id::VARCHAR, record FROM raw.ads WHERE outcome = 'record'
        ORDER BY fetched, response_id"""
    ).values:
        details = json.loads(raw).get("propertyDetails") or {}
        seen = values.setdefault(listing_id, ([], [], []))
        seen[0].append((details.get("address") or {}).get("displayUnit"))
        seen[1].append(details.get("fullBathroomCount"))
        seen[2].append(details.get("halfBathroomCount"))
    reported = frame(
        "SELECT listing_id, label_floor, full_baths, half_baths FROM ads.reported"
    )
    expected = {}
    for listing_id, (labels, full, half) in values.items():
        reads = {cohort.label_floor(label)[1] for label in labels}
        floor = next(iter(reads)) if len(reads) == 1 else None
        expected[listing_id] = (
            floor,
            cohort.consensus(full),
            cohort.consensus(half),
        )
    assert {i: tuple(r) for i, r in reported.iterrows()} == expected

    got = frame(
        """SELECT listing_id, fate, listed_floor, label_derived_floor, floor_status,
        building_floor_count, advertised_floor, square_feet, full_baths, half_baths,
        neighbourhood, regions FROM analysis.candidates"""
    )
    for listing_id, row in got.iterrows():
        floor, status = cohort.floor_of(
            {"advertised_floor": row.advertised_floor},
            values[listing_id][0],
            row.building_floor_count,
        )
        assert (row.listed_floor, row.floor_status) == (floor, status)
        assert row.label_derived_floor == (floor if status == "label_proxy" else None)

    def fates(*ids):
        return got.loc[[str(i) for i in ids], "fate"].tolist()

    assert fates(9000080, 9000081, 9000082, 900009) == [
        "superseded_in_unit_month",
        "kept",
        "superseded_in_unit_month",
        "kept",
    ]
    assert fates(9000083, 9000084, 9000085) == 2 * [
        "conflicting_layout_same_unit_month"
    ] + ["kept"]
    assert fates(9000109, 9000110) == 2 * ["conflicting_layout_same_unit_month"]
    floors = got.loc[[str(i) for i in range(9000086, 9000098)] + ["9000108"]]
    assert floors[["listed_floor", "floor_status"]].values.tolist() == [
        [4, "label_proxy"],
        [12, "label_proxy"],
        [3, "label_proxy"],
        [5, "label_proxy"],
        [3, "label_proxy"],
        [None, "unresolved_or_conflicting_capture_labels"],
        [None, "above_captured_building_floor_count"],
        [None, "two_digit_label_without_building_count"],
        [9, "label_proxy"],
        [None, "unresolved_or_conflicting_capture_labels"],
        [3, "explicit_source_floor"],
        [None, "unresolved_or_conflicting_capture_labels"],
        [None, "unresolved_or_conflicting_capture_labels"],
    ]
    assert got.building_floor_count[["9000081", "9000087", "9000093"]].tolist() == [
        6,
        20,
        None,
    ]
    assert got.neighbourhood[["9000081", "9000087", "9000093"]].tolist() == [
        "Case Hill",
        "Case Hill",
        "Case Flats",
    ]
    assert all(list(r) == ["cases"] for r in got.regions)
    # Of the bathroom cases, only ads 9000098, 9000102 and 9000103 have a valid layout.
    assert reported.loc[[str(i) for i in range(9000098, 9000104)]].values.tolist() == [
        [2, 2, 1],
        [2, 1, None],
        [2, 1, None],
        [2, 1, None],
        [2, 1, None],
        [2, 2, None],
    ]
    assert sorted(
        got.index.intersection([str(i) for i in range(9000098, 9000108)])
    ) == [
        "9000098",
        "9000102",
        "9000103",
        "9000104",
        "9000105",
        "9000106",
        "9000107",
    ]
    assert got.square_feet[["9000104", "9000105", "9000106", "9000107"]].tolist() == [
        None,
        150,
        6000,
        None,
    ]
    rows = ctx.fetchdf("SELECT listing_id FROM analysis.rows").listing_id
    assert sorted(rows) == sorted(got.index[got.fate == "kept"])


class Failures(TerminalConsole):
    """A console that also keeps the errors of the models that failed."""

    failed = ()

    def log_failed_models(self, errors):
        self.failed = errors
        super().log_failed_models(errors)


def test_failed_audit_leaves_the_built_tables(tmp_path, monkeypatch):
    """An export file repeating an answer fails the audit of ads.answers. The plan stops there,
    and the tables of the earlier build stay as they were."""
    export = copy_export(tmp_path)
    context(monkeypatch, tmp_path / "state", export).plan(
        auto_apply=True, no_prompts=True
    )
    db = duckdb.connect(config={"TimeZone": "UTC"})
    repeated = db.execute(
        "SELECT * FROM read_parquet(?) ORDER BY response_id LIMIT 1",
        [str(FIXTURE / "export/ads/run-0002/*.parquet")],
    ).df()
    append_answers(export, repeated)
    console = Failures()
    monkeypatch.setattr(sqlmesh.core.console, "_CONSOLE", console)
    ctx = context(monkeypatch, tmp_path / "state", export)
    with pytest.raises(PlanError):
        ctx.plan(auto_apply=True, no_prompts=True)
    assert [(e.node.snapshot_name, str(e.__cause__)) for e in console.failed] == [
        ('"pipeline"."ads"."answers"', "Audits failed: unique_combination_of_columns")
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
    lost = "FROM s4 WHERE listing_id > (SELECT min(listing_id) FROM s4)"
    model.write_text(model.read_text().replace("FROM s4", lost))
    console = Failures()
    monkeypatch.setattr(sqlmesh.core.console, "_CONSOLE", console)
    ctx = context(monkeypatch, tmp_path / "state", project=project)
    with pytest.raises(PlanError):
        ctx.plan(auto_apply=True, no_prompts=True)
    assert [(e.node.snapshot_name, str(e.__cause__)) for e in console.failed] == [
        ('"pipeline"."analysis"."latest_ask"', "Audits failed: every_row")
    ]


def test_rewritten_file_without_a_new_hash_stops_the_load(tmp_path, monkeypatch):
    """An export file written again under its old manifest line stops the next load, though
    the file keeps its old modification time."""
    export = copy_export(tmp_path)
    context(monkeypatch, tmp_path / "state", export)
    line = json.loads((export / "manifest.ndjson").read_text().splitlines()[0])
    path = export / line["path"]
    before = path.stat()
    db = duckdb.connect()
    db.execute(
        f"COPY (SELECT * FROM '{path}') TO '{path}.new' (FORMAT parquet, COMPRESSION gzip)"
    )
    Path(f"{path}.new").replace(path)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(Exception, match="differs from its SHA-256 in the manifest"):
        context(monkeypatch, tmp_path / "state", export)


@pytest.mark.parametrize("source", ["another record", "no record"])
def test_record_with_another_hash_stops_the_load(tmp_path, monkeypatch, source):
    """An answer giving a record with the SHA-256 of another record, or of no record, stops the
    next load."""
    export = copy_export(tmp_path)
    db = duckdb.connect(config={"TimeZone": "UTC"})
    answers = db.execute(
        "SELECT * FROM read_parquet(?) WHERE outcome = 'record' ORDER BY response_id",
        [str(FIXTURE / "export/ads/*/*.parquet")],
    ).df()
    planted = answers.tail(1)
    digest = (
        answers.record_sha256.iloc[0]
        if source == "another record"
        else hashlib.sha256(b"planted").hexdigest()
    )
    assert digest != planted.record_sha256.iloc[0]
    planted = planted.assign(
        fetched=planted.fetched + pd.Timedelta(days=8),
        response_id=answers.response_id.max() + 1,
        run=5,
        record_sha256=digest,
    )
    append_answers(export, planted)
    message = f"the record of answer {planted.response_id.iloc[0]} in .* differs from its hash"
    with pytest.raises(Exception, match=message):
        context(monkeypatch, tmp_path / "state", export)


@pytest.fixture
def config(tmp_path, monkeypatch):
    """The pipeline's config module, reading its manifest from an empty folder."""
    monkeypatch.setenv("PIPELINE_EXPORT", str(FIXTURE / "export"))
    monkeypatch.setenv("PIPELINE_STATE", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("config", PROJECT / "config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "EXPORT", tmp_path / "export")
    (tmp_path / "export").mkdir()
    return module


def test_list_indexes_are_literals(render_context):
    """No model indexes a list in brackets with a computed position. SQLMesh renders each model
    through sqlglot, and sqlglot 30.8 adds 1 to such an index once it knows the list's type, so
    the models read computed positions with list_extract."""
    computed = [
        (name, bracket.sql("duckdb"))
        for name, model in render_context.models.items()
        if model.is_sql
        for bracket in model.query.find_all(exp.Bracket)
        if not all(isinstance(i, exp.Literal) for i in bracket.expressions)
    ]
    assert computed == []


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
    paths, version, files = config.exported("ads")
    assert paths == [str(config.EXPORT / "ads/a"), str(config.EXPORT / "ads/b")]
    assert files == {"ads/a": "1", "ads/b": "2"}
    # The exporter's cut-off last line and a repeated line change nothing.
    cut = json.dumps({"path": "ads/d", "sha256": "4", "table": "ads"})
    write(("ads/a", "1", "ads"), ("ads/b", "2", "ads"), ("ads/a", "1", "ads"), cut=cut)
    assert config.exported("ads") == (paths, version, files)
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


def answer_file(path, record, digest):
    """Write an export file at `path` with an answer giving `record` under `digest`. Either can
    be None."""
    duckdb.connect().execute(
        """COPY (SELECT 1::BIGINT AS response_id, 'record' AS outcome,
        ?::VARCHAR AS record_sha256, ?::VARCHAR AS record) TO '{}' (FORMAT parquet)""".format(
            path
        ),
        [digest, record],
    )
    return path


def test_check_files_hashes_new_or_changed_files(config, monkeypatch):
    def sha(text):
        return hashlib.sha256(text.encode()).hexdigest()

    first = answer_file(config.EXPORT / "first", "one", sha("one"))
    second = answer_file(config.EXPORT / "second", "two", sha("two"))
    listed = {"first": config.file_sha256(first), "second": config.file_sha256(second)}
    hashed = []
    file_sha256 = config.file_sha256
    monkeypatch.setattr(
        config,
        "file_sha256",
        lambda path: hashed.append(path.name) or file_sha256(path),
    )
    config.check_files(listed)
    assert hashed == ["first", "second"]
    # A file keeping its stat and its hash isn't read again.
    config.check_files(listed)
    assert hashed == ["first", "second"]
    # The same bytes written back, with the old modification time, give the file a new change
    # time and another read, and it passes.
    before = second.stat()
    second.write_bytes(second.read_bytes())
    os.utime(second, ns=(before.st_atime_ns, before.st_mtime_ns))
    config.check_files(listed)
    assert hashed == ["first", "second", "second"]
    # So does a new hash in the manifest, and the file fails it.
    with pytest.raises(ValueError, match="second differs from its SHA-256"):
        config.check_files({**listed, "second": sha("2")})
    # The record keeps the file checked before the failing one.
    config.check_files(listed)
    assert hashed == ["first"] + ["second"] * 4
    # A path with two hashes in two tables stops the check.
    with pytest.raises(ValueError, match="manifest gives second two hashes"):
        config.check_files(listed, {"second": sha("2")})
    # A file listed with its own hash fails when a record differs from its answer's hash, on
    # every check.
    answer_file(first, "three", sha("one"))
    listed["first"] = file_sha256(first)
    for _ in range(2):
        with pytest.raises(
            ValueError, match="answer 1 in .*first differs from its hash"
        ):
            config.check_files(listed)
    assert hashed[-2:] == ["first", "first"]
    # An unreadable record of the checks gets every file checked again.
    answer_file(first, "three", sha("three"))
    listed["first"] = file_sha256(first)
    config.check_files(listed)
    (config.STATE / "export-hashes.json").write_text("{")
    hashed.clear()
    config.check_files(listed)
    assert hashed == ["first", "second"]
    # An answer giving a record with no record and no hash fails too.
    answer_file(first, None, None)
    listed["first"] = file_sha256(first)
    with pytest.raises(ValueError, match="answer 1 in .*first differs from its hash"):
        config.check_files(listed)
