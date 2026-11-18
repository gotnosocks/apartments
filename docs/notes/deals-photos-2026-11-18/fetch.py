"""Image read of the low outliers, part 2: fetch each image of `keys.py`'s list once.

Images go in the order of the readers' batches, from the CDN directly at 1 request a
second, with the request and storage code of
`docs/notes/photo-disagreement-2026-11-14/f2_fetch.py`. A photo is the `-p_e.webp`
rendition. A plan is the uncropped rendition of `f2b_plans.py`. Originals go to the
archive by listing id, and JPEG copies go under each blind label in `rate/`. Each request
adds a line to `fetch.jsonl`. Run it with a Python that has Pillow
(`venvs/bridge-root`). The script stops after 300 failures in a row.
"""

import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
from PIL import Image

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "photo-disagreement-2026-11-14")
)
import f2_fetch as F  # noqa: E402

OUT = Path("/data1/apartments/tmp/deals-photos-2026-11-18")
F.OUT = OUT
PLAN = "uncropped_scaled_within_1536_1152"
GIVE_UP = 300

images = pd.read_parquet(OUT / "images.parquet")
blind = pd.read_parquet(OUT / "blind.parquet")
labels = blind.groupby("listing_id").label.apply(list).to_dict()
first = blind.groupby("listing_id").batch.min()
images = images.assign(batch=images.listing_id.map(first)).sort_values(
    ["batch", "listing_id", "kind", "order"]
)
log = OUT / "fetch.jsonl"
done = [json.loads(s) for s in log.read_text().splitlines()] if log.exists() else []
tried = {(d["listing_id"], d["key"]) for d in done}
todo = [r for r in images.itertuples() if (r.listing_id, r.key) not in tried]
print(len(tried), "tried,", len(todo), "to fetch", flush=True)
misses = 0
with log.open("a") as sink:
    for n, r in enumerate(todo, 1):
        line = {"listing_id": r.listing_id, "key": r.key, "kind": r.kind}
        line["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        start = time.monotonic()
        try:
            if r.kind == "photo":
                url = f"https://photos.zillowstatic.com/fp/{r.key}-p_e.webp"
                body, line["status"] = F.direct(url)
                if body is not None:
                    F.store(
                        body, r.listing_id, r.kind, r.order, r.key, labels[r.listing_id]
                    )
                    line.update(bytes=len(body), saved=True)
            else:
                url = f"https://photos.zillowstatic.com/fp/{r.key}-{PLAN}.webp"
                body, line["status"] = F.direct(url)
                if body is not None:
                    with Image.open(io.BytesIO(body)) as image:
                        small = image.convert("RGB")
                        small.thumbnail((1280, 1280), Image.LANCZOS)
                    folder = F.ARCHIVE / "floor-plans" / r.listing_id
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / f"{r.key}-{PLAN}.webp").write_bytes(body)
                    for label in labels[r.listing_id]:
                        target = OUT / "rate" / label / "plan.jpg"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        small.save(target, "JPEG", quality=85)
                    line.update(bytes=len(body), saved=True)
        except Exception as error:
            line["error"] = type(error).__name__
        sink.write(json.dumps(line, sort_keys=True) + "\n")
        sink.flush()
        misses = 0 if line.get("saved") else misses + 1
        if misses >= GIVE_UP:
            print("stopped after", GIVE_UP, "failures in a row", flush=True)
            break
        if n % 200 == 0:
            print(time.strftime("%H:%M:%S"), n, "done, batch", r.batch, flush=True)
        time.sleep(max(0.0, F.DIRECT_GAP - (time.monotonic() - start)))
print("finished", flush=True)
