"""The dataset of a fit that scores the ads on the market now.

    python -m rentfrontier.market SRC OUT --ads ADS.parquet [--input MODULE.NAME=PATH]...

SRC is a dataset directory (`rentfrontier.b0nyc` writes the NYC one). OUT gets its rows with
four columns from the pipeline's ads parquet, joined on `listing_id`:
- `status`: the ad's latest status (ACTIVE, RENTED, ...);
- `first_day` and `first_ask`: the day the ad was first listed and its first ask;
- `off_day`: the day it left the market, missing for an ad still on it.

The `market` split (`rentfrontier.splits.market_split`) holds out the rows whose status is in
OPEN. Their latest ask is not a final ask yet, so the fit trains on the closed ads and
predicts the open ones (`rentfrontier.drift` keeps the predictions).

OUT also gets `inputs.json`, written from the `--input` options. The feature modules read
their snapshots (the rows parquet, the listing codes, the building registry, ...) from paths
set as module constants, each pinned to the build the earlier fits used. A dataset from a later
build needs later snapshots, and `apply_inputs` points each named constant at the dataset's
own path before a design is built, for example

    --input rentfrontier.building_zones_floor_asof3.ROWS=/data1/.../rows-ddd2fe8f5da041b8.parquet
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

import pandas as pd

from .b0data import sha256

# Statuses of an ad whose latest ask is not final.
OPEN = ("ACTIVE", "TEMPORARILY_OFF_MARKET")
COLUMNS = ("status", "first_day", "first_ask", "off_day")
INPUTS = "inputs.json"


def with_status(src: Path, out: Path, ads: Path, inputs: dict | None = None) -> dict:
    frame = pd.read_parquet(src / "rows.parquet")
    manifest = json.loads((src / "manifest.json").read_text())
    a = pd.read_parquet(ads, columns=["listing_id", *COLUMNS])
    a = a.assign(listing_id=a.listing_id.astype(str)).drop_duplicates("listing_id")
    a = a.set_index("listing_id").reindex(frame.listing_id.astype(str))
    for c in COLUMNS:
        frame[c] = a[c].to_numpy()
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    (out / INPUTS).write_text(json.dumps(inputs or {}, indent=2))
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "market": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "ads": str(ads),
            "ads_sha256": sha256(ads),
            "status": frame.status.fillna("missing").value_counts().to_dict(),
            "open": int(frame.status.isin(OPEN).sum()),
            "inputs": inputs or {},
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def apply_inputs(dataset) -> dict:
    """Point the module constants named in `dataset`'s inputs.json at their paths, and return
    the mapping. A dataset with no inputs.json leaves every constant as it is."""
    path = Path(dataset) / INPUTS if dataset else None
    if path is None or not path.exists():
        return {}
    inputs = json.loads(path.read_text())
    for key, value in inputs.items():
        module, name = key.rsplit(".", 1)
        mod = importlib.import_module(module)
        if not hasattr(mod, name):
            raise AttributeError(
                f"{INPUTS} names {key}, which {module} does not define"
            )
        setattr(mod, name, Path(value))
    return inputs


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--ads", type=Path, required=True)
    p.add_argument("--input", action="append", default=[], metavar="MODULE.NAME=PATH")
    args = p.parse_args(argv)
    inputs = dict(item.split("=", 1) for item in args.input)
    print(
        json.dumps(
            with_status(args.src, args.out, args.ads, inputs)["market"], indent=2
        )
    )


if __name__ == "__main__":
    main()
