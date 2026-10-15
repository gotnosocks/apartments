"""Write made-up ads and analysis rows for the latest-ask cases the real fixture lacks.

In the API data each ad has one analysis row and a record for every ad, so the full build
never meets several rows of one ad, a capture before a row, an ad without records or a missing
answer. This script makes up a small export and rows with those cases, then writes the latest
ask `rentfrontier.latest_ask.choose` gives each row. It reads the records the way
`latest_ask.listings` reads listing observations: an answer without a record counts for
nothing, and the ad's latest record wins.

    PYTHONPATH=frontier/src /data1/apartments/venvs/serve-frontier/bin/python \\
        pipeline/tests/make_cases.py

The cases:

- ad 9000001 has three rows, two of them on one day. The first of those two stands for no days,
  so it takes the last change before its day.
- ad 9000002 has a row with no change on or after its day and a record collected later, so it
  takes the last change before its day, and then its page price.
- ad 9000003's only record was collected before its row.
- ad 9000004 has no answers at all.
- ad 9000005's latest answer is missing, so its earlier record stands.
- ad 9000006's row lacks a bedroom count, and ad 9000007's row lacks a building. So do the rows
  of ads 9000008 and 9000009, in the same building and with the same bedroom count. Rows without
  a building or a bedroom count get no building median, so the wide asks of 9000006 and 9000007
  fall back to the first ask. Had the missing values grouped together, the medians of 4800 would
  have kept the latest asks.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from rentfrontier import latest_ask

OUT = Path(__file__).resolve().parent / "fixture" / "cases"
TOWER = "1-case-street-new_york"


def record(listing_id, changes, price, status="ACTIVE", on=None, off=None):
    return json.dumps(
        {
            "id": str(listing_id),
            "status": status,
            "onMarketAt": on or changes[0][0][:10],
            "createdAt": f"{changes[0][0]}T09:00:00.000-04:00",
            "offMarketAt": off,
            "pricing": {
                "price": price,
                "priceChanges": [
                    {"changedAt": f"{day}T10:00:00.000-04:00", "price": p}
                    for day, p in changes
                ],
            },
        },
        sort_keys=True,
    )


# Each answer: listing id, when it was fetched, and its record, or None for a missing answer.
ANSWERS = [
    (
        9000001,
        "2026-10-01",
        record(
            9000001,
            [
                ("2026-03-01", 3000),
                ("2026-04-10", 3100),
                ("2026-05-01", 3050),
                ("2026-06-01", 3200),
            ],
            3200,
        ),
    ),
    (
        9000002,
        "2026-09-01",
        record(9000002, [("2026-02-01", 2500), ("2026-03-01", 2600)], 2700),
    ),
    (9000003, "2026-01-15", record(9000003, [("2026-01-10", 1800)], 1800)),
    (
        9000005,
        "2026-08-01",
        record(9000005, [("2026-07-01", 4000), ("2026-07-20", 4200)], 4200),
    ),
    (9000005, "2026-09-15", None),
    (
        9000006,
        "2026-09-01",
        record(9000006, [("2026-05-01", 2000), ("2026-06-01", 5000)], 5000),
    ),
    (
        9000007,
        "2026-09-01",
        record(9000007, [("2026-05-01", 2000), ("2026-06-01", 5000)], 5000),
    ),
]
# Each row: listing id, its day, its first ask, its building and its bedroom count.
ROWS = [
    (9000001, "2026-03-01", 3000, TOWER, "1.0"),
    (9000001, "2026-05-01", 3050, TOWER, "1.0"),
    (9000001, "2026-05-01", 3050, TOWER, "1.0"),
    (9000002, "2026-06-15", 2500, TOWER, "1.0"),
    (9000003, "2026-02-01", 1900, TOWER, "1.0"),
    (9000004, "2026-04-01", 2950, TOWER, "1.0"),
    (9000005, "2026-07-01", 4000, TOWER, "2.0"),
    (9000006, "2026-05-01", 2000, TOWER, None),
    (9000007, "2026-05-01", 2000, None, "1.0"),
    (9000008, "2026-05-01", 4800, TOWER, None),
    (9000009, "2026-05-01", 4800, None, "1.0"),
]


def main():
    (OUT / "export" / "ads" / "run-0001").mkdir(parents=True, exist_ok=True)
    answers = pd.DataFrame(
        {
            "listing_id": np.array([a[0] for a in ANSWERS], dtype="int64"),
            "fetched": pd.to_datetime(
                [f"{a[1]}T12:00:00Z" for a in ANSWERS], utc=True
            ).as_unit("us"),
            "response_id": np.arange(1, len(ANSWERS) + 1, dtype="int64"),
            "run": np.ones(len(ANSWERS), dtype="int32"),
            "region": "cases",
            "generation": np.ones(len(ANSWERS), dtype="int32"),
            "outcome": ["record" if a[2] else "missing" for a in ANSWERS],
            "record_sha256": [
                hashlib.sha256(a[2].encode()).hexdigest() if a[2] else None
                for a in ANSWERS
            ],
            "record": [a[2] for a in ANSWERS],
        }
    )
    path = Path("ads/run-0001") / f"responses-0000001-{len(ANSWERS):07d}.parquet"
    answers.to_parquet(OUT / "export" / path, index=False)
    line = {
        "first": 1,
        "last": len(ANSWERS),
        "path": str(path),
        "rows": len(ANSWERS),
        "run": 1,
        "sha256": hashlib.sha256((OUT / "export" / path).read_bytes()).hexdigest(),
        "table": "ads",
        "written": "2026-10-15T12:00:00Z",
    }
    (OUT / "export" / "manifest.ndjson").write_text(
        json.dumps(line, sort_keys=True) + "\n"
    )

    rows = pd.DataFrame(
        {
            "ordinal": np.arange(len(ROWS), dtype="int64"),
            "audit_id": [f"case-{i}" for i in range(len(ROWS))],
            "source_listing_id": [str(r[0]) for r in ROWS],
            "price_at": pd.to_datetime([f"{r[1]}T00:00:00Z" for r in ROWS], utc=True),
            "asking_rent": [float(r[2]) for r in ROWS],
            "log_rent": np.log([float(r[2]) for r in ROWS]),
            "building": pd.array([r[3] for r in ROWS], dtype="str"),
            "bedrooms": pd.array([r[4] for r in ROWS], dtype="str"),
        }
    )
    rows.to_parquet(OUT / "rows.parquet", index=False)

    # As `latest_ask.listings` builds its table: each ad's latest record.
    table = pd.DataFrame(
        [
            {
                "listing_id": str(listing_id),
                "collected_at": pd.Timestamp(f"{fetched}T12:00:00Z").timestamp(),
                **latest_ask.record_latest(raw),
            }
            for listing_id, fetched, raw in ANSWERS
            if raw
        ]
    )
    table = table.sort_values(["collected_at", "listing_id"])
    table = table.drop_duplicates("listing_id", keep="last").set_index("listing_id")
    expected = latest_ask.choose(rows, table)
    expected.insert(0, "ordinal", rows.ordinal)
    expected.to_parquet(OUT / "latest-ask.parquet", index=False)
    print(expected.to_string())


if __name__ == "__main__":
    main()
