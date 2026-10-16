"""ledger.entries: each entry of the corrections ledger, checked against its rules.

The ledger is a folder of NDJSON files, `pipeline/ledger/*.ndjson` unless `PIPELINE_LEDGER`
names another folder. A person or a script adds a file for each batch of decisions and appends
lines to it, one decision a line. Lines already merged to master stay as they are, which
`tests/test_ledger.py` checks against the merge base. A decision is undone by a later `retract`
line. This model reads every file with `read`, and `ledger.status` checks each entry against
the kept rows.

A line holds one JSON object with these keys:

- `change`: `exclude` drops the ad's row, `set` gives the row new values, and `retract` undoes
  an earlier entry.
- `listing_id`: the ad, for an exclude or a set.
- `reason`: a short label for an exclude, such as `nonresidential`.
- `set`: the new values of one field of the row, as `{"bedrooms": 1}`, `{"full_baths": 2,
  "half_baths": 0}` or `{"square_feet": 600}`.
- `entry`: for a retract, the ID of the entry it undoes.
- `when` (optional for an exclude): the row's values the decision rests on, as `{"period":
  "2019-08", "bedrooms": 0}`, with the month as YYYY-MM and `null` for a value the row lacks.
  A set gives the recorded value of each field it sets. While each value matches the row, the
  entry applies. Otherwise it goes stale, and `ledger.status` lists it.
- `evidence`: a list of items, each with a `kind` and its details, such as a `quote`, a
  `listing_id` or a `detail`. Kinds:
    - `ad_text`: the ad's own words.
    - `other_ad`: another ad for the same unit.
    - `stated_size`: a size an ad states for the unit.
    - `floor_plan`: a plan of the unit.
    - `line_units`: units of the same line in the building.
    - `city_record`: a city record, such as PLUTO or a certificate of occupancy.
    - `read`: a reviewer's reading of the ads, with what they found.
    - `owner`: Ben's own reading, with its date.
- `decided`: the day of the decision, as YYYY-MM-DD.
- `source` (optional): the file and line the decision came from.
- `note` (optional): anything else.

An entry's ID is the first 16 hex digits of the SHA-256 of its line, without the line break.

`read` stops with `LedgerError`, naming the file and line, when an entry breaks one of these
rules:

1. Every entry has evidence.
2. A set rests on evidence beyond the ad's own words: at least one item of a backing kind,
   `other_ad`, `stated_size`, `floor_plan`, `line_units` or `owner`. Ad text or a price alone
   does not back a change of a coded field.
3. A retract names an earlier exclude or set, and no other retract names it too.
4. No line repeats an earlier line.

`config.py` lists the ledger's files with their SHA-256 in the variable `ledger`, so a new or
changed file gives the model a new fingerprint. The model reads the files again when it runs and
stops when one differs from its hash, as a file edited after the project loaded would. The
parser lives in this file, so the model's fingerprint covers the rules too.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
from sqlglot import exp
from sqlmesh import ExecutionContext, model

CHANGES = ("exclude", "set", "retract")
# The fields a set changes together, under the name ledger.status gives them.
FIELDS = {
    "bedrooms": ("bedrooms",),
    "baths": ("full_baths", "half_baths"),
    "square_feet": ("square_feet",),
}
WHEN = ("period", "bedrooms", "full_baths", "half_baths", "square_feet")
INTEGERS = ("full_baths", "half_baths")
KINDS = (
    "ad_text",
    "other_ad",
    "stated_size",
    "floor_plan",
    "line_units",
    "city_record",
    "read",
    "owner",
)
BACKING = ("other_ad", "stated_size", "floor_plan", "line_units", "owner")
KEYS = {
    "exclude": {"change", "listing_id", "reason", "when", "evidence", "decided"},
    "set": {"change", "listing_id", "set", "when", "evidence", "decided"},
    "retract": {"change", "entry", "evidence", "decided"},
}
OPTIONAL = {"when", "source", "note"}
# The columns of ledger.entries, in order, with their DuckDB types.
COLUMNS = {
    "entry": "VARCHAR",
    "file": "VARCHAR",
    "line": "INTEGER",
    "seq": "INTEGER",
    "listing_id": "VARCHAR",
    "change": "VARCHAR",
    "reason": "VARCHAR",
    "field": "VARCHAR",
    "bedrooms": "DOUBLE",
    "full_baths": "BIGINT",
    "half_baths": "BIGINT",
    "square_feet": "DOUBLE",
    "retracts": "VARCHAR",
    **{f"when_{key}": "VARCHAR" if key == "period" else "DOUBLE" for key in WHEN},
    "when_keys": "VARCHAR[]",
    "kinds": "VARCHAR[]",
    "evidence": "VARCHAR",
    "decided": "DATE",
    "source": "VARCHAR",
    "note": "VARCHAR",
}


class LedgerError(ValueError):
    pass


def entry_id(line: str) -> str:
    return hashlib.sha256(line.encode()).hexdigest()[:16]


def number(value, key, integer=False):
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise LedgerError(f"{key} takes a number of at least 0, not {value!r}")
    if integer and value != int(value):
        raise LedgerError(f"{key} takes a whole number, not {value!r}")
    return int(value) if integer else float(value)


def when_value(key, value):
    if value is None and key != "period":
        return None
    if key == "period":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
            raise LedgerError(f"when.period takes a month as YYYY-MM, not {value!r}")
        date.fromisoformat(f"{value}-01")
        return value
    return number(value, f"when.{key}", key in INTEGERS)


def parse(text: str) -> dict:
    """The columns of ledger.entries for the line `text`, checked against rules 1 and 2."""
    try:
        line = json.loads(text)
    except json.JSONDecodeError as error:
        raise LedgerError(f"not JSON: {error}") from None
    if not isinstance(line, dict):
        raise LedgerError("a line holds a JSON object")
    change = line.get("change")
    if change not in CHANGES:
        raise LedgerError(f"change is one of {', '.join(CHANGES)}, not {change!r}")
    named = f"{'an' if change == 'exclude' else 'a'} {change}"
    if missing := sorted(KEYS[change] - OPTIONAL - line.keys()):
        raise LedgerError(f"{named} needs {', '.join(missing)}")
    if extra := sorted(line.keys() - KEYS[change] - OPTIONAL):
        raise LedgerError(f"{named} takes no {', '.join(extra)}")
    row = dict.fromkeys(COLUMNS)
    row["change"] = change

    evidence = line["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise LedgerError("evidence is a list of at least one item")
    for item in evidence:
        if not isinstance(item, dict) or item.get("kind") not in KINDS:
            raise LedgerError(f"each item of evidence has a kind of {', '.join(KINDS)}")
    row["kinds"] = sorted({item["kind"] for item in evidence})
    row["evidence"] = json.dumps(evidence, sort_keys=True)
    try:
        row["decided"] = date.fromisoformat(line["decided"])
    except (TypeError, ValueError):
        raise LedgerError(
            f"decided is a day as YYYY-MM-DD, not {line['decided']!r}"
        ) from None
    for key in ("source", "note"):
        if key in line and not isinstance(line[key], str):
            raise LedgerError(f"{key} is text")
        row[key] = line.get(key)

    if change == "retract":
        if not isinstance(line["entry"], str) or not re.fullmatch(
            r"[0-9a-f]{16}", line["entry"]
        ):
            raise LedgerError("entry is the 16 hex digits of an entry's ID")
        row["retracts"] = line["entry"]
        return row

    if not isinstance(line["listing_id"], str) or not line["listing_id"].isdigit():
        raise LedgerError("listing_id is the ad's ID, written as a string of digits")
    row["listing_id"] = line["listing_id"]
    when = line.get("when", {})
    if not isinstance(when, dict) or set(when) - set(WHEN):
        raise LedgerError(f"when maps some of {', '.join(WHEN)} to values")
    for key, value in when.items():
        row[f"when_{key}"] = when_value(key, value)
    row["when_keys"] = sorted(when)

    if change == "exclude":
        if not isinstance(line["reason"], str) or not line["reason"]:
            raise LedgerError("an exclude gives its reason")
        row["reason"] = line["reason"]
        return row

    values = line["set"]
    field = isinstance(values, dict) and next(
        (name for name, keys in FIELDS.items() if set(keys) == set(values)), None
    )
    if not field:
        groups = "; ".join(" and ".join(keys) for keys in FIELDS.values())
        raise LedgerError(f"a set gives one of: {groups}")
    for key, value in values.items():
        row[key] = number(value, key, key in INTEGERS)
        if row[key] == 0 and key == "square_feet":
            raise LedgerError("square_feet takes a size above 0")
        if key not in when:
            raise LedgerError(f"a set gives the recorded {key} in when")
    row["field"] = field
    if not set(row["kinds"]) & set(BACKING):
        raise LedgerError(
            f"a set needs evidence of a backing kind ({', '.join(BACKING)}), "
            "beyond the ad's own words"
        )
    return row


def read(paths) -> list[dict]:
    """Each entry of the files `paths`, in order of file name and line, checked against the
    rules. Blank lines are skipped."""
    rows, seen = [], {}
    for path in sorted(map(Path, paths), key=lambda p: p.name):
        for number_, text in enumerate(path.read_text().splitlines(), start=1):
            if not text.strip():
                continue
            where = f"{path.name}:{number_}"
            try:
                row = parse(text)
            except LedgerError as error:
                raise LedgerError(f"{where}: {error}") from None
            entry = entry_id(text)
            if entry in seen:
                raise LedgerError(f"{where}: repeats {seen[entry]['where']}")
            row.update(entry=entry, file=path.name, line=number_, seq=len(rows) + 1)
            if row["change"] == "retract":
                target = seen.get(row["retracts"])
                if target is None or target["change"] == "retract":
                    raise LedgerError(
                        f"{where}: retracts {row['retracts']}, which is no earlier "
                        "exclude or set"
                    )
                if target["retracted"]:
                    raise LedgerError(
                        f"{where}: {row['retracts']} is retracted at {target['retracted']}"
                    )
                target["retracted"] = where
                row["listing_id"] = target["listing_id"]
            seen[entry] = {
                "where": where,
                "change": row["change"],
                "listing_id": row["listing_id"],
                "retracted": None,
            }
            rows.append(row)
    return rows


@model(
    "ledger.entries",
    kind="FULL",
    columns=COLUMNS,
    grain="entry",
    audits=[
        ("unique_values", {"columns": [exp.column("entry")]}),
        (
            "not_null",
            {
                "columns": [
                    exp.column(name)
                    for name in ("entry", "file", "line", "seq", "listing_id", "change")
                ]
            },
        ),
    ],
    description="Each entry of the corrections ledger, checked against its rules.",
)
def execute(context: ExecutionContext, start, end, execution_time, **kwargs):
    listed = context.var("ledger")
    for path, digest in listed.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise LedgerError(f"{path} changed after the project loaded")
    rows = read(listed)
    if rows:
        yield pd.DataFrame(rows, columns=list(COLUMNS))
