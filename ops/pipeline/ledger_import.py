"""Add the corrections of the chain's latest rules to the corrections ledger, as a new batch file.

    pipeline/.venv/bin/python ops/pipeline/ledger_import.py [--name NAME]

The chain keys its corrections by `audit_id`, a row of one of its datasets, and the ledger keys
them by the ad's `listing_id`. The script works in these steps:

1. It reads the rule files in `RULES`, in the order `rentfrontier.data` applies them. For each
   correction it reads the dataset listed in the rule's provenance file, and takes the row's ad
   and its recorded values from the dataset's `observations.jsonl`. A quarantine line gives its ad and
   month itself.
2. It gathers the evidence for each correction:
     - the ad's words, from the rule file;
     - the reads in `READS`, `PLANS` and `SIZES` that decided the row, with each read's second
       signal: a size the unit's ads state, or another ad for the unit;
     - the unit's other ads in `DATASET`, the latest dataset. They back a set when more of them
       give the corrected value than give the recorded one.
3. It writes each exclude, and each set with backing, as a ledger line to
   `pipeline/ledger/NAME.ndjson`. It leaves out a line when the ledger already holds an entry
   with the same change, ad, month, reason or field and values, unless a retract undoes that
   entry. A later run after a new rule version thus adds only the new rows. It stops when NAME exists.
4. It writes each set without backing to `config/reviews/ledger-held-NAME.jsonl`, with the
   counts of the unit's other ads, for a reader to look for backing.
5. It checks the new file with the ledger's own parser and prints the counts.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import re
from datetime import date
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "pipeline" / "ledger"
DATASET = Path(
    "/data1/apartments/frontier/datasets/"
    "chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-mw-api-analysis-20261015-c9eea95"
)
# The files of the latest version of each correction and quarantine rule of the chain.
RULES = [
    "config/corrections/bedrooms-ad-v3-20261008.jsonl",
    "config/corrections/bedrooms-ad-v4-20261015.jsonl",
    "config/corrections/bedrooms-ad-v5-20261015.jsonl",
    "config/corrections/bedrooms-ad-v6-20261015.jsonl",
    "config/corrections/bedrooms-ad-v7-20261016.jsonl",
    "config/corrections/baths-ad-v3-20261008.jsonl",
    "config/corrections/sqft-units-v1-20261015.jsonl",
    "config/reviews/quarantine-v32-20261016.jsonl",
]
READS = [
    "config/reviews/ad-fit-reads-20261015-bedrooms.jsonl",
    "config/reviews/ad-fit-reads-20261015-studios.jsonl",
    "config/reviews/ad-fit-reads-20261016-api.jsonl",
]
PLANS = [
    "config/reviews/floor-plans-20261015-bedrooms.jsonl",
    "config/reviews/floor-plans-20261015-studios.jsonl",
]
SIZES = "config/reviews/sqft-units-reads-20261015.jsonl"
OTHER_AD = re.compile(r"Another ad for the unit \((\d+), (\d{4}-\d{2}-\d{2})\)")


def lines(path):
    with open(REPO / path) as f:
        for number, text in enumerate(f, start=1):
            if text.strip():
                yield number, json.loads(text)


def by_audit(paths, verdict=None):
    found = {}
    for path in paths:
        for _, line in lines(path):
            if verdict is None or line.get("verdict") == verdict:
                found[line["audit_id"]] = {**line, "file": path}
    return found


def observations(db, datasets):
    """Load the rows of each dataset in `datasets` with the columns the ledger reads, tagged
    with the dataset's place in the list."""
    columns = {
        "audit_id": "VARCHAR",
        "source_listing_id": "VARCHAR",
        "unit_id": "VARCHAR",
        "period": "DATE",
        "bedrooms": "DOUBLE",
        "reported_full_bathrooms": "BIGINT",
        "reported_half_bathrooms": "BIGINT",
        "square_feet": "DOUBLE",
    }
    for number, dataset in enumerate(datasets):
        db.execute(
            f"""CREATE OR REPLACE TABLE obs{number} AS
            SELECT audit_id, source_listing_id AS listing_id, unit_id,
                strftime(period, '%Y-%m') AS month, bedrooms,
                reported_full_bathrooms AS full_baths, reported_half_bathrooms AS half_baths,
                square_feet, {number} AS dataset
            FROM read_json(?, format = 'newline_delimited', columns = {columns!r})""",
            [str(Path(dataset) / "observations.jsonl")],
        )
    db.execute(
        "CREATE OR REPLACE TABLE obs AS "
        + " UNION ALL ".join(f"SELECT * FROM obs{n}" for n in range(len(datasets)))
    )


def others(db, latest, row, field, corrected):
    """The unit's other ads in DATASET that give the corrected value, and the count of those
    that give the recorded one."""
    if field == "bedrooms":
        same, value = "bedrooms = ?", [[corrected], [row["bedrooms"]]]
    else:
        same = "full_baths = ? AND coalesce(half_baths, 0) = ?"
        value = [
            [corrected["full_baths"], corrected["half_baths"]],
            [row["full_baths"], row["half_baths"] or 0],
        ]
    query = f"""SELECT listing_id, min(month) FROM obs
        WHERE dataset = ? AND unit_id = ? AND listing_id <> ? AND {same}
        GROUP BY listing_id ORDER BY 2"""
    base = [latest, row["unit_id"], row["listing_id"]]
    agree = db.execute(query, base + value[0]).fetchall()
    disagree = db.execute(query, base + value[1]).fetchall()
    return agree, len(disagree)


def same_size(db, latest, row, corrected):
    """The unit's other ads in DATASET with the row's bedroom count and a size within 10% of
    `corrected`."""
    return db.execute(
        """SELECT listing_id, min(month), min(square_feet) FROM obs
        WHERE dataset = ? AND unit_id = ? AND listing_id <> ? AND bedrooms = ?
            AND abs(square_feet / ? - 1) <= 0.1
        GROUP BY listing_id ORDER BY 2""",
        [latest, row["unit_id"], row["listing_id"], row["bedrooms"], corrected],
    ).fetchall()


def signal(read):
    """The evidence item of a read's second signal."""
    text = read.get("second_signal")
    if not text:
        return None
    if match := OTHER_AD.match(text):
        return {
            "kind": "other_ad",
            "listing_id": match[1],
            "listed": match[2],
            "detail": text,
        }
    if text.startswith("The unit's stated"):
        return {"kind": "stated_size", "detail": text}
    return {"kind": "read", "detail": text}


def file_day(path):
    return f"{path[-14:-10]}-{path[-10:-8]}-{path[-8:-6]}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--name", default=f"{date.today().isoformat()}-chain")
    args = parser.parse_args(argv)
    out = LEDGER / f"{args.name}.ndjson"
    held_path = REPO / "config" / "reviews" / f"ledger-held-{args.name}.jsonl"
    if out.exists():
        raise SystemExit(f"{out} exists: the ledger takes a new file for each batch")

    spec = importlib.util.spec_from_file_location(
        "ledger_entries", REPO / "pipeline" / "models" / "ledger" / "entries.py"
    )
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)

    def key(entry):
        values = tuple(
            entry.get(name) for name in ("bedrooms", "full_baths", "half_baths")
        )
        return (
            entry["change"],
            entry["listing_id"],
            entry.get("reason") or entry.get("field"),
            entry.get("when_period"),
            values + (entry.get("square_feet"),),
        )

    existing = ledger.read(sorted(LEDGER.glob("*.ndjson")))
    retracted = {row["retracts"] for row in existing if row["change"] == "retract"}
    known = {key(row) for row in existing if row["entry"] not in retracted}

    sources = {}
    for path in RULES:
        provenance = REPO / path.replace(".jsonl", ".provenance.json")
        if provenance.exists():
            sources[path] = str(Path(json.loads(provenance.read_text())["dataset"]))
    datasets = sorted({*sources.values(), str(DATASET)})
    sources = {path: datasets.index(dataset) for path, dataset in sources.items()}
    latest = datasets.index(str(DATASET))
    db = duckdb.connect(config={"memory_limit": "1500MB", "threads": 4})
    observations(db, datasets)
    reads = by_audit(READS, "correct_bedrooms")
    plans = by_audit(PLANS, "correct_bedrooms")
    sizes = by_audit([SIZES])

    def row_of(dataset, audit):
        cursor = db.execute(
            "SELECT * FROM obs WHERE dataset = ? AND audit_id = ? LIMIT 1",
            [dataset, audit],
        )
        found = cursor.fetchone()
        return found and dict(zip([c[0] for c in cursor.description], found))

    written, held, counts = [], [], collections.Counter()
    for path in RULES:
        rule = Path(path).name.rsplit("-", 1)[0]
        for number, line in lines(path):
            source = f"{path}:{number}"
            if path not in sources:
                action = line["action"]
                when = {"period": line["period"]}
                if action == "quarantine_bedrooms_unknown":
                    row = row_of(latest, line["audit_id"])
                    if row is not None:
                        when["bedrooms"] = row["bedrooms"]
                evidence = [{"kind": "read", "detail": line["reason"]}]
                if line.get("evidence"):
                    evidence.insert(0, {"kind": "ad_text", "quote": line["evidence"]})
                entry = {
                    "change": "exclude",
                    "listing_id": str(line["source_listing_id"]),
                    "reason": action.removeprefix("quarantine_"),
                    "when": when,
                    "evidence": evidence,
                    "decided": line["review"],
                    "source": source,
                }
                written.append((rule, entry))
                continue

            row = row_of(sources[path], line["audit_id"])
            if row is None:
                counts[f"{rule}: row missing from its dataset"] += 1
                continue
            field = line["field"]
            evidence = []
            if field == "square_feet":
                values = {"square_feet": line["corrected"]}
                when = {"square_feet": row["square_feet"]}
                read = sizes[line["audit_id"]]
                if line["basis"] == "line":
                    evidence.append({"kind": "line_units", "detail": line["evidence"]})
                elif backing := same_size(db, latest, row, line["corrected"]):
                    evidence.append(
                        {
                            "kind": "other_ad",
                            "listings": [lid for lid, _, _ in backing],
                            "detail": line["evidence"],
                        }
                    )
                for quote in (read.get("size_quote"), line.get("layout_quote")):
                    if quote:
                        evidence.append({"kind": "ad_text", "quote": quote})
                note = read.get("second_note") or read.get("first_note")
                evidence.append({"kind": "read", "file": SIZES, "detail": note})
                agree, disagree = [], 0
            else:
                if field == "bedrooms":
                    values = {"bedrooms": line["corrected"]}
                    when = {"bedrooms": row["bedrooms"]}
                else:
                    values = {
                        "full_baths": line["full_baths"],
                        "half_baths": line["half_baths"],
                    }
                    when = {
                        "full_baths": row["full_baths"],
                        "half_baths": row["half_baths"],
                    }
                evidence.append({"kind": "ad_text", "quote": line["evidence"]})
                read = reads.get(line["audit_id"])
                if (
                    field == "bedrooms"
                    and read
                    and read["bedrooms"] == line["corrected"]
                ):
                    evidence.append(
                        {"kind": "read", "file": read["file"], "detail": read["reason"]}
                    )
                    if item := signal(read):
                        evidence.append(item)
                plan = plans.get(line["audit_id"])
                if (
                    field == "bedrooms"
                    and plan
                    and plan["plan_bedrooms"] == line["corrected"]
                ):
                    evidence.append(
                        {
                            "kind": "floor_plan",
                            "plan": plan["plan"],
                            "page": plan["plan_page_url"],
                            "labels": plan["plan_labels"],
                            "bedrooms": plan["plan_bedrooms"],
                        }
                    )
                agree, disagree = others(
                    db, latest, row, field, values.get("bedrooms", values)
                )
                if len(agree) > disagree:
                    evidence.append(
                        {
                            "kind": "other_ad",
                            "listings": [lid for lid, _ in agree],
                            "detail": f"{len(agree)} other ads of the unit give the corrected "
                            f"value and {disagree} the recorded one",
                        }
                    )
            # A bath rule records the total of bathrooms, and the row gives full and half.
            if field != "baths" and line["recorded"] != row[field]:
                counts[f"{rule}: recorded value differs from the dataset's"] += 1
            entry = {
                "change": "set",
                "listing_id": row["listing_id"],
                "set": values,
                "when": when,
                "evidence": evidence,
                "decided": line.get("review") or file_day(path),
                "source": source,
            }
            if not {item["kind"] for item in evidence} & set(ledger.BACKING):
                held.append(
                    {
                        **entry,
                        "rule": rule,
                        "audit_id": line["audit_id"],
                        "unit_id": row["unit_id"],
                        "agree": len(agree),
                        "disagree": disagree,
                    }
                )
                counts[f"{rule}: held"] += 1
                continue
            written.append((rule, entry))

    texts = []
    for rule, entry in written:
        parsed = ledger.parse(json.dumps(entry))
        if key(parsed) in known:
            counts[f"{rule}: repeats a ledger entry"] += 1
            continue
        known.add(key(parsed))
        texts.append(json.dumps(entry, sort_keys=True))
        counts[f"{rule}: {entry['change']}"] += 1
    LEDGER.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(text + "\n" for text in texts))
    ledger.read(sorted(LEDGER.glob("*.ndjson")))
    if held:
        held_path.write_text(
            "".join(json.dumps(h, sort_keys=True) + "\n" for h in held)
        )
    for name, count in sorted(counts.items()):
        print(f"{count:6d}  {name}")
    print(
        f"{len(texts)} lines to {out.relative_to(REPO)}, {len(held)} held in "
        f"{held_path.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
