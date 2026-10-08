"""How each listing ended, from its own StreetEasy record in the granular crawls
(each listing's last capture), keyed by listing id: its last ask, the price
changes on the way, and how long it was listed.

    python -m rentfrontier.listing_outcomes

writes EXTERNAL_ROOT/listing-outcomes/<date>-<commit>/listing-outcomes.parquet
and provenance.json. Refuses a dirty tree.

These are outcomes: they are known only once the listing is over, so they go
on the frame for reading (`attach`), never into a feature set. A listing still
on the market at its last capture is `still_listed`, and its days are counted
to that capture.
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json

import pandas as pd
import pyarrow.parquet as pq

from rentfrontier.listing_extras import CRAWLS, EXTERNAL_ROOT, _git

OUTCOMES_FILE = (
    "/data1/apartments/external/listing-outcomes/20261008-PENDING/"
    "listing-outcomes.parquet"
)
COLUMNS = [
    "final_ask",
    "first_ask",
    "n_changes",
    "n_cuts",
    "n_raises",
    "days_listed",
    "still_listed",
    "status",
]


def record_outcomes(raw: str, collected_at: float) -> dict:
    """The outcome fields of one raw listing record captured at `collected_at`
    (Unix seconds)."""
    d = json.loads(raw)
    pricing = d.get("pricing") or {}
    prices = [
        c.get("price")
        for c in sorted(pricing.get("priceChanges") or [], key=lambda c: c["changedAt"])
        if c.get("price")
    ]
    final = pricing.get("price") or (prices[-1] if prices else None)
    steps = list(zip(prices, prices[1:] + ([final] if final and prices else [])))
    steps = [(a, b) for a, b in steps if a != b]
    status = d.get("status")
    start = pd.to_datetime(d.get("onMarketAt") or d.get("createdAt"), utc=True)
    end = pd.to_datetime(d.get("offMarketAt"), utc=True)
    still = status == "ACTIVE" or pd.isna(end)
    if still:
        end = pd.Timestamp(collected_at, unit="s", tz="UTC")
    return {
        "final_ask": final,
        "first_ask": prices[0] if prices else final,
        "n_changes": len(steps),
        "n_cuts": sum(b < a for a, b in steps),
        "n_raises": sum(b > a for a, b in steps),
        "days_listed": (end - start).days if pd.notna(start) else None,
        "still_listed": still,
        "status": status,
    }


def build() -> pd.DataFrame:
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
                            **record_outcomes(r["raw_listing_json"], r["collected_at"]),
                        }
                    )
    out = pd.DataFrame(rows).sort_values(["collected_at", "listing_id"])
    return out.drop_duplicates("listing_id", keep="last").reset_index(drop=True)


def attach(frame: pd.DataFrame, path: str = OUTCOMES_FILE) -> pd.DataFrame:
    """The frame with each row's listing outcome (`COLUMNS`), matched on
    source_listing_id; NaN for a listing no crawl captured."""
    table = pd.read_parquet(path, columns=["listing_id", *COLUMNS])
    table = table.set_index("listing_id").reindex(
        frame.source_listing_id.astype(str).to_numpy()
    )
    return frame.assign(**{c: table[c].to_numpy() for c in COLUMNS})


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    table = build()
    out_dir = EXTERNAL_ROOT / "listing-outcomes" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "listing-outcomes.parquet"
    table.to_parquet(path, index=False)
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "built_at": started.isoformat(),
                "commit": commit,
                "crawls": CRAWLS,
                "listings": len(table),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {path}: {len(table)} listings")
    print(table[COLUMNS].describe(include="all").to_string())


if __name__ == "__main__":
    main()
