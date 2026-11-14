"""Write a B0 dataset with rewritten text flags for income-restricted and shared housing.

    python -m rentfrontier.b0textflags SRC OUT

L1 reads three flags that `b0data` sets from each listing's description with the patterns in
`b0data.TEXT_FLAGS`: `income_restricted`, `shared_space` and `rent_stabilized`. On 2026-11-13
Sonnet and Haiku readers judged 335 descriptions of L1's dataset, drawn by which patterns mark
them (`docs/notes/text-flags-2026-11-13.md`):

- All 20 ads marked income-restricted by the old flag alone quote a fee schedule ("optional
  for income restricted units"), and all 25 marked by `b0income.INCOME` alone are
  income-restricted. A few the readers called income-restricted escape both: "requires
  approval by the state agency HDC", "income caps", a table of maximum incomes by household
  size.
- 19 of the 20 ads the old `shared_space` flag marks through "roommate" are whole apartments
  ("perfect for roommates", "we can help you find roommates on Nooklyn"). The real shares are
  SRO rooms, studios with a bathroom in the hall or shared with other tenants, and rooms for
  rent in a shared apartment.
- All 30 ads with the old `rent_stabilized` flag are stabilized, and the misses are a few
  misspellings, so I leave that flag as it is.

So I add two columns and leave every column of SRC as it was:

- `income_restricted_v2`: `INCOME_V2`, which is `b0income.INCOME` with the phrases above and
  without an agent's name it took for "AMI". On 2026-11-14 a Sonnet reader found a
  stabilized ad with "no income restrictions" among the rows it marked
  (`docs/notes/income-flag-2026-11-14.md`), so `income_marked` passes over a match with
  NEGATION just before it, and a description keeps its mark only through another match.
- `shared_space_v2`: `SHARED_V2`, written from the readers' quotes.

On the rows `income_restricted_v2` marks I also read the program's terms, as TERMS:

- `ami_pct_text`: the AMI percentage the ad gives its unit, from `ami_tier`. An ad stating
  several percentages gets the one it ties to its unit ("this unit is at 130% AMI"), or NaN.
- `ami_tiers_text`: how many different AMI percentages the ad states.
- `income_min_text` and `income_max_text`: the household income band the ad states, from
  `income_band`. With a table by household size the maximum comes from its first line,
  usually a single person. A program sets the minimum income from the rent, so the minimum
  carries the ask itself and a fit must not read it.

The other rows get NaN, 0, NaN and NaN. All of these stay text features added beside the
coded fields, since ad text never overrides a coded field (Ben, 2026-10-04).

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256) a row group at a time. For each listing of SRC I keep its latest record,
by the later of `collected_at` and `last_collected_at`, as `b0data` picks the record for its
text flags, and I skip a record with neither time, as `b0data`'s `arg_max` does. I match the
patterns on the description as `cautions.plain` leaves it. A listing whose latest record has
no description longer than `b0data.MIN_DESCRIPTION` characters gets false in both columns, as
do listings missing from the records.

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with the two flags and TERMS added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `textflags` entry giving
  SRC's path and rows SHA-256, the patterns and the negation, the listings read, the rows
  whose listing has a description, for each flag the rows marked and the rows it gains and
  loses against the old flag, and for TERMS their patterns and the rows each one is set on.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import cautions
from .b0data import MIN_DESCRIPTION, sha256
from .b0income import INCOME

# INCOME's "ami", but not in the name of the agent Jonathan Ben-Ami, who lists in 22 ads.
_AMI = r"(?<!mon )(?<!bel )\bami\b"
assert _AMI in INCOME.pattern
# Matched on the text as `cautions.plain` leaves it, like INCOME.
INCOME_V2 = re.compile(
    INCOME.pattern.replace(_AMI, r"(?<!mon )(?<!bel )(?<!ben-)(?<!ben )\bami\b")
    # The state agency that finances income-restricted rentals.
    + r"|\bhdc\b"
    + r"|income caps?\b"
    # A table of income limits by household size ("maximum for 2 hh", "1 person $99,086").
    + r"|max(?:imum)?\.? (?:income )?for (?:a )?[1-9] ?(?:person|people|persons|hh|household)"
    + r"|\b[1-9] ?(?:person|people|persons|ppl|hh|household)s?(?: household)?:? ?-? ?\$ ?\d{2,3},?\d{3}"
    + r"|is an affordable unit"
)

_FACILITY = r"(?:bath|bathroom|kitchen|toilet)s?"
# People outside the renter's household. Roommates are left out, since "shared with your
# roommate" is how whole apartments for roommates are sold.
_OTHERS = (
    r"(?:neighbou?rs?|tenants?|persons?|people|residents?|studios?|units?|apartments?"
    r"|housemates?|occupants?)"
)
SHARED_V2 = re.compile(
    # An SRO room, unless the building was converted from one.
    r"(?<!former )(?<!converted )(?<!ex-)(?<!ex )\bsro\b|single[- ]room[- ]occupancy"
    # A bathroom or kitchen shared with other tenants, down the hall or on each floor.
    rf"|{_FACILITY} (?:is |are )?shared (?:with|between|among) (?:\w+ ){{0,2}}{_OTHERS}\b"
    rf"|shared {_FACILITY} (?:with|between|among) (?:\w+ ){{0,2}}{_OTHERS}\b"
    rf"|shared {_FACILITY} (?:(?:is |are )?(?:located )?(?:in|down|across|on) (?:the )?hall"
    r"|one door down)"
    rf"|(?<!living )(?<!dining )\b(?:studio|room|unit|sro|efficiency)s? (?:with|w/|has|have"
    rf"|features) (?:a |an )?shared {_FACILITY}"
    rf"|(?:each|every) floor (?:has|have|features|shares) (?:a |an )?(?:[\w-]+,? ){{0,2}}"
    rf"(?:shared|communal) {_FACILITY}"
    # A room for rent in a shared home.
    r"|(?:this|our|my|in a|in an) shared (?:apartment|apt|house|home|unit|suite)\b"
    r"|roommate matching|room pricing"
    r"|\b(?:a|private|furnished|single|sunny|bright|cozy|nice|spacious) rooms? for rent\b"
    r"|furnished (?:private )?room (?:for rent|available|in)\b"
    r"|(?:live|living|join|joining)(?: with)? (?:\d|one|two|three|four|five) "
    r"(?:other |friendly |great |current |amazing |cool )?"
    r"(?:roommates?|roomates?|housemates?|flatmates?)"
    r"|(?:i am|i'm|im|we are|we're) (?:looking for|seeking|searching for) (?:a |an |one )?"
    r"(?:\w+ )?(?:roommate|roomate|housemate|flatmate)\b"
)
NEW = {"income_restricted_v2": INCOME_V2, "shared_space_v2": SHARED_V2}
OLD = {"income_restricted_v2": "income_restricted", "shared_space_v2": "shared_space"}

# A negation just before a match of INCOME_V2: "no income restrictions", "non-income
# restricted", "without any income caps". Only an article or "any" may come between, so "no
# fee income restricted unit" keeps its mark. NEGATED_WINDOW covers the longest negation.
NEGATION = re.compile(r"\b(?:no|not|non|without)[- ](?:(?:an?|any)[- ])?$")
NEGATED_WINDOW = 16

_PCT = r"(\d{2,3})(?:\.\d+)? ?(?:%|percent)"
_PCT_RANGE = rf"(?: ?(?:-|to|and|or|/|&) ?{_PCT})?"
# An AMI percentage: "130% ami", "165% of ami", "120 percent area median income", "ami: 110%",
# "175 ami %". A range ("70%-130% ami") gives both of its ends.
AMI_PCT = re.compile(
    rf"{_PCT}{_PCT_RANGE} (?:of (?:the )?)?(?:\(?ami\b|area median|median income)"
    rf"|\bami(?: level| band| tier| limit| category)?:? ?(?:of |at |is )?{_PCT}{_PCT_RANGE}"
    r"|\b(\d{2,3}) ami ?%"
)
# The text before a percentage the ad ties to its unit: "this unit is at 130% ami".
TIED = re.compile(r"this (?:unit|apartment|apt|home|residence)\b[^.]{0,40}$")
TIED_WINDOW = 60
AMI_RANGE = (20, 300)

_USD = r"\$+ ?(\d{1,3}(?:, ?\d{3})+(?:\.\d+)?|\d{2,7}(?:\.\d+)?k?)"
# The household income band: "minimum household income: $83,538", "maximum income (varies
# with household size): $187,110", "between $78,694 and $220,344", "$119,570 max income".
INCOME_MIN = re.compile(
    r"(?:\bmin(?:imum|\.)?|at least|no less than)"
    r"(?: combined| annual| household| yearly| gross| total)*(?: income)?"
    r"(?: requirements?| required| limit)?(?: for this unit)?(?: is| of)?[ :*-]*" + _USD
)
INCOME_MAX = re.compile(
    r"(?:\bmax(?:imum|imim|\.)?|not exceed|cannot exceed|can not exceed|no more than"
    r"|must be below|income below)(?:(?!min)[^$.]){0,40}?[ :*-]*" + _USD
)
INCOME_BETWEEN = re.compile(
    r"(?:between|range|bracket)[^$.]{0,30}?"
    + _USD
    + r"(?: min)?,? ?(?:and|-|to) ?"
    + _USD
)
INCOME_MAX_AFTER = re.compile(_USD + r" max\b")
INCOME_RANGE = (10_000, 1_000_000)
TERMS = ["ami_pct_text", "ami_tiers_text", "income_min_text", "income_max_text"]
# TERMS on a row the income flag leaves unmarked.
NO_TERMS = (float("nan"), 0, float("nan"), float("nan"))


def income_marked(low: str) -> bool:
    """Whether INCOME_V2 matches the plain text `low` somewhere without NEGATION just
    before the match."""
    return any(
        not NEGATION.search(low[max(0, m.start() - NEGATED_WINDOW) : m.start()])
        for m in INCOME_V2.finditer(low)
    )


def flags(text: str) -> tuple[bool, ...]:
    """Whether `text` is longer than MIN_DESCRIPTION characters, then whether the text is that
    long and `income_marked` marks it, then whether it is that long and SHARED_V2 matches."""
    # `b0data` measures the lowercased text.
    known = len(text.lower()) > MIN_DESCRIPTION
    low = cautions.plain(text)
    return (known, known and income_marked(low), known and bool(SHARED_V2.search(low)))


def ami_tier(low: str) -> tuple[float, int]:
    """The AMI percentage the plain text `low` gives its unit, and how many different AMI
    percentages it states within AMI_RANGE. The percentage is the only one stated, or with
    several, the only one TIED to the unit; otherwise it is NaN."""
    stated, tied = set(), set()
    for m in AMI_PCT.finditer(low):
        before = low[max(0, m.start() - TIED_WINDOW) : m.start()]
        for g in m.groups():
            if g and AMI_RANGE[0] <= int(g) <= AMI_RANGE[1]:
                stated.add(int(g))
                if TIED.search(before):
                    tied.add(int(g))
    pick = stated if len(stated) == 1 else tied
    return (float(next(iter(pick))) if len(pick) == 1 else float("nan"), len(stated))


def _usd(s: str) -> float:
    s = s.replace(",", "").replace(" ", "")
    v = float(s[:-1]) * 1000 if s.endswith("k") else float(s)
    return v if INCOME_RANGE[0] <= v <= INCOME_RANGE[1] else float("nan")


def _first(rx: re.Pattern, low: str, group: int = 0) -> float:
    for m in rx.finditer(low):
        v = _usd(m.groups()[group])
        if v == v:
            return v
    return float("nan")


def income_band(low: str) -> tuple[float, float]:
    """The minimum and maximum household income the plain text `low` states: the first amount
    after a minimum or a maximum, else the ends of a band "between" two amounts, and for the
    maximum, else an amount followed by "max". A missing end is NaN, as is an amount outside
    INCOME_RANGE."""
    lo, hi = _first(INCOME_MIN, low), _first(INCOME_MAX, low)
    if lo != lo:
        lo = _first(INCOME_BETWEEN, low, 0)
    if hi != hi:
        hi = _first(INCOME_BETWEEN, low, 1)
    if hi != hi:
        hi = _first(INCOME_MAX_AFTER, low)
    return lo, hi


def terms(text: str) -> tuple[float, int, float, float]:
    """The values of TERMS for a description `text`: `ami_tier` and `income_band` on the text
    as `cautions.plain` leaves it."""
    low = cautions.plain(text)
    return (*ami_tier(low), *income_band(low))


def latest_flags(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each listing in `ids` with a record in the records file `path`, `known` and the
    columns of NEW from `flags` on the description of its latest record, and TERMS from
    `terms` where the income flag is set. I read the record texts of a row group only for the
    rows I keep, and keep the flags and terms alone."""
    seen: dict[str, tuple] = {}
    file = pq.ParquetFile(path)
    names = set(file.schema_arrow.names)
    times = [c for c in ("collected_at", "last_collected_at") if c in names]
    for group in range(file.num_row_groups):
        head = file.read_row_group(group, columns=["listing_id", *times])
        lid = [str(x) for x in head["listing_id"].to_pylist()]
        at = [
            max((t for t in ts if t is not None), default=None)
            for ts in zip(*(head[c].to_pylist() for c in times))
        ]
        # DuckDB's arg_max in `b0data` passes over a record with a null time.
        keep = [
            i in ids and t is not None and (i not in seen or seen[i][0] < t)
            for i, t in zip(lid, at)
        ]
        if not any(keep):
            continue
        raws = file.read_row_group(group, columns=["raw_listing_json"]).filter(
            pa.array(keep)
        )
        rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
        for (i, t), raw in zip(rows, raws["raw_listing_json"].to_pylist()):
            # A listing twice in a row group keeps its later record.
            if i not in seen or seen[i][0] < t:
                listing = json.loads(raw) if raw else {}
                text = str(listing.get("description") or "")
                marks = flags(text)
                seen[i] = (t, *marks, *(terms(text) if marks[1] else NO_TERMS))
        del raws
    return pd.DataFrame(
        [(i, *v[1:]) for i, v in seen.items()],
        columns=["listing_id", "known", *NEW, *TERMS],
    ).set_index("listing_id")


def textflags(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    lid = frame.listing_id.astype(str)
    read = latest_flags(Path(records["path"]), set(lid))
    known = lid.map(read.known).eq(True).to_numpy()
    for col in NEW:
        frame[col] = lid.map(read[col]).eq(True).to_numpy()
    for col, empty in zip(TERMS, NO_TERMS):
        frame[col] = lid.map(read[col]).fillna(empty).to_numpy()
    frame["ami_tiers_text"] = frame.ami_tiers_text.astype("int16")
    # OUT is made after the read of the records, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    columns = {}
    for col, old in OLD.items():
        new, was = frame[col].to_numpy(), frame[old].to_numpy(bool)
        columns[col] = {
            "pattern": NEW[col].pattern,
            **(
                {"negation": NEGATION.pattern, "negation_window": NEGATED_WINDOW}
                if col == "income_restricted_v2"
                else {}
            ),
            "old_flag": old,
            "rows_marked": int(new.sum()),
            "rows_gained": int((new & ~was).sum()),
            "rows_lost": int((~new & was).sum()),
        }
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "textflags": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "each pattern matched on the description of the listing's latest record "
            "as cautions.plain leaves it (docs/notes/text-flags-2026-11-13.md)",
            "columns": columns,
            "listings_read": len(read),
            "rows_described": int(known.sum()),
            "terms": {
                "patterns": {
                    "ami_pct": AMI_PCT.pattern,
                    "tied": TIED.pattern,
                    "income_min": INCOME_MIN.pattern,
                    "income_max": INCOME_MAX.pattern,
                    "income_between": INCOME_BETWEEN.pattern,
                    "income_max_after": INCOME_MAX_AFTER.pattern,
                },
                "rows_with_ami_pct": int(frame.ami_pct_text.notna().sum()),
                "rows_with_several_tiers": int((frame.ami_tiers_text > 1).sum()),
                "rows_with_income_min": int(frame.income_min_text.notna().sum()),
                "rows_with_income_max": int(frame.income_max_text.notna().sum()),
            },
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(textflags(args.src, args.out)["textflags"], indent=2))


if __name__ == "__main__":
    main()
