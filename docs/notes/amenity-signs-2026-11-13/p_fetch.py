"""S12's photo pilot, the fetch: each photo of `p_sample.py`'s list once, through OxyLabs.

argv: DIR. The script reads `DIR/photos.parquet` and fetches each key not yet in
`DIR/fetch.jsonl` from https://photos.zillowstatic.com/fp/<key>-p_e.webp through the OxyLabs
Realtime API, with no retry. It holds crawls/oxylabs.lock while it runs, sends at most 55
requests a minute, and stops at 520 requests in all, counting the lines already logged. It
saves each image as a JPEG of at most 768 pixels on its longer side, under every label that
shows it, as `DIR/rate/<label>/pNN.jpg`, and logs a line per key with the status and size."""

import base64
import concurrent.futures as cf
import fcntl
import io
import json
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import requests
from PIL import Image

LOCK = Path("/data1/apartments/archive/crawls/oxylabs.lock")
ENV = Path("/home/ben/code/apartments/.env")
API = "https://realtime.oxylabs.io/v1/queries"
CAP = 520
PER_MINUTE = 55
SIDE = 768
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


class Bucket:
    def __init__(self, per_minute):
        self.gap = 60.0 / per_minute
        self.next = time.monotonic()
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + self.gap
        time.sleep(max(0.0, start - now))


def fetch(key, places, auth, bucket, root):
    bucket.wait()
    url = f"https://photos.zillowstatic.com/fp/{key}-p_e.webp"
    line = {"key": key, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        response = requests.post(
            API,
            json={"source": "universal", "url": url, "content_encoding": "base64"},
            auth=auth,
            timeout=120,
            allow_redirects=False,
        )
        line["api_status"] = response.status_code
        if response.status_code != 200:
            return line
        results = response.json().get("results") or []
        item = results[0] if len(results) == 1 else {}
        line["status"] = item.get("status_code", item.get("status"))
        content = item.get("content")
        if line["status"] != 200 or not isinstance(content, str):
            return line
        if len(content) > MAX_BYTES * 4 // 3 + 8:
            raise ValueError("size")
        body = base64.b64decode(content, validate=True)
        with Image.open(io.BytesIO(body)) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("format")
            line.update(bytes=len(body), width=image.width, height=image.height)
            small = image.convert("RGB")
            small.thumbnail((SIDE, SIDE), Image.LANCZOS)
        for label, order in places:
            target = root / "rate" / label / f"p{order:02d}.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            small.save(target, "JPEG", quality=85)
        line["saved"] = len(places)
    except Exception as error:
        line["error"] = type(error).__name__
    return line


def main():
    root = Path(sys.argv[1])
    p = pd.read_parquet(root / "photos.parquet")
    places = {k: list(zip(g.label, g.order)) for k, g in p.groupby("key")}
    log = root / "fetch.jsonl"
    done = []
    if log.exists():
        done = [json.loads(s) for s in log.read_text().splitlines() if s.strip()]
    seen = {d["key"] for d in done}
    keys = sorted(k for k in places if k not in seen)[: max(0, CAP - len(done))]
    print(f"{len(done)} done, {len(keys)} to fetch", flush=True)
    if not keys:
        return
    auth = credentials()
    bucket = Bucket(PER_MINUTE)
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        print(time.strftime("%H:%M:%S"), "holding oxylabs.lock", flush=True)
        with log.open("a") as sink, cf.ThreadPoolExecutor(6) as pool:
            lines = pool.map(lambda k: fetch(k, places[k], auth, bucket, root), keys)
            for n, line in enumerate(lines, 1):
                sink.write(json.dumps(line, sort_keys=True) + "\n")
                sink.flush()
                if n % 100 == 0 or n == len(keys):
                    print(time.strftime("%H:%M:%S"), n, "fetched", flush=True)


if __name__ == "__main__":
    main()
