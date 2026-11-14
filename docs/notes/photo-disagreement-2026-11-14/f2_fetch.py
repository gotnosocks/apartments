"""Photo disagreement, part 2: fetch each image of `f1_keys.py`'s list once.

argv: optional limit on the number of keys to fetch in this run.

For each (listing, key) of `images.parquet` not yet in the archive, the script requests
https://photos.zillowstatic.com/fp/<key>-p_e.webp from the CDN directly, at 1 request a
second. When the direct request returns no image, it sends the same URL through the OxyLabs
Realtime API with the request of S12's `p_fetch.py`, at most 55 a minute, while holding
`crawls/oxylabs.lock`, with no retry, and stops using OxyLabs at 3,500 requests counted over
every line of `fetch.jsonl`. After 20 direct failures in a row it stops asking the CDN
directly and sends the remaining keys through OxyLabs.

The original bytes go to `archive/photos/<listing id>/<key>-p_e.webp`, or to
`archive/floor-plans/<listing id>/` for a plan. A JPEG copy of at most 768 pixels on its
longer side (1,280 for a plan) goes under every blind label of the listing, as
`rate/<label>/p01.jpg` ... `p08.jpg` and `rate/<label>/plan.jpg`. Each request adds a line to
`fetch.jsonl` with its route (direct or oxylabs), status and size. At its start the script
writes any reader copy missing for an image already in the archive."""

import base64
import fcntl
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from PIL import Image

OUT = Path("/data1/apartments/tmp/photo-disagreement-2026-11-14")
ARCHIVE = Path("/data1/apartments/archive")
LOCK = ARCHIVE / "crawls/oxylabs.lock"
ENV = Path("/home/ben/code/apartments/.env")
API = "https://realtime.oxylabs.io/v1/queries"
AGENT = "Mozilla/5.0 (X11; Linux x86_64)"
OXY_CAP = 3500
DIRECT_GAP = 1.0
OXY_GAP = 60.0 / 55
GIVE_UP = 20
SIDE = {"photo": 768, "plan": 1280}
MAX_BYTES = 16 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000


def credentials():
    values = {}
    for line in ENV.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep:
            values[name.strip()] = value.strip().strip("'\"")
    user = values.get("OXYLABS_USERNAME") or values.get("OXYLABS_USER")
    if not user or not values.get("OXYLABS_PASSWORD"):
        raise RuntimeError("Oxylabs credentials are not configured")
    return user, values["OXYLABS_PASSWORD"]


def direct(url):
    """The image bytes from the CDN, or None, with the HTTP status."""
    response = requests.get(url, headers={"User-Agent": AGENT}, timeout=60)
    if response.status_code != 200 or len(response.content) > MAX_BYTES:
        return None, response.status_code
    return response.content, 200


def through_oxylabs(url, auth):
    """The image bytes through the Realtime API, or None, with the target's status."""
    response = requests.post(
        API,
        json={"source": "universal", "url": url, "content_encoding": "base64"},
        auth=auth,
        timeout=120,
        allow_redirects=False,
    )
    if response.status_code != 200:
        return None, f"api {response.status_code}"
    results = response.json().get("results") or []
    item = results[0] if len(results) == 1 else {}
    status = item.get("status_code", item.get("status"))
    content = item.get("content")
    if status != 200 or not isinstance(content, str):
        return None, status
    if len(content) > MAX_BYTES * 4 // 3 + 8:
        return None, "size"
    return base64.b64decode(content, validate=True), 200


def store(body, lid, kind, order, key, labels):
    """Check that `body` is an image, save the original and the readers' copies, and return
    its width and height."""
    with Image.open(io.BytesIO(body)) as image:
        if image.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("format")
        size = image.size
        small = image.convert("RGB")
        small.thumbnail((SIDE[kind], SIDE[kind]), Image.LANCZOS)
    folder = ARCHIVE / ("floor-plans" if kind == "plan" else "photos") / lid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}-p_e.webp").write_bytes(body)
    name = "plan.jpg" if kind == "plan" else f"p{order:02d}.jpg"
    for label in labels:
        target = OUT / "rate" / label / name
        target.parent.mkdir(parents=True, exist_ok=True)
        small.save(target, "JPEG", quality=85)
    return size


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    images = pd.read_parquet(OUT / "images.parquet")
    blind = pd.read_parquet(OUT / "blind.parquet")
    labels = blind.groupby("listing_id").label.apply(list).to_dict()
    log = OUT / "fetch.jsonl"
    done = []
    if log.exists():
        done = [json.loads(s) for s in log.read_text().splitlines() if s.strip()]
    saved = {(d["listing_id"], d["key"]) for d in done if d.get("saved")}
    tried_both = {
        (d["listing_id"], d["key"]) for d in done if d.get("route") == "oxylabs"
    }
    oxy_used = sum(d.get("route") == "oxylabs" for d in done)
    for r in images.itertuples():
        name = "plan.jpg" if r.kind == "plan" else f"p{r.order:02d}.jpg"
        missing = [
            x for x in labels[r.listing_id] if not (OUT / "rate" / x / name).exists()
        ]
        if (r.listing_id, r.key) in saved and missing:
            folder = "floor-plans" if r.kind == "plan" else "photos"
            original = ARCHIVE / folder / r.listing_id / f"{r.key}-p_e.webp"
            store(original.read_bytes(), r.listing_id, r.kind, r.order, r.key, missing)
    todo = [
        r
        for r in images.itertuples()
        if (r.listing_id, r.key) not in saved | tried_both
    ][:limit]
    print(
        f"{len(saved)} saved, {len(todo)} to fetch, {oxy_used} oxylabs requests so far"
    )
    auth, lock, misses, use_direct = None, None, 0, True
    with log.open("a") as sink:
        for n, r in enumerate(todo, 1):
            url = f"https://photos.zillowstatic.com/fp/{r.key}-p_e.webp"
            line = {"listing_id": r.listing_id, "key": r.key, "kind": r.kind}
            body = None
            if use_direct:
                line.update(route="direct", at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
                start = time.monotonic()
                try:
                    body, line["status"] = direct(url)
                    if body is not None:
                        size = store(
                            body,
                            r.listing_id,
                            r.kind,
                            r.order,
                            r.key,
                            labels[r.listing_id],
                        )[:2]
                        line.update(bytes=len(body), width=size[0], height=size[1])
                        line["saved"] = True
                except Exception as error:
                    line["error"] = type(error).__name__
                sink.write(json.dumps(line, sort_keys=True) + "\n")
                sink.flush()
                misses = 0 if line.get("saved") else misses + 1
                if misses >= GIVE_UP:
                    use_direct = False
                    print("direct requests stopped after", GIVE_UP, "failures in a row")
                time.sleep(max(0.0, DIRECT_GAP - (time.monotonic() - start)))
            if not line.get("saved") and oxy_used < OXY_CAP:
                if lock is None:
                    auth = credentials()
                    lock = LOCK.open("a")
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    print(time.strftime("%H:%M:%S"), "holding oxylabs.lock", flush=True)
                line = {"listing_id": r.listing_id, "key": r.key, "kind": r.kind}
                line.update(route="oxylabs", at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
                start = time.monotonic()
                oxy_used += 1
                try:
                    body, line["status"] = through_oxylabs(url, auth)
                    if body is not None:
                        size = store(
                            body,
                            r.listing_id,
                            r.kind,
                            r.order,
                            r.key,
                            labels[r.listing_id],
                        )[:2]
                        line.update(bytes=len(body), width=size[0], height=size[1])
                        line["saved"] = True
                except Exception as error:
                    line["error"] = type(error).__name__
                sink.write(json.dumps(line, sort_keys=True) + "\n")
                sink.flush()
                time.sleep(max(0.0, OXY_GAP - (time.monotonic() - start)))
            if n % 100 == 0 or n == len(todo):
                print(
                    time.strftime("%H:%M:%S"),
                    n,
                    "done",
                    oxy_used,
                    "oxylabs",
                    flush=True,
                )


if __name__ == "__main__":
    main()
