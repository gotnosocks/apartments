"""CPU-only archive processing. Local commands stream files; no local data analysis."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import modal

ROOT = Path(__file__).resolve().parents[1]
VOLUME_NAME = "chelsea-archive"
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App("chelsea-archive-processing")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "pymc==6.2.0",
        "pytensor==3.2.3",
        "nutpie==0.16.11",
        "arviz==1.2.0",
        "numpy==2.4.6",
        "pandas==3.0.5",
        "pyarrow==24.0.0",
        "h5netcdf==1.8.1",
        "h5py==3.16.0",
        "duckdb==1.5.5",
        "scipy==1.18.0",
        "beautifulsoup4==4.14.3",
        "parsel==1.10.0",
    )
    .env(
        {
            "PYTHONPATH": "/root/src:/root/models",
            "APARTMENTS_DB_MEMORY_LIMIT": "2GB",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
            "PYTENSOR_FLAGS": "cxx=",
        }
    )
    .add_local_dir(
        ROOT / "src/apartments", "/root/src/apartments", ignore=["__pycache__"]
    )
    .add_local_dir(
        ROOT / "src/streeteasy_archive",
        "/root/src/streeteasy_archive",
        ignore=["__pycache__"],
    )
    .add_local_file(ROOT / "models/rent_model.py", "/root/models/rent_model.py")
    .add_local_file(ROOT / "models/modal_archive.py", "/root/modal_archive.py")
    .add_local_dir(ROOT / "config", "/root/config")
)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_id(value):
    import re

    if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        raise ValueError(
            "Snapshot IDs may contain letters, digits, dash and underscore only"
        )
    return value


def write_json(path, value):
    """Keep resume markers intact if the local client is interrupted."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def upload_files(snapshot, archive, database):
    """One file per upload batch: SDK streams large blobs rather than reading them whole."""
    import fcntl

    snapshot = safe_id(snapshot)
    cache = ROOT / "data/modal-upload" / snapshot
    cache.mkdir(parents=True, exist_ok=True)
    ledger_path = cache / "uploaded.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    # Keep the snapshot stable while making the SQLite backup and uploading bodies.
    with (archive / "crawler.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = cache / "archive.sqlite3"
        if not backup.exists() and "sqlite" not in ledger:
            source = sqlite3.connect(
                (archive / "archive.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
            )
            partial = backup.with_suffix(".partial")
            partial.unlink(missing_ok=True)
            target = sqlite3.connect(partial)
            source.execute("PRAGMA cache_size=-8192")
            source.backup(target, pages=256, sleep=0.05)
            target.close()
            source.close()
            partial.replace(backup)

        def put(path, remote, key):
            if key in ledger:
                return
            print(f"Uploading {path.name} ({path.stat().st_size} bytes)", flush=True)
            with volume.batch_upload(force=True) as batch:
                batch.put_file(path, remote)
            ledger[key] = {"path": remote, "bytes": path.stat().st_size}
            write_json(ledger_path, ledger)

        put(backup, f"/snapshots/{snapshot}/archive.sqlite3", "sqlite")
        if backup.exists():
            backup.unlink()  # Only our completed temporary backup, never the live archive.
        if database and database.exists():
            if Path(str(database) + ".wal").exists():
                raise RuntimeError(
                    "Database writer/WAL is active; finish its import before uploading"
                )
            put(database, f"/snapshots/{snapshot}/apartments.duckdb", "database")
        # Body names are content hashes and immutable. Share across all snapshots.
        shared_path = ROOT / "data/modal-upload/bodies-uploaded.json"
        shared = json.loads(shared_path.read_text()) if shared_path.exists() else {}
        pending = []
        pending_bytes = 0

        def flush():
            if not pending:
                return
            with volume.batch_upload(force=True) as batch:
                for path in pending:
                    batch.put_file(path, "/" + path.relative_to(archive).as_posix())
            for path in pending:
                shared[path.relative_to(archive).as_posix()] = path.stat().st_size
            write_json(shared_path, shared)
            print(f"Uploaded {len(shared)} body files", flush=True)
            pending.clear()

        for path in sorted((archive / "bodies").rglob("*.gz")):
            relative = path.relative_to(archive).as_posix()
            if relative in shared:
                continue
            size = path.stat().st_size
            if len(pending) >= 128 or pending_bytes + size > 16 * 1024 * 1024:
                flush()
                pending_bytes = 0
            pending.append(path)
            pending_bytes += size
        flush()
        complete = cache / "complete.json"
        complete.write_text(
            json.dumps(
                {
                    "snapshot": snapshot,
                    "created_at_epoch": time.time(),
                    "files": ledger,
                    "body_files": len(shared),
                }
            )
        )
        with volume.batch_upload(force=True) as batch:
            batch.put_file(complete, f"/snapshots/{snapshot}/complete.json")
    print("Upload complete: " + snapshot, flush=True)


@app.function(
    image=image,
    cpu=(2, 2),
    memory=(8192, 8192),
    timeout=3600,
    max_containers=1,
    retries=0,
    volumes={"/archive": volume},
    include_source=False,
)
def prepare(snapshot: str):
    """Incrementally import, audit buildings one page at a time, and prepare model input."""
    import sys
    import re
    import collections

    sys.path[:0] = ["/root/src", "/root/models"]
    from apartments.archive_import import import_archive
    from streeteasy_archive.scope import objects
    from streeteasy_archive.extract import flight_text
    from rent_model import prepare_data

    started = time.monotonic()
    base = Path("/archive/snapshots") / safe_id(snapshot)
    if not (base / "complete.json").exists():
        raise ValueError("Snapshot upload is incomplete")
    result = base / "prepared"
    if (result / "metadata.json").exists():
        return json.loads((result / "metadata.json").read_text())
    bodies = base / "bodies"
    if not bodies.exists():
        bodies.symlink_to("/archive/bodies", target_is_directory=True)
    print("Importing missing archive captures", flush=True)
    counts = import_archive(
        base, base / "apartments.duckdb", body_root=Path("/archive/bodies")
    )
    if counts["failed"]:
        raise RuntimeError(
            f"Archive import failed for {counts['failed']} captures; rerun after fixing errors"
        )
    volume.commit()
    print("Auditing building coverage", flush=True)
    source = sqlite3.connect((base / "archive.sqlite3").as_uri() + "?mode=ro", uri=True)
    source.execute("PRAGMA cache_size=-16384")
    result.mkdir(exist_ok=True)
    building_ids = set()
    totals = collections.defaultdict(lambda: [0, 0])
    # Filter in SQL before reading JSON; NEVER fetchall the 6.9GB snapshot table.
    rows = source.execute("""SELECT s.url,s.extracted FROM snapshots s
        WHERE s.url LIKE 'https://streeteasy.com/building/%'
        AND instr(substr(s.url, length('https://streeteasy.com/building/')+1), '/')=0
        AND instr(s.url,'?')=0
        AND s.id=(SELECT max(s2.id) FROM snapshots s2 WHERE s2.url=s.url)""")
    with (result / "buildings.jsonl").open("w") as output:
        for url, raw in rows:
            data = json.loads(raw)
            slug = url.rsplit("/", 1)[-1]
            primary = next(
                (
                    o
                    for o in objects(data)
                    if o.get("slug") == slug and "residentialUnitCount" in o
                ),
                None,
            )
            if not primary or primary.get("id") in building_ids:
                continue
            refs = {}
            stream = flight_text(data.get("scripts", []))
            for m in re.finditer(r"(?<![A-Za-z0-9_])([0-9a-f]+):(?=[{\[])", stream):
                try:
                    refs[m[1]] = json.JSONDecoder().raw_decode(stream[m.end() :])[0]
                except ValueError:
                    pass
            area = primary.get("area")
            if isinstance(area, str) and area.startswith("$"):
                area = refs.get(area[1:])
            if not isinstance(area, dict) or not (
                {area.get("id"), area.get("slug")} & {"chelsea", "west-chelsea"}
            ):
                continue
            building_ids.add(primary["id"])
            entry = {
                k: primary.get(k)
                for k in ["id", "slug", "name", "type", "residentialUnitCount"]
            }
            entry.update(url=url, area=area)
            output.write(json.dumps(entry) + "\n")
            totals[str(entry["type"])][0] += 1
            totals[str(entry["type"])][1] += entry["residentialUnitCount"] or 0
    queue = dict(
        source.execute(
            "SELECT f.state,count(*) FROM frontier f JOIN scope_urls s USING(generation,url) WHERE f.generation=(SELECT max(id) FROM generations) GROUP BY f.state"
        )
    )
    source.close()
    print("Preparing monthly model observations", flush=True)
    data, periods = prepare_data(base / "apartments.duckdb", "monthly")
    import numpy as np
    from rent_model import FEATURES

    if (
        data.duplicated(["unit_key", "period"]).any()
        or not np.isfinite(data[FEATURES + ["log_rent"]].to_numpy(dtype=float)).all()
    ):
        raise ValueError("Invalid model input")
    path = result / "training_data.parquet"
    data.to_parquet(path, index=False)
    metadata = {
        "frequency": "monthly",
        "coverage": data.attrs["coverage"],
        "excluded_furnished_units": data.attrs["excluded_furnished_units"],
        "size_log_scale": data.attrs["size_log_scale"],
        "buildings": data.attrs["names"],
        "snapshot": {
            "id": snapshot,
            "training_sha256": digest(path),
            "scoped_queue": queue,
            "discovered_queue_drained": not queue.get("pending", 0)
            and not queue.get("inflight", 0),
            "coverage_is_exhaustive": False,
            "building_totals": dict(totals),
            "import": counts,
            "worker_seconds": time.monotonic() - started,
            "unit_identity_warning": "Source unit labels are not verified distinct physical units.",
        },
    }
    (result / "metadata.json").write_text(json.dumps(metadata, indent=2))
    volume.commit()
    return metadata


@app.local_entrypoint()
def main(action: str = "prepare", snapshot: str = "chelsea-20260908", output: str = ""):
    safe_id(snapshot)
    if action == "upload":
        upload_files(snapshot, ROOT / "data/archive", ROOT / "data/apartments.duckdb")
    elif action == "prepare":
        print(json.dumps(prepare.remote(snapshot), indent=2))
    elif action == "download":
        destination = Path(output or ROOT / "data/model/prepared" / snapshot)
        destination.mkdir(parents=True, exist_ok=True)
        for name in ["training_data.parquet", "metadata.json", "buildings.jsonl"]:
            with (destination / name).open("wb") as stream:
                for chunk in volume.read_file(f"/snapshots/{snapshot}/prepared/{name}"):
                    stream.write(chunk)
        print(destination)
    else:
        raise ValueError("action must be upload, prepare, or download")
