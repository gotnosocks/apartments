"""Freeze a fit's inputs and its prepared rows as a reference for the rebuilt data pipeline.

    python ops/pipeline/reference.py run RUN_DIR NAME
    python ops/pipeline/reference.py spec NAME --commit SHA --dataset DIR --rules R1,R2,... \
        [--features SET] [--split rows]
    python ops/pipeline/reference.py verify NAME
    python ops/pipeline/reference.py columns NAME

`run` takes the dataset, split, data rules, feature set and commit from a fit's result.json.
`spec` takes them from the command line, for a fit still in a queue. Either way the script
exports the commit's tree with `git archive`, then runs the commit's own `rentfrontier` in the
frontier venv to prepare the rows the way `rentfrontier.run` does before sampling:

1. `data.load` reads the dataset's observations.
2. `data.split_and_rules` draws the split and applies the data rules.
3. `features.build` builds the feature matrix, when the reference has a feature set.

It writes the prepared rows to `rows.parquet`, with the held-out mask as a `heldout` column,
and the feature matrix to `features.parquet`, keyed by `audit_id`. Every file the preparation
read goes into `blobs/` under its SHA-256, read-only, so later changes to the original files
leave the reference alone. For a fit with a result.json, `manifest.json` records whether the
row hash and each input hash still equal the fit's own record.

`verify` hashes every blob and output of a reference again and reports any change.

`columns` repeats the feature build and `model.prepare` on a reference's frozen rows and prints
the columns each of them read, along with the columns neither read. Then it drops those unread
columns, builds the features again and reports whether the matrix came out the same.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(
    os.environ.get("PIPELINE_REFERENCE_ROOT", "/data1/apartments/pipeline/reference")
)
TREES = Path("/data1/apartments/tmp/pipeline/ref-trees")
PYTHON = "/data1/apartments/venvs/serve-frontier/bin/python"
REPO = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tree(commit: str) -> Path:
    """The commit's files, exported once into TREES."""
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", f"{commit}^{{commit}}"], text=True
    ).strip()
    path = TREES / commit
    if not path.exists():
        TREES.mkdir(parents=True, exist_ok=True)
        part = Path(tempfile.mkdtemp(dir=TREES, prefix=".part-"))
        archive = subprocess.Popen(
            ["git", "-C", str(REPO), "archive", commit], stdout=subprocess.PIPE
        )
        subprocess.run(["tar", "-x", "-C", str(part)], stdin=archive.stdout, check=True)
        if archive.wait():
            raise SystemExit(f"git archive {commit} failed")
        part.rename(path)
    return path


def blob(path: str, expected: str | None = None) -> dict:
    """Copy a file into ROOT/blobs under its SHA-256, unless a copy is there already."""
    source = Path(path)
    digest = sha256(source)
    target = ROOT / "blobs" / digest
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(".part")
        shutil.copyfile(source, part)
        if sha256(part) != digest:
            raise SystemExit(f"{source} changed while it was copied")
        part.chmod(0o444)
        part.rename(target)
    out = {"path": str(source), "sha256": digest, "bytes": source.stat().st_size}
    if expected is not None:
        out["recorded_sha256"] = expected
        out["matches_record"] = digest == expected
    return out


def prepare(spec: dict, out: Path) -> dict:
    """Runs in the frontier venv with the commit's rentfrontier first on sys.path."""
    import numpy as np
    import pandas as pd

    from rentfrontier import data, features, run

    start = time.perf_counter()
    frame = data.load(Path(spec["dataset"]))
    rules = tuple(spec["rules"])
    frame, heldout = data.split_and_rules(frame, spec["split"], rules)
    rows_sha256 = data.rows_sha256(frame, heldout)
    inputs = {"observations": str(Path(spec["dataset"]) / "observations.jsonl")}
    for rule, path in data.RULE_SOURCES.items():
        if rule in rules:
            inputs[f"rule {rule}"] = str(path)
    rows = frame.copy()
    rows["heldout"] = np.asarray(heldout, dtype=bool)
    rows.to_parquet(out / "rows.parquet", index=False)
    result = {
        "rows_sha256": rows_sha256,
        "rows": len(frame),
        "heldout": int(heldout.sum()),
    }
    if spec.get("features"):
        feats = features.build(
            spec["features"], frame, ~np.asarray(heldout, dtype=bool)
        )
        for name, source in run.feature_sources(spec["features"]).items():
            inputs[f"feature {name}"] = source["path"]
        matrix = pd.DataFrame(feats.values, columns=list(feats.names))
        matrix.insert(0, "audit_id", frame.audit_id.to_numpy())
        matrix.to_parquet(out / "features.parquet", index=False)
        (out / "features.json").write_text(
            json.dumps(
                {
                    "id": feats.id,
                    "names": list(feats.names),
                    "groups": list(feats.groups),
                    "prior_scale": np.asarray(feats.prior_scale).tolist(),
                },
                indent=1,
            )
        )
        result["features"] = len(feats.names)
    result["inputs"] = inputs
    result["seconds"] = round(time.perf_counter() - start, 1)
    return result


def traced_columns(frame, heldout: np.ndarray, spec: dict) -> dict:
    """Runs in the frontier venv. Repeats the feature build and `model.prepare` on the frozen
    rows, noting each of the rows' columns that a data frame reads by name meanwhile.

    The patched calls cover `df.col`, `df["col"]`, `df[[...]]`, `df.get`, `"col" in df` and
    the key arguments of `groupby`, `merge`, `sort_values`, `drop_duplicates` and `set_index`.
    Any frame with a column of the same name counts, so the lists can hold a column the step
    read from another table under that name. Afterwards the function drops the columns neither
    step read, builds the features again and checks that nothing changed.
    """
    import numpy as np
    import pandas as pd

    from rentfrontier import features, model

    names = set(frame.columns)
    read: set[str] = set()

    def note(key) -> None:
        keys = key if isinstance(key, (list, tuple, pd.Index)) else [key]
        read.update(k for k in keys if isinstance(k, str) and k in names)

    patched = {}

    def patch(method: str, *kwargs: str, positional: bool = True) -> None:
        original = getattr(pd.DataFrame, method)
        patched[method] = original

        def wrapper(self, *args, **kw):
            if positional and args:
                note(args[0])
            for k in kwargs:
                note(kw.get(k))
            return original(self, *args, **kw)

        setattr(pd.DataFrame, method, wrapper)

    patch("__getitem__")
    patch("__getattr__")
    patch("__contains__")
    patch("get")
    patch("groupby", "by")
    patch("merge", "on", "left_on", "right_on", positional=False)
    patch("sort_values", "by")
    patch("drop_duplicates", "subset")
    patch("set_index", "keys")
    out = {}
    try:
        feats = None
        if spec.get("features"):
            feats = features.build(spec["features"], frame, ~heldout)
            out["features.build"] = sorted(read)
            read.clear()
        if feats is not None:
            model.prepare(frame, heldout, feats)
            out["model.prepare"] = sorted(read)
    finally:
        for method, original in patched.items():
            setattr(pd.DataFrame, method, original)
    out["unread"] = sorted(names - set().union(*map(set, out.values())))
    if feats is not None:
        # The patches miss reads through other calls, so build again without the unread
        # columns and compare.
        rest = frame.drop(columns=out["unread"])
        again = features.build(spec["features"], rest, ~heldout)
        model.prepare(rest, heldout, again)
        out["same_without_unread"] = list(again.names) == list(feats.names) and bool(
            np.array_equal(again.values, feats.values, equal_nan=True)
        )
    return out


def freeze(name: str, spec: dict, record: dict | None = None) -> None:
    out = ROOT / name
    if (out / "manifest.json").exists():
        raise SystemExit(f"{out} is frozen already")
    code = tree(spec["commit"])
    out.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        PYTHONPATH=str(code / "frontier" / "src"),
        JAX_PLATFORMS="cpu",
        FRONTIER_DATASET=spec["dataset"],
    )
    child = subprocess.run(
        [PYTHON, __file__, "_prepare", json.dumps(spec), str(out)],
        env=env,
        cwd=code,
        capture_output=True,
        text=True,
    )
    sys.stderr.write(child.stderr[-4000:])
    if child.returncode:
        raise SystemExit(f"preparation failed ({child.returncode})")
    prepared = json.loads(child.stdout.strip().splitlines()[-1])
    recorded = {}
    if record:
        recorded["observations"] = record.get("dataset_observations_sha256")
        for rule, source in record.get("data_rule_sources", {}).items():
            recorded[f"rule {rule}"] = source["sha256"]
        for key, source in record.get("feature_sources", {}).items():
            recorded[f"feature {key}"] = source["sha256"]
    inputs = {
        role: blob(path, recorded.get(role) if record else None)
        for role, path in prepared.pop("inputs").items()
    }
    outputs = {}
    for path in sorted(out.iterdir()):
        path.chmod(0o444)
        outputs[path.name] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    manifest = {
        "name": name,
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "spec": spec,
        "prepared": prepared,
        "inputs": inputs,
        "outputs": outputs,
    }
    if record:
        manifest["run"] = record.get("name")
        manifest["rows_sha256_matches_run"] = prepared["rows_sha256"] == record.get(
            "rows_sha256"
        )
        manifest["inputs_match_run"] = all(
            i.get("matches_record", True) for i in inputs.values()
        )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    (out / "manifest.json").chmod(0o444)
    print(json.dumps({k: v for k, v in manifest.items() if k != "inputs"}, indent=1))


def verify(name: str) -> int:
    manifest = json.loads((ROOT / name / "manifest.json").read_text())
    changed = [
        role
        for role, i in manifest["inputs"].items()
        if sha256(ROOT / "blobs" / i["sha256"]) != i["sha256"]
    ]
    changed += [
        path
        for path, o in manifest["outputs"].items()
        if sha256(ROOT / name / path) != o["sha256"]
    ]
    for item in changed:
        print(f"{name}: {item} changed")
    if not changed:
        print(
            f"{name}: {len(manifest['inputs'])} inputs, {len(manifest['outputs'])} outputs unchanged"
        )
    return 1 if changed else 0


def columns(name: str) -> None:
    manifest = json.loads((ROOT / name / "manifest.json").read_text())
    spec = manifest["spec"]
    code = tree(spec["commit"])
    env = dict(
        os.environ,
        PYTHONPATH=str(code / "frontier" / "src"),
        JAX_PLATFORMS="cpu",
        FRONTIER_DATASET=spec["dataset"],
    )
    child = subprocess.run(
        [PYTHON, __file__, "_columns", name],
        env=env,
        cwd=code,
        capture_output=True,
        text=True,
    )
    sys.stderr.write(child.stderr[-4000:])
    if child.returncode:
        raise SystemExit(f"column trace failed ({child.returncode})")
    print(child.stdout.strip().splitlines()[-1])


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["_prepare"]:
        print(json.dumps(prepare(json.loads(argv[1]), Path(argv[2]))))
        return 0
    if argv[:1] == ["_columns"]:
        import numpy as np
        import pandas as pd

        manifest = json.loads((ROOT / argv[1] / "manifest.json").read_text())
        frame = pd.read_parquet(ROOT / argv[1] / "rows.parquet")
        heldout = frame.pop("heldout").to_numpy()
        print(
            json.dumps(
                traced_columns(frame, np.asarray(heldout, bool), manifest["spec"])
            )
        )
        return 0
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("run_dir", type=Path)
    p.add_argument("name")
    p = sub.add_parser("spec")
    p.add_argument("name")
    p.add_argument("--commit", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--features")
    p.add_argument("--split", default="rows")
    p = sub.add_parser("verify")
    p.add_argument("name")
    p = sub.add_parser("columns")
    p.add_argument("name")
    args = parser.parse_args(argv)
    if args.command == "verify":
        return verify(args.name)
    if args.command == "columns":
        columns(args.name)
        return 0
    if args.command == "run":
        record = json.loads((args.run_dir / "result.json").read_text())
        spec = {
            "commit": record["commit"],
            "dataset": record["dataset"],
            "split": record["split"],
            "rules": record["data_rules"],
            "features": record["feature_set"],
        }
        freeze(args.name, spec, record)
    else:
        spec = {
            "commit": args.commit,
            "dataset": args.dataset,
            "split": args.split,
            "rules": [r for r in args.rules.split(",") if r],
            "features": args.features,
        }
        freeze(args.name, spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
