"""Write a small made-up export with price histories the real fixture lacks.

The real fixture holds whole buildings cut from the full export. The case tests copy the export
this script writes to `fixture/cases/export`, then append the ads each test needs.

    /data1/apartments/venvs/serve-frontier/bin/python pipeline/tests/make_cases.py

The ads:

- ad 9000001 changes its price four times, and its page price differs from all its changes.
- ad 9000002 changes its price twice, and its page price differs from both.
- ad 9000003's only record was collected in January.
- ad 9000005's latest answer is missing, so its earlier record stands.
- ads 9000006 and 9000007 more than double their asks.

The records name no building, so the build finds no unit page for any of these ads, and none of
them gives a fit-ready row.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

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
            3250,
        ),
    ),
    (
        9000002,
        "2026-09-01",
        record(9000002, [("2026-02-01", 2500), ("2026-03-01", 2600)], 2700),
    ),
    (9000003, "2026-01-15", record(9000003, [("2026-01-10", 1800)], 1850)),
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
# The building of the case tower. The case records name no building, so the build finds no unit
# page for any of their ads.
BUILDING_ANSWERS = [
    (
        "900001",
        "2026-10-01",
        json.dumps({"id": "900001", "slug": TOWER}, sort_keys=True),
    )
]


def write_answers(table, key, answers, first):
    """Write `answers`, each a key, the day it was fetched and its record or None, as a file of
    run 1 of `table` with response IDs from `first`, and return its manifest line."""
    ids = np.arange(first, first + len(answers), dtype="int64")
    frame = pd.DataFrame(
        {
            key: [a[0] for a in answers],
            "fetched": pd.to_datetime(
                [f"{a[1]}T12:00:00Z" for a in answers], utc=True
            ).as_unit("us"),
            "response_id": ids,
            "run": np.ones(len(answers), dtype="int32"),
            "region": "cases",
            "generation": np.ones(len(answers), dtype="int32"),
            "outcome": ["record" if a[2] else "missing" for a in answers],
            "record_sha256": [
                hashlib.sha256(a[2].encode()).hexdigest() if a[2] else None
                for a in answers
            ],
            "record": [a[2] for a in answers],
        }
    )
    path = Path(table) / "run-0001" / f"responses-{ids[0]:07d}-{ids[-1]:07d}.parquet"
    (OUT / "export" / path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUT / "export" / path, index=False)
    return {
        "first": int(ids[0]),
        "last": int(ids[-1]),
        "path": str(path),
        "rows": len(answers),
        "run": 1,
        "sha256": hashlib.sha256((OUT / "export" / path).read_bytes()).hexdigest(),
        "table": table,
        "written": "2026-10-15T12:00:00Z",
    }


def main():
    ads = [(np.int64(a[0]), *a[1:]) for a in ANSWERS]
    lines = [
        write_answers("ads", "listing_id", ads, 1),
        write_answers("buildings", "building_id", BUILDING_ANSWERS, len(ANSWERS) + 1),
    ]
    (OUT / "export" / "manifest.ndjson").write_text(
        "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines)
    )


if __name__ == "__main__":
    main()
