"""ledger.entries: each entry of the corrections ledger, checked against its rules.

The ledger is a folder of NDJSON files, `pipeline/ledger/*.ndjson` unless `PIPELINE_LEDGER`
names another folder. A person or a script writes a new file for each batch of decisions, one
decision a line, with a name sorting after the files already merged. A file stays as it is once
merged to master, and `tests/test_ledger.py` checks that against the merge base. A later
`retract` line undoes a decision. This model reads every file with `read`, and `ledger.status`
checks each entry against the kept rows.

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
- `evidence`: a list of items, each with a `kind` and its details. Kinds, with the details
  each needs:
    - `ad_text`: the ad's own words, as a `quote`.
    - `other_ad`: another ad for the same unit, as its `listing_id`, or its ads as `listings`,
      with a `detail`.
    - `stated_size`: a size an ad states for the unit, in a `detail`.
    - `floor_plan`: a plan of the unit, as the `plan` file or a `detail`.
    - `line_units`: units of the same line in the building, as their ads' `listings`, with a
      `detail`.
    - `city_record`: a city record, such as PLUTO or a certificate of occupancy, in a `detail`.
    - `read`: a reviewer's reading of the ads, with what they found in a `detail`.
    - `owner`: Ben's own reading, with its date, in a `detail`.

  An item may hold more keys, such as the `file` of a read or the `quote` of another ad.
- `decided`: the day of the decision, as YYYY-MM-DD.
- `source` (optional): the file and line the decision came from.
- `note` (optional): anything else.

An entry's ID is the first 16 hex digits of the SHA-256 of its line, without the line break.

`read` stops with `LedgerError`, naming the file and line, when an entry breaks one of these
rules:

1. Every entry has evidence, and each item gives the details its kind needs. The ads of an
   `other_ad` or `line_units` item are other ads than the entry's own.
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
import math
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
# The fields with whole values. Bedrooms stay DOUBLE, the type of analysis.kept's column.
WHOLE = ("bedrooms", *INTEGERS)
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
# The text an item of each kind gives, as one of these keys.
TEXT = {"ad_text": ("quote",), "floor_plan": ("plan", "detail")}
KEYS = {
    "exclude": {"change", "listing_id", "reason", "when", "evidence", "decided"},
    "set": {"change", "listing_id", "set", "when", "evidence", "decided"},
    "retract": {"change", "entry", "evidence", "decided"},
}
OPTIONAL = {
    "exclude": {"when", "source", "note"},
    "set": {"when", "source", "note"},
    "retract": {"source", "note"},
}
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


def number(value, key):
    field = key.removeprefix("when.")
    try:
        # An integer too large for a float overflows here.
        finite = math.isfinite(value) and value >= 0
    except (TypeError, OverflowError):
        finite = False
    if isinstance(value, bool) or not finite:
        raise LedgerError(f"{key} takes a finite number of at least 0, not {value!r}")
    if field in WHOLE and value != int(value):
        raise LedgerError(f"{key} takes a whole number, not {value!r}")
    # The rows pass through a data frame, where a column with missing values holds floats. From
    # 2**53 up, floats skip whole numbers, so a float of 2**53 may come from 2**53 + 1.
    if field in WHOLE and value >= 2**53:
        raise LedgerError(f"{key} takes a number below 2**53, not {value!r}")
    return int(value) if field in INTEGERS else float(value)


def is_ad_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]+", value) is not None


def check_item(item, listing_id):
    """Stop unless the evidence item `item` gives the details its kind needs, for the entry of
    the ad `listing_id`."""
    if not isinstance(item, dict) or item.get("kind") not in KINDS:
        raise LedgerError(f"each item of evidence has a kind of {', '.join(KINDS)}")
    kind = item["kind"]
    keys = TEXT.get(kind, ("detail",))
    if not any(isinstance(item.get(key), str) and item[key].strip() for key in keys):
        raise LedgerError(f"{kind} evidence gives its {' or '.join(keys)}")
    if kind not in ("other_ad", "line_units"):
        return
    ads = item.get("listings", [])
    if kind == "other_ad" and "listing_id" in item:
        ads = [item["listing_id"], *ads] if isinstance(ads, list) else ads
    if not isinstance(ads, list) or not ads or not all(map(is_ad_id, ads)):
        names = "listing_id or listings" if kind == "other_ad" else "listings"
        raise LedgerError(f"{kind} evidence gives its ads' IDs as {names}")
    if listing_id in ads:
        raise LedgerError(f"{kind} evidence gives other ads than the entry's own")


def when_value(key, value):
    if value is None and key != "period":
        return None
    if key == "period":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
            raise LedgerError(f"when.period takes a month as YYYY-MM, not {value!r}")
        try:
            date.fromisoformat(f"{value}-01")
        except ValueError:
            raise LedgerError(f"when.period is no month: {value!r}") from None
        return value
    return number(value, f"when.{key}")


def parse(text: str) -> dict:
    """The columns of ledger.entries for the line `text`, checked against rules 1 and 2."""

    def refuse(constant):
        raise LedgerError(f"{constant} is no number of the ledger")

    try:
        line = json.loads(text, parse_constant=refuse)
    except json.JSONDecodeError as error:
        raise LedgerError(f"not JSON: {error}") from None
    if not isinstance(line, dict):
        raise LedgerError("a line holds a JSON object")
    change = line.get("change")
    if change not in CHANGES:
        raise LedgerError(f"change is one of {', '.join(CHANGES)}, not {change!r}")
    named = f"{'an' if change == 'exclude' else 'a'} {change}"
    if missing := sorted(KEYS[change] - OPTIONAL[change] - line.keys()):
        raise LedgerError(f"{named} needs {', '.join(missing)}")
    if extra := sorted(line.keys() - KEYS[change] - OPTIONAL[change]):
        raise LedgerError(f"{named} takes no {', '.join(extra)}")
    row = dict.fromkeys(COLUMNS)
    row["change"] = change

    evidence = line["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise LedgerError("evidence is a list of at least one item")
    for item in evidence:
        check_item(item, line.get("listing_id"))
    row["kinds"] = sorted({item["kind"] for item in evidence})
    row["evidence"] = json.dumps(evidence, sort_keys=True)
    decided = line["decided"]
    try:
        if not isinstance(decided, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", decided
        ):
            raise ValueError
        row["decided"] = date.fromisoformat(decided)
    except ValueError:
        raise LedgerError(f"decided is a day as YYYY-MM-DD, not {decided!r}") from None
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

    if not is_ad_id(line["listing_id"]):
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
        row[key] = number(value, key)
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
        # JSON allows U+2028 inside a string, where splitlines would cut the line.
        lines = path.read_text(encoding="utf-8").split("\n")
        for number_, text in enumerate(lines, start=1):
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
