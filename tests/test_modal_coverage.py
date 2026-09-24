import importlib.util
import json
import sqlite3
from pathlib import Path


def load_module():
    path = Path(__file__).parents[1] / "models/modal_coverage.py"
    spec = importlib.util.spec_from_file_location("modal_coverage_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_reconciles_inventory_and_missing_building(tmp_path):
    module = load_module()
    db = sqlite3.connect(tmp_path / "archive.sqlite3")
    db.executescript("""
      CREATE TABLE generations(id INTEGER PRIMARY KEY);
      CREATE TABLE scope_buildings(generation INTEGER, url TEXT);
      CREATE TABLE scope_urls(generation INTEGER, url TEXT);
      CREATE TABLE frontier(generation INTEGER, url TEXT, kind TEXT, state TEXT);
      CREATE TABLE snapshots(id INTEGER PRIMARY KEY, url TEXT, extracted TEXT);
      CREATE TABLE observations(id INTEGER PRIMARY KEY, url TEXT, error TEXT,
                                status INTEGER, fetched REAL, body_hash TEXT);
    """)
    db.execute("INSERT INTO generations VALUES (1)")
    root = "https://streeteasy.com/building/one-chelsea"
    missing = "https://streeteasy.com/building/two-chelsea"
    inv = root + "?archive_view=unavailable-rentals"
    for url in (root, inv, "https://streeteasy.com/rental/7"):
        db.execute("INSERT INTO scope_urls VALUES (1,?)", (url,))
    db.execute("INSERT INTO scope_buildings VALUES (1,?)", (root,))
    db.execute("INSERT INTO scope_buildings VALUES (1,?)", (missing,))
    db.execute("INSERT INTO frontier VALUES (1,?,?,?)", (inv, "inventory", "done"))
    db.execute(
        "INSERT INTO frontier VALUES (1,?,?,?)",
        ("https://streeteasy.com/rental/7", "listing", "pending"),
    )
    building = {
        "scripts": [
            {
                "json": {
                    "rentalSummary": [{"unavailableCount": 3}],
                    "slug": "one-chelsea",
                    "residentialUnitCount": 4,
                }
            }
        ],
        "links": [{"url": "/rental/7", "kind": "listing"}],
    }
    inventory = {
        "inventory": {
            "count": 1,
            "links": [{"url": "https://streeteasy.com/rental/7"}],
            "expected_counts": [3],
        },
        "links": [],
    }
    db.execute("INSERT INTO snapshots VALUES (?,?,?)", (1, root, json.dumps(building)))
    db.execute("INSERT INTO snapshots VALUES (?,?,?)", (2, inv, json.dumps(inventory)))
    db.execute("INSERT INTO observations VALUES (1,?,NULL,200,1,NULL)", (root,))
    db.execute("INSERT INTO observations VALUES (2,?,NULL,200,1,NULL)", (inv,))
    db.commit()

    result = module.audit_connection(db)
    assert result["source_inventory_counts"] == {"rentals": 3, "sales": 0}
    assert result["inventory_captures"]["complete"] == 0
    assert result["inventory_captures"]["incomplete_or_failed"] == 1
    assert (
        result["discovered_listing_detail_urls"]["from_unavailable_inventory_unique"]
        == 1
    )
    assert result["building_pages"]["missing_scoped_buildings"] == 1
    assert result["scoped_frontier"]["listing:pending"] == 1
    db.close()
