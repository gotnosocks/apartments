"""Photo disagreement, part 2b: the uncropped copy of each floor plan.

The `-p_e.webp` rendition of the CDN is a 596 by 446 crop, which cuts the edges off a floor
plan. For each plan of `images.parquet` this script requests
https://photos.zillowstatic.com/fp/<key>-uncropped_scaled_within_1536_1152.webp from the CDN
directly, at 1 request a second, with no OxyLabs fallback. It stores the file beside the
cropped one in `archive/floor-plans/<listing id>/`, replaces the readers' `plan.jpg` under
each blind label with a JPEG of at most 1,280 pixels, and adds a line of kind `plan_full` to
`fetch.jsonl`. A plan with a failed request keeps its cropped `plan.jpg`."""

import io
import json
import time

import pandas as pd
from f2_fetch import ARCHIVE, DIRECT_GAP, OUT, direct
from PIL import Image

RENDITION = "uncropped_scaled_within_1536_1152"


def main():
    images = pd.read_parquet(OUT / "images.parquet")
    blind = pd.read_parquet(OUT / "blind.parquet")
    labels = blind.groupby("listing_id").label.apply(list).to_dict()
    log = OUT / "fetch.jsonl"
    done = [json.loads(s) for s in log.read_text().splitlines() if s.strip()]
    seen = {(d["listing_id"], d["key"]) for d in done if d["kind"] == "plan_full"}
    plans = images[images.kind == "plan"]
    with log.open("a") as sink:
        for r in plans.itertuples():
            if (r.listing_id, r.key) in seen:
                continue
            line = {"listing_id": r.listing_id, "key": r.key, "kind": "plan_full"}
            line.update(route="direct", at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            start = time.monotonic()
            try:
                url = f"https://photos.zillowstatic.com/fp/{r.key}-{RENDITION}.webp"
                body, line["status"] = direct(url)
                if body is not None:
                    with Image.open(io.BytesIO(body)) as image:
                        line.update(width=image.width, height=image.height)
                        small = image.convert("RGB")
                        small.thumbnail((1280, 1280), Image.LANCZOS)
                    folder = ARCHIVE / "floor-plans" / r.listing_id
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / f"{r.key}-{RENDITION}.webp").write_bytes(body)
                    for label in labels[r.listing_id]:
                        target = OUT / "rate" / label / "plan.jpg"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        small.save(target, "JPEG", quality=85)
                    line.update(bytes=len(body), saved=True)
            except Exception as error:
                line["error"] = type(error).__name__
            sink.write(json.dumps(line, sort_keys=True) + "\n")
            sink.flush()
            time.sleep(max(0.0, DIRECT_GAP - (time.monotonic() - start)))
    done = [json.loads(s) for s in log.read_text().splitlines() if s.strip()]
    full = [d for d in done if d["kind"] == "plan_full"]
    print(len(full), "plan requests,", sum(bool(d.get("saved")) for d in full), "saved")


if __name__ == "__main__":
    main()
