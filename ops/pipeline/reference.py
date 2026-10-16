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

It writes the prepared rows to `rows.parquet`, with the held-out mask as a `heldout` column, and
the feature matrix to `features.parquet`, keyed by `audit_id`. The preparation runs under `strace`,
which logs every file the process and its children open. The script then copies each file opened
for reading into `blobs/` under its SHA-256, read-only, so later changes to the original files
leave the reference alone. Files under the exported tree, the venv, Python's install and the system
folders hold code, so the script leaves them out. It also leaves out directories and the scratch
folder described below. If the preparation read a file elsewhere that it had also opened for
writing, or a file gone by the time of the copy, the freeze stops, since the copy might not hold
what the preparation read.

The preparation keeps the hash `data.load` takes of the observations before parsing them, and
hashes the rule files and the feature sources before and after its calls. The freeze stops if a
hash differs by the time of the copy. For any other file, the freeze stops if the file's
modification or status-change time comes after the preparation started, or if its status changes
while the script hashes and copies it. The preparation writes its caches into an empty scratch
folder, set as `FRONTIER_OUTPUT_ROOT`, so `data.load` and `descriptions.load` build them from the
inputs rather than read caches written by other jobs. Its temporary files go to the same folder,
set as `TMPDIR`. For a fit with a result.json, `manifest.json` records
whether the row hash and the hashes of the observations, rule files and feature sources equal the
fit's own record. Any of those the record lacks counts as a mismatch. A fit records no hashes for
the other files. The manifest also lists the version of every package in the venv.

`verify` hashes every blob and output of a reference again and reports any change or missing
file.

`columns` repeats the feature build and `model.prepare` on a reference's frozen rows and prints
the columns each of them read, along with the columns neither read. It reports whether the
build gave the frozen matrix. Then it drops the unread columns, runs both steps again and
reports whether the features and the prepared arrays came out the same.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
# Opened files under these folders belong to the system, so they are not inputs.
SYSTEM = ("/usr/", "/lib/", "/lib64/", "/etc/", "/proc/", "/sys/", "/dev/", "/run/")
# A successful open in `strace -y` output: its flags, then the returned descriptor's path.
OPEN = re.compile(r"^\d+ +open(?:at)?\(.*, (O_[\w|]+)(?:, 0\d*)?\) = \d+<(.+)>$")


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


def blob(path: str, read: str, expected: str | None = None) -> dict:
    """Copy a file into ROOT/blobs under its SHA-256, unless a copy is there already.

    `read` is the hash the preparation took while it read the file. A file with another hash
    now changed after the read, so the copy would hold other data, and the freeze stops.
    `expected` is the fit's record of the hash, when there is one.
    """
    source = Path(path)
    digest = sha256(source)
    if digest != read:
        raise SystemExit(f"{source} changed after the preparation read it")
    target = ROOT / "blobs" / digest
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(".part")
        try:
            shutil.copyfile(source, part)
            if sha256(part) != digest:
                raise SystemExit(f"{source} changed while it was copied")
            part.chmod(0o444)
            part.rename(target)
        finally:
            part.unlink(missing_ok=True)
    out = {"path": str(source), "sha256": digest, "bytes": target.stat().st_size}
    if expected is not None:
        out["recorded_sha256"] = expected
        out["matches_record"] = digest == expected
    return out


def opened(log: Path, skip: tuple[str, ...]) -> list[str]:
    """The files an `strace -f -y` log shows opened for reading, outside `skip` and directories.

    The preparation writes only below `skip`, so a file outside it that the log also shows
    opened for writing holds data the preparation made, and a file gone by now can't be copied.
    Either one stops the freeze.
    """
    read, written = set(), set()
    for line in log.read_text(errors="replace").splitlines():
        match = OPEN.match(line)
        if not match:
            continue
        flags, path = match.groups()
        if re.search("O_WRONLY|O_RDWR|O_CREAT|O_TRUNC", flags):
            written.add(path)
        elif "O_DIRECTORY" not in flags and not path.startswith(skip):
            read.add(path)
    read = {p for p in read if not Path(p).is_dir()}
    if odd := sorted(p for p in read if p in written or not Path(p).is_file()):
        raise SystemExit(
            "the preparation read files outside its scratch folder that it also wrote, "
            f"or that are gone: {', '.join(odd)}"
        )
    return sorted(read)


def prepare(spec: dict, out: Path) -> dict:
    """Runs in the frontier venv with the commit's rentfrontier first on sys.path."""
    from importlib import metadata

    import numpy as np
    import pandas as pd

    from rentfrontier import data, features, run

    start = time.perf_counter()
    frame = data.load(Path(spec["dataset"]), cache_root=data.OUTPUT_ROOT)
    inputs = {
        "observations": {
            "path": str(Path(spec["dataset"]) / "observations.jsonl"),
            "sha256": frame.attrs["source_sha256"],
        }
    }
    rules = tuple(spec["rules"])
    files = {r: Path(p) for r, p in data.RULE_SOURCES.items() if r in rules}
    before = {r: data.sha256(p) for r, p in files.items()}
    frame, heldout = data.split_and_rules(frame, spec["split"], rules)
    for rule, path in files.items():
        if data.sha256(path) != before[rule]:
            raise SystemExit(f"{path} changed while the rules read it")
        inputs[f"rule {rule}"] = {"path": str(path), "sha256": before[rule]}
    rows_sha256 = data.rows_sha256(frame, heldout)
    rows = frame.copy()
    rows["heldout"] = np.asarray(heldout, dtype=bool)
    rows.to_parquet(out / "rows.parquet", index=False)
    result = {
        "rows_sha256": rows_sha256,
        "rows": len(frame),
        "heldout": int(heldout.sum()),
    }
    if spec.get("features"):
        sources = run.feature_sources(spec["features"])
        feats = features.build(
            spec["features"], frame, ~np.asarray(heldout, dtype=bool)
        )
        if run.feature_sources(spec["features"]) != sources:
            raise SystemExit("a feature source changed while the features were built")
        for name, source in sources.items():
            inputs[f"feature {name}"] = {
                "path": source["path"],
                "sha256": source["sha256"],
            }
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
    result["python"] = {
        "version": sys.version.split()[0],
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
    }
    result["packages"] = dict(
        sorted((d.metadata["Name"], d.version) for d in metadata.distributions())
    )
    result["seconds"] = round(time.perf_counter() - start, 1)
    return result


def same(a, b) -> bool:
    """Whether two results hold equal values, field by field, with NaN equal to NaN."""
    import numpy as np
    import pandas as pd

    if type(a) is not type(b):
        return False
    if isinstance(a, (pd.Index, pd.Series, pd.DataFrame)):
        return a.equals(b)
    if isinstance(a, np.ndarray):
        return (
            a.shape == b.shape
            and a.dtype == b.dtype
            and bool(np.array_equal(a, b, equal_nan=a.dtype.kind in "fc"))
        )
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(map(same, a, b))
    if isinstance(a, float):
        return a == b or (a != a and b != b)
    if hasattr(a, "__dict__"):
        return same(vars(a), vars(b))
    return bool(a == b)


def traced_columns(
    frame, heldout: np.ndarray, spec: dict, frozen: pd.DataFrame | None = None
) -> dict:
    """Runs in the frontier venv. Repeats the feature build and `model.prepare` on the frozen
    rows, noting each of the rows' columns that a data frame reads by name meanwhile.

    The patched calls cover `df.col`, `df["col"]`, `df[[...]]`, `df.get`, `"col" in df` and
    the key arguments of `groupby`, `merge`, `sort_values`, `drop_duplicates` and `set_index`.
    Any frame with a column of the same name counts, so the lists can hold a column the step
    read from another table under that name. Reads through other calls, such as
    `"col" in df.columns`, go unnoted. To cover those, the function drops the columns neither
    step read, then builds the features and runs `model.prepare` again. It compares every
    field of the two feature builds and of the two prepared results, the sampler's arrays
    among them. With `frozen`, the reference's `features.parquet`, it also compares the first
    build with the frozen matrix.
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
        feats = prepared = None
        if spec.get("features"):
            feats = features.build(spec["features"], frame, ~heldout)
            out["features.build"] = sorted(read)
            read.clear()
        if feats is not None:
            prepared = model.prepare(frame, heldout, feats)
            out["model.prepare"] = sorted(read)
    finally:
        for method, original in patched.items():
            setattr(pd.DataFrame, method, original)
    out["unread"] = sorted(names - set().union(*map(set, out.values())))
    if feats is not None:
        if frozen is not None:
            out["same_as_frozen"] = (
                list(frozen.columns) == ["audit_id", *feats.names]
                and bool(np.array_equal(frozen.audit_id, frame.audit_id))
                and bool(
                    np.array_equal(
                        frozen.drop(columns="audit_id").to_numpy(),
                        feats.values,
                        equal_nan=True,
                    )
                )
            )
        rest = frame.drop(columns=out["unread"])
        again = features.build(spec["features"], rest, ~heldout)
        out["same_without_unread"] = same(feats, again) and same(
            prepared, model.prepare(rest, heldout, again)
        )
    return out


def status(stat: os.stat_result) -> tuple:
    """The parts of a file's status that change when someone writes to or replaces it."""
    return stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def child_env(code: Path, spec: dict, scratch: Path) -> dict:
    """The preparation's environment, with its caches and temporary files under `scratch`."""
    (scratch / "tmp").mkdir(exist_ok=True)
    return dict(
        os.environ,
        PYTHONPATH=str(code / "frontier" / "src"),
        JAX_PLATFORMS="cpu",
        FRONTIER_DATASET=spec["dataset"],
        FRONTIER_OUTPUT_ROOT=str(scratch / "output"),
        FRONTIER_COMMIT=spec["commit"],
        TMPDIR=str(scratch / "tmp"),
    )


def freeze(name: str, spec: dict, record: dict | None = None) -> None:
    out = ROOT / name
    if (out / "manifest.json").exists():
        raise SystemExit(f"{out} is frozen already")
    code = tree(spec["commit"])
    # A failed attempt leaves its outputs behind.
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as scratch:
        scratch = Path(scratch)
        log = scratch / "opens.log"
        started = time.time_ns()
        child = subprocess.run(
            [
                "strace",
                "-f",
                "-qq",
                "--seccomp-bpf",
                "-y",
                "-o",
                str(log),
                "-e",
                "trace=open,openat",
                "-e",
                "status=successful",
                PYTHON,
                __file__,
                "_prepare",
                json.dumps(spec),
                str(out),
            ],  # fmt: skip
            env=child_env(code, spec, scratch),
            cwd=code,
            capture_output=True,
            text=True,
        )
        sys.stderr.write(child.stderr[-4000:])
        if child.returncode:
            raise SystemExit(f"preparation failed ({child.returncode})")
        prepared = json.loads(child.stdout.strip().splitlines()[-1])
        python = prepared["python"]
        skip = tuple(
            f"{os.path.realpath(p)}/"
            for p in (code, scratch, out, python["prefix"], python["base_prefix"])
        )
        files = opened(log, (*skip, os.path.realpath(__file__), *SYSTEM))
    recorded = {}
    if record:
        recorded["observations"] = record.get("dataset_observations_sha256")
        for rule, source in record.get("data_rule_sources", {}).items():
            recorded[f"rule {rule}"] = source["sha256"]
        for key, source in record.get("feature_sources", {}).items():
            recorded[f"feature {key}"] = source["sha256"]
    inputs = {
        role: blob(i["path"], i["sha256"], recorded.get(role) if record else None)
        for role, i in prepared.pop("inputs").items()
    }
    hashed = {os.path.realpath(i["path"]) for i in inputs.values()}
    for path in files:
        if path in hashed:
            continue
        before = Path(path).stat()
        if max(before.st_mtime_ns, before.st_ctime_ns) >= started:
            raise SystemExit(f"{path} changed after the preparation started")
        inputs[f"file {path}"] = blob(path, sha256(Path(path)))
        after = Path(path).stat()
        if status(after) != status(before):
            raise SystemExit(f"{path} changed while it was copied")
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
        # An input missing from the fit's record counts as a mismatch.
        manifest["inputs_match_run"] = all(
            i.get("matches_record") is True
            for role, i in inputs.items()
            if not role.startswith("file ")
        ) and set(recorded) <= set(inputs)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    (out / "manifest.json").chmod(0o444)
    print(json.dumps({k: v for k, v in manifest.items() if k != "inputs"}, indent=1))


def verify(name: str) -> int:
    manifest = json.loads((ROOT / name / "manifest.json").read_text())
    files = {
        role: (ROOT / "blobs" / i["sha256"], i)
        for role, i in manifest["inputs"].items()
    }
    files.update(
        (path, (ROOT / name / path, o)) for path, o in manifest["outputs"].items()
    )
    changed = []
    for item, (path, record) in files.items():
        if not path.exists():
            changed.append(item)
            print(f"{name}: {item} missing")
        elif sha256(path) != record["sha256"]:
            changed.append(item)
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
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as scratch:
        child = subprocess.run(
            [PYTHON, __file__, "_columns", name],
            env=child_env(code, spec, Path(scratch)),
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
        matrix = ROOT / argv[1] / "features.parquet"
        frozen = pd.read_parquet(matrix) if matrix.exists() else None
        print(
            json.dumps(
                traced_columns(
                    frame, np.asarray(heldout, bool), manifest["spec"], frozen
                )
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
