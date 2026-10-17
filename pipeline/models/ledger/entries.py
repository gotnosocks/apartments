"""ledger.entries and ledger.unit_entries: each entry of the corrections ledger and of the unit
ledger, checked against its ledger's rules.

The corrections ledger is a folder of NDJSON files, `pipeline/ledger/*.ndjson`, or the folder
`PIPELINE_LEDGER` gives. A person or a script writes a new file for each batch of decisions, one
decision a line, with a name sorting after the files already merged. A file stays as it is once
merged to master, and `tests/test_ledger.py` checks that against the merge base. A later
`retract` line undoes a decision. ledger.entries reads every file with `read`, and
`ledger.status` checks each entry against the kept rows.

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

The unit ledger is a second folder of NDJSON files, `units` inside the ledger's folder. It moves
ads to another unit or building where ads.identity placed them wrong. Its files follow the
corrections ledger's rules for names, merges and retracts, and the folder may be missing while
it holds no entries. ledger.unit_entries reads every file with `read_units`,
`ledger.unit_status` checks each entry against the ads and buildings, and `ads.placed` applies
the live entries before the unit-month check.

A line of the unit ledger holds one JSON object with these keys:

- `change`:
    - `join_units` puts the ads of two or more unit pages of a building into one unit.
    - `split_unit` takes some ads of a unit page into a unit of their own.
    - `move_building` gives a building's ads another building.
    - `retract` undoes an earlier entry of the unit ledger.
- `building`: the building's slug, as the ads' unit pages give it before any move.
- `units`: for a join, the slugs of its units, as their pages end.
- `unit`: for a split, the slug of the unit its ads leave.
- `listings`: for a split, the IDs of its ads. The new unit's ID ends with the first of them,
  so their order matters.
- `to`: for a move, the slug of the building its ads join.
- `entry`, `evidence`, `decided`, `source` and `note`: as in the corrections ledger. The
  evidence kinds are the same.

`read_units` stops with `LedgerError`, giving the file and line, when an entry breaks one of
these rules:

1. Every entry has evidence, and each item gives the details its kind needs. A split's own ads
   are its listings, so an `other_ad` or `line_units` item cites other ads.
2. A join, split or move rests on at least one item of a backing kind: those of rule 2 above,
   or `city_record`.
3. Among the entries still in force, a page takes part in one join at most, an ad in one split
   and a building in one move. A building with ads moving to it stays where it is, and no ads
   move to a building on the move.
4. A retract gives the ID of an earlier entry of the unit ledger, and no other retract gives it
   too. The retracted entry's pages, ads or building are free for later entries.
5. No line repeats an earlier line.

`config.py` lists each ledger's files with their SHA-256, the corrections ledger's in the
variable `ledger` and the unit ledger's in `ledger_units`, so a new or changed file gives its
model a new fingerprint. Each model reads its files again when it runs and stops when one
differs from its hash, as a file edited after the project loaded would. The parsers live in
this file, so the models' fingerprints cover the rules too.
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
# SQLMesh fingerprints the model by the text of the values it reads, and a set's order changes
# with the process's hash seed, so the keys of a change are tuples.
KEYS = {
    "exclude": ("change", "listing_id", "reason", "when", "evidence", "decided"),
    "set": ("change", "listing_id", "set", "when", "evidence", "decided"),
    "retract": ("change", "entry", "evidence", "decided"),
}
OPTIONAL = {
    "exclude": ("when", "source", "note"),
    "set": ("when", "source", "note"),
    "retract": ("source", "note"),
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


def load_line(text, changes, keys, optional):
    """The JSON object of the line `text`, with its change among `changes` and with the keys
    `keys` and `optional` give for that change."""

    def refuse(constant):
        raise LedgerError(f"{constant} is no number of the ledger")

    try:
        line = json.loads(text, parse_constant=refuse)
    except json.JSONDecodeError as error:
        raise LedgerError(f"not JSON: {error}") from None
    if not isinstance(line, dict):
        raise LedgerError("a line holds a JSON object")
    change = line.get("change")
    if change not in changes:
        raise LedgerError(f"change is one of {', '.join(changes)}, not {change!r}")
    named = f"{'an' if change == 'exclude' else 'a'} {change}"
    if missing := sorted(set(keys[change]) - set(optional[change]) - line.keys()):
        raise LedgerError(f"{named} needs {', '.join(missing)}")
    if extra := sorted(line.keys() - set(keys[change]) - set(optional[change])):
        raise LedgerError(f"{named} takes no {', '.join(extra)}")
    return line


def read_evidence(line, row, ads):
    """Fill the row's evidence, day and notes from `line`. Each item of evidence is checked for
    each ad of `ads`, the ads the entry changes, or None for an entry of no single ad."""
    evidence = line["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise LedgerError("evidence is a list of at least one item")
    for item in evidence:
        for ad in ads:
            check_item(item, ad)
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


def read_retract(line, row):
    if not isinstance(line["entry"], str) or not re.fullmatch(
        r"[0-9a-f]{16}", line["entry"]
    ):
        raise LedgerError("entry is the 16 hex digits of an entry's ID")
    row["retracts"] = line["entry"]


def parse(text: str) -> dict:
    """The columns of ledger.entries for the line `text`, checked against rules 1 and 2."""
    line = load_line(text, CHANGES, KEYS, OPTIONAL)
    change = line["change"]
    row = dict.fromkeys(COLUMNS)
    row["change"] = change
    read_evidence(line, row, [line.get("listing_id")])
    if change == "retract":
        read_retract(line, row)
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


def lines(paths):
    """Each line of the files `paths` with text, in order of file name and line, with its place
    as `file:line`."""
    for path in sorted(map(Path, paths), key=lambda p: p.name):
        # JSON allows U+2028 inside a string, where splitlines would cut the line.
        texts = path.read_text(encoding="utf-8").split("\n")
        for number_, text in enumerate(texts, start=1):
            if text.strip():
                yield path, number_, text


def read(paths) -> list[dict]:
    """Each entry of the files `paths`, in order of file name and line, checked against the
    rules. Blank lines are skipped."""
    rows, seen = [], {}
    for path, number_, text in lines(paths):
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
            target = retracted(seen, row, where, "exclude or set")
            row["listing_id"] = target["listing_id"]
        seen[entry] = {
            "where": where,
            "change": row["change"],
            "listing_id": row["listing_id"],
            "retracted": None,
        }
        rows.append(row)
    return rows


def retracted(seen, row, where, kinds):
    """The earlier entry the retract `row` undoes, marked as retracted at `where`."""
    target = seen.get(row["retracts"])
    if target is None or target["change"] == "retract":
        raise LedgerError(
            f"{where}: retracts {row['retracts']}, which is no earlier {kinds}"
        )
    if target["retracted"]:
        raise LedgerError(
            f"{where}: {row['retracts']} is retracted at {target['retracted']}"
        )
    target["retracted"] = where
    return target


# The unit ledger, `units/*.ndjson` inside the ledger's folder. Its entries place ads in units
# and buildings, keyed on the unit's page or the building's slug rather than on one ad.
UNIT_CHANGES = ("join_units", "split_unit", "move_building", "retract")
UNIT_KEYS = {
    "join_units": ("change", "building", "units", "evidence", "decided"),
    "split_unit": ("change", "building", "unit", "listings", "evidence", "decided"),
    "move_building": ("change", "building", "to", "evidence", "decided"),
    "retract": ("change", "entry", "evidence", "decided"),
}
UNIT_OPTIONAL = dict.fromkeys(UNIT_CHANGES, ("source", "note"))
# A city record backs a move of a building, as the lot registry backs 97 Horatio Street's.
UNIT_BACKING = (*BACKING, "city_record")
# The page of a unit, from its building's slug and its own, as ads.identity builds it.
PAGE = "https://streeteasy.com/building/{}/{}"
UNIT_COLUMNS = {
    "entry": "VARCHAR",
    "file": "VARCHAR",
    "line": "INTEGER",
    "seq": "INTEGER",
    "change": "VARCHAR",
    "building": "VARCHAR",
    "pages": "VARCHAR[]",
    "listings": "VARCHAR[]",
    "to_building": "VARCHAR",
    "retracts": "VARCHAR",
    "kinds": "VARCHAR[]",
    "evidence": "VARCHAR",
    "decided": "DATE",
    "source": "VARCHAR",
    "note": "VARCHAR",
}


def slug(value, key):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_-]+", value):
        raise LedgerError(
            f"{key} is a slug of lowercase letters, digits, '-' and '_', not {value!r}"
        )
    return value


def parse_unit(text: str) -> dict:
    """The columns of ledger.unit_entries for the line `text`, checked against the rules of
    a single line."""
    line = load_line(text, UNIT_CHANGES, UNIT_KEYS, UNIT_OPTIONAL)
    change = line["change"]
    row = dict.fromkeys(UNIT_COLUMNS)
    row["change"] = change
    ads = [None]
    if change == "retract":
        read_evidence(line, row, ads)
        read_retract(line, row)
        return row
    building = row["building"] = slug(line["building"], "building")
    if change == "join_units":
        units = line["units"]
        if not isinstance(units, list) or len(units) < 2:
            raise LedgerError("a join_units gives at least two units")
        units = [slug(unit, "each unit") for unit in units]
        if len(set(units)) < len(units):
            raise LedgerError("a join_units gives each unit once")
        row["pages"] = sorted(PAGE.format(building, unit) for unit in units)
    elif change == "split_unit":
        row["pages"] = [PAGE.format(building, slug(line["unit"], "unit"))]
        ads = line["listings"]
        if not isinstance(ads, list) or not ads or not all(map(is_ad_id, ads)):
            raise LedgerError("a split_unit gives its ads' IDs as listings")
        if len(set(ads)) < len(ads):
            raise LedgerError("a split_unit gives each ad once")
        row["listings"] = ads
    else:
        row["to_building"] = slug(line["to"], "to")
        if row["to_building"] == building:
            raise LedgerError("a move_building moves a building to another")
    read_evidence(line, row, ads)
    if not set(row["kinds"]) & set(UNIT_BACKING):
        raise LedgerError(
            f"a {change} needs evidence of a backing kind ({', '.join(UNIT_BACKING)}), "
            "beyond the ad's own words"
        )
    return row


def claims(row):
    """What the entry `row` takes for itself: the pages of a join, the ads of a split, the
    building a move moves."""
    if row["change"] == "join_units":
        return [("page", page) for page in row["pages"]]
    if row["change"] == "split_unit":
        return [("ad", ad) for ad in row["listings"]]
    return [("moved", row["building"])]


CLAIMED = {
    "page": "the page {} is in the join at {}",
    "ad": "ad {} is in the split at {}",
    "moved": "{} moves at {}",
}


def read_units(paths) -> list[dict]:
    """Each entry of the unit ledger's files `paths`, in order of file name and line, checked
    against the rules. Blank lines are skipped."""
    rows, seen = [], {}
    # The claims of the entries not retracted, and the buildings they move to.
    taken, targets = {}, {}
    for path, number_, text in lines(paths):
        where = f"{path.name}:{number_}"
        try:
            row = parse_unit(text)
        except LedgerError as error:
            raise LedgerError(f"{where}: {error}") from None
        entry = entry_id(text)
        if entry in seen:
            raise LedgerError(f"{where}: repeats {seen[entry]['where']}")
        row.update(entry=entry, file=path.name, line=number_, seq=len(rows) + 1)
        if row["change"] == "retract":
            target = retracted(seen, row, where, "unit entry")
            row["building"] = target["building"]
            for claim in target["claims"]:
                del taken[claim]
            if target["to"]:
                targets[target["to"]].remove(target["where"])
            mine, to = [], None
        else:
            mine, to = claims(row), row["to_building"]
            for kind, key in mine:
                if (kind, key) in taken:
                    raise LedgerError(
                        f"{where}: {CLAIMED[kind].format(key, taken[kind, key])}"
                    )
            if row["change"] == "move_building":
                if targets.get(row["building"]):
                    raise LedgerError(
                        f"{where}: {row['building']} takes the move at "
                        f"{targets[row['building']][0]}, so it stays where it is"
                    )
                if ("moved", to) in taken:
                    raise LedgerError(
                        f"{where}: {to} moves at {taken['moved', to]}, so nothing moves to it"
                    )
                targets.setdefault(to, []).append(where)
            taken |= dict.fromkeys(mine, where)
        seen[entry] = {
            "where": where,
            "change": row["change"],
            "building": row["building"],
            "claims": mine,
            "to": to,
            "retracted": None,
        }
        rows.append(row)
    return rows


def unchanged(listed):
    """Stop when a file of `listed`, the files with their SHA-256, changed after the project
    loaded."""
    for path, digest in listed.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise LedgerError(f"{path} changed after the project loaded")


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
    unchanged(listed)
    rows = read(listed)
    if rows:
        yield pd.DataFrame(rows, columns=list(COLUMNS))


@model(
    "ledger.unit_entries",
    kind="FULL",
    columns=UNIT_COLUMNS,
    grain="entry",
    audits=[
        ("unique_values", {"columns": [exp.column("entry")]}),
        (
            "not_null",
            {
                "columns": [
                    exp.column(name)
                    for name in ("entry", "file", "line", "seq", "change", "building")
                ]
            },
        ),
    ],
    description="Each entry of the unit ledger, checked against its rules.",
)
def execute_units(context: ExecutionContext, start, end, execution_time, **kwargs):
    listed = context.var("ledger_units")
    unchanged(listed)
    rows = read_units(listed)
    if rows:
        yield pd.DataFrame(rows, columns=list(UNIT_COLUMNS))
