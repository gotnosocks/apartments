"""Draft ledger lines for the reads coded commercial or placeholder. Not imported.

Each line follows `pipeline/models/ledger/entries.py`: an exclude with its reason, the
reader's quote as `ad_text` evidence, the reading as a `read` item, and `when` holding the
row's month and coded bedrooms. One placeholder code (C033, "Apt" on every ad of the
building) is held back after the hand check, since a studio building's lister could write it.
"""

import json
from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/commercial-sweep")
HERE = Path(__file__).resolve().parent
HELD_BACK = {"C033"}
SOURCE = "commercial sweep 2026-11-20 blind Sonnet reads (docs/notes/commercial-sweep-2026-11-20)"
REASON = {"commercial": "nonresidential", "placeholder": "bedrooms_unknown"}

if __name__ == "__main__":
    R = pd.read_parquet(OUT / "reads.parquet")
    M = pd.read_parquet(
        OUT / "marks.parquet", columns=["listing_id", "first_day", "bedrooms"]
    )
    M["listing_id"] = M.listing_id.astype(str)
    R["listing_id"] = R.listing_id.astype(str)
    R = R.merge(M, on="listing_id", how="left")
    keep = R[R.answer.isin(list(REASON)) & ~R.read_id.isin(HELD_BACK)].sort_values(
        "read_id"
    )
    lines = []
    for r in keep.itertuples():
        bed = None if pd.isna(r.bedrooms) else float(r.bedrooms)
        lines.append(
            {
                "change": "exclude",
                "decided": "2026-11-20",
                "evidence": [
                    {"kind": "ad_text", "quote": f"Ad text: {r.quote}"},
                    {
                        "kind": "read",
                        "detail": f"Sonnet read {r.read_id}, blind to the ask: {r.why}",
                    },
                ],
                "listing_id": r.listing_id,
                "reason": REASON[r.answer],
                "source": SOURCE,
                "when": {"bedrooms": bed, "period": str(r.first_day)[:7]},
            }
        )
    with open(HERE / "candidate_rows.ndjson", "w") as f:
        for x in lines:
            f.write(json.dumps(x, sort_keys=True) + "\n")
    print(
        "lines",
        len(lines),
        "by reason",
        keep.answer.map(REASON).value_counts().to_dict(),
    )
    print("held back", sorted(HELD_BACK))
