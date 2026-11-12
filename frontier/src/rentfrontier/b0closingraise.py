"""Write a B0 dataset where a raise typed as its ad closed gives way to the ask before it.

    python -m rentfrontier.b0closingraise SRC OUT

`b0closing` moves every row priced at a change from its listing's off-market day back to the
last ask before that day, 104,330 rows in the served dataset. I timed the price and status
events in those listings' records (`docs/notes/closing-asks-2026-11-11.md`) and found
support for the move where the lister raised the ask within 5 minutes before the ad's
off-market status event, or after that event. A price typed then stood on the open ad for 5
minutes at most. I move those rows to the price standing on the ad before the raise, and
leave the rest at their off-day price: the cuts, and the raises typed more than 5 minutes
before the status event.

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256). On each rental listing's last capture I run
`latest_ask.record_latest` twice, with `stale_days` 7 and -1, and take the last change of
each run (`v9` and `v10`), as `b0closing` does. When the two differ I also time the record's
events:

- the off-market day is the day of the record's `offMarketAt`;
- the status event is the earliest entry of `statusChanges` dated on the off-market day
  with a status other than `ACTIVE`, `DRAFT` and `IN_BROKERAGE_REVIEW`;
- the late changes are the entries of `pricing.priceChanges` dated on or after the
  off-market day, among those `record_latest` keeps with `stale_days` 7. The last of them
  gives `v9`;
- `wait` is the seconds from the last late change to the status event, positive when the
  lister typed the price first. A record lacking either event has no `wait`;
- the standing price is the price of the last late change typed more than 300 seconds
  before the status event. When no late change was typed that early, the standing price is
  `v10`, the ad's last ask before its off-market day.

I compare events as instants in UTC. I take each event's day from its timestamp as written,
with its New York offset, as `record_latest` does.

A row changes when all of these hold:

1. `b0closing.reprice` holds for it: its `latest_ask_how` is `latest`, its latest ask equals
   `v9`, and `v10` differs from `v9`;
2. `wait` is 300 seconds or less, so the lister typed `v9` as the ad closed or after it;
3. `v9` is above the standing price.

The row then takes the standing price. I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with those rows' `latest_ask` replaced and their
  `latest_ask_how` set to `latest, before closing raise`. I date them as `b0closing` does: by
  the day of the standing price's change when it falls on or after the row's day (`change`),
  and otherwise by the row's day (`row, change before`). An open row of a market dataset
  keeps its day, the scoring day `rentfrontier.market` gave it; only its ask changes.
- SRC's other files, copied: `set_aside.parquet` in a latest dataset, `inputs.json` in a
  market dataset.
- `manifest.json`: SRC's manifest with `rows_sha256` updated, and a `closing_raise` entry
  giving SRC's path and rows SHA-256, the rule, the rows `b0closing.reprice` would change,
  the rows changed here with their median log change and the count taking a standing price
  typed on the off-market day, and the rows left at their off-day price: those whose ask
  stood for more than 300 seconds, those typed as the ad closed at or below the standing
  price, and those with no `wait`.

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
# A price typed up to this many seconds before the off-market status event, or at any time
# after it, counts as typed while the ad closed.
MAX_WAIT = 300
# A status change to one of these leaves the ad on the market or not yet on it.
OPEN = {"ACTIVE", "DRAFT", "IN_BROKERAGE_REVIEW"}


def _instant(value: str) -> dt.datetime:
    """The timestamp `value` as an instant, read as UTC when it carries no offset."""
    t = dt.datetime.fromisoformat(value)
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def standing(raw: str, kept: list[tuple[str, float]]) -> tuple:
    """For the raw listing record `raw` and the (day, price) changes `kept` by
    `record_latest`: the seconds from the last kept price change dated on or after the
    off-market day to the first off-market status event dated on that day, and the price
    and day of the last such change typed more than `MAX_WAIT` seconds before that event
    (NaN and None when no change was typed that early). All three are missing when the
    record lacks the off-market day or either event."""
    d = json.loads(raw)
    off = _day(d.get("offMarketAt"))
    missing = (np.nan, np.nan, None)
    if off is None:
        return missing
    late = [
        (_instant(c["changedAt"]), float(c["price"]), _day(c["changedAt"]))
        for c in sorted(
            (
                c
                for c in (d.get("pricing") or {}).get("priceChanges") or []
                if c.get("price")
            ),
            key=lambda c: c["changedAt"],
        )
        if _day(c["changedAt"]) >= off
        and (_day(c["changedAt"]), float(c["price"])) in kept
    ]
    closed = [
        _instant(c["changedAt"])
        for c in d.get("statusChanges") or []
        if c.get("changedAt")
        and _day(c["changedAt"]) == off
        and c.get("status") not in OPEN
    ]
    if not late or not closed:
        return missing
    waits = [(min(closed) - at).total_seconds() for at, _, _ in late]
    stood = [c for c, w in zip(late, waits) if w > MAX_WAIT]
    return (waits[-1], *(stood[-1][1:] if stood else missing[1:]))


def last_asks(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each rental listing in `ids`, `v9`, `v10` and `d10` as `b0closing.last_asks` gives
    them from the listing's last capture in the records file `path`, and that capture's
    `wait`, standing price and its day (`standing`) when `v9` and `v10` differ. I read a row
    group at a time, and its record texts only for the rows I keep, as `b0closing.last_asks`
    does."""
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
            late, early = (
                record_latest(raw, days)["changes"] or [(None, np.nan)]
                for days in (STALE_DAYS, CLOSING_STALE_DAYS)
            )
            v9, (d10, v10) = late[-1][1], early[-1]
            timed = standing(raw, late) if v9 != v10 else (np.nan, np.nan, None)
            seen[i] = (t, v9, v10, d10, *timed)
        del raws
    return pd.DataFrame(
        [(i, *v) for i, (_, *v) in seen.items()],
        columns=["listing_id", "v9", "v10", "d10", "wait", "stood", "stood_day"],
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
    waited = lid.map(asks.wait).to_numpy(float)
    stood = lid.map(asks.stood).to_numpy(float)
    late = ~np.isnan(stood)
    before = np.where(late, stood, lid.map(asks.v10).to_numpy(float))
    closing = would & (waited <= MAX_WAIT)
    change = closing & (frame.latest_ask.to_numpy(float) > before)
    new = before[change]
    step = np.log(frame.latest_ask.to_numpy(float)[change] / new)
    frame.loc[change, "latest_ask"] = new
    frame.loc[change, "latest_ask_how"] = HOW
    # A market dataset's open rows keep the scoring day `rentfrontier.market` moved them to.
    is_open = (
        frame["open"].to_numpy(bool) if "open" in frame else np.zeros(len(frame), bool)
    )
    dated = change & ~is_open
    day = pd.to_datetime(frame.price_at[dated], utc=True).dt.strftime("%Y-%m-%d")
    changed = np.where(late, lid.map(asks.stood_day), lid.map(asks.d10))[dated]
    after = changed >= day.to_numpy()
    frame.loc[dated, "latest_day"] = [
        pd.Timestamp(d).date() for d in np.where(after, changed, day)
    ]
    frame.loc[dated, "latest_day_how"] = np.where(after, "change", "row, change before")
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "closing_raise": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "a row priced at a change from its listing's off-market day, typed "
            f"within {MAX_WAIT} seconds before the off-market status event or after it, "
            "takes the price standing on the ad before that when the change raised it",
            "listings_read": len(asks),
            "closing_would_change": int(would.sum()),
            "changed": int(change.sum()),
            "changed_to_off_day_price": int((change & late).sum()),
            "dated_by_row": int((~after).sum()),
            "open_repriced": int((change & is_open).sum()),
            "median_log_change": round(float(np.median(step)), 4)
            if len(step)
            else None,
            "kept_off_day_price": {
                "stood": int((would & (waited > MAX_WAIT)).sum()),
                "closing_cut": int((closing & ~change).sum()),
                "no_wait": int((would & np.isnan(waited)).sum()),
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
