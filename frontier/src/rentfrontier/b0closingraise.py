"""Write a B0 dataset where a raise typed as its ad closed gives way to the ask before it.

    python -m rentfrontier.b0closingraise SRC OUT

`b0closing` moves every row priced at a change from its listing's off-market day back to the
last ask before that day, 104,330 rows in the served dataset. I timed the price and status
events in those listings' records (`docs/notes/closing-asks-2026-11-11.md`) and found
support for the move in part of the rows:

- In 57,633 rows the lister raised the ask within 5 minutes before the ad's off-market
  status event, or after that event. A price typed then stood on the open ad for 5 minutes
  at most. The median log raise is 0.087.
- In 17,063 rows the lister raised the ask more than 5 minutes before the status event, with
  a median log raise of 0.031.
- In 29,634 rows the lister cut the ask.

I move the first group and leave the other two at their off-day price.

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256). On each rental listing's last capture I run
`latest_ask.record_latest` twice, with `stale_days` 7 and -1, and take the last change of
each run (`v9` and `v10`), as `b0closing` does. When the two differ I also time the record's
events:

- the off-market day is the day of the record's `offMarketAt`;
- from the entries of `pricing.priceChanges` with a price and a day on or after the
  off-market day, I take the earliest;
- from the entries of `statusChanges` dated on the off-market day with a status other than
  `ACTIVE`, `DRAFT` and `IN_BROKERAGE_REVIEW`, I take the earliest;
- `wait` is the seconds from the price change to the status event, positive when the lister
  typed the price first. A record lacking either event has no `wait`.

I compare the two events as instants in UTC. I take each event's day from its timestamp as
written, with its New York offset, as `record_latest` does.

A row changes when all of these hold:

1. `b0closing.reprice` holds for it: its `latest_ask_how` is `latest`, its latest ask equals
   `v9`, and `v10` differs from `v9`;
2. `v9` is above `v10`, so the off-day change raised the ask;
3. `wait` is 300 seconds or less.

The row then takes `v10`, the ad's last ask before its off-market day. I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with those rows' `latest_ask` replaced and their
  `latest_ask_how` set to `latest, before closing raise`. I date them as `b0closing` does: by
  the day of the `v10` change when it falls on or after the row's day (`change`), and
  otherwise by the row's day (`row, change before`).
- `set_aside.parquet`: SRC's, copied.
- `manifest.json`: SRC's manifest with `rows_sha256` updated, and a `closing_raise` entry
  giving SRC's path and rows SHA-256, the rule, the rows `b0closing.reprice` would change,
  the rows changed here with their median log change, and the rows left at their off-day
  price, counted as cuts, raises with a longer wait and raises with no wait.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .b0closing import reprice
from .b0data import sha256
from .latest_ask import CLOSING_STALE_DAYS, STALE_DAYS, _day, record_latest

HOW = "latest, before closing raise"
# A raise typed up to this many seconds before the off-market status event, or at any time
# after it, counts as typed while the ad closed.
MAX_WAIT = 300
# A status change to one of these leaves the ad on the market or not yet on it.
OPEN = {"ACTIVE", "DRAFT", "IN_BROKERAGE_REVIEW"}


def _instant(value: str) -> dt.datetime:
    """The timestamp `value` as an instant, read as UTC when it carries no offset."""
    t = dt.datetime.fromisoformat(value)
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def wait(raw: str) -> float:
    """The seconds from the first price change dated on or after the off-market day of the
    raw listing record `raw` to its first off-market status event dated on that day, or NaN
    when the record lacks the day or either event."""
    d = json.loads(raw)
    off = _day(d.get("offMarketAt"))
    if off is None:
        return np.nan
    priced = [
        _instant(c["changedAt"])
        for c in (d.get("pricing") or {}).get("priceChanges") or []
        if c.get("price") and _day(c["changedAt"]) >= off
    ]
    closed = [
        _instant(c["changedAt"])
        for c in d.get("statusChanges") or []
        if c.get("changedAt")
        and _day(c["changedAt"]) == off
        and c.get("status") not in OPEN
    ]
    if not priced or not closed:
        return np.nan
    return (min(closed) - min(priced)).total_seconds()


def last_asks(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each rental listing in `ids`, `v9`, `v10` and `d10` as `b0closing.last_asks` gives
    them from the listing's last capture in the records file `path`, and the `wait` of that
    capture when `v9` and `v10` differ (NaN otherwise). I read a row group at a time, and its
    record texts only for the rows I keep, as `b0closing.last_asks` does."""
    seen: dict[str, tuple] = {}
    file = pq.ParquetFile(path)
    for group in range(file.num_row_groups):
        head = file.read_row_group(
            group, columns=["listing_id", "listing_type", "last_collected_at"]
        )
        lid = [str(x) for x in head["listing_id"].to_pylist()]
        at = head["last_collected_at"].to_pylist()
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
            v9, v10 = (
                (record_latest(raw, days)["changes"] or [(None, np.nan)])[-1]
                for days in (STALE_DAYS, CLOSING_STALE_DAYS)
            )
            seen[i] = (
                t,
                v9[1],
                v10[1],
                v10[0],
                wait(raw) if v9[1] != v10[1] else np.nan,
            )
        del raws
    return pd.DataFrame(
        [(i, *v) for i, (_, *v) in seen.items()],
        columns=["listing_id", "v9", "v10", "d10", "wait"],
    ).set_index("listing_id")


def closing_raise(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    ids = pd.read_parquet(src / "rows.parquet", columns=["listing_id"]).listing_id
    asks = last_asks(Path(records["path"]), set(ids.astype(str)))
    frame = pd.read_parquet(src / "rows.parquet")
    lid = frame.listing_id.astype(str)
    would = reprice(frame, asks)
    raised = would & (
        lid.map(asks.v9).to_numpy(float) > lid.map(asks.v10).to_numpy(float)
    )
    waited = lid.map(asks.wait).to_numpy(float)
    change = raised & (waited <= MAX_WAIT)
    new = lid[change].map(asks.v10).to_numpy(float)
    step = np.log(frame.latest_ask.to_numpy(float)[change] / new)
    frame.loc[change, "latest_ask"] = new
    frame.loc[change, "latest_ask_how"] = HOW
    day = pd.to_datetime(frame.price_at[change], utc=True).dt.strftime("%Y-%m-%d")
    d10 = lid[change].map(asks.d10)
    after = (d10 >= day).to_numpy()
    frame.loc[change, "latest_day"] = [
        pd.Timestamp(d).date() for d in np.where(after, d10, day)
    ]
    frame.loc[change, "latest_day_how"] = np.where(
        after, "change", "row, change before"
    )
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    shutil.copy(src / "set_aside.parquet", out / "set_aside.parquet")
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "closing_raise": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "a row priced at a raise from its listing's off-market day, typed "
            f"within {MAX_WAIT} seconds before the off-market status event or after it, "
            "takes the last change dated before that day",
            "listings_read": len(asks),
            "closing_would_change": int(would.sum()),
            "changed": int(change.sum()),
            "dated_by_row": int((~after).sum()),
            "median_log_change": round(float(np.median(step)), 4)
            if len(step)
            else None,
            "kept_off_day_price": {
                "cut": int((would & ~raised).sum()),
                "raise_wait_over_max": int((raised & (waited > MAX_WAIT)).sum()),
                "raise_no_wait": int((raised & np.isnan(waited)).sum()),
            },
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
    print(json.dumps(closing_raise(args.src, args.out)["closing_raise"], indent=2))


if __name__ == "__main__":
    main()
