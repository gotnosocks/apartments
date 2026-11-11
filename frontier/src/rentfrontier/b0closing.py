"""Write a B0 dataset with each row priced at its listing's last ask before the off-market day.

    python -m rentfrontier.b0closing SRC OUT

The pipeline prices a row at its listing's last kept price change (`ads.kept_changes`, as
`latest-ask-v9` does). Changes dated on the off-market day count when they stay within a
factor of 2 of the ask before them. In the served dataset 104,330 rows take such a change,
72% of them raises, with a median of +4.6%. The outlier sprint of 2026-11-11 read many of
them: a broker types the agreed rent, a gross figure or a new placeholder into the price on
the day the ad closes. `latest-ask-v10` (`latest_ask.CLOSING_STALE_DAYS`) drops every
change from the off-market day on, and no fit had tested it on a B0 dataset.

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256) and run `latest_ask.record_latest` on each rental listing's last
capture twice, with `stale_days` 7 and -1. A row changes when all of these hold:

1. its `latest_ask_how` is `latest`;
2. its latest ask equals the last change kept with 7 days, which leaves out rows priced net
   of free months and rows a ledger entry set;
3. the last change kept with -1 differs from it.

The row then takes the last change kept with -1, the ad's last ask before its off-market
day. I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with those rows' `latest_ask` replaced and their
  `latest_ask_how` set to `latest, before off day`.
- `set_aside.parquet`: SRC's, copied.
- `manifest.json`: SRC's manifest with `rows_sha256` updated, and a `closing` entry giving
  SRC's path and rows SHA-256, the rule, the rows changed and the median log change.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .b0data import sha256
from .latest_ask import CLOSING_STALE_DAYS, STALE_DAYS, record_latest

HOW = "latest, before off day"


def last_asks(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each rental listing in `ids`, the price of the last change `record_latest` keeps
    from its last capture in the records file `path`, with 7 days (`v9`) and with -1
    (`v10`). A listing with no kept change gets NaN. I read a row group at a time, and its
    record texts only for the rows I keep, since the texts of the whole file run to tens of
    GB."""
    seen: dict[str, tuple] = {}
    file = pq.ParquetFile(path)
    for group in range(file.num_row_groups):
        head = file.read_row_group(
            group, columns=["listing_id", "listing_type", "collected_at"]
        )
        lid = [str(x) for x in head["listing_id"].to_pylist()]
        at = head["collected_at"].to_pylist()
        keep = [
            kind == "rental" and i in ids and (i not in seen or seen[i][0] < t)
            for i, kind, t in zip(lid, head["listing_type"].to_pylist(), at)
        ]
        if not any(keep):
            continue
        raws = file.read_row_group(group, columns=["raw_listing_json"]).filter(
            pa.array(keep)
        )
        rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
        for (i, t), raw in zip(rows, raws["raw_listing_json"].to_pylist()):
            if not raw or (i in seen and seen[i][0] >= t):
                continue
            last = [
                (record_latest(raw, days)["changes"] or [(None, np.nan)])[-1][1]
                for days in (STALE_DAYS, CLOSING_STALE_DAYS)
            ]
            seen[i] = (t, *last)
        del raws
    return pd.DataFrame(
        [(i, v9, v10) for i, (_, v9, v10) in seen.items()],
        columns=["listing_id", "v9", "v10"],
    ).set_index("listing_id")


def reprice(frame: pd.DataFrame, asks: pd.DataFrame) -> np.ndarray:
    """Whether each row of `frame` takes its listing's `v10` ask, by the rule above."""
    lid = frame.listing_id.astype(str)
    v9, v10 = lid.map(asks.v9).to_numpy(float), lid.map(asks.v10).to_numpy(float)
    ask = frame.latest_ask.to_numpy(float)
    return (
        (frame.latest_ask_how == "latest").to_numpy()
        & (np.abs(ask - v9) < 0.5)
        & np.isfinite(v10)
        & (np.abs(v10 - v9) >= 0.5)
    )


def closing(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    ids = pd.read_parquet(src / "rows.parquet", columns=["listing_id"]).listing_id
    asks = last_asks(Path(records["path"]), set(ids.astype(str)))
    frame = pd.read_parquet(src / "rows.parquet")
    change = reprice(frame, asks)
    new = frame.listing_id.astype(str)[change].map(asks.v10).to_numpy(float)
    step = np.log(frame.latest_ask.to_numpy(float)[change] / new)
    frame.loc[change, "latest_ask"] = new
    frame.loc[change, "latest_ask_how"] = HOW
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    shutil.copy(src / "set_aside.parquet", out / "set_aside.parquet")
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "closing": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "a row priced at its listing's last kept change takes the last change "
            "dated before the off-market day (latest-ask-v10)",
            "listings_read": len(asks),
            "changed": int(change.sum()),
            "raised_share": round(float((step > 0).mean()), 4) if len(step) else None,
            "median_log_change": round(float(np.median(step)), 4)
            if len(step)
            else None,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(closing(args.src, args.out)["closing"], indent=2))


if __name__ == "__main__":
    main()
