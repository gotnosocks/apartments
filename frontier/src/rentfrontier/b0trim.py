"""Write a B0 dataset with its trend grid starting at the first week of dense data.

    python -m rentfrontier.b0trim SRC OUT [--min-rows 100]

B0's weekly trend grid starts at the earliest latest-ask day in its rows. In the 2026-10-19
off-market dataset that day is 2010-07-28, while steady weekly data begins in December 2013:
18 rows fall in the 3.4 years between, and the trend walks about 177 weeks with almost nothing
under it. The B0.2 fit of 2026-10-19 placed the early level 0.3 log points apart across its
chains, and the drift moved with it.

I read SRC's `rows.parquet` and count rows per week on B0's grid (weeks from `b0.EPOCH`, by
`latest_day`). The dense start is the earliest week from which every week up to the last holds
at least `--min-rows` rows. I then write OUT with:

- `rows.parquet`: SRC's rows on or after the dense start, in SRC's order.
- `set_aside.parquet`: the earlier rows, kept for the record.
- `manifest.json`: SRC's manifest with `rows`, `latest_day_how` and `rows_sha256` updated for
  the kept rows, and a `trim` entry giving SRC's path and rows SHA-256, the rule, the dense
  start, and how many rows I set aside.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0
from .b0data import sha256

MIN_ROWS = 100


def dense_start(day: pd.Series, min_rows: int = MIN_ROWS) -> pd.Timestamp:
    """The Monday of the earliest week from which every week through the last holds at least
    `min_rows` of the days in `day`."""
    week = ((pd.to_datetime(day) - b0.EPOCH).dt.days // 7).to_numpy()
    lo = week.min()
    n = np.bincount(week - lo)
    thin = np.flatnonzero(n < min_rows)
    first = 0 if len(thin) == 0 else thin[-1] + 1
    if first >= len(n):
        raise ValueError(f"the last week holds fewer than {min_rows} rows")
    return b0.EPOCH + pd.Timedelta(weeks=int(lo + first))


def trim(src: Path, out: Path, min_rows: int = MIN_ROWS) -> dict:
    frame = pd.read_parquet(src / "rows.parquet")
    manifest = json.loads((src / "manifest.json").read_text())
    start = dense_start(frame.latest_day, min_rows)
    keep = (pd.to_datetime(frame.latest_day) >= start).to_numpy()
    out.mkdir(parents=True, exist_ok=False)
    frame[keep].to_parquet(out / "rows.parquet", index=False)
    frame[~keep].to_parquet(out / "set_aside.parquet", index=False)
    kept = frame[keep]
    manifest |= {
        "rows": int(keep.sum()),
        "latest_day_how": kept.latest_day_how.value_counts().to_dict(),
        "flags": {name: int(kept[name].sum()) for name in manifest.get("flags", {})},
        "rows_sha256": sha256(out / "rows.parquet"),
        "trim": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": f"every week from the start holds at least {min_rows} rows",
            "min_rows": min_rows,
            "dense_start": str(start.date()),
            "set_aside": int((~keep).sum()),
            "set_aside_sha256": sha256(out / "set_aside.parquet"),
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
    p.add_argument("--min-rows", type=int, default=MIN_ROWS)
    args = p.parse_args(argv)
    print(json.dumps(trim(args.src, args.out, args.min_rows), indent=2))


if __name__ == "__main__":
    main()
