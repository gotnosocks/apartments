import importlib.util
import json
import shutil
from pathlib import Path

import duckdb
import pytest

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent
DIFF = REPO / "ops" / "pipeline" / "diff.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


diff = load("pipeline_diff", DIFF)


def edited(tmp_path, edits):
    """A copy of this checkout's pipeline with `edits`, a map from a file under `pipeline/` to
    a function of its text, beside a link to this checkout's src."""
    root = tmp_path / "edit"
    shutil.copytree(
        PROJECT,
        root / "pipeline",
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests"),
    )
    (root / "src").symlink_to(REPO / "src")
    for name, edit in edits.items():
        path = root / "pipeline" / name
        path.write_text(edit(path.read_text() if path.exists() else ""))
    return root


def run(tmp_path, root, *args):
    (tmp_path / "ledger").mkdir(exist_ok=True)
    out = tmp_path / "diff.json"
    status = diff.main(
        [
            "--base-dir",
            str(REPO),
            "--edit-dir",
            str(root),
            "--ledger",
            str(tmp_path / "ledger"),
            "--json",
            str(out),
            "--keep",
            str(tmp_path / "scratch"),
            *args,
        ]
    )
    return status, (json.loads(out.read_text()) if status == 0 else None)


def test_diff_reports_each_change(tmp_path, capsys):
    def narrow(text):
        old = "BETWEEN 150 AND 6000 THEN c.square_feet"
        assert text.count(old) == 1
        return text.replace(old, "BETWEEN 150 AND 700 THEN c.square_feet")

    def probe(text):
        old = "price AS latest_ask, how FROM s4"
        assert text.count(old) == 1
        return text.replace(old, "price AS latest_ask, how, 1 AS probe FROM s4")

    model = "MODEL (name analysis.probe, kind VIEW);\nSELECT listing_id FROM analysis.kept\n"
    root = edited(
        tmp_path,
        {
            "models/analysis/candidates.sql": narrow,
            "models/analysis/latest_ask.sql": probe,
            "models/analysis/probe.sql": lambda _: model,
        },
    )
    status, result = run(tmp_path, root, "--rows", "2")
    assert status == 0
    base = tmp_path / "scratch" / "base" / "tables"
    large = duckdb.sql(
        f"SELECT listing_id FROM '{base}/analysis.candidates.parquet' "
        "WHERE square_feet > 700 ORDER BY listing_id"
    ).fetchall()
    assert len(large) > 2
    models = result["models"]
    for name in ("analysis.candidates", "analysis.kept", "analysis.rows"):
        model = models[name]
        assert model["changed"] == len(large) and model["changed_columns"] == {
            "square_feet": len(large)
        }
        assert model["only_in_base"] == model["only_in_edit"] == 0
        assert [row["key"] for row in model["examples"]["changed"]] == [
            {"listing_id": listing_id} for (listing_id,) in large[:2]
        ]
        assert all(
            row["values"]["square_feet"][1] is None
            for row in model["examples"]["changed"]
        )
    assert models["analysis.latest_ask"]["columns_only_in_edit"] == ["probe"]
    assert not models["analysis.latest_ask"]["changed"]
    assert result["models_only_in_edit"] == ["analysis.probe"]
    assert result["models_only_in_base"] == []
    differs = {name for name, model in models.items() if model["differs"]}
    assert differs == {
        "analysis.candidates",
        "analysis.kept",
        "analysis.rows",
        "analysis.latest_ask",
    }
    printed = capsys.readouterr().out
    assert "analysis.probe: only in the edit" in printed
    assert f"listing_id={large[0][0]}: square_feet " in printed
    assert "unchanged: ads.answers, " in printed


def test_diff_compares_rows_without_a_grain(tmp_path):
    def no_price_events(text):
        return text.rstrip() + "\nWHERE v.__typename <> 'PriceChangeOfInterest'\n"

    root = edited(tmp_path, {"models/ads/history_events.sql": no_price_events})
    status, result = run(tmp_path, root)
    assert status == 0
    base = tmp_path / "scratch" / "base" / "tables"
    (prices,) = duckdb.sql(
        f"SELECT count(*) FROM '{base}/ads.history_events.parquet' WHERE kind = 'PRICE'"
    ).fetchone()
    assert prices > 0
    model = result["models"]["ads.history_events"]
    assert model["grain"] == [] and model["changed"] == 0
    assert model["only_in_base"] == prices and model["only_in_edit"] == 0
    assert model["rows"]["base"] - model["rows"]["edit"] == prices
    assert all(row["kind"] == "PRICE" for row in model["examples"]["only_in_base"])


def test_diff_stops_on_a_failed_build(tmp_path, capsys):
    def duplicate(text):
        return text.rstrip() + "\nUNION ALL (SELECT * FROM analysis.kept LIMIT 1)\n"

    root = edited(tmp_path, {"models/analysis/rows.sql": duplicate})
    status, _ = run(tmp_path, root)
    assert status == 1
    assert "the edit build stopped" in capsys.readouterr().err


def test_archive_writes_the_revision(tmp_path):
    diff.archive("HEAD", tmp_path / "code")
    assert (tmp_path / "code" / "pipeline" / "config.py").is_file()
    assert (tmp_path / "code" / "src" / "apartments").is_dir()
    assert not (tmp_path / "code" / "ops").exists()
