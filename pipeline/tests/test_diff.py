import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

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
    """A copy of this checkout's pipeline with `edits`, a map from a file under the checkout to
    a function of its text. The copy links to this checkout's src unless an edit is in src."""
    root = tmp_path / "edit"
    shutil.copytree(
        PROJECT,
        root / "pipeline",
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests"),
    )
    if any(name.startswith("src/") for name in edits):
        shutil.copytree(
            REPO / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__")
        )
    else:
        (root / "src").symlink_to(REPO / "src")
    for name, edit in edits.items():
        path = root / name
        if edit is None:
            path.unlink()
        else:
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
            "pipeline/models/analysis/candidates.sql": narrow,
            "pipeline/models/analysis/latest_ask.sql": probe,
            "pipeline/models/analysis/probe.sql": lambda _: model,
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

    root = edited(tmp_path, {"pipeline/models/ads/history_events.sql": no_price_events})
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


def test_diff_follows_steps_and_src(tmp_path):
    def no_size(text):
        old = '"square_feet": number(details.get("livingAreaSize")),'
        assert text.count(old) == 1
        return text.replace(old, '"square_feet": None,')

    def spaced(text):
        old = "separators=(',', ':')"
        assert text.count(old) == 1
        return text.replace(old, "separators=(', ', ': ')")

    root = edited(
        tmp_path,
        {
            "pipeline/steps/attributes.py": no_size,
            "src/apartments/corrections.py": spaced,
        },
    )
    status, result = run(tmp_path, root)
    assert status == 0
    base = tmp_path / "scratch" / "base" / "tables"
    sizes, lists = duckdb.sql(
        "SELECT count(square_feet), count(*) FILTER (view_exposures LIKE '%,%') "
        f"FROM '{base}/ads.record_attributes.parquet'"
    ).fetchone()
    assert sizes > 0 and lists > 0
    model = result["models"]["ads.record_attributes"]
    assert model["changed_columns"]["square_feet"] == sizes
    assert model["changed_columns"]["view_exposures"] >= lists


def test_diff_stops_on_a_failed_build(tmp_path, capsys):
    def duplicate(text):
        return text.rstrip() + "\nUNION ALL (SELECT * FROM analysis.kept LIMIT 1)\n"

    root = edited(tmp_path, {"pipeline/models/analysis/rows.sql": duplicate})
    status, _ = run(tmp_path, root)
    assert status == 1
    assert "the edit build stopped" in capsys.readouterr().err


def test_side_imports_only_its_own_steps():
    code = (
        f"import runpy; runpy.run_path({str(DIFF)!r})['isolate'](); "
        "import steps; print(list(steps.__path__))"
    )
    env = dict(
        os.environ, PYTHONPATH=os.pathsep.join([str(PROJECT), str(REPO / "src")])
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == repr([str(PROJECT / "steps")])


def tables(tmp_path, base, edit):
    """Write the queries `base` and `edit` to Parquet files and describe them as diff.side does."""
    sides = {}
    for which, query, grain in (("base", *base), ("edit", *edit)):
        path = tmp_path / f"{which}.parquet"
        duckdb.sql(f"COPY ({query}) TO '{path}' (FORMAT parquet)")
        sides[which] = {"grain": grain, "table": str(path)}
    return sides["base"], sides["edit"]


def compared(tmp_path, base, edit):
    return diff.compare_model(duckdb.connect(), *tables(tmp_path, base, edit), 5)


def test_compare_retyped_columns(tmp_path):
    result = compared(
        tmp_path,
        ("SELECT 1 AS id, 5 AS n UNION ALL SELECT 2, 6", ["id"]),
        ("SELECT '1' AS id, '05' AS n UNION ALL SELECT '2', 'six'", ["id"]),
    )
    assert result["retyped"] == {
        "id": ["INTEGER", "VARCHAR"],
        "n": ["INTEGER", "VARCHAR"],
    }
    assert result["changed"] == 2 and result["changed_columns"] == {"n": 2}
    assert result["examples"]["changed"][0] == {
        "key": {"id": "1"},
        "values": {"n": ["5", "05"]},
    }
    numbers = compared(
        tmp_path,
        ("SELECT 1 AS id, 5 AS n", ["id"]),
        ("SELECT 1.0::DOUBLE AS id, 5::BIGINT AS n", ["id"]),
    )
    assert (
        numbers["retyped"] and numbers["changed"] == 0 and numbers["only_in_base"] == 0
    )


def test_compare_repeated_grain_as_multisets(tmp_path):
    rows = "SELECT 1 AS id, 'a' AS v UNION ALL SELECT 1, 'b'"
    same = compared(tmp_path, (rows, ["id"]), (rows, ["id"]))
    assert not same["differs"] and same["grain"] == []
    assert (
        same["note"]
        == "rows compared as multisets: id repeats in the base and the edit"
    )
    moved = compared(tmp_path, (rows, ["id"]), ("SELECT 1 AS id, 'a' AS v", ["id"]))
    assert moved["only_in_base"] == 1 and moved["examples"]["only_in_base"] == [
        {"id": 1, "v": "b"}
    ]


def test_compare_grain_change_and_odd_columns(tmp_path):
    regrained = compared(
        tmp_path,
        ("SELECT 1 AS id, 2 AS d", ["id"]),
        ("SELECT 1 AS id, 2 AS d", ["id", "d"]),
    )
    assert regrained["differs"] and regrained["note"].endswith("the grain changed")
    assert regrained["only_in_base"] == regrained["only_in_edit"] == 0
    markers = compared(
        tmp_path,
        ("SELECT 1 AS id, true AS in_base, 1 AS in_edit", ["id"]),
        ("SELECT 1 AS id, true AS in_base, 1 AS in_edit", ["id"]),
    )
    assert not markers["differs"]
    apart = compared(tmp_path, ("SELECT 1 AS a", []), ("SELECT 1 AS b", []))
    assert apart["differs"] and apart["note"].startswith("rows not compared")


def test_archive_writes_the_revision(tmp_path):
    diff.archive("HEAD", tmp_path / "code")
    assert (tmp_path / "code" / "pipeline" / "config.py").is_file()
    assert (tmp_path / "code" / "src" / "apartments").is_dir()
    assert not (tmp_path / "code" / "ops").exists()
