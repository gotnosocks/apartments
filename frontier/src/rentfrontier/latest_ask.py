"""Each NB8 row's latest ask: the last price its listing showed while it was on
the market, from the listing's own StreetEasy record in the granular crawls.

    python -m rentfrontier.latest_ask

writes EXTERNAL_ROOT/latest-ask/<date>-<commit>/latest-ask.parquet (one line per
NB8 row: audit_id, the row's first ask, its latest ask and how the latest ask
was chosen) and provenance.json. Refuses a dirty tree. The `latest-ask-v2` data
rule prices each row from this file.

For each listing the builder reads the last capture's `pricing.priceChanges`
in date order. Landlords often type a placeholder ($10,000, $1,000, $500) into
the price on the day they take a listing down. So a change dated on or after
the listing's off-market day is skipped when it is more than twice or under
half the ask before it. Smaller changes on that day are mostly the final ask
(a raise or cut as the listing is let) and count. A listing still on the market
keeps all its changes, and changes dated on the day the listing went up always
count, so a typo the advertiser fixed that same day gives way to the fix.

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
   two in the same way.

A row keeps its `price_at`, the day its listing first asked, even when its
price is from a later change.
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import data
from rentfrontier.listing_extras import CRAWLS, EXTERNAL_ROOT, _git

# A change on or after the off-market day this far from the ask before it is a
# placeholder.
PLACEHOLDER_RATIO = 2.0
# A latest ask outside this factor of the first ask is checked against the
# building's other rows (check 1).
MAX_RATIO = 2.0
# A page price this far from the kept ask, and matching no change, is a digit
# error in one of them (check 2).
DIGIT_RATIO = (9.0, 11.0)


def _day(value) -> str | None:
    return str(value)[:10] if value else None


def record_latest(raw: str) -> dict:
    """The kept price changes of one raw listing record, as (day, price) in date
    order, and its page price when no change carries it."""
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
    kept = []
    for c in changes:
        day = _day(c["changedAt"])
        if not (still or day < off or day == on) and kept:
            ratio = c["price"] / kept[-1]["price"]
            if ratio > PLACEHOLDER_RATIO or ratio < 1 / PLACEHOLDER_RATIO:
                continue
        kept.append(c)
    price = pricing.get("price")
    return {
        "changes": [(_day(c["changedAt"]), float(c["price"])) for c in kept],
        "page_price": price
        if price and price not in {c["price"] for c in changes}
        else None,
        "n_placeholder": len(changes) - len(kept),
    }


def listings() -> pd.DataFrame:
    """One line per listing id, from its last capture in any crawl."""
    rows = []
    for crawl in CRAWLS.values():
        for path in sorted(
            glob.glob(f"{crawl}/listing_observations/**/*.parquet", recursive=True)
        ):
            table = pq.read_table(
                path, columns=["listing_id", "collected_at", "raw_listing_json"]
            )
            for r in table.to_pylist():
                if r["raw_listing_json"]:
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
    digit = page / price
    digit = (
        last
        & ~np.isnan(page)
        & (
            ((digit >= DIGIT_RATIO[0]) & (digit <= DIGIT_RATIO[1]))
            | ((1 / digit >= DIGIT_RATIO[0]) & (1 / digit <= DIGIT_RATIO[1]))
        )
    )
    picked = nearer(price, page)
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


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    frame = data.load(data.DATASET_NB8)
    out = choose(frame, listings())
    out_dir = EXTERNAL_ROOT / "latest-ask" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "latest-ask.parquet"
    out.to_parquet(path, index=False)
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "built_at": started.isoformat(),
                "commit": commit,
                "dataset": str(data.DATASET_NB8),
                "crawls": CRAWLS,
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
    main()
