"""Write the dataset copy for the first-ask fit: the base model's rows with each ad's first ask
in place of its latest ask.

    python -I first_ask_dataset.py OUT_DIR [--check]

I read the base dataset's rows.parquet and the observations cache, join each row's first ask
(`asking_rent`, the ad's initial own-advertisement ask) on `listing_id = source_listing_id`,
and write OUT_DIR/rows.parquet with these changes on every row that has a positive first ask:

- `latest_ask` becomes the first ask;
- `latest_day` becomes the row's own day (`price_at` as a date), so the fit reads the walk at
  the date the first ask was posted rather than at the last price move;
- `latest_ask_how` and `latest_day_how` record the swap.

Rows without a first ask (about 162,000 of 1,896,486) keep their latest ask, and the manifest
counts them. The split function orders ads by `price_at`, which the copy leaves alone, so the
latest split's held-out mask matches the base run's. set_aside.parquet is copied unchanged, and
manifest.json gains a `first_ask` section with the counts and the source files' SHA-256.

This mirrors the swap `rentfrontier.simulate` performs for a simulated rows.parquet, so the
copy runs through `ops/modal-fit --dataset OUT_DIR` with the unchanged `building-zones-floor`
model. `--check` only prints the counts and writes nothing. The write asserts a unique first
ask per listing and an identical held-out mask, and writes the held-out listing ids to
OUT_DIR/heldout_ids.json. Run it with the frontier venv, since the mask check imports
`rentfrontier.splits`.

The research group's fable wrote this script for its first-ask fit request (board post
20261023T072305Z, amended in 20261023T075703Z).
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
OBS = Path("/data1/apartments/frontier/cache/observations-aecf9b7724d3208a-v2.parquet")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    rows = pd.read_parquet(BASE / "rows.parquet")
    obs = pd.read_parquet(
        OBS, columns=["source_listing_id", "asking_rent", "price_basis"]
    )
    # Conflict rule, frozen 2026-10-23: only the historical initial own-advertisement ask counts
    # as a first ask. The cache holds 235 rows with price_basis = current_capture_gross_ask, 88 of
    # them beside a historical row for the same listing (50 with a different value); those rows
    # are dropped here, so the 147 listings with only a capture-basis value keep their latest ask.
    obs = obs[
        (obs.asking_rent > 0)
        & (obs.price_basis == "historical_initial_own_advertisement_ask")
    ]
    assert obs.source_listing_id.is_unique, (
        "more than one historical first ask for a listing"
    )
    first = rows.listing_id.map(obs.set_index("source_listing_id").asking_rent)
    ok = first.notna().to_numpy()
    counts = {
        "rows": int(len(rows)),
        "with_first_ask": int(ok.sum()),
        "kept_latest_ask": int((~ok).sum()),
        "first_equals_latest": int((np.isclose(first[ok], rows.latest_ask[ok])).sum()),
    }
    print(json.dumps(counts, indent=2))
    if a.check:
        return

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    copy = rows.copy()
    copy.loc[ok, "latest_ask"] = first[ok].to_numpy(float)
    copy.loc[ok, "latest_day"] = pd.to_datetime(rows.price_at[ok], utc=True).dt.date
    copy.loc[ok, "latest_ask_how"] = "first ask"
    copy.loc[ok, "latest_day_how"] = "row"
    copy.to_parquet(out / "rows.parquet")
    shutil.copy(BASE / "set_aside.parquet", out / "set_aside.parquet")
    manifest = json.loads((BASE / "manifest.json").read_text())
    manifest["first_ask"] = {
        "source_rows": str(BASE / "rows.parquet"),
        "source_rows_sha256": manifest.get("rows_sha256"),
        "observations": str(OBS),
        "observations_sha256": sha256(OBS),
        **counts,
    }
    manifest["rows_sha256"] = sha256(out / "rows.parquet")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    # Held-out identity: the latest split must pick the same ads from the copy as from the base.
    # The split module lives in the frontier package, so this runs in the coordinator's env.
    from rentfrontier.splits import latest_split  # noqa: E402

    base_mask = np.asarray(latest_split(rows))
    copy_mask = np.asarray(latest_split(copy))
    assert base_mask.shape == copy_mask.shape and (base_mask == copy_mask).all(), (
        "held-out mask differs"
    )
    held_ids = (
        set(rows.listing_id[base_mask.astype(bool)])
        if base_mask.dtype != np.int64
        else set(rows.listing_id.iloc[base_mask])
    )
    (out / "heldout_ids.json").write_text(json.dumps(sorted(int(i) for i in held_ids)))
    print("held-out ads:", len(held_ids))


if __name__ == "__main__":
    main()
