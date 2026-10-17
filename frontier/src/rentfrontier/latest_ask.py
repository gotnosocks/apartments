"""Each NB8 row's latest ask: the last price its listing showed while it was on
the market, from the listing's own StreetEasy record in the granular crawls or
in the data pipeline's records file.

    python -m rentfrontier.latest_ask [nb9]
    python -m rentfrontier.latest_ask --crawl <granular dir> --tag <name> <dataset dir>...
    python -m rentfrontier.latest_ask --crawl page --crawl <granular dir> --tag <name> <dataset dir>
    python -m rentfrontier.latest_ask --crawl page --crawl records --tag <name> <dataset dir>

writes EXTERNAL_ROOT/latest-ask/<date>-<commit>/latest-ask.parquet (one line per
row of data.DATASET_NB8, or of data.DATASET_NB9 with `nb9`, or of every dataset
named after `--crawl`: audit_id, the row's first ask, its latest ask and how the latest ask
was chosen) and provenance.json. Refuses a dirty tree. The `latest-ask-v2` data
rule prices each row from this file.

`--crawl records` reads the API records of the newest clean build in the
pipeline's catalog, after checking the file's SHA-256 (`rentfrontier.api_records`),
in place of an API granular export. Each record counts as captured at its last
fetch, and provenance.json adds the file's name and SHA-256 under `records`.

For each listing the builder reads the last rental capture's
`pricing.priceChanges` in date order. A sale listing can carry a rental's id,
so it skips sale observations. Landlords often type a placeholder ($10,000, $1,000, $500) into
the price on the day they take a listing down. So a change dated on or after
the listing's off-market day is skipped when it is more than twice or under
half the ask before it, or a raise of more than 20% to exactly $10,000.
Smaller changes on that day are mostly the final ask (a raise or cut as the
listing is let) and count. A listing still on the market
keeps all its changes, and changes dated on the day the listing went up always
count, so a typo the advertiser fixed that same day gives way to the fix.
Before that check, the builder drops every change dated more than a week after
the off-market day, whatever its size, unless the record's status changes show
the listing going ACTIVE again after that day. Brokers reuse an old ad's record
for a later ad of the same apartment, so those changes carry a later ad's asks.
The table for latest-ask-v10 goes further with `CLOSING_STALE_DAYS` and drops
every change from the off-market day on, so each row ends at its last ask
while listed. It keeps the changes of an ad listed and closed on the same day,
and those of an ad that went ACTIVE again after its off day.

Each row then takes the last kept change dated from the row's own day up to
the day of its listing's next NB8 row, so two rows of one listing each keep
their own episode. A row with no change in those dates takes the change in
effect on its day, and a row newer than the listing's last capture keeps its
ask. Two checks follow:

1. A latest ask more than twice or under half the row's first ask is more
   likely a typo, or a sale price, in one of the two. The row takes whichever
   of the two is nearer the median first ask of the building's other rows with
   the same bedroom count, and keeps its first ask when the building has no
   such row. The median takes in the building's later rows as well, as
   quarantine-v13's screen does; it decides about 250 rows.
2. On a listing's last row, a page price (`pricing.price`) matching no change
   is the listing's current price, and the row takes it when it is within a
   factor of 2 of the kept ask. One differing by a factor of 9 to 11 has a
   dropped or added digit in one of them, and the row takes the nearer of the
   two in the same way. For this digit check the builder leaves out only a
   page price matching a kept change. A listing correcting a tenfold typo on
   its last day on the market shows the fix as its page price, and the
   placeholder check above drops the fix as a change.

A row keeps its `price_at`, the day its listing first asked, even when its
price is from a later change.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import api_records, data
from rentfrontier.listing_extras import CRAWLS, EXTERNAL_ROOT, _git

# A change on or after the off-market day this far from the ask before it is a
# placeholder.
PLACEHOLDER_RATIO = 2.0
# So is a raise of more than 20% to exactly $10,000, the commonest placeholder:
# 189 of the first changes after an off-market day rise more than 20% to it,
# against 92 to the next commonest price.
PLACEHOLDER_PRICE, PLACEHOLDER_RAISE = 10000, 1.2
# A change dated more than this many days after the off-market day edits an ad
# long gone, unless the ad went ACTIVE again after that day. Listing 2273410 ran
# for 5 days in December 2017, and its record carries changes to $2,250 and
# $3,000 from March 2019, the asks of a later ad for the same apartment.
STALE_DAYS = 7
# latest-ask-v10 passes this as `stale_days`, so it also drops the changes dated
# on the off-market day and in the week after it.
CLOSING_STALE_DAYS = -1
# A latest ask outside this factor of the first ask is checked against the
# building's other rows (check 1).
MAX_RATIO = 2.0
# A page price this far from the kept ask, and matching no kept change, is a
# digit error in one of them (check 2). A page price equal to a dropped change
# counts, so a dropped placeholder of $500 to $1,000 also enters the check, and
# the building median then keeps the ask.
DIGIT_RATIO = (9.0, 11.0)


def _day(value) -> str | None:
    return str(value)[:10] if value else None


def _stale(day: str, off: str | None, active: list[str], stale_days) -> bool:
    """Whether a change on `day` falls more than `stale_days` days after the
    off-market day `off`, with no ACTIVE status dated after `off`."""
    if stale_days is None or off is None or any(a > off for a in active):
        return False
    return (dt.date.fromisoformat(day) - dt.date.fromisoformat(off)).days > stale_days


def record_latest(raw: str, stale_days: int | None = STALE_DAYS) -> dict:
    """The kept price changes of one raw listing record, as (day, price) in date
    order, its page price when no change carries it, and its page price for the
    digit check when no kept change carries it. `n_placeholder` counts the
    changes dropped as placeholders or as stale; `stale_days=None` keeps the
    stale ones."""
    d = json.loads(raw)
    pricing = d.get("pricing") or {}
    changes = sorted(
        (c for c in pricing.get("priceChanges") or [] if c.get("price")),
        key=lambda c: c["changedAt"],
    )
    on, off = (
        _day(d.get("onMarketAt") or d.get("createdAt")),
        _day(d.get("offMarketAt")),
    )
    still = d.get("status") == "ACTIVE" or off is None
    active = [
        _day(c["changedAt"])
        for c in d.get("statusChanges") or []
        if c.get("status") == "ACTIVE" and c.get("changedAt")
    ]
    kept = []
    for c in changes:
        day = _day(c["changedAt"])
        if not still and day != on and _stale(day, off, active, stale_days):
            continue
        if not (still or day < off or day == on) and kept:
            ratio = c["price"] / kept[-1]["price"]
            if ratio > PLACEHOLDER_RATIO or ratio < 1 / PLACEHOLDER_RATIO:
                continue
            if c["price"] == PLACEHOLDER_PRICE and ratio > PLACEHOLDER_RAISE:
                continue
        kept.append(c)
    price = pricing.get("price")
    return {
        "changes": [(_day(c["changedAt"]), float(c["price"])) for c in kept],
        "page_price": price
        if price and price not in {c["price"] for c in changes}
        else None,
        "digit_page": price
        if price and price not in {c["price"] for c in kept}
        else None,
        "n_placeholder": len(changes) - len(kept),
    }


def listings(crawls=None, records: dict | None = None) -> pd.DataFrame:
    """One line per listing id, from its last capture in any crawl. A crawl
    `records` is the pipeline's records file, `records` once checked."""
    rows = []
    columns = ["listing_id", "listing_type", "collected_at", "raw_listing_json"]
    for crawl in (crawls or CRAWLS).values():
        for r in api_records.observations(crawl, columns, records):
            if r["listing_type"] == "rental" and r["raw_listing_json"]:
                rows.append(
                    {
                        "listing_id": str(r["listing_id"]),
                        "collected_at": r["collected_at"],
                        **record_latest(r["raw_listing_json"]),
                    }
                )
    out = pd.DataFrame(rows).sort_values(["collected_at", "listing_id"])
    return out.drop_duplicates("listing_id", keep="last").set_index("listing_id")


def _row_latest(frame: pd.DataFrame, table: pd.DataFrame) -> tuple:
    """Each row's last kept change dated from its own day up to the day of its
    listing's next NB8 row, and whether the page price speaks for the row. A row
    with no change in those dates takes the change in effect on its day when
    the capture came after that day; otherwise it gets NaN."""
    lid = frame.source_listing_id.astype(str).to_numpy()
    at = pd.to_datetime(frame.price_at, utc=True)
    day = at.dt.strftime("%Y-%m-%d").to_numpy()
    order = np.lexsort((day, lid))
    nxt = np.full(len(frame), "9999-99-99", dtype=object)
    same = lid[order][1:] == lid[order][:-1]
    nxt[order[:-1][same]] = day[order][1:][same]
    changes = table.changes.to_dict()
    captured = pd.to_datetime(
        frame.source_listing_id.astype(str).map(table.collected_at), unit="s", utc=True
    )
    after = (captured > at).to_numpy()
    out = np.full(len(frame), np.nan)
    for i in range(len(frame)):
        before = np.nan
        for when, price in changes.get(lid[i], ()):
            if when < day[i]:
                before = price
            elif when < nxt[i]:
                out[i] = price
        if np.isnan(out[i]) and after[i]:
            out[i] = before
    # A page price belongs to a listing's last row, when captured after it.
    return out, (nxt == "9999-99-99") & after


def _peer_median(frame: pd.DataFrame) -> np.ndarray:
    """Each row's median log first ask over the other rows of its building
    with the same bedroom count; NaN when it has none."""
    key = frame.building.astype(str) + "|" + frame.bedrooms.astype(str)
    out = np.full(len(frame), np.nan)
    for idx in key.groupby(key).indices.values():
        if len(idx) < 2:
            continue
        v = frame.log_rent.to_numpy()[idx]
        for j, i in enumerate(idx):
            out[i] = np.median(np.delete(v, j))
    return out


def choose(frame: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """audit_id, first_ask, latest_ask and how it was chosen, for every row."""
    t = table.reindex(frame.source_listing_id.astype(str).to_numpy())
    first = frame.asking_rent.to_numpy(float)
    live, last = _row_latest(frame, table)
    page = t.page_price.to_numpy(float)
    digit_page = t.digit_page.to_numpy(float)
    peer = _peer_median(frame)

    def nearer(a, b):
        da, db = np.abs(np.log(a) - peer), np.abs(np.log(b) - peer)
        return np.where(np.isnan(peer), a, np.where(db < da, b, a))

    price = np.where(np.isnan(live), first, live)
    how = np.where(
        np.isnan(live),
        np.where(
            t.index.isin(table.index), "own ask, captured before the row", "uncaptured"
        ),
        "latest",
    )
    ratio = price / first
    wide = (ratio > MAX_RATIO) | (ratio < 1 / MAX_RATIO)
    picked = nearer(first, price)
    how = np.where(
        wide,
        np.where(picked == first, "first, nearer building", "latest, nearer building"),
        how,
    )
    price = np.where(wide, picked, price)
    # On a listing's last row, captured after it, a page price within the factor of the kept ask
    # is the listing's current price.
    near = (
        last
        & ~np.isnan(page)
        & (page / price <= MAX_RATIO)
        & (price / page <= MAX_RATIO)
    )
    how = np.where(near & (page != price), "page price", how)
    price = np.where(near, page, price)
    # A page price matching a dropped change counts here: a listing fixing a typo on its last day.
    digit = digit_page / price
    digit = (
        last
        & ~np.isnan(digit_page)
        & (
            ((digit >= DIGIT_RATIO[0]) & (digit <= DIGIT_RATIO[1]))
            | ((1 / digit >= DIGIT_RATIO[0]) & (1 / digit <= DIGIT_RATIO[1]))
        )
    )
    picked = nearer(price, digit_page)
    how = np.where(digit & (picked != price), "page price, digit", how)
    price = np.where(digit, picked, price)
    return pd.DataFrame(
        {
            "audit_id": frame.audit_id.to_numpy(),
            "first_ask": first,
            "latest_ask": price,
            "how": how,
        }
    )


def parse(argv: list[str]) -> tuple[dict | None, str, list[Path]]:
    """The crawls, the directory tag and the datasets a command line names."""
    # With --crawl, the datasets named after it come from that one crawl (the
    # API backfill's regions); their buildings and listings are disjoint, so
    # one pass over their rows together gives each row what a pass of its own
    # would.
    # `--crawl page` stands for the page crawls (CRAWLS) and `--crawl records`
    # for the pipeline's records file. With several --crawl flags, listings()
    # reads every crawl named and takes each listing's last capture in any of
    # them.
    if argv[:1] != ["--crawl"]:
        return None, "", [data.DATASET_NB9 if argv == ["nb9"] else data.DATASET_NB8]
    crawls, tag = {}, ""
    while argv[:1] == ["--crawl"]:
        if argv[1] == "page":
            crawls.update(CRAWLS)
        else:
            crawls[f"crawl-{len(crawls)}" if crawls else "crawl"] = argv[1]
        argv = argv[2:]
    if argv[:1] == ["--tag"]:
        tag, argv = f"-{argv[1]}", argv[2:]
    return crawls, tag, [Path(d) for d in argv]


def main(argv: list[str]):
    crawls, tag, datasets = parse(argv)
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    frames = [data.load(d) for d in datasets]
    for key in ("building", "source_listing_id"):
        seen = pd.concat(f[key].drop_duplicates() for f in frames)
        if seen.duplicated().any():
            raise SystemExit(f"datasets share a {key}")
    frame = pd.concat(frames, ignore_index=True)
    records = (
        api_records.records_file()
        if api_records.CRAWL in (crawls or CRAWLS).values()
        else None
    )
    out = choose(frame, listings(crawls, records))
    out_dir = EXTERNAL_ROOT / "latest-ask" / f"{started:%Y%m%d}-{commit[:7]}{tag}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "latest-ask.parquet"
    out.to_parquet(path, index=False)
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "built_at": started.isoformat(),
                "commit": commit,
                "dataset": ", ".join(map(str, datasets)),
                "crawls": crawls or CRAWLS,
                "records": records,
                "rows": len(out),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {path}: {len(out)} rows")
    print(out.how.value_counts().to_string())
    changed = out[out.latest_ask != out.first_ask]
    r = np.abs(np.log(changed.latest_ask / changed.first_ask))
    print(
        f"changed {len(changed)}; median |change| {np.median(r):.3f}; over 2x {int((r > np.log(2)).sum())}"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
