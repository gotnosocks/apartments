import hashlib
import importlib.util
import json
import shutil
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
    export = copy_export(tmp_path / "full")
    ctx = context(monkeypatch, tmp_path / "state", export)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == [
        "ads.kept_changes",
        "ads.latest_record",
        "ads.price_changes",
        "analysis.latest_ask",
        "analysis.latest_change",
        "raw.ads",
    ]
    pd.testing.assert_frame_equal(
        latest_ask(ctx), pd.read_parquet(FIXTURE / "latest-ask.parquet")
    )
    again = (
        context(monkeypatch, tmp_path / "state", export).plan_builder("prod").build()
    )
    assert not again.has_changes and not again.new_snapshots


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
