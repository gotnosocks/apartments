"""Write a B0 dataset with a column for how the previous ad of each row's unit ended.

    python -m rentfrontier.b0ending SRC OUT

S3 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 leaves part
of the previous ad's ending in its residuals: after a delisting or a pause the unit's next ask
sits about 1% under L1's median, against 0.34% after a rental. This script puts S3's reading of
that ending into a dataset as the column `prev_ending`, for a model to read.

I take each row's previous ad as L1's lease phase takes it
(`drift_building_phase.months_since_previous`): a unit is a (building, unit_id) pair, I order
its rows by price_at and then audit_id, and the row before is the previous ad. A unit's first
row and a row with no unit_id have none. I date the opening of a row's ad as S3 did: its
first `ACTIVE` status change, or its price_at when that comes first or the ad has no `ACTIVE`
change.

I read the status changes (`statusChanges`) of each listing's latest record, by the later of
`collected_at` and `last_collected_at`, from the records file of SRC's own pipeline build (the
manifest's `build.records`, checked against its SHA-256). I skip a record with neither time and
keep the first of two records with the same time. For a row with a previous ad, I keep the
previous ad's changes dated strictly before the row's ad opened and drop the rest, changes
with no readable date among them. In what is left, the ending is S3's: the first change to
one of the `ENDINGS` statuses after the last `ACTIVE` change. `prev_ending` takes

    none                  no previous ad, or no unit_id
    rented                the ending is RENTED or IN_CONTRACT
    no_longer_available   NO_LONGER_AVAILABLE
    delisted              DELISTED
    temp_off_market       TEMPORARILY_OFF_MARKET
    undated               a previous ad with no ending dated before the row's ad opened: it was
                          still on the market then, its changes before then hold no ACTIVE
                          change, or it has no record or no status changes

Each row reads only changes dated before its own ad opened, so a previous ad that came back on
the market after that keeps the ending it had when the row opened. The column reads no price.
S3 also read the previous ad's price path, but those prices are the asks of another row, the
last of them that row's target, so they stay out of the dataset.

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with the categorical column `prev_ending` added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and an `ending` entry giving SRC's
  path and rows SHA-256, the records file, the rule, the listings read and the rows in each
  category.

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

ACTIVE = "ACTIVE"
# The statuses that end an ad, and the category of each.
ENDINGS = {
    "RENTED": "rented",
    "IN_CONTRACT": "rented",
    "NO_LONGER_AVAILABLE": "no_longer_available",
    "DELISTED": "delisted",
    "TEMPORARILY_OFF_MARKET": "temp_off_market",
}
CATEGORIES = (
    "none",
    "rented",
    "no_longer_available",
    "delisted",
    "temp_off_market",
    "undated",
)
# Status codes in the events table: 0 for ACTIVE, 1 to 5 for the endings, 6 for the rest
# (DRAFT, IN_STREETEASY_REVIEW and the like).
CODES = {ACTIVE: 0, **{s: i + 1 for i, s in enumerate(ENDINGS)}}
OTHER = len(CODES)
CODE_CATEGORY = np.array([None, *ENDINGS.values()], dtype=object)
NAT = np.datetime64("NaT", "us")


def _naive_us(times) -> np.ndarray:
    """UTC times as tz-naive datetime64[us], NaT where missing."""
    return (
        pd.DatetimeIndex(pd.to_datetime(times, utc=True))
        .tz_convert(None)
        .as_unit("us")
        .to_numpy()
    )


def previous_row(frame: pd.DataFrame) -> np.ndarray:
    """Each row's position of its unit's previous ad in `frame`, -1 for a unit's first ad and
    for a row with no unit_id. Units and the order of their ads follow
    `drift_building_phase.months_since_previous`."""
    at = _naive_us(frame.price_at)
    none = frame.unit_id.isna().to_numpy()
    unit_id = frame.unit_id.astype(object).to_numpy()
    key = (
        frame.building.astype(str).to_numpy(object) + "|" + np.where(none, "", unit_id)
    )
    order = pd.DataFrame(
        {
            "key": key.astype(str),
            "at": at,
            "audit": frame.audit_id.astype(str).to_numpy(),
        }
    ).sort_values(["key", "at", "audit"], kind="stable")
    pos = order.index.to_numpy()
    keys = order.key.to_numpy()
    same = keys[1:] == keys[:-1]
    prev = np.full(len(frame), -1, dtype=np.int64)
    prev[pos[1:][same]] = pos[:-1][same]
    prev[none] = -1
    return prev


def latest_records(path: Path, ids: pd.Index) -> pd.DataFrame:
    """For each listing in `ids` with a record in the records file `path`, the row group and
    offset of its latest record, with `row`, the listing's place in `ids`."""
    file = pq.ParquetFile(path)
    names = set(file.schema_arrow.names)
    times = [c for c in ("collected_at", "last_collected_at") if c in names]
    parts = []
    for group in range(file.num_row_groups):
        head = file.read_row_group(group, columns=["listing_id", *times])
        lid = pd.Index(head["listing_id"].to_numpy(zero_copy_only=False).astype(str))
        at = np.fmax.reduce(
            [head[c].to_numpy(zero_copy_only=False).astype(np.float64) for c in times]
        )
        parts.append(
            pd.DataFrame(
                {
                    "row": ids.get_indexer(lid),
                    "collected": at,
                    "group": group,
                    "offset": np.arange(len(lid)),
                }
            )
        )
    recs = pd.concat(parts, ignore_index=True)
    recs = recs[(recs.row >= 0) & recs.collected.notna()]
    # The latest time wins, and of two records with the same time the first in the file.
    recs = recs.sort_values(
        ["row", "collected", "group", "offset"], ascending=[True, False, True, True]
    )
    return recs.drop_duplicates("row").reset_index(drop=True)


def status_events(path: Path, recs: pd.DataFrame) -> pd.DataFrame:
    """The status changes of the records `recs` (from `latest_records`), one line per change:
    `row`, `pos` (its place in the record's list), `code` (see `CODES`) and `time`."""
    file = pq.ParquetFile(path)
    parts = []
    for group, sel in recs.groupby("group", sort=True):
        raws = (
            file.read_row_group(int(group), columns=["raw_listing_json"])[
                "raw_listing_json"
            ]
            .take(pa.array(sel.offset.to_numpy()))
            .to_pylist()
        )
        rows, pos, codes, ats = [], [], [], []
        for row, raw in zip(sel.row.to_numpy(), raws):
            listing = json.loads(raw) if raw else {}
            for k, change in enumerate(listing.get("statusChanges") or []):
                rows.append(row)
                pos.append(k)
                codes.append(CODES.get(change.get("status"), OTHER))
                ats.append(change.get("changedAt"))
        del raws
        if rows:
            parts.append(
                pd.DataFrame(
                    {
                        "row": np.asarray(rows, dtype=np.int64),
                        "pos": np.asarray(pos, dtype=np.int32),
                        "code": np.asarray(codes, dtype=np.int8),
                        "time": _naive_us(
                            pd.to_datetime(
                                pd.Series(ats, dtype=object),
                                utc=True,
                                format="ISO8601",
                                errors="coerce",
                            )
                        ),
                    }
                )
            )
    if not parts:
        return pd.DataFrame(
            {
                "row": np.zeros(0, np.int64),
                "pos": np.zeros(0, np.int32),
                "code": np.zeros(0, np.int8),
                "time": np.zeros(0, "datetime64[us]"),
            }
        )
    return pd.concat(parts, ignore_index=True)


def opened(frame: pd.DataFrame, events: pd.DataFrame) -> np.ndarray:
    """When each row's ad opened: its first ACTIVE change, or its price_at when that comes
    first or the ad has none."""
    at = _naive_us(frame.price_at)
    active = events[(events.code == CODES[ACTIVE]) & events.time.notna()]
    first = active.groupby("row").time.min()
    on = np.full(len(frame), NAT)
    on[first.index.to_numpy()] = first.to_numpy()
    return np.where(~np.isnat(on) & (on < at), on, at)


def endings(frame: pd.DataFrame, events: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Each row's `prev_ending` as a code into `CATEGORIES`, and counts for the manifest."""
    prev = previous_row(frame)
    has = prev >= 0
    if len(np.unique(prev[has])) != has.sum():
        raise AssertionError("a row is the previous ad of two rows")
    # Each previous ad's changes count up to the opening of the row that follows it.
    cut = np.full(len(frame), NAT)
    cut[prev[has]] = opened(frame, events)[has]
    e = events[events.time < cut[events.row.to_numpy()]]
    last_active = e[e.code == CODES[ACTIVE]].groupby("row").pos.max()
    after = e.row.map(last_active)
    e = e[(e.code > 0) & (e.code < OTHER) & (e.pos > after)]
    first = e.sort_values(["row", "pos"]).drop_duplicates("row")
    end = np.zeros(len(frame), dtype=np.int8)
    end[first.row.to_numpy()] = first.code.to_numpy()
    names = np.full(len(frame), "none", dtype=object)
    code = end[prev[has]]
    names[has] = np.where(code > 0, CODE_CATEGORY[code], "undated")
    read = np.zeros(len(frame), dtype=bool)
    read[events.row.unique()] = True
    stats = {
        "rows_with_previous": int(has.sum()),
        "previous_without_status_changes": int(
            (has & ~read[np.maximum(prev, 0)]).sum()
        ),
    }
    return pd.Index(CATEGORIES).get_indexer(names), stats


def ending(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    ids = pd.Index(frame.listing_id.astype(str))
    if not ids.is_unique:
        raise SystemExit(f"{src} holds a listing twice")
    recs = latest_records(Path(records["path"]), ids)
    events = status_events(Path(records["path"]), recs)
    codes, stats = endings(frame, events)
    frame["prev_ending"] = pd.Categorical.from_codes(codes, categories=CATEGORIES)
    # OUT is made after the read of the records, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "ending": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "records": records["path"],
            "rule": "the first change to RENTED or IN_CONTRACT (rented), "
            "NO_LONGER_AVAILABLE, DELISTED or TEMPORARILY_OFF_MARKET after the last "
            "ACTIVE change, among the status changes of the latest record of the unit's "
            "previous ad (L1's phase order) dated strictly before the row's ad opened (its "
            "first ACTIVE change or its price_at, whichever comes first); S3 of "
            "docs/notes/causal-screens-2026-11-13.md",
            "listings_read": len(recs),
            **stats,
            "rows": {
                name: int(n)
                for name, n in zip(
                    CATEGORIES, np.bincount(codes, minlength=len(CATEGORIES))
                )
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
    print(json.dumps(ending(args.src, args.out)["ending"], indent=2))


if __name__ == "__main__":
    main()
