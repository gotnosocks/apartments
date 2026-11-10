"""The dataset of a fit that scores the ads on the market on a given day.

    python -m rentfrontier.market SRC OUT --ads ADS.parquet [--as-of DAY] [--input MODULE.NAME=PATH]...

SRC is a dataset directory (`rentfrontier.b0nyc` writes the NYC one). OUT gets its rows with
columns from the pipeline's ads parquet, joined on `listing_id`:
- `status`: the ad's latest status (ACTIVE, RENTED, ...);
- `first_day` and `first_ask`: the day the ad was first listed and its first ask;
- `off_day`: the day it left the market, missing for an ad still on it;
and with
- `open`: whether the ad is on the market on the scoring day;
- `final_day`: the row's own `latest_day`, before the change below.

Without `--as-of` the scoring day is the newest `latest_day` in SRC, and the open ads are those
whose status is in OPEN. Their latest ask is not a final ask yet.

With `--as-of DAY` the dataset is a backtest of that day. An ad first listed on or before DAY
that left the market after it is open, and its row keeps its final ask, so a fit can be scored
on asks it has not seen. An ad first listed after DAY, or still on the market now, is set
aside (`set_aside.parquet`), because the first was not there to see and the second has no
final ask.

An open row's `latest_day` and `price_at` are moved to the scoring day. The model then
predicts the ad's final ask at the market's level on that day, and the as-of features read
every training ad as earlier. The `market` split (`rentfrontier.splits.market_split`) holds
out the open rows, so a fit trains on the closed ads and predicts the open ones
(`rentfrontier.drift` keeps the predictions).

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


def with_status(
    src: Path,
    out: Path,
    ads: Path,
    inputs: dict | None = None,
    as_of: str | None = None,
) -> dict:
    frame = pd.read_parquet(src / "rows.parquet")
    manifest = json.loads((src / "manifest.json").read_text())
    a = pd.read_parquet(ads, columns=["listing_id", *COLUMNS])
    a = a.assign(listing_id=a.listing_id.astype(str)).drop_duplicates()
    if a.listing_id.duplicated().any():
        raise SystemExit(f"{ads} has rows that disagree for one listing")
    a = a.set_index("listing_id").reindex(frame.listing_id.astype(str))
    for c in COLUMNS:
        frame[c] = a[c].to_numpy()
    last = pd.to_datetime(frame.latest_day)
    still = frame.status.isin(OPEN).to_numpy()
    if as_of is None:
        day = last.max()
        is_open = still
        keep = pd.Series(True, index=frame.index).to_numpy()
    else:
        day = pd.Timestamp(as_of)
        first = pd.to_datetime(frame.first_day).fillna(
            pd.to_datetime(frame.price_at).dt.tz_localize(None)
        )
        # A relisted ad can carry an ask dated after the day it first went off the market,
        # so an ad counts as closed only when its last ask is in by the scoring day too.
        end = pd.to_datetime(frame.off_day).fillna(last)
        end = end.where(end >= last, last)
        keep = (first <= day).to_numpy() & ~still
        is_open = keep & (end > day).to_numpy()
    frame["open"] = is_open
    frame["final_day"] = frame.latest_day
    # Move the open rows to the scoring day, in each column's own type.
    frame["latest_day"] = last.where(~is_open, day).astype(last.dtype).dt.date
    at = pd.to_datetime(frame.price_at)
    stamp = day.tz_localize(at.dt.tz) if at.dt.tz is not None else day
    frame["price_at"] = at.where(~is_open, stamp).astype(at.dtype)
    out.mkdir(parents=True, exist_ok=False)
    kept = frame[keep]
    kept.to_parquet(out / "rows.parquet", index=False)
    if not keep.all():
        frame[~keep].to_parquet(out / "set_aside.parquet", index=False)
    (out / INPUTS).write_text(json.dumps(inputs or {}, indent=2))
    manifest |= {
        "rows": int(keep.sum()),
        "rows_sha256": sha256(out / "rows.parquet"),
        "market": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "ads": str(ads),
            "ads_sha256": sha256(ads),
            "scoring_day": str(day.date()),
            "backtest": as_of is not None,
            "status": kept.status.fillna("missing").value_counts().to_dict(),
            "open": int(kept.open.sum()),
            "set_aside": int((~keep).sum()),
            "inputs": inputs or {},
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def apply_inputs(dataset) -> dict:
    """Point the module constants named in `dataset`'s inputs.json at their paths, and return
    the mapping. A dataset with no inputs.json leaves every constant as it is. Only a path
    constant of a `rentfrontier` module can be named: the file comes with the dataset, and
    it must not be able to set anything else."""
    path = Path(dataset) / INPUTS if dataset else None
    if path is None or not path.exists():
        return {}
    inputs = json.loads(path.read_text())
    found = []
    for key, value in inputs.items():
        module, _, name = key.rpartition(".")
        if not module.startswith("rentfrontier."):
            raise ValueError(f"{INPUTS} names {key}, which is not in rentfrontier")
        mod = importlib.import_module(module)
        if not isinstance(getattr(mod, name, None), Path):
            raise ValueError(f"{INPUTS} names {key}, which is not a path of {module}")
        if not isinstance(value, str):
            raise ValueError(f"{INPUTS} gives {key} a value that is not a path")
        found.append((mod, name, Path(value)))
    for mod, name, value in found:
        setattr(mod, name, value)
    return inputs


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--ads", type=Path, required=True)
    p.add_argument("--as-of", help="a backtest's scoring day, YYYY-MM-DD")
    p.add_argument("--input", action="append", default=[], metavar="MODULE.NAME=PATH")
    args = p.parse_args(argv)
    inputs = dict(item.split("=", 1) for item in args.input)
    m = with_status(args.src, args.out, args.ads, inputs, args.as_of)
    print(json.dumps(m["market"], indent=2))


if __name__ == "__main__":
    main()
