"""Current listings from a finished history crawl, with no requests.

Ben, 2026-10-10: "Can we treat the listing groups together and use historical listings that
are <7 days old for the current views on the app?" A history crawl reads each unit page, and
a unit page carries the unit's current advertisement. This takes every rental advertisement
whose newest capture in a granular dataset says ACTIVE, re-reads that saved page and projects
it with the current-listings interpreter (`candidate_refresh.interpret`), so the rows have the
same format as a current-listings capture (`details/snapshot/candidates.jsonl`).

Each row is dated by its page's capture time (`collected_at` and `known_at`), never by when
this ran: an ACTIVE status here is only what the page said then. A newer capture of the same
area supersedes these rows; that choice belongs to the reader.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

import duckdb

from . import candidate_refresh as refresh
from . import unit_canonical
from .corrections import canonical
from .research_pipeline import digest, publish_bundle

VERSION = "crawl-current-listings-v1"


def active_ads(dataset):
    """(listing ID, URL, canonical unit URL, snapshot ID, body hash, capture time) for each
    rental advertisement whose newest capture in the dataset says ACTIVE."""
    root = Path(dataset)
    observations = root / "listing_observations" / "*.parquet"
    snapshots = root / "snapshots" / "*.parquet"
    return duckdb.sql(f"""
        with o as (
            select listing_id, url, canonical_unit_url, snapshot_id, listing_type,
                json_extract_string(raw_listing_json, '$.status') status,
                row_number() over (partition by listing_id
                                   order by collected_at desc, snapshot_id desc) rn
            from read_parquet('{observations}') where listing_type = 'rental')
        select o.listing_id, o.url, o.canonical_unit_url, o.snapshot_id, s.body_hash, s.observed_at
        from o join read_parquet('{snapshots}') s using (snapshot_id)
        where o.rn = 1 and o.status = 'ACTIVE'
        order by o.listing_id""").fetchall()


def _body(db, crawl, body_hash):
    """The saved page, or None when it is missing or does not match its hash."""
    row = db.execute("select path from bodies where hash = ?", (body_hash,)).fetchone()
    path = Path(row[0]) if row else None
    if path is not None and not path.is_absolute():
        path = Path(crawl) / path
    if path is None or not path.is_file():
        return None
    data = path.read_bytes()
    data = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
    return data if hashlib.sha256(data).hexdigest() == body_hash else None


def build(dataset, snapshot, crawl, output):
    """Write `output/details/snapshot` from a dataset, its snapshot and the crawl's bodies."""
    dataset, snapshot = Path(dataset), Path(snapshot)
    ads = active_ads(dataset)
    if not ads:
        raise ValueError("No ACTIVE rental advertisements in the dataset")
    plan = {
        "version": VERSION,
        "dataset": str(dataset),
        "dataset_manifest_sha256": digest(dataset / "complete.json"),
        "snapshot": str(snapshot),
        "crawl": str(crawl),
        "listing_ids": [a[0] for a in ads],
        "implementation_sha256": {
            p.name: digest(p) for p in [*refresh._code_paths(), Path(__file__)]
        },
        "limitations": [
            "ACTIVE is what each saved page said when it was captured, not now.",
            "Ads listed after a unit's page was captured are missing; this is not a census.",
            "No corrections overlay is applied; source attributes are as captured.",
        ],
    }
    plan_hash = refresh._hash(plan)
    db = sqlite3.connect(f"file:{snapshot}?immutable=1", uri=True)
    candidates, failures = [], []
    for listing_id, url, unit_url, snapshot_id, body_hash, observed in ads:
        target = {
            "url": url,
            "source_listing_id": listing_id,
            "canonical_unit_url": unit_url,
            "unit_id": unit_canonical.canonical_unit_id(unit_url) if unit_url else None,
            "previous_record": {},
        }
        observation = {
            "id": snapshot_id,
            "body_hash": body_hash,
            "fetched": observed,
            "error": None if unit_url else "no canonical unit",
            "status": 200,
        }
        at = datetime.fromtimestamp(observed, UTC).isoformat()
        body = _body(db, crawl, body_hash)
        if body is None:
            observation["error"] = (
                observation["error"] or "saved body missing or hash mismatch"
            )
            body = b""
        result = refresh.interpret(
            target, observation, body, plan_hash, interpreted_at=at
        )
        if result["status"] != "parsed":
            failures.append(
                {k: result.get(k) for k in ("source_listing_id", "url", "reason")}
            )
            continue
        row = result["candidate"]
        row["crawl_provenance"] = {
            "plan_sha256": plan_hash,
            "snapshot_id": snapshot_id,
            "requested_url": url,
        }
        candidates.append(row)
    report = {
        "version": VERSION,
        "plan_sha256": plan_hash,
        "active_advertisements": len(ads),
        "candidates": len(candidates),
        "failures": len(failures),
        "collected_range": [
            min(c["collected_at"] for c in candidates) if candidates else None,
            max(c["collected_at"] for c in candidates) if candidates else None,
        ],
    }
    lines = lambda rows: "".join(canonical(r) + "\n" for r in rows)  # noqa: E731
    publish_bundle(
        Path(output) / "details" / "snapshot",
        {
            "candidates.jsonl": lines(candidates),
            "failures.jsonl": lines(failures),
            "report.json": canonical(report) + "\n",
            "crawl-plan.json": canonical(plan) + "\n",
        },
        {"version": VERSION, "plan_sha256": plan_hash},
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "snapshot", "crawl", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(build(**vars(parser.parse_args()))))
