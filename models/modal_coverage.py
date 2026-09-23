"""Streaming coverage audit for a StreetEasy archive snapshot.

The audit reads SQLite metadata and extracted JSON only.  It never opens body
files and keeps the large snapshots table streaming, so it can run beside the
archive volume without copying the archive locally.
"""

from __future__ import annotations

import json
import gzip
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import modal

ROOT = Path(__file__).resolve().parents[1]
VOLUME_NAME = "chelsea-archive"
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App("chelsea-archive-coverage")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("parsel==1.10.0")
    .env({"PYTHONPATH": "/root:/root/src"})
    .add_local_dir(
        ROOT / "src/streeteasy_archive",
        "/root/src/streeteasy_archive",
        ignore=["__pycache__"],
    )
    .add_local_file(ROOT / "models/modal_coverage.py", "/root/modal_coverage.py")
)


def _root(url: str) -> str | None:
    match = re.fullmatch(r"https://streeteasy\.com/building/([^/?#]+)", url or "")
    return match.group(0) if match else None


def _inventory_category(url: str) -> str | None:
    value = dict(parse_qsl(urlsplit(url).query)).get("archive_view")
    return {"unavailable-rentals": "rentals", "unavailable-sales": "sales"}.get(value)


def _successful_observation(db, url: str, body_hash: str | None = None):
    query = """SELECT status,error,fetched,body_hash FROM observations
               WHERE url=? AND error IS NULL AND (status BETWEEN 200 AND 299 OR status=304)"""
    args = [url]
    if body_hash:
        query += " AND body_hash=?"
        args.append(body_hash)
    return db.execute(query + " ORDER BY fetched DESC,id DESC LIMIT 1", args).fetchone()


def _inventory_result(data: dict, source_url: str) -> dict:
    inventory = data.get("inventory") or {}
    links = inventory.get("links") or []
    records = inventory.get("records") or links  # pre-closing-schema captures
    displayed = inventory.get("count")
    expected = inventory.get("expected_counts") or []
    expected_max = max(expected) if expected else None
    link_urls = {x.get("url") for x in links if isinstance(x, dict) and x.get("url")}
    complete = (
        isinstance(displayed, int)
        and len(records) == displayed
        and (expected_max is None or expected_max <= displayed)
    )
    return {
        "url": source_url,
        "category": _inventory_category(source_url),
        "displayed_count": displayed,
        "record_count": len(records),
        "detail_link_count": len(links),
        "closing_record_count": sum(
            x.get("kind") == "closing" for x in records if isinstance(x, dict)
        ),
        "unique_detail_link_count": len(link_urls),
        "expected_summary_max": expected_max,
        "complete": complete,
    }


def audit_connection(db: sqlite3.Connection, generation: int | None = None) -> dict:
    """Return a bounded, JSON serializable coverage report from an open DB."""
    from streeteasy_archive.scope import summary_counts

    if generation is None:
        row = db.execute("SELECT max(id) FROM generations").fetchone()
        generation = row[0] if row and row[0] is not None else None

    queue = Counter()
    if generation is not None:
        for kind, state, count in db.execute(
            "SELECT f.kind,f.state,count(*) FROM frontier f "
            "JOIN scope_urls s ON s.generation=f.generation AND s.url=f.url "
            "WHERE f.generation=? GROUP BY f.kind,f.state",
            (generation,),
        ):
            queue[f"{kind or 'unknown'}:{state}"] = count

    # Keep only URL keys and small counters in memory.  Extracted JSON is read
    # one snapshot at a time; this is essential for the multi-GB archive.
    latest_buildings = {}
    latest_inventory = {}
    listing_urls = set()
    inventory_listing_urls = set()
    expected_by_building = defaultdict(lambda: {"rentals": 0, "sales": 0})
    for url, extracted in db.execute(
        "SELECT s.url,s.extracted FROM snapshots s "
        "WHERE s.id=(SELECT max(s2.id) FROM snapshots s2 WHERE s2.url=s.url) "
        "ORDER BY s.id"
    ):
        try:
            data = json.loads(extracted)
        except (TypeError, ValueError):
            continue
        category = _inventory_category(url)
        if category:
            latest_inventory[url] = _inventory_result(data, url)
            for item in (data.get("inventory") or {}).get("links") or []:
                if isinstance(item, dict) and item.get("url"):
                    inventory_listing_urls.add(item["url"])
        root = _root(url)
        if root:
            latest_buildings[root] = url
            for category_name, key in (
                ("rentals", "rentalSummary"),
                ("sales", "saleSummary"),
            ):
                values = summary_counts(data, key)
                if values:
                    expected_by_building[root][category_name] = max(values)
        for item in data.get("links") or []:
            if (
                isinstance(item, dict)
                and item.get("kind") == "listing"
                and item.get("url")
            ):
                listing_urls.add(item["url"])

    scope_buildings = set()
    if generation is not None:
        for (url,) in db.execute(
            "SELECT url FROM scope_buildings WHERE generation=?", (generation,)
        ):
            if _root(url):
                scope_buildings.add(url)
    captured_buildings = set(latest_buildings)
    missing = sorted(scope_buildings - captured_buildings)

    inventory_errors = Counter()
    inventory_failed_examples = []
    for url, error, status in db.execute(
        "SELECT o.url,o.error,o.status FROM observations o "
        "WHERE o.url LIKE '%archive_view=unavailable-%' AND o.error IS NOT NULL "
        "AND o.id=(SELECT max(o2.id) FROM observations o2 WHERE o2.url=o.url)"
    ):
        inventory_errors[str(error).split(":", 1)[0]] += 1
        if len(inventory_failed_examples) < 100:
            inventory_failed_examples.append(
                {"url": url, "status": status, "error": error}
            )
    inventory_complete = sum(x["complete"] for x in latest_inventory.values())
    inventory_incomplete = (
        len(latest_inventory) - inventory_complete + sum(inventory_errors.values())
    )
    expected_total = {
        category: sum(values[category] for values in expected_by_building.values())
        for category in ("rentals", "sales")
    }

    return {
        "generation": generation,
        "generated_at_epoch": time.time(),
        "building_pages": {
            "captured_latest": len(captured_buildings),
            "scoped_expected": len(scope_buildings),
            "missing_scoped_buildings": len(missing),
            "missing_examples": missing[:100],
        },
        "source_inventory_counts": expected_total,
        "inventory_captures": {
            "total_latest": len(latest_inventory),
            "complete": inventory_complete,
            "incomplete_or_failed": inventory_incomplete,
            "failed_by_reason": dict(inventory_errors),
            "failed_examples": inventory_failed_examples,
            "details": list(latest_inventory.values())[:1000],
        },
        "discovered_listing_detail_urls": {
            "all_unique": len(listing_urls),
            "from_unavailable_inventory_unique": len(inventory_listing_urls),
            "examples": sorted(listing_urls)[:100],
        },
        "scoped_frontier": dict(sorted(queue.items())),
        "limitations": [
            "Source unit labels are not equated with distinct physical units.",
            "Counts are archive captures and discovered URLs, not provider inventory guarantees.",
        ],
    }


def audit_snapshot(snapshot: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", snapshot):
        raise ValueError("invalid snapshot id")
    path = Path("/archive/snapshots") / snapshot / "archive.sqlite3"
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return audit_connection(db)
    finally:
        db.close()


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
def debug_inventory_failures(snapshot: str, limit: int = 20) -> dict:
    """Inspect a small number of failed inventory bodies without provider calls."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", snapshot):
        raise ValueError("invalid snapshot id")
    from parsel import Selector
    from lxml import etree
    from streeteasy_archive.extract import _scripts
    from streeteasy_archive.scope import summary_counts

    db_path = Path("/archive/snapshots") / snapshot / "archive.sqlite3"
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = []
    query = """SELECT o.url,o.error,o.status,o.body_hash,b.path FROM observations o
               LEFT JOIN bodies b ON b.hash=o.body_hash
               WHERE o.url LIKE '%archive_view=unavailable-%' AND o.error LIKE 'parser coverage gap%'
                 AND o.id=(SELECT max(o2.id) FROM observations o2 WHERE o2.url=o.url)
               ORDER BY o.url LIMIT ?"""
    try:
        for url, error, status, body_hash, relative in db.execute(
            query, (min(max(limit, 1), 100),)
        ):
            item = {
                "url": url,
                "status": status,
                "error": error,
                "body_hash": body_hash,
            }
            if not relative:
                item["body"] = "missing"
                rows.append(item)
                continue
            try:
                with gzip.open(Path("/archive") / relative, "rb") as stream:
                    body = stream.read(32 * 1024 * 1024 + 1)
                sel = Selector(
                    root=etree.fromstring(
                        body.strip() or b"<html/>", etree.HTMLParser(no_network=True)
                    ),
                    type="html",
                )
                dialogs = sel.css('[role="dialog"]')
                labels = [
                    x.strip()
                    for x in dialogs.css('[role="tab"]').xpath("string(.)").getall()
                    if x.strip()
                ]
                selected = [
                    x.strip()
                    for x in dialogs.css('button[aria-pressed="true"]')
                    .xpath("string(.)")
                    .getall()
                    if x.strip()
                ]
                hrefs = dialogs.css("a::attr(href)").getall()
                unit_hrefs = [x for x in hrefs if re.search(r"/(?:rental|sale)/\d+", x)]
                rows_count = len(dialogs.css("tbody tr"))
                all_labels = re.findall(r"All\s*\(\s*([\d,]+)\s*\)", " ".join(labels))
                scripts = _scripts(sel)
                item.update(
                    {
                        "bytes": len(body),
                        "title": sel.css("title::text").get(),
                        "dialog_count": len(dialogs),
                        "tab_labels": labels[:20],
                        "selected_buttons": selected[:10],
                        "tbody_row_count": rows_count,
                        "dialog_detail_href_count": len(unit_hrefs),
                        "all_tab_counts": [int(x.replace(",", "")) for x in all_labels],
                        "raw_summary_counts": {
                            "rentals": summary_counts(
                                {"scripts": scripts}, "rentalSummary"
                            ),
                            "sales": summary_counts(
                                {"scripts": scripts}, "saleSummary"
                            ),
                        },
                        "expected_selector": "[role=dialog] tbody tr",
                        "detail_selector": "[role=dialog] tbody tr a[href*=/rental/]",
                    }
                )
            except Exception as exc:
                item["body_parse_error"] = f"{type(exc).__name__}: {exc}"
            rows.append(item)
    finally:
        db.close()
    return {
        "snapshot": snapshot,
        "failed_inventory_count_sampled": len(rows),
        "failures": rows,
    }


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
def audit(snapshot: str):
    report = audit_snapshot(snapshot)
    out = Path("/archive/snapshots") / snapshot / "coverage.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    volume.commit()
    return report


@app.local_entrypoint()
def main(snapshot: str = "chelsea-20260908", action: str = "audit"):
    if action == "debug":
        print(
            json.dumps(
                debug_inventory_failures.remote(snapshot), indent=2, sort_keys=True
            )
        )
    elif action == "audit":
        print(json.dumps(audit.remote(snapshot), indent=2, sort_keys=True))
    else:
        raise ValueError("action must be audit or debug")
