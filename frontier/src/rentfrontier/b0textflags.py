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
  without an agent's name it took for "AMI".
- `shared_space_v2`: `SHARED_V2`, written from the readers' quotes.

Both stay text features added beside the coded fields, since ad text never overrides a coded
field (Ben, 2026-10-04).

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256) a row group at a time. For each listing of SRC I keep its latest record,
by the later of `collected_at` and `last_collected_at`, as `b0data` picks the record for its
text flags, and I skip a record with neither time, as `b0data`'s `arg_max` does. I match the
patterns on the description as `cautions.plain` leaves it. A listing whose latest record has
no description longer than `b0data.MIN_DESCRIPTION` characters gets false in both columns, as
do listings missing from the records.

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with the two columns added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `textflags` entry giving
  SRC's path and rows SHA-256, the patterns, the listings read, the rows whose listing has a
  description, and for each new column the rows marked and the rows it gains and loses
  against the old flag.

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


def flags(text: str) -> tuple[bool, ...]:
    """Whether `text` is longer than MIN_DESCRIPTION characters, then for each pattern of
    NEW whether the text is that long and matches it."""
    # `b0data` measures the lowercased text.
    known = len(text.lower()) > MIN_DESCRIPTION
    low = cautions.plain(text)
    return (known, *(known and bool(rx.search(low)) for rx in NEW.values()))


def latest_flags(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each listing in `ids` with a record in the records file `path`, `known` and the
    columns of NEW from `flags` on the description of its latest record. I read the record
    texts of a row group only for the rows I keep, and keep the flags alone."""
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
                seen[i] = (t, *flags(str(listing.get("description") or "")))
        del raws
    return pd.DataFrame(
        [(i, *v[1:]) for i, v in seen.items()],
        columns=["listing_id", "known", *NEW],
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
