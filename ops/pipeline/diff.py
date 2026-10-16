"""Build the pipeline's tables with the base code and with an edit, and list the differences.

    pipeline/.venv/bin/python ops/pipeline/diff.py [--base REV] [--export DIR] [--ledger DIR]
        [--rows N] [--json FILE] [--keep DIR]

1. The script writes `pipeline/` and `src/` at REV, HEAD unless given, to a scratch folder with
   `git archive`. These are the base. The edit is this checkout, with its uncommitted changes.
2. It builds both sides from empty at once, each in a process of its own. A side's process puts
   the side's `pipeline/` and `src/` first on `PYTHONPATH` and drops the folders added by the
   venv's .pth files. It plans the `prod` environment of the side's project and writes each
   model's table to a Parquet file. Both sides read the same export, the test fixture's unless
   given. Each side reads its own `pipeline/ledger`, or both read DIR with `--ledger`. When a
   plan stops, at an audit or an error, the script prints the side and the end of its output
   and exits with status 1.
3. It compares the sides' tables model by model:
   - a model with a grain: it joins the sides on the grain and counts the rows only in the base,
     the rows only in the edit and the rows with changed values, with a count for each changed
     column. When the grain changed, or repeats on a side, it compares the rows as multisets
     instead and notes the reason;
   - a model without a grain: it counts the rows of each side missing from the other, as
     multisets;
   - every model: it lists models and columns present on one side only, and columns with a new
     type. It compares rows on the columns present on both sides, and a retyped column by value
     when both types hold numbers, as text otherwise.
4. It prints a report, with up to N rows of each kind for each changed model (5 unless given)
   and then the unchanged models. With `--json` it writes the whole comparison to FILE as well.
   It deletes the scratch folder, or keeps it in DIR with `--keep`.

A plan in each side's process rebuilds every model, so an edit to a model, to `pipeline/steps`
or to `src/` shows in the tables. On thelio the script takes about 6 s.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "pipeline" / "tests" / "fixture" / "export"


class BuildError(Exception):
    pass


def archive(rev: str, dest: Path) -> None:
    """Write `pipeline/` and `src/` at `rev` into `dest`."""
    dest.mkdir(parents=True)
    tar = subprocess.run(
        ["git", "-C", str(REPO), "archive", rev, "pipeline", "src"],
        check=True,
        capture_output=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)


def build(root: Path, export: Path, ledger: Path | None, out: Path) -> float:
    """Build the project in `root/pipeline` from empty, in a process of its own, with its state
    and tables in `out`. Return the seconds the process took."""
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(root / "pipeline"), str(root / "src")]),
        PIPELINE_EXPORT=str(export),
        PIPELINE_STATE=str(out / "state"),
        PIPELINE_LEDGER=str(ledger or root / "pipeline" / "ledger"),
        PIPELINE_MEMORY="1GB",
        PIPELINE_WORKERS="2",
    )
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, __file__, "--side", str(root / "pipeline"), str(out)],
        env=env,
        capture_output=True,
        text=True,
    )
    if done.returncode:
        lines = (done.stdout + done.stderr).splitlines()
        raise BuildError("\n".join(lines[-30:]))
    return time.monotonic() - started


def isolate() -> None:
    """Drop the folders the venv's .pth files add to the import path, except those in
    PYTHONPATH."""
    # The venv's editable install puts its checkout's pipeline/ and src/ on the path, after this
    # side's code. As `steps` has no `__init__.py`, Python would merge that checkout's `steps`
    # into this side's, and a module missing here would load from there.
    own = set(os.environ.get("PYTHONPATH", "").split(os.pathsep))
    added = {
        line.strip()
        for folder in site.getsitepackages()
        for pth in Path(folder).glob("*.pth")
        for line in pth.read_text().splitlines()
        if line.strip() and not line.startswith(("#", "import"))
    }
    sys.path[:] = [p for p in sys.path if p in own or p not in added]


def side(project: Path, out: Path) -> None:
    """Plan `prod` for `project` and write each model's table and description to `out`."""
    isolate()
    from sqlglot import exp
    from sqlmesh import Context

    ctx = Context(paths=str(project))
    ctx.plan(auto_apply=True, no_prompts=True)
    (out / "tables").mkdir()
    models = {}
    for model in ctx.models.values():
        path = out / "tables" / f"{model.name}.parquet"
        ctx.engine_adapter.execute(
            f"COPY (SELECT * FROM {model.name}) TO '{path}' (FORMAT parquet)"
        )
        grain = [
            column.name
            for g in model.grains
            for column in (g.expressions if isinstance(g, exp.Tuple) else [g])
        ]
        models[model.name] = {"grain": grain, "table": str(path)}
    (out / "models.json").write_text(json.dumps(models, indent=1, sort_keys=True))


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


NUMBERS = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "UHUGEINT",
    "FLOAT",
    "DOUBLE",
}


def is_number(kind: str) -> bool:
    return kind in NUMBERS or kind.startswith("DECIMAL")


def compare_model(db, base: dict, edit: dict, rows: int) -> dict:
    """Compare a model's tables on the two sides."""
    types = {}
    for which, model in (("base", base), ("edit", edit)):
        described = db.execute(f"DESCRIBE SELECT * FROM '{model['table']}'").fetchall()
        types[which] = {name: kind for name, kind, *_ in described}
    common = [c for c in types["edit"] if c in types["base"]]
    result = {
        "rows": {
            which: db.execute(f"SELECT count(*) FROM '{m['table']}'").fetchone()[0]
            for which, m in (("base", base), ("edit", edit))
        },
        "grains": {"base": base["grain"], "edit": edit["grain"]},
        "columns_only_in_base": [c for c in types["base"] if c not in types["edit"]],
        "columns_only_in_edit": [c for c in types["edit"] if c not in types["base"]],
        "retyped": {
            c: [types["base"][c], types["edit"][c]]
            for c in common
            if types["base"][c] != types["edit"][c]
        },
        "grain": [],
        "note": None,
        "only_in_base": 0,
        "only_in_edit": 0,
        "changed": 0,
        "changed_columns": {},
        "examples": {"only_in_base": [], "only_in_edit": [], "changed": []},
    }
    if common:
        compare_rows(db, base, edit, common, types, rows, result)
    else:
        result["note"] = "rows not compared: the tables have no column in common"
    result["differs"] = bool(
        result["grains"]["base"] != result["grains"]["edit"]
        or result["columns_only_in_base"]
        or result["columns_only_in_edit"]
        or result["retyped"]
        or result["only_in_base"]
        or result["only_in_edit"]
        or result["changed"]
    )
    return result


def compare_rows(db, base, edit, common, types, rows, result) -> None:
    """Compare the rows of the two tables on the columns in `common`, into `result`."""

    # A column with a new type compares by value when both types hold numbers, and as text
    # otherwise, so 5 and '05' differ.
    def selected(c):
        before, after = types["base"][c], types["edit"][c]
        if before == after or (is_number(before) and is_number(after)):
            return quote(c)
        return f"{quote(c)}::VARCHAR AS {quote(c)}"

    columns = ", ".join(map(selected, common))
    db.execute(
        f"CREATE OR REPLACE TEMP VIEW b AS SELECT {columns} FROM '{base['table']}'"
    )
    db.execute(
        f"CREATE OR REPLACE TEMP VIEW e AS SELECT {columns} FROM '{edit['table']}'"
    )
    grain = base["grain"]
    keys = ", ".join(map(quote, grain))
    reason = None
    if grain != edit["grain"]:
        reason = "the grain changed"
    elif grain and not all(c in common for c in grain):
        reason = f"{', '.join(grain)} is not a column of both tables"
    elif grain:
        repeats = [
            which
            for which, view in (("base", "b"), ("edit", "e"))
            if db.execute(
                f"SELECT count(*) > (SELECT count(*) FROM (SELECT DISTINCT {keys} FROM {view})) "
                f"FROM {view}"
            ).fetchone()[0]
        ]
        if repeats:
            reason = f"{', '.join(grain)} repeats in the {' and the '.join(repeats)}"
    if grain and not reason:
        compare_keyed(db, grain, [c for c in common if c not in grain], rows, result)
        return
    if reason:
        result["note"] = f"rows compared as multisets: {reason}"
    compare_multisets(db, rows, result)


def compare_keyed(db, grain, values, rows, result) -> None:
    """Join the two sides on `grain` and count the rows of each kind, into `result`."""
    result["grain"] = grain
    # A marker column tells which side has a row, as a grain column may hold NULL. Its name
    # takes underscores in front until it differs from every column of the tables.
    in_base, in_edit = "in_base", "in_edit"
    while {in_base, in_edit} & {*grain, *values}:
        in_base, in_edit = "_" + in_base, "_" + in_edit
    columns = [f"coalesce(b.{quote(c)}, e.{quote(c)}) AS {quote(c)}" for c in grain]
    columns += [
        f"b.{quote(in_base)} IS NOT NULL AS {quote(in_base)}",
        f"e.{quote(in_edit)} IS NOT NULL AS {quote(in_edit)}",
    ]
    for c in values:
        columns += [
            f"b.{quote(c)} IS DISTINCT FROM e.{quote(c)} AS {quote('changed ' + c)}",
            f"b.{quote(c)} AS {quote('base ' + c)}",
            f"e.{quote(c)} AS {quote('edit ' + c)}",
        ]
    on = " AND ".join(f"b.{quote(c)} IS NOT DISTINCT FROM e.{quote(c)}" for c in grain)
    db.execute(
        f"""CREATE OR REPLACE TEMP TABLE joined AS SELECT {", ".join(columns)}
        FROM (SELECT *, true AS {quote(in_base)} FROM b) b
        FULL JOIN (SELECT *, true AS {quote(in_edit)} FROM e) e ON {on}"""
    )
    only = {
        "only_in_base": f"{quote(in_base)} AND NOT {quote(in_edit)}",
        "only_in_edit": f"{quote(in_edit)} AND NOT {quote(in_base)}",
    }
    both = f"{quote(in_base)} AND {quote(in_edit)}"
    any_change = " OR ".join(quote("changed " + c) for c in values) or "false"
    for kind, where in only.items():
        result[kind] = db.execute(
            f"SELECT count(*) FROM joined WHERE {where}"
        ).fetchone()[0]
    result["changed"] = db.execute(
        f"SELECT count(*) FROM joined WHERE {both} AND ({any_change})"
    ).fetchone()[0]
    result["changed_columns"] = {
        c: n
        for c in values
        if (
            n := db.execute(
                f"SELECT count(*) FROM joined WHERE {both} AND {quote('changed ' + c)}"
            ).fetchone()[0]
        )
    }
    keys = ", ".join(map(quote, grain))
    result["examples"] = {
        kind: records(
            db, f"SELECT {keys} FROM joined WHERE {where} ORDER BY {keys} LIMIT {rows}"
        )
        for kind, where in only.items()
    }
    result["examples"]["changed"] = [
        {
            "key": {c: row[c] for c in grain},
            "values": {
                c: [row["base " + c], row["edit " + c]]
                for c in result["changed_columns"]
                if row["changed " + c]
            },
        }
        for row in records(
            db,
            f"SELECT * FROM joined WHERE {both} AND ({any_change}) "
            f"ORDER BY {keys} LIMIT {rows}",
        )
    ]


def compare_multisets(db, rows, result) -> None:
    """Count the rows of each side missing from the other, as multisets, into `result`."""
    for which, this, other in (("base", "b", "e"), ("edit", "e", "b")):
        missing = f"SELECT * FROM {this} EXCEPT ALL SELECT * FROM {other}"
        result[f"only_in_{which}"] = db.execute(
            f"SELECT count(*) FROM ({missing})"
        ).fetchone()[0]
        result["examples"][f"only_in_{which}"] = records(
            db, f"SELECT * FROM ({missing}) ORDER BY ALL LIMIT {rows}"
        )


def records(db, sql: str) -> list[dict]:
    cursor = db.execute(sql)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def compare(base: Path, edit: Path, rows: int) -> dict:
    """Compare the tables of the two built sides in `base` and `edit`."""
    import duckdb

    sides = {
        which: json.loads((path / "models.json").read_text())
        for which, path in (("base", base), ("edit", edit))
    }
    db = duckdb.connect(config={"memory_limit": "1GB", "threads": 2})
    models = {}
    for name in sorted(sides["base"].keys() & sides["edit"].keys()):
        models[name] = compare_model(db, sides["base"][name], sides["edit"][name], rows)
    return {
        "models_only_in_base": sorted(sides["base"].keys() - sides["edit"].keys()),
        "models_only_in_edit": sorted(sides["edit"].keys() - sides["base"].keys()),
        "models": models,
    }


def short(value, width=60) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= width else text[: width - 3] + "..."


def report(result: dict) -> str:
    """The comparison as text."""
    lines = []
    for which in ("base", "edit"):
        for name in result[f"models_only_in_{which}"]:
            lines.append(f"{name}: only in the {which}")
    unchanged = []
    for name, model in result["models"].items():
        if not model["differs"]:
            unchanged.append(name)
            continue
        counts = [
            f"{model['rows']['base']:,} rows in the base, {model['rows']['edit']:,} in the edit"
        ]
        if model["only_in_base"]:
            counts.append(f"{model['only_in_base']:,} only in the base")
        if model["only_in_edit"]:
            counts.append(f"{model['only_in_edit']:,} only in the edit")
        if model["changed"]:
            columns = ", ".join(
                f"{c} {n:,}" for c, n in model["changed_columns"].items()
            )
            counts.append(f"{model['changed']:,} changed ({columns})")
        lines.append(f"{name}: " + "; ".join(counts))
        for which in ("base", "edit"):
            if model[f"columns_only_in_{which}"]:
                columns = ", ".join(model[f"columns_only_in_{which}"])
                lines.append(f"  columns only in the {which}: {columns}")
        for column, (before, after) in model["retyped"].items():
            lines.append(f"  {column}: type {before} in the base, {after} in the edit")
        if model["grains"]["base"] != model["grains"]["edit"]:
            grains = {k: ", ".join(g) or "none" for k, g in model["grains"].items()}
            lines.append(
                f"  grain: {grains['base']} in the base, {grains['edit']} in the edit"
            )
        if model["note"]:
            lines.append(f"  {model['note']}")
        for which in ("base", "edit"):
            for row in model["examples"][f"only_in_{which}"]:
                lines.append(f"  only in the {which}: {short(row, 90)}")
        for row in model["examples"]["changed"]:
            key = ", ".join(f"{c}={short(v)}" for c, v in row["key"].items())
            for column, (before, after) in row["values"].items():
                lines.append(f"  {key}: {column} {short(before)} -> {short(after)}")
    if unchanged:
        lines.append("unchanged: " + ", ".join(unchanged))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="HEAD", help="the revision to compare with")
    parser.add_argument(
        "--base-dir", type=Path, help="a folder with pipeline/ and src/"
    )
    parser.add_argument("--edit-dir", type=Path, default=REPO, help=argparse.SUPPRESS)
    parser.add_argument("--export", type=Path, default=FIXTURE)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--keep", type=Path)
    parser.add_argument("--side", nargs=2, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.side:
        side(*args.side)
        return 0

    started = time.monotonic()
    scratch = args.keep or Path(tempfile.mkdtemp(prefix="pipeline-diff-"))
    try:
        base_root = args.base_dir
        if base_root is None:
            base_root = scratch / "code"
            archive(args.base, base_root)
        outs = {"base": scratch / "base", "edit": scratch / "edit"}
        for out in outs.values():
            out.mkdir(parents=True)
        roots = {"base": base_root, "edit": args.edit_dir}
        with ThreadPoolExecutor(2) as pool:
            jobs = {
                which: pool.submit(build, roots[which], args.export, args.ledger, out)
                for which, out in outs.items()
            }
            seconds = {}
            for which, job in jobs.items():
                try:
                    seconds[which] = job.result()
                except BuildError as error:
                    print(f"the {which} build stopped:\n{error}", file=sys.stderr)
                    return 1
        result = compare(outs["base"], outs["edit"], args.rows)
        result["seconds"] = {**seconds, "total": time.monotonic() - started}
        if args.json:
            args.json.write_text(json.dumps(result, indent=1, default=str))
        print(report(result))
        print(
            f"built the base in {seconds['base']:.1f} s and the edit in "
            f"{seconds['edit']:.1f} s, {result['seconds']['total']:.1f} s in all"
        )
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
