"""Add a drop-lot review file's decisions to the corrections ledger, as `drop_lot` entries in a
new batch file.

    pipeline/.venv/bin/python ops/pipeline/drop_lot_import.py REVIEWS --name NAME

Data improvements writes a review file such as `config/reviews/drop-lot-20261017.jsonl` after a
reader goes through the rows `analysis.building_check` flags. Each line gives an ad, the lot
`buildings.lots` gave its building, the reader's reason and note, and evidence of three kinds:

- `lot_record`: the flag, with the lot's MapPLUTO record;
- `pad_lookup`: the lot PAD gives the ad's own address;
- `ad_text`: the ad's words, as `Ad text: "..."`.

The script works in these steps:

1. It turns each line into a `drop_lot` line of the ledger. The `when` gives the review's lot,
   so the entry goes stale when the ad's building takes another lot. The lot record and the
   PAD lookup become `city_record` items, the ad's words an `ad_text` quote, and the reader's
   note a `read` with the review's source file. `source` gives the review file and line.
2. It leaves out a line when an entry of the ledger came from the same review file and line,
   and checks each other line with the ledger's own parser, stopping at the first it refuses.
3. It writes the lines to `pipeline/ledger/NAME.ndjson`, stopping when the file exists, and
   prints the counts. When every line is already in the ledger, it writes no file.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "pipeline" / "ledger"
ENTRIES = REPO / "pipeline" / "models" / "ledger" / "entries.py"
CITY = {"lot_record", "pad_lookup"}


def load_entries():
    spec = importlib.util.spec_from_file_location("entries", ENTRIES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(review):
    """The ledger evidence of the review line `review`."""
    items = []
    for item in review["evidence"]:
        detail = item["detail"]
        if item["kind"] in CITY:
            items.append({"kind": "city_record", "detail": detail})
        elif item["kind"] == "ad_text":
            quote = detail.removeprefix("Ad text:").strip()
            if len(quote) > 1 and quote[0] == quote[-1] == '"':
                quote = quote[1:-1]
            items.append({"kind": "ad_text", "quote": quote})
        else:
            raise SystemExit(
                f"{review['listing_id']}: no ledger kind for {item['kind']!r}"
            )
    items.append({"kind": "read", "detail": review["note"], "file": review["source"]})
    return items


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("reviews", type=Path)
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    reviews = args.reviews.resolve()
    label = reviews.relative_to(REPO).as_posix()
    out = LEDGER / f"{args.name}.ndjson"
    if out.exists():
        raise SystemExit(f"{out} exists")
    entries = load_entries()
    sources = {
        row["source"]
        for row in entries.read(sorted(LEDGER.glob("*.ndjson")))
        if row["source"]
    }
    lines, skipped = [], 0
    for number, text in enumerate(reviews.read_text().split("\n"), start=1):
        if not text.strip():
            continue
        review = json.loads(text)
        source = f"{label}:{number}"
        if source in sources:
            skipped += 1
            continue
        line = {
            "change": "drop_lot",
            "listing_id": str(review["listing_id"]),
            "reason": review["reason"],
            "when": {"bbl": review["bbl"]},
            "evidence": evidence(review),
            "decided": review["decided"],
            "source": source,
        }
        text = json.dumps(line, sort_keys=True, ensure_ascii=False)
        try:
            entries.parse(text)
        except entries.LedgerError as error:
            raise SystemExit(f"{source}: {error}") from error
        lines.append(text)
    if not lines:
        print(f"{label}: all {skipped} lines already in the ledger, no file written")
        return 0
    out.write_text("".join(f"{line}\n" for line in lines))
    rows = entries.read([out])
    print(
        f"{out.relative_to(REPO)}: {len(rows)} entries, {skipped} already in the ledger,",
        dict(collections.Counter(row["reason"] for row in rows)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
