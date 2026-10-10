"""Write a smaller copy of an archive database without its duplicate page HTML.

Each Oxylabs capture stores the provider envelope in `snapshots.extracted` under
`provider_capture`, and its `results[].content` is the full page HTML. The same bytes
are already kept, content-addressed, as the gzip body named by `snapshots.body_hash`
(`bodies/<hh>/<hash>.gz`), so the copy in the JSON is about 44% of every crawl and
snapshot database. No reader uses it: `capture.capture_metadata` already drops it from
observations for the same reason.

`compact_database` never touches the source. It writes a new database that keeps
every table, row id and index, and rewrites only `snapshots.extracted`: a result's
`content` is replaced by `content_sha256` when the content hashes to the row's
`body_hash` and that body file exists (and, with `verify_bodies`, decompresses to bytes
with that hash). Any other row is copied unchanged and counted in the report.
"""

from __future__ import annotations

import contextlib
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3

STRIPPED_KEY = "content_sha256"


def strip_results(results, body_hash):
    """`results` with each `content` replaced by `content_sha256`, or (None, reason) when
    any content is not the page HTML that hashes to `body_hash`."""
    stripped = []
    for result in results:
        if not isinstance(result, dict) or "content" not in result:
            stripped.append(result)
            continue
        content = result["content"]
        if not isinstance(content, str):
            return None, "content_not_text"
        if hashlib.sha256(content.encode()).hexdigest() != body_hash:
            return None, "content_differs_from_body"
        item = {k: v for k, v in result.items() if k != "content"}
        item[STRIPPED_KEY] = body_hash
        stripped.append(item)
    return stripped, "stripped"


def without_page_copy(provider, body):
    """The provider envelope as the crawler stores it: the page HTML it repeats is replaced by
    the hash of `body`, which the store keeps once in `bodies/`. Returned unchanged when the
    HTML is not that body, as `compact_database` would leave it."""
    results = provider.get("results") if isinstance(provider, dict) else None
    if not isinstance(results, list):
        return provider
    stripped, _ = strip_results(results, hashlib.sha256(body).hexdigest())
    return provider if stripped is None else {**provider, "results": stripped}


def strip_provider_content(extracted, body_hash, body_ok):
    """Return (new extracted text or None if unchanged, bytes removed, reason)."""
    if not extracted or '"provider_capture"' not in extracted:
        return None, 0, "no_provider_capture"
    data = json.loads(extracted)
    provider = data.get("provider_capture")
    results = provider.get("results") if isinstance(provider, dict) else None
    if not isinstance(results, list) or not any(
        isinstance(r, dict) and "content" in r for r in results
    ):
        return None, 0, "no_provider_content"
    stripped, reason = strip_results(results, body_hash)
    if stripped is None:
        return None, 0, reason
    if not body_ok(body_hash):
        return None, 0, "body_unavailable"
    provider["results"] = stripped
    # The crawler stores extracted with json.dumps defaults; keep that format.
    text = json.dumps(data)
    return text, len(extracted) - len(text), "stripped"


def _body_checker(bodies, verify_bodies):
    """Paths from the source `bodies` table, resolved against the crawl directory."""
    seen = {}

    def ok(body_hash):
        if body_hash not in seen:
            path = bodies.get(body_hash)
            good = path is not None and path.is_file()
            if good and verify_bodies:
                try:
                    raw = gzip.decompress(path.read_bytes())
                except (OSError, EOFError):
                    raw = None
                good = raw is not None and hashlib.sha256(raw).hexdigest() == body_hash
            seen[body_hash] = good
        return seen[body_hash]

    return ok


def compact_database(source, destination, crawl_dir, verify_bodies=True):
    """Copy `source` to a new `destination` without duplicate provider HTML.

    `crawl_dir` is the directory that holds the crawl's `bodies/`; the source's
    `bodies` table paths are relative to it. Returns a report dict.
    """
    source, destination = Path(source).resolve(), Path(destination)
    crawl_dir = Path(crawl_dir).resolve()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Compacted database destination already exists")
    wal = Path(str(source) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError("Refusing to compact a database with a nonempty WAL")
    # immutable=1 reads a database that is still being written silently wrong, so
    # hold the crawler's lock for the whole copy.
    with contextlib.ExitStack() as held:
        for lock in {source.parent / "crawler.lock", crawl_dir / "crawler.lock"}:
            if lock.exists():
                f = held.enter_context(lock.open("a"))
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError(f"A crawler holds {lock}") from None
        return _copy(source, destination, crawl_dir, verify_bodies)


def _copy(source, destination, crawl_dir, verify_bodies):
    src = sqlite3.connect(source.as_uri() + "?immutable=1", uri=True)
    objects = src.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master"
        " WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
    ).fetchall()
    tables = [name for kind, name, _, _ in objects if kind == "table"]
    bodies = {}
    if "bodies" in tables:
        bodies = {
            h: crawl_dir / p for h, p in src.execute("SELECT hash, path FROM bodies")
        }
    page_size = src.execute("PRAGMA page_size").fetchone()[0]
    user_version = src.execute("PRAGMA user_version").fetchone()[0]
    src.close()

    body_ok = _body_checker(bodies, verify_bodies)
    reasons = {}
    saved = [0]

    def strip(extracted, body_hash):
        text, removed, reason = strip_provider_content(extracted, body_hash, body_ok)
        reasons[reason] = reasons.get(reason, 0) + 1
        saved[0] += removed
        return extracted if text is None else text

    partial = destination.with_name(destination.name + ".partial")
    partial.unlink(missing_ok=True)
    # A URI connection lets ATTACH open the source immutable (read-only, no -shm).
    db = sqlite3.connect(partial.resolve().as_uri(), uri=True)
    db.create_function("strip_provider_content", 2, strip, deterministic=True)
    try:
        db.execute(f"PRAGMA page_size={int(page_size)}")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("ATTACH DATABASE ? AS src", (source.as_uri() + "?immutable=1",))
        for kind, _, _, sql in objects:
            if kind == "table":
                db.execute(sql)
        counts = {}
        for name in tables:
            columns = [r[1] for r in db.execute(f'PRAGMA src.table_info("{name}")')]
            select = [
                "strip_provider_content(extracted, body_hash)"
                if name == "snapshots" and c == "extracted"
                else f'"{c}"'
                for c in columns
            ]
            names = ", ".join(f'"{c}"' for c in columns)
            # rowid is copied too, so row ids of tables without an INTEGER PRIMARY
            # KEY stay the same.
            has_rowid = (
                db.execute(
                    "SELECT 1 FROM src.sqlite_master WHERE name=? AND sql LIKE"
                    " '%WITHOUT ROWID%'",
                    (name,),
                ).fetchone()
                is None
            )
            if has_rowid:
                db.execute(
                    f'INSERT INTO main."{name}"(rowid, {names})'
                    f' SELECT rowid, {", ".join(select)} FROM src."{name}" ORDER BY rowid'
                )
            else:
                db.execute(
                    f'INSERT INTO main."{name}"({names})'
                    f' SELECT {", ".join(select)} FROM src."{name}"'
                )
            counts[name] = db.execute(f'SELECT count(*) FROM main."{name}"').fetchone()[
                0
            ]
            if (
                counts[name]
                != db.execute(f'SELECT count(*) FROM src."{name}"').fetchone()[0]
            ):
                raise RuntimeError(f"Row count differs for {name}")
        if db.execute(
            "SELECT 1 FROM src.sqlite_master WHERE name='sqlite_sequence'"
        ).fetchone():
            db.execute("DELETE FROM main.sqlite_sequence")
            db.execute(
                "INSERT INTO main.sqlite_sequence SELECT * FROM src.sqlite_sequence"
            )
        for kind, _, _, sql in objects:
            if kind != "table":
                db.execute(sql)
        db.execute(f"PRAGMA user_version={int(user_version)}")
        if db.execute(
            "SELECT 1 FROM src.sqlite_master WHERE name='sqlite_stat1'"
        ).fetchone():
            # Keep the source's planner statistics; ANALYZE of one table creates
            # sqlite_stat1, whose rows are then replaced by the source's.
            db.execute(f'ANALYZE main."{tables[0]}"')
            db.execute("DELETE FROM main.sqlite_stat1")
            db.execute("INSERT INTO main.sqlite_stat1 SELECT * FROM src.sqlite_stat1")
        db.commit()
        db.execute("DETACH DATABASE src")
        db.execute("PRAGMA journal_mode=DELETE")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Compacted database failed integrity_check")
    except BaseException:
        db.close()
        partial.unlink(missing_ok=True)
        raise
    db.close()
    # Callers may delete the source after this returns, so make the copy durable.
    with partial.open("rb") as f:
        os.fsync(f.fileno())
    partial.replace(destination)
    directory = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {
        "source": str(source),
        "destination": str(destination),
        "source_bytes": source.stat().st_size,
        "destination_bytes": destination.stat().st_size,
        "json_bytes_removed": saved[0],
        "snapshots": reasons,
        "rows": counts,
        "verify_bodies": verify_bodies,
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", help="archive.sqlite3 to read (never modified)")
    parser.add_argument("destination", help="new database path (must not exist)")
    parser.add_argument(
        "--crawl-dir", required=True, help="directory holding the crawl's bodies/"
    )
    parser.add_argument(
        "--no-verify-bodies",
        action="store_true",
        help="check that body files exist but do not decompress and hash them",
    )
    args = parser.parse_args(argv)
    report = compact_database(
        args.source, args.destination, args.crawl_dir, not args.no_verify_bodies
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
