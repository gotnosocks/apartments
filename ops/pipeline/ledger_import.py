"""Add the corrections of the chain's latest rules to the corrections ledger, as a new batch file.

    pipeline/.venv/bin/python ops/pipeline/ledger_import.py [--name NAME]

The chain keys its corrections by `audit_id`, a row of one of its datasets, and the ledger keys
them by the ad's `listing_id`. The script works in these steps:

1. It reads the rule files in `RULES`, in the order `rentfrontier.data` applies them. For each
   correction it reads the dataset of the version adding the line. A version's provenance file
   gives the dataset of the lines it adds, and from bedrooms-ad-v7 on, a version's file starts
   with its base rule's lines. It takes the row's ad and its recorded values from the dataset's
   `observations.jsonl`. A quarantine line gives its ad and month itself, the month as YYYY-MM
   or as its first day.
2. It gathers the evidence for each correction:
     - the ad's words, from the rule file, or Ben's own reading when the rule's line gives
       his name and the day;
     - the reads in `READS`, `PLANS` and `SIZES` that decided the row, with each read's second
       signal: a size the unit's ads state, another ad for the unit, a floor plan, or Ben's
       own review;
     - the unit's other ads in `DATASET`, the latest dataset. They back a set when more of them
       give the corrected value than give the recorded one;
     - for a size set, the unit's other ads with the same bedroom count and a size within 10%
       of the corrected one, or for a rule's line basis, the latest ad of each other unit of
       the line with that bedroom count and size.
   A stated size backs a bedroom set when it lies nearer the corrected count's median size in
   `DATASET` than the recorded count's median and each median between them. A size nearest a
   count past the corrected one still backs the set, as listers seldom understate bedrooms.
   Otherwise the importer keeps the size as a `read`, with the count it lies nearer to. Either
   item gives the importer's medians, as the reader compared the size with medians of its own.
3. It writes each exclude, and each set with backing, as a ledger line to
   `pipeline/ledger/NAME.ndjson`. It stops when NAME exists. It leaves out a correction when
     - an entry of the ledger came from the same rule file and line, as the rule versions keep
       their lines once written;
     - the latest entry for the same change, ad, and reason or field holds the same values and
       `when`, so the correction repeats it;
     - a retracted entry for the same change, ad, and reason or field holds the same values
       and `when`, so a retract stays in force over a rule version made before it.
   A later run after a new rule version thus adds only the new decisions.
4. It writes each set without backing to `config/reviews/ledger-held-NAME.jsonl`, with the
   counts of the unit's other ads, for a reader to look for backing. It leaves out a held set
   under the same rules as in step 3, and when an earlier held file lists the same values and
   `when` for the ad.
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
    "/data1/apartments/frontier/datasets/all-scraped-analysis-20261016-5f07157"
)
# The files of the latest version of each correction and quarantine rule of the chain.
RULES = [
    "config/corrections/bedrooms-ad-v3-20261008.jsonl",
    "config/corrections/bedrooms-ad-v4-20261015.jsonl",
    "config/corrections/bedrooms-ad-v5-20261015.jsonl",
    "config/corrections/bedrooms-ad-v6-20261015.jsonl",
    "config/corrections/bedrooms-ad-v9-20261016.jsonl",
    "config/corrections/baths-ad-v3-20261008.jsonl",
    "config/corrections/sqft-units-v1-20261015.jsonl",
    "config/reviews/quarantine-v33-20261016.jsonl",
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
STATED = re.compile(r"The unit's stated ([\d,]+) sq ft")
# A second signal from Ben's own review of a plan, a video or the unit's ads.
BEN = re.compile(r"\bby Ben\b")
# A rule line's evidence giving Ben's own reading and its day, as in "(Ben, 2026-10-16)",
# in place of the ad's words.
BEN_LINE = re.compile(r"\(Ben, \d{4}-\d{2}-\d{2}\)")


def lines(path):
    with open(REPO / path) as f:
        for number, text in enumerate(f, start=1):
            if text.strip():
                yield number, json.loads(text)


def quarantine(path):
    return Path(path).name.startswith("quarantine-")


def month(period):
    """Give a quarantine line's period as YYYY-MM, from YYYY-MM or the month's first day."""
    if not re.fullmatch(r"\d{4}-\d{2}(-01)?", period):
        raise SystemExit(f"the quarantine period {period!r} isn't a month")
    return period[:7]


def line_datasets(path):
    """Give the dataset of each line of the correction file at `path`, by line number.

    A version's provenance gives the dataset of the rows it adds, its last `rows` lines. From
    bedrooms-ad-v7 on, a version's file starts with its base rule's lines, and those take the
    datasets the base rule's provenance gives them."""
    provenance = REPO / path.replace(".jsonl", ".provenance.json")
    if not provenance.exists():
        raise SystemExit(f"{path} has no provenance file to give its dataset")
    given = json.loads(provenance.read_text())
    numbered = list(lines(path))
    start = len(numbered) - given.get("rows", len(numbered))
    if start < 0:
        raise SystemExit(f"{path} has fewer lines than its provenance file gives")
    found = {number: str(Path(given["dataset"])) for number, _ in numbered[start:]}
    if start:
        (base,) = (REPO / "config" / "corrections").glob(
            f"{given['base_rule']}-2*.jsonl"
        )
        base = str(base.relative_to(REPO))
        if list(lines(base)) != numbered[:start]:
            raise SystemExit(f"{path} doesn't start with the lines of {base}")
        found |= line_datasets(base)
    return found


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
        "building_id": "VARCHAR",
        "canonical_unit_url": "VARCHAR",
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
            SELECT audit_id, source_listing_id AS listing_id, building_id, unit_id,
                -- The line is the letters after the floor in the unit's label, as I in 14I.
                nullif(regexp_extract(canonical_unit_url, '/[0-9]*([a-z]+)$', 1), '') AS line,
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


def line_size(db, latest, row, corrected):
    """The latest ad in DATASET of each other unit of the row's line, with the row's bedroom
    count and a size within 10% of `corrected`."""
    return db.execute(
        """SELECT arg_max(listing_id, month) FROM obs
        WHERE dataset = ? AND building_id = ? AND line = ? AND unit_id <> ? AND bedrooms = ?
            AND abs(square_feet / ? - 1) <= 0.1
        GROUP BY unit_id ORDER BY 1""",
        [
            latest,
            row["building_id"],
            row["line"],
            row["unit_id"],
            row["bedrooms"],
            corrected,
        ],
    ).fetchall()


def medians(db, latest):
    """The median size of each bedroom count in DATASET."""
    return dict(
        db.execute(
            """SELECT bedrooms, median(square_feet) FROM obs
            WHERE dataset = ? AND square_feet > 0 AND bedrooms IS NOT NULL
            GROUP BY bedrooms""",
            [latest],
        ).fetchall()
    )


def signal(read, sizes, recorded):
    """The evidence item of a read's second signal, with `sizes` the median size of each
    bedroom count and `recorded` the row's bedroom count."""
    text = read.get("second_signal")
    if not text:
        return None
    if match := STATED.match(text):
        # The reader's own comparison used other medians, so the item gives the importer's.
        stated = float(match[1].replace(",", ""))
        corrected = read["bedrooms"]
        distance = {count: abs(size - stated) for count, size in sizes.items()}
        # The size has to rule out the recorded count and each count between it and the
        # corrected one. A size nearest a count past the corrected one still backs the set,
        # as listers seldom understate bedrooms.
        if recorded is None:
            rivals = [count for count in sizes if count != corrected]
        else:
            low, high = sorted((recorded, corrected))
            rivals = [
                count for count in sizes if low <= count <= high and count != corrected
            ]
        rival = min(rivals, key=distance.get, default=None)
        size = f"The unit's stated {stated:,.0f} sq ft"
        if corrected not in sizes:
            detail = (
                f"{size} backs no count of {corrected:g}, as no ad of the latest dataset "
                f"with {corrected:g} bedrooms states a size."
            )
        elif rival is None:
            detail = (
                f"{size} rules out no other count, as no ad of the latest dataset with the "
                "recorded count states a size."
            )
        elif distance[corrected] < distance[rival]:
            return {
                "kind": "stated_size",
                "square_feet": stated,
                "detail": (
                    f"{size} lies nearer the median {corrected:g}-bedroom size "
                    f"({sizes[corrected]:,.0f}) than the median {rival:g}-bedroom size "
                    f"({sizes[rival]:,.0f})."
                ),
            }
        else:
            detail = (
                f"{size} lies nearer the median {rival:g}-bedroom size "
                f"({sizes[rival]:,.0f}) than the median {corrected:g}-bedroom size "
                f"({sizes[corrected]:,.0f}), so it backs no count of {corrected:g}."
            )
        return {"kind": "read", "square_feet": stated, "detail": detail}
    if match := OTHER_AD.match(text):
        return {
            "kind": "other_ad",
            "listing_id": match[1],
            "listed": match[2],
            "detail": text,
        }
    if text.startswith("Floor plan"):
        return {"kind": "floor_plan", "detail": text}
    if BEN.search(text):
        return {"kind": "owner", "detail": text}
    return {"kind": "read", "detail": text}


def rule_evidence(text):
    """The evidence item for a bedroom or bath rule line's `evidence`: the ad's words, or Ben's
    own reading when the text gives his name and the day, as a floor plan item when he read a
    floor plan."""
    if not BEN_LINE.search(text):
        return {"kind": "ad_text", "quote": text}
    if "floor plan" in text.lower():
        return {"kind": "floor_plan", "detail": text}
    return {"kind": "owner", "detail": text}


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

    def slot(entry):
        return (
            entry["change"],
            entry["listing_id"],
            entry.get("reason") or entry.get("field"),
        )

    def key(entry):
        names = ("bedrooms", "full_baths", "half_baths", "square_feet")
        when = tuple(entry[f"when_{name}"] for name in ledger.WHEN)
        return (tuple(entry[name] for name in names), when, tuple(entry["when_keys"]))

    existing = ledger.read(sorted(LEDGER.glob("*.ndjson")))
    imported = {row["source"] for row in existing if row["source"]}
    retracts = {row["retracts"] for row in existing if row["change"] == "retract"}
    latest, retracted = {}, set()
    for row in existing:
        if row["change"] != "retract":
            latest[slot(row)] = key(row)
        if row["entry"] in retracts:
            retracted.add((slot(row), key(row)))

    sources = {path: line_datasets(path) for path in RULES if not quarantine(path)}
    datasets = sorted(
        {*(d for found in sources.values() for d in found.values()), str(DATASET)}
    )
    sources = {
        path: {number: datasets.index(d) for number, d in found.items()}
        for path, found in sources.items()
    }
    latest_dataset = datasets.index(str(DATASET))
    db = duckdb.connect(config={"memory_limit": "1500MB", "threads": 4})
    observations(db, datasets)
    sizes_of = medians(db, latest_dataset)
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

    def same_set(entry):
        return json.dumps(
            [entry["listing_id"], entry["set"], entry["when"]], sort_keys=True
        )

    # The sets of earlier held files, which a reader needs once.
    held_sets = {
        same_set(json.loads(text))
        for path in sorted(held_path.parent.glob("ledger-held-*.jsonl"))
        if path != held_path
        for text in path.read_text().splitlines()
    }
    texts, held, counts = [], [], collections.Counter()

    def add(rule, entry, details=None):
        """Write the entry, or hold a set without backing, unless it repeats the latest entry
        of its slot or a retracted one."""
        kinds = {item["kind"] for item in entry["evidence"]}
        hold = entry["change"] == "set" and not kinds & set(ledger.BACKING)
        # A held set parses with a placeholder item of a backing kind, only to find its slot
        # and key.
        placeholder = [{"kind": "owner", "detail": "placeholder"}] if hold else []
        parsed = ledger.parse(
            json.dumps({**entry, "evidence": entry["evidence"] + placeholder})
        )
        here = (slot(parsed), key(parsed))
        if latest.get(here[0]) == here[1] or here in retracted:
            counts[f"{rule}: repeats a ledger entry"] += 1
        elif hold and same_set(entry) in held_sets:
            counts[f"{rule}: repeats a held set"] += 1
        elif hold:
            held_sets.add(same_set(entry))
            held.append({**entry, **details})
            counts[f"{rule}: held"] += 1
        else:
            latest[here[0]] = here[1]
            texts.append(json.dumps(entry, sort_keys=True))
            counts[f"{rule}: {entry['change']}"] += 1

    for path in RULES:
        rule = Path(path).name.rsplit("-", 1)[0]
        for number, line in lines(path):
            source = f"{path}:{number}"
            if source in imported:
                counts[f"{rule}: in the ledger"] += 1
                continue
            if quarantine(path):
                action = line["action"]
                when = {"period": month(line["period"])}
                if action == "quarantine_bedrooms_unknown":
                    row = row_of(latest_dataset, line["audit_id"])
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
                add(rule, entry)
                continue

            row = row_of(sources[path][number], line["audit_id"])
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
                    if units := line_size(db, latest_dataset, row, line["corrected"]):
                        evidence.append(
                            {
                                "kind": "line_units",
                                "listings": [lid for (lid,) in units],
                                "detail": line["evidence"],
                            }
                        )
                elif backing := same_size(db, latest_dataset, row, line["corrected"]):
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
                evidence.append(rule_evidence(line["evidence"]))
                read = reads.get(line["audit_id"])
                if (
                    field == "bedrooms"
                    and read
                    and read["bedrooms"] == line["corrected"]
                ):
                    evidence.append(
                        {"kind": "read", "file": read["file"], "detail": read["reason"]}
                    )
                    if item := signal(read, sizes_of, row["bedrooms"]):
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
                    db, latest_dataset, row, field, values.get("bedrooms", values)
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
            add(
                rule,
                entry,
                {
                    "rule": rule,
                    "audit_id": line["audit_id"],
                    "unit_id": row["unit_id"],
                    "agree": len(agree),
                    "disagree": disagree,
                },
            )

    if texts:
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
