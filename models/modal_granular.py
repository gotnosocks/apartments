"""Bounded CPU-only, resumable cloud export; never downloads the archive."""

from pathlib import Path
import json
import re
import time
import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("chelsea-granular-data")
volume = modal.Volume.from_name("chelsea-archive")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "pyarrow==24.0.0", "duckdb==1.5.5", "parsel==1.10.0", "jsonpatch==1.33"
    )
    .env(
        {"PYTHONPATH": "/root/src", "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"}
    )
    .add_local_dir(
        ROOT / "src/apartments", "/root/src/apartments", ignore=["__pycache__"]
    )
    .add_local_dir(
        ROOT / "src/streeteasy_archive",
        "/root/src/streeteasy_archive",
        ignore=["__pycache__"],
    )
    .add_local_file(ROOT / "config/corrections.jsonl", "/root/corrections.jsonl")
)
SNAPSHOT = "/archive/snapshots/chelsea-backfill-20260912/archive.sqlite3"


def root_for(run):
    if not re.fullmatch("[A-Za-z0-9_-]+", run):
        raise ValueError("Unsafe run ID")
    return Path("/archive/datasets") / run


@app.function(
    image=image,
    cpu=2,
    memory=4096,
    timeout=3600,
    volumes={"/archive": volume},
    max_containers=1,
)
def prepare(run):
    from apartments.granular_export import prepare as work

    out = work(SNAPSHOT, root_for(run), "/root/corrections.jsonl")
    volume.commit()
    return out


@app.function(
    image=image,
    cpu=2,
    memory=4096,
    timeout=7200,
    volumes={"/archive": volume},
    max_containers=4,
    retries=1,
)
def shard(run, part):
    from apartments.granular_export import process_shard

    volume.reload()
    out = process_shard(SNAPSHOT, root_for(run), part, "/archive/bodies")
    volume.commit()
    print(json.dumps({k: v for k, v in out.items() if k != "errors"}), flush=True)
    return {k: v for k, v in out.items() if k != "errors"}


@app.function(
    image=image,
    cpu=2,
    memory=4096,
    timeout=3600,
    volumes={"/archive": volume},
    max_containers=1,
)
def finish(run):
    from apartments.granular_export import finish as work

    volume.reload()
    out = work(root_for(run))
    volume.commit()
    return out


@app.function(
    image=image,
    cpu=0.25,
    memory=512,
    timeout=86400,
    volumes={"/archive": volume},
    max_containers=1,
)
def run_all(run="chelsea-granular-20260916"):
    plan = prepare.remote(run)
    print("Prepared", plan, flush=True)
    for result in shard.starmap(
        [(run, i) for i in range(plan["shards"])], order_outputs=False
    ):
        print("Completed", result, flush=True)
    result = finish.remote(run)
    print("COMPLETE", result["tables"], flush=True)
    return result


@app.function(
    image=image, cpu=0.25, memory=512, timeout=120, volumes={"/archive": volume}
)
def status(run="chelsea-granular-20260916"):
    volume.reload()
    root = root_for(run)
    if not root.exists():
        return {"state": "not_started"}
    plan = (
        json.loads((root / "plan.json").read_text())
        if (root / "plan.json").exists()
        else None
    )
    checks = [json.loads(p.read_text()) for p in (root / "checkpoints").glob("*.json")]
    return {
        "plan": plan,
        "completed_shards": len(checks),
        "seconds": sum(c["seconds"] for c in checks),
        "counts": {
            t: sum(c["counts"].get(t, 0) for c in checks)
            for t in (checks[0]["counts"] if checks else [])
        },
        "report": json.loads((root / "quality-report.json").read_text())
        if (root / "quality-report.json").exists()
        else None,
    }


@app.function(
    image=image,
    cpu=2,
    memory=4096,
    timeout=600,
    volumes={"/archive": volume},
    max_containers=1,
)
def probe(run="chelsea-granular-20260916"):
    import gzip
    from apartments.granular_parse import parse_listing
    from apartments.granular_media import page_type, parse_media_gallery

    volume.reload()
    root = root_for(run)
    plan = json.loads((root / "plan.json").read_text())
    samples = []
    started = time.time()
    for i in range(0, plan["shards"], max(1, plan["shards"] // 20)):
        job = json.loads((root / "jobs" / f"{i:05d}.json").read_text())
        item = next((r for r in job if r["kind"] == "listing"), None)
        if not item:
            continue
        read_start = time.time()
        h = item["body_hash"]
        body = gzip.decompress(
            (Path("/archive/bodies") / h[:2] / f"{h}.gz").read_bytes()
        )
        read_seconds = time.time() - read_start
        parse_start = time.time()
        if page_type(item) == "media_gallery":
            row, events = parse_media_gallery(body, item["url"]), []
        else:
            row, events = parse_listing(body, item["url"])
        parse_seconds = time.time() - parse_start
        samples.append(
            {
                **{k: v for k, v in row.items() if k != "raw_listing_json"},
                "events": len(events),
                "first_event": events[0] if events else None,
                "bytes": len(body),
                "read_seconds": read_seconds,
                "parse_seconds": parse_seconds,
            }
        )
    return {"seconds": time.time() - started, "samples": samples}


@app.function(
    image=image,
    cpu=2,
    memory=2048,
    timeout=600,
    volumes={"/archive": volume},
    max_containers=1,
)
def inspect_findings(run="chelsea-granular-20260916"):
    import duckdb
    from parsel import Selector
    from streeteasy_archive.extract import canonical_url, kind_for

    volume.reload()
    root = root_for(run)
    db = duckdb.connect(config={"memory_limit": "512MB", "threads": "2"})
    for table in (
        "listing_observations",
        "building_observations",
        "event_mentions",
        "inventory_rows",
        "inventory_observations",
        "snapshots",
    ):
        db.execute(
            f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{root}/{table}/*.parquet')"
        )
    result = {}
    result["distinct_building_slugs"] = db.execute(
        "SELECT count(DISTINCT building_slug) FROM building_observations"
    ).fetchone()[0]
    result["numeric_flags_by_type"] = db.execute(
        """SELECT listing_type,count(*) FILTER(WHERE bedrooms<0 OR bedrooms>20),count(*) FILTER(WHERE bathrooms<=0 OR bathrooms>20),count(*) FILTER(WHERE room_count<=0 OR room_count>20) FROM listing_observations GROUP BY listing_type"""
    ).fetchall()
    result["nonpositive_prices_by_category"] = db.execute(
        "SELECT event_category,count(*) FROM event_mentions WHERE price<=0 GROUP BY event_category"
    ).fetchall()
    result["attribute_disagreement_fields"] = db.execute(
        """SELECT listing_type,count(*) FILTER(WHERE bed>1),count(*) FILTER(WHERE bath>1),count(*) FILTER(WHERE sqft>1) FROM (SELECT listing_type,building_slug,unit_label,count(DISTINCT bedrooms) bed,count(DISTINCT bathrooms) bath,count(DISTINCT square_feet) sqft FROM listing_observations WHERE unit_label IS NOT NULL AND building_slug IS NOT NULL GROUP BY ALL) GROUP BY listing_type"""
    ).fetchall()
    ids = db.execute(
        "SELECT i.snapshot_id,s.url,i.count,i.row_count FROM inventory_observations i JOIN snapshots s USING(snapshot_id) WHERE i.count<>i.row_count"
    ).fetchall()
    result["inventory_mismatches"] = []
    for sid, url, count, rows in ids:
        rec = {
            "snapshot_id": sid,
            "url": url,
            "displayed_count": count,
            "retained_rows": rows,
            "rows_without_record": [],
        }
        for row in db.execute(
            "SELECT row_index,listing_url,row_kind,row_html FROM inventory_rows WHERE snapshot_id=? ORDER BY row_index",
            [sid],
        ).fetchall():
            if row[1] is None:
                rec["rows_without_record"].append(row)
        result["inventory_mismatches"].append(rec)
    # Check the exporter pairing against every saved HTML row, without downloading it.
    mismatch = []
    missing = []
    checked = 0
    cursor = db.execute(
        "SELECT snapshot_id,row_index,listing_url,row_html FROM inventory_rows"
    )
    while batch := cursor.fetchmany(256):
        for sid, index, expected, html in batch:
            if not html:
                if expected:
                    missing.append(
                        {"snapshot_id": sid, "row_index": index, "url": expected}
                    )
                continue
            urls = [
                canonical_url(x)
                for x in Selector(text=html).css("a::attr(href)").getall()
            ]
            actual = next(
                (u for u in urls if u and kind_for(u) == "listing"), None
            ) or next((u for u in urls if u and "/closing/" in u), None)
            checked += 1
            if actual != expected:
                mismatch.append(
                    {
                        "snapshot_id": sid,
                        "row_index": index,
                        "expected": expected,
                        "html_url": actual,
                    }
                )
    result["inventory_link_check"] = {
        "checked_rows": checked,
        "mismatches": len(mismatch),
        "examples": mismatch[:10],
        "missing_html": len(missing),
    }
    db.close()
    return result
