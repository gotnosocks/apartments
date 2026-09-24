"""Resume bounded offline reparses into an immutable description-only bundle.

Captured HTML and granular source tables are never modified. Each accepted row
binds the new interpretation to the exact old listing payload and capture body.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import importlib.metadata
import json
import multiprocessing
import os
from pathlib import Path
import re
import tempfile

from . import granular_parse, unit_canonical, research_pipeline
from .research_pipeline import digest, read_bundle
from streeteasy_archive import extract, flight

VERSION = "description-recovery-v1"
_REFERENCE = re.compile(r"\$[0-9a-f]+")
_HASH = re.compile(r"[0-9a-f]{64}")


def _json(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _atomic(path, content):
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".partial-", delete=False
    ) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    temporary.replace(path)


def _inventory(root):
    files = {"complete.json": digest(root / "complete.json")}
    for name in ("listing_observations", "snapshots"):
        paths = sorted((root / name).glob("*.parquet"))
        if not paths:
            raise ValueError(f"Missing source shards: {name}")
        files.update({str(p.relative_to(root)): digest(p) for p in paths})
    return files


def _implementation():
    return {
        name: digest(path)
        for name, path in {
            "description_recovery": __file__,
            "granular_parse": granular_parse.__file__,
            "flight": flight.__file__,
            "extract": extract.__file__,
            "unit_canonical": unit_canonical.__file__,
            "research_pipeline": research_pipeline.__file__,
        }.items()
    }


def _read_body(path, limit):
    chunks, size, sha = [], 0, hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        while size < limit:
            block = stream.read(min(65536, limit - size))
            if not block:
                return b"".join(chunks), sha.hexdigest()
            chunks.append(block)
            sha.update(block)
            size += len(block)
        # A capture at the limit is conservatively rejected, without reading an
        # additional decompressed byte. This bounds each worker's input memory.
        raise ValueError("body_decompression_limit")


def recover_capture(capture, body_root, *, max_body_bytes=32 * 1024 * 1024):
    """Reparse one candidate, returning an accepted or quarantined audit row."""
    raw_string = capture["raw_listing_json"]
    original = json.loads(raw_string)
    reference = original.get("description")
    row = {
        "snapshot_id": capture["snapshot_id"],
        "listing_id": str(capture["listing_id"]),
        "source_url": capture["url"],
        "canonical_unit_url": capture.get("canonical_unit_url"),
        "source_observed_at": capture.get("snapshot_observed_at"),
        "source_body_sha256": capture.get("body_hash"),
        "original_raw_listing_sha256": hashlib.sha256(raw_string.encode()).hexdigest(),
        "original_description_reference": reference,
        "interpreted_at": datetime.now(timezone.utc).isoformat(),
        "recovery_version": VERSION,
        "parser_version": granular_parse.VERSION,
        "flight_decoder_version": flight.VERSION,
    }

    def reject(reason, **extra):
        return {**row, "status": "quarantined", "reason": reason, **extra}

    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        return reject("not_unresolved_description_reference")
    body_hash = capture.get("body_hash")
    if not isinstance(body_hash, str) or not _HASH.fullmatch(body_hash):
        return reject("missing_or_invalid_body_hash")
    if capture.get("snapshot_url") != capture["url"]:
        return reject("snapshot_url_mismatch")
    try:
        body, actual_hash = _read_body(
            Path(body_root) / body_hash[:2] / (body_hash + ".gz"), max_body_bytes
        )
    except FileNotFoundError:
        return reject("missing_archive_body")
    except (OSError, EOFError, ValueError) as exc:
        return reject("body_read_failure", detail=str(exc)[:400])
    if actual_hash != body_hash:
        return reject("body_hash_mismatch", actual_body_sha256=actual_hash)
    try:
        parsed, _ = granular_parse.parse_listing(body, capture["url"])
    except Exception as exc:
        return reject("reparse_error", detail=f"{type(exc).__name__}: {exc}"[:400])
    if parsed.get("parse_status") != "ok":
        return reject(
            "reparse_not_ok",
            parse_status=parsed.get("parse_status"),
            detail=parsed.get("error"),
        )
    if str(parsed.get("listing_id")) != str(capture["listing_id"]) or str(
        original.get("id")
    ) != str(capture["listing_id"]):
        return reject("listing_identity_mismatch")
    identity_fields = (
        "canonical_unit_url",
        "unit_label",
        "building_slug",
        "listing_type",
    )
    changes = [
        name for name in identity_fields if parsed.get(name) != capture.get(name)
    ]
    if changes:
        return reject("source_identity_changed", changed_identity_fields=changes)
    current = json.loads(parsed["raw_listing_json"])
    text = current.get("description")
    if not isinstance(text, str) or not text.strip() or _REFERENCE.fullmatch(text):
        return reject("description_not_recovered")
    old_other = {k: v for k, v in original.items() if k != "description"}
    new_other = {k: v for k, v in current.items() if k != "description"}
    if _json(old_other) != _json(new_other):
        changed = sorted(
            k
            for k in old_other.keys() | new_other.keys()
            if _json(old_other.get(k)) != _json(new_other.get(k))
            or (k in old_other) != (k in new_other)
        )
        return reject(
            "non_description_payload_changed",
            changed_top_level_fields=changed,
            reparsed_raw_listing_sha256=hashlib.sha256(
                parsed["raw_listing_json"].encode()
            ).hexdigest(),
        )
    return {
        **row,
        "status": "accepted",
        "resolved_description": text,
        "description_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "reparsed_raw_listing_sha256": hashlib.sha256(
            parsed["raw_listing_json"].encode()
        ).hexdigest(),
    }


def _worker(task):
    capture, body_root, limit = task
    return recover_capture(capture, body_root, max_body_bytes=limit)


def build_description_recovery(
    dataset,
    body_root,
    output,
    *,
    workers=4,
    batch_size=64,
    max_body_bytes=32 * 1024 * 1024,
    progress=None,
):
    """Hash inputs, resume committed batches, and publish a verified bundle.

    At most ``batch_size`` captures are queued and ``workers`` bodies are parsed
    concurrently. A batch becomes reusable only after its content-hash checkpoint
    commits. All configuration, source and implementation hashes must match on
    resume. ``progress`` is an optional callback after each committed batch.
    """
    import duckdb

    if (
        not 1 <= workers <= 8
        or not 1 <= batch_size <= 256
        or not 1024 <= max_body_bytes <= 32 * 1024 * 1024
    ):
        raise ValueError("Invalid bounded worker, batch or body-size configuration")
    root, bodies, out = (
        Path(dataset).resolve(),
        Path(body_root).resolve(),
        Path(output).resolve(),
    )
    if out == root or root in out.parents or out == bodies or bodies in out.parents:
        raise ValueError("Recovery output must be separate from immutable source data")
    source_files = _inventory(root)
    source_complete = json.loads((root / "complete.json").read_text())
    if source_complete.get("unit_association_rule") != "canonical-url-v1":
        raise ValueError("Completed canonical-url-v1 source required")
    implementation = _implementation()
    plan = {
        "recovery_version": VERSION,
        "source_dataset": str(root),
        "body_root": str(bodies),
        "source_manifest_sha256": _hash(source_files),
        "source_files": source_files,
        "implementation_sha256": implementation,
        "batch_size": batch_size,
        "max_body_bytes": max_body_bytes,
        "runtime_versions": {
            name: importlib.metadata.version(name)
            for name in ("duckdb", "parsel", "lxml")
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / "recovery-plan.json").exists():
            if json.loads((out / "recovery-plan.json").read_text()) != plan:
                raise ValueError(
                    "Recovery inputs or implementation changed; choose a new output directory"
                )
        elif any(p.name != ".build.lock" for p in out.iterdir()):
            raise ValueError("Recovery output contains unrelated files")
        else:
            _atomic(out / "recovery-plan.json", _json(plan) + "\n")
        if (out / "complete.json").exists():
            return read_bundle(out)
        parts, checkpoints = out / "parts", out / "checkpoints"
        parts.mkdir(exist_ok=True)
        checkpoints.mkdir(exist_ok=True)
        db = duckdb.connect(config={"memory_limit": "512MB", "threads": "2"})
        total, part, counts, reasons = 0, 0, Counter(), Counter()
        try:
            for name in ("listing_observations", "snapshots"):
                db.read_parquet(
                    [str(root / p) for p in source_files if p.startswith(name + "/")]
                ).create_view(name)
            duplicate = db.execute(
                "SELECT snapshot_id FROM snapshots GROUP BY snapshot_id HAVING count(*) > 1 LIMIT 1"
            ).fetchone()
            if duplicate:
                raise ValueError("Duplicate source snapshot metadata")
            db.execute("""SELECT l.*, s.body_hash, s.url AS snapshot_url, s.observed_at AS snapshot_observed_at FROM listing_observations l
                LEFT JOIN snapshots s USING(snapshot_id)
                WHERE l.listing_type='rental' AND regexp_full_match(json_extract_string(l.raw_listing_json,'$.description'), '\\$[0-9a-f]+')
                ORDER BY l.snapshot_id""")
            keys = [item[0] for item in db.description]
            previous_id = None
            with (
                ProcessPoolExecutor(
                    max_workers=workers, mp_context=multiprocessing.get_context("spawn")
                )
                if workers > 1
                else _InlineExecutor() as pool
            ):
                while batch := db.fetchmany(batch_size):
                    captures = [dict(zip(keys, values)) for values in batch]
                    for capture in captures:
                        if (
                            previous_id is not None
                            and capture["snapshot_id"] <= previous_id
                        ):
                            raise ValueError(
                                "Duplicate or unordered listing snapshot candidates"
                            )
                        previous_id = capture["snapshot_id"]
                    path, checkpoint = (
                        parts / f"{part:06d}.jsonl",
                        checkpoints / f"{part:06d}.json",
                    )
                    candidate_hash = _hash(captures)
                    if checkpoint.exists():
                        saved = json.loads(checkpoint.read_text())
                        if (
                            saved["candidate_sha256"] != candidate_hash
                            or digest(path) != saved["artifact_sha256"]
                        ):
                            raise ValueError("Recovery checkpoint integrity failure")
                        # JSONL records end at LF, not Unicode separators that
                        # can occur literally inside recovered description text.
                        with path.open(encoding="utf-8", newline="\n") as source:
                            result = [json.loads(line) for line in source]
                        if len(result) != len(captures) or [
                            r["snapshot_id"] for r in result
                        ] != [r["snapshot_id"] for r in captures]:
                            raise ValueError("Recovery checkpoint row identity failure")
                    else:
                        result = list(
                            pool.map(
                                _worker,
                                [(c, str(bodies), max_body_bytes) for c in captures],
                            )
                        )
                        _atomic(path, "".join(_json(r) + "\n" for r in result))
                        _atomic(
                            checkpoint,
                            _json(
                                {
                                    "candidate_sha256": candidate_hash,
                                    "artifact_sha256": digest(path),
                                    "rows": len(result),
                                }
                            )
                            + "\n",
                        )
                    counts.update(r["status"] for r in result)
                    reasons.update(
                        r["reason"] for r in result if r["status"] == "quarantined"
                    )
                    total += len(result)
                    part += 1
                    if progress:
                        progress(
                            {
                                "processed": total,
                                "accepted": counts["accepted"],
                                "quarantined": counts["quarantined"],
                                "batches": part,
                            }
                        )
        finally:
            db.close()
        if _inventory(root) != source_files or _implementation() != implementation:
            raise ValueError("Source or implementation changed during recovery")
        coverage = {
            "candidates": total,
            "accepted": counts["accepted"],
            "quarantined": counts["quarantined"],
            "quarantine_reasons": dict(sorted(reasons.items())),
            "batches": part,
        }
        # Stream final artifacts from committed parts; publishing the completion
        # marker last makes incomplete finalization safely resumable.
        for status, name in (
            ("accepted", "accepted.jsonl"),
            ("quarantined", "quarantined.jsonl"),
        ):
            with tempfile.NamedTemporaryFile(
                "w", dir=out, encoding="utf-8", prefix=".partial-", delete=False
            ) as stream:
                for index in range(part):
                    with (parts / f"{index:06d}.jsonl").open(
                        encoding="utf-8", newline="\n"
                    ) as source:
                        for line in source:
                            if json.loads(line)["status"] == status:
                                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
                temporary = Path(stream.name)
            temporary.replace(out / name)
        _atomic(out / "source-files.json", _json(source_files) + "\n")
        _atomic(out / "coverage.json", _json(coverage) + "\n")
        files = {
            name: digest(out / name)
            for name in (
                "accepted.jsonl",
                "quarantined.jsonl",
                "source-files.json",
                "coverage.json",
            )
        }
        manifest = {
            "recovery_version": VERSION,
            "parser_version": granular_parse.VERSION,
            "flight_decoder_version": flight.VERSION,
            "source_dataset": str(root),
            "source_manifest_sha256": _hash(source_files),
            "implementation_sha256": implementation,
            "runtime_versions": plan["runtime_versions"],
            "coverage": coverage,
            "files": files,
            "clock_contract": "interpreted_at is new interpretation knowledge, never a new capture or attribute effective date",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic(out / "complete.json", _json(manifest) + "\n")
        return read_bundle(out)


class _InlineExecutor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def map(self, function, tasks):
        return map(function, tasks)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("body_root")
    parser.add_argument("output")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    manifest = build_description_recovery(
        args.dataset,
        args.body_root,
        args.output,
        workers=args.workers,
        batch_size=args.batch_size,
        progress=lambda value: print(_json(value), flush=True),
    )
    print(_json(manifest), flush=True)
