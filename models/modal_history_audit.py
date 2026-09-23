"""Read-only, bounded rental history quality audit; never contacts StreetEasy/Oxylabs."""

import json, re, gzip, sqlite3, time, hashlib
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("chelsea-history-quality")
volume = modal.Volume.from_name("chelsea-archive")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("parsel==1.10.0")
    .env({"PYTHONPATH": "/root/src"})
    .add_local_dir(
        ROOT / "src/streeteasy_archive",
        "/root/src/streeteasy_archive",
        ignore=["__pycache__"],
    )
)


@app.function(
    image=image,
    cpu=(2, 2),
    memory=(4096, 4096),
    timeout=1800,
    retries=0,
    volumes={"/archive": volume},
)
def audit():
    from streeteasy_archive.extract import _scripts, flight_text
    from parsel import Selector

    started = time.time()
    db = sqlite3.connect(
        "file:/archive/crawls/chelsea-resume/archive.sqlite3?mode=ro",
        uri=True,
        timeout=15,
    )
    generation = db.execute("select max(id) from generations").fetchone()[0]
    queue = db.execute(
        "select f.kind,f.state,count(*) from frontier f join scope_urls s using(generation,url) where f.generation=? group by f.kind,f.state",
        (generation,),
    ).fetchall()
    # Covered index scan: does not load the 100+ GB extracted JSON payloads.
    # SQLite's single max() aggregate selects body_hash from the max-ID row.
    snapshots = {
        u: (h, i)
        for u, h, i in db.execute(
            "select url,body_hash,max(id) from snapshots where generation=? group by url",
            (generation,),
        ).fetchall()
    }
    states = dict(
        db.execute(
            "select url,state from frontier where generation=?", (generation,)
        ).fetchall()
    )
    inventory_urls = [u for u in snapshots if "archive_view=unavailable-rentals" in u]
    print(
        f"Metadata loaded: {len(snapshots)} captured URLs, {len(inventory_urls)} rental inventories",
        flush=True,
    )
    inventories = []
    for n, u in enumerate(inventory_urls):
        h, i = snapshots[u]
        row = db.execute(
            "select json_extract(extracted,'$.inventory') from snapshots where id=?",
            (i,),
        ).fetchone()
        inv = json.loads(row[0]) if row and row[0] else {}
        links = list(
            dict.fromkeys(x["url"] for x in inv.get("links", []) if x.get("url"))
        )
        records = inv.get("records") or inv.get("links") or []
        count = inv.get("count")
        expected = max(inv.get("expected_counts") or [0])
        inventories.append(
            {
                "url": u,
                "displayed": count,
                "records": len(records),
                "complete": isinstance(count, int)
                and len(records) == count
                and expected <= count,
                "detail_urls": links,
                "captured_details": sum(x in snapshots for x in links),
                "pending_details": sum(states.get(x) == "pending" for x in links),
                "done_without_snapshot": sum(
                    states.get(x) == "done" and x not in snapshots for x in links
                ),
            }
        )
        if n % 200 == 0:
            print(f"Inventory audit {n}/{len(inventory_urls)}", flush=True)
    redirects = []
    for inv in inventories:
        inv["redirect_captures"] = 0
        for u in inv["detail_urls"]:
            if u in snapshots:
                continue
            observation = db.execute(
                "select status,headers from observations where url=? order by id desc limit 1",
                (u,),
            ).fetchone()
            if observation and observation[0] in (301, 302, 303, 307, 308):
                from urllib.parse import urljoin

                headers = json.loads(observation[1])
                location = next(
                    (v for k, v in headers.items() if k.lower() == "location"), None
                )
                target = urljoin(u, location) if isinstance(location, str) else None
                if target in snapshots:
                    inv["redirect_captures"] += 1
                    redirects.append(
                        {
                            "url": u,
                            "target": target,
                            "target_snapshot_id": snapshots[target][1],
                        }
                    )
    db.close()
    inventories.sort(key=lambda x: x["records"], reverse=True)
    selected = inventories[:8]
    for inv in inventories:
        if (
            any(
                x in inv["url"]
                for x in ("ten23", "sierra", "130-west-15", "130-west-15th")
            )
            and inv not in selected
        ):
            selected.append(inv)
    selected = selected[:14]
    chosen = set()
    for inv in selected:
        urls = [u for u in inv["detail_urls"] if u in snapshots]
        chosen.update(
            sorted(urls, key=lambda u: hashlib.sha256(u.encode()).hexdigest())[:24]
        )
    chosen.update(
        u for u in snapshots if re.search(r"/building/[^/]*ten23[^/]*/0?4c$", u, re.I)
    )
    # Separate deterministic broader rental-page sample; not selected for density.
    broad = sorted(
        (u for u in snapshots if re.search(r"/rental/\d+$", u)),
        key=lambda u: hashlib.sha256(u.encode()).hexdigest(),
    )[:100]
    chosen.update(broad)

    def read(u):
        h, i = snapshots[u]
        item = {
            "url": u,
            "body_hash": h,
            "snapshot_id": i,
            "sample": "broad" if u in broad else "dense",
        }
        try:
            with gzip.open(Path("/archive/bodies") / h[:2] / (h + ".gz"), "rb") as f:
                body = f.read(33554433)
            if len(body) > 33554432:
                raise ValueError("body exceeds audit limit")
            sel = Selector(text=body.decode("utf-8", "replace"))
            stream = flight_text(_scripts(sel))
            listing = {}
            for m in re.finditer(r'"listing"\s*:', stream):
                try:
                    value, _ = json.JSONDecoder().raw_decode(stream[m.end() :].lstrip())
                except ValueError:
                    continue
                if isinstance(value, dict) and isinstance(
                    value.get("propertyDetails"), dict
                ):
                    listing = value
                    break
            details = listing.get("propertyDetails") or {}
            address = details.get("address") or {}
            href = sel.css('[data-testid="addressLink"]::attr(href)').get() or ""
            match = re.search(r"/building/([^/?#]+)", href or u)
            events = []
            for episode in listing.get("propertyHistory") or []:
                for event in episode.get("rentalEventsOfInterest") or []:
                    events.append(dict(event, listing_id=episode.get("listingId")))
            unique = {json.dumps(e, sort_keys=True, default=str): e for e in events}
            events = list(unique.values())
            dates = sorted(str(e.get("date"))[:10] for e in events if e.get("date"))
            visible_rows = len(sel.css('[data-testid="priceHistoryTable"] tbody tr'))
            item.update(
                {
                    "embedded_listing": bool(listing),
                    "building": match.group(1) if match else None,
                    "address": address.get("street"),
                    "unit": address.get("displayUnit"),
                    "event_count": len(events),
                    "episode_count": len({e.get("listing_id") for e in events}),
                    "first": dates[0] if dates else None,
                    "last": dates[-1] if dates else None,
                    "visible_rows": visible_rows,
                    "bedrooms": details.get("bedroomCount"),
                    "square_feet": details.get("livingAreaSize"),
                    "has_features": bool(details.get("features")),
                    "status": listing.get("status"),
                    "events": events,
                }
            )
        except Exception as e:
            item["error"] = type(e).__name__ + ": " + str(e)[:150]
        return item

    print(f"Reading {len(chosen)} detail bodies", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        samples = list(pool.map(read, sorted(chosen)))
    # Count units separately from URLs. Alias collisions are deliberately not merged.
    units = {}
    for x in samples:
        if x.get("building") and x.get("unit"):
            key = (x["building"], str(x["unit"]).lstrip("#").upper())
            if key not in units or x.get("event_count", 0) > units[key].get(
                "event_count", 0
            ):
                units[key] = x
    for inv in selected:
        inv["sampled_details"] = sum(x["url"] in inv["detail_urls"] for x in samples)
    return {
        "generated_at_epoch": time.time(),
        "elapsed_seconds": time.time() - started,
        "generation": generation,
        "queue": queue,
        "inventories": [
            {k: v for k, v in inv.items() if k != "detail_urls"} for inv in inventories
        ],
        "redirect_captures": redirects,
        "selected_buildings": [
            {k: v for k, v in inv.items() if k != "detail_urls"} for inv in selected
        ],
        "samples": samples,
        "sample_units": len(units),
        "limitations": [
            "Inventory rows are listing episodes, not physical units.",
            "Only captured rental inventories are audited; pending building pages may discover more.",
            "Detail sample is intentionally enriched for dense inventories, plus 100 deterministic rental URLs.",
            "Embedded histories are checked against retained source data, not live website completeness.",
            "The reader sees the last committed cloud archive; the ongoing batch may be newer.",
        ],
    }


@app.local_entrypoint()
def main(output: str = "/tmp/chelsea-history-audit.json"):
    result = audit.remote()
    Path(output).write_text(json.dumps(result, indent=2))
    print(f"Saved compact audit to {output}", flush=True)
