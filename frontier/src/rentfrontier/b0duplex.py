"""Write a B0 dataset with a column marking the rows of duplex apartments.

    python -m rentfrontier.b0duplex SRC OUT

S7 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) read each listing's
description for an apartment on two or three levels. Its pattern marked 6.0% of the 1,790,425
rows in S7's own dataset, and Sonnet readers took 186 of 200 marked ads for duplex apartments.
L1 prices a duplex right on average, but the asks of duplex ads scatter about 35% wider than
other ads'. This script puts S7's pattern into a dataset as the column `duplex`, for a model to
read.

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256) a row group at a time. For each listing of SRC I keep its latest record, by
the later of `collected_at` and `last_collected_at`, as `b0data` picks the record for its text
flags. I skip a record with neither time, as `b0data`'s `arg_max` does. I mark the listing a
duplex when the description in that record

1. has the word duplex or triplex (`DUP`) and calls no building a duplex (`DUP_BUILDING`:
   "duplex building", "duplex house", "two-family" and the like), or
2. describes an apartment on two or three levels (`LEVELS`: "bi-level", "spans two floors",
   "internal staircase" and the like).

The patterns are S7's (`docs/notes/causal-screens-2026-11-13/s7_text.py`), and I match them
with pyarrow's RE2, as S7 did. A listing whose latest record has no description longer than
`b0data.MIN_DESCRIPTION` characters gets false, as do listings missing from the records.

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with the boolean column `duplex` added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `duplex` entry giving SRC's
  path and rows SHA-256, the rule and its patterns, the listings read, the rows whose listing
  has a description and the rows marked.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .b0data import MIN_DESCRIPTION, sha256

DUP = r"(?i)\b(?:duplex|triplex)"
DUP_BUILDING = r"(?i)\b(?:duplex|triplex)\s+(?:building|house|townhouse|brownstone|walk-?up)|two[- ]family"
LEVELS = (
    r"(?i)\bbi-?level\b|\btwo[- ]level (?:apartment|unit|home|loft|penthouse|residence|layout)"
    r"|\bspans? (?:over )?(?:two|2|three|3) (?:full )?(?:floors|levels|stories)"
    r"|\bspread (?:out )?(?:over|across) (?:two|2|three|3) (?:full )?(?:floors|levels|stories)"
    r"|\b(?:internal|interior|private) (?:spiral )?stair(?:case|s|way)"
)


def marks(texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """For each text, whether it is longer than MIN_DESCRIPTION characters, and whether it is
    that long and follows the duplex rule of the module's docstring."""
    a = pa.array(texts, pa.string())

    def match(pattern):
        return pc.match_substring_regex(a, pattern).to_numpy(zero_copy_only=False)

    known = pc.utf8_length(a).to_numpy(zero_copy_only=False) > MIN_DESCRIPTION
    return known, known & ((match(DUP) & ~match(DUP_BUILDING)) | match(LEVELS))


def latest_marks(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each listing in `ids` with a record in the records file `path`, `known` and
    `duplex` from `marks` on the description of its latest record. I read the record texts
    of a row group only for the rows I keep, and keep the marks alone."""
    seen: dict[str, tuple[float, bool, bool]] = {}
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
        texts = []
        for raw in raws["raw_listing_json"].to_pylist():
            listing = json.loads(raw) if raw else {}
            texts.append(str(listing.get("description") or ""))
        known, duplex = marks(texts)
        rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
        for (i, t), k, d in zip(rows, known, duplex):
            # A listing twice in a row group keeps its later record.
            if i not in seen or seen[i][0] < t:
                seen[i] = (t, bool(k), bool(d))
        del raws, texts
    return pd.DataFrame(
        [(i, k, d) for i, (_, k, d) in seen.items()],
        columns=["listing_id", "known", "duplex"],
    ).set_index("listing_id")


def duplex(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    lid = frame.listing_id.astype(str)
    read = latest_marks(Path(records["path"]), set(lid))
    known = lid.map(read.known).eq(True).to_numpy()
    frame["duplex"] = lid.map(read.duplex).eq(True).to_numpy()
    # OUT is made after the read of the records, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "duplex": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "the description of the listing's latest record has the word duplex "
            "or triplex and calls no building a duplex, or describes an apartment on two "
            "or three levels (S7 of docs/notes/causal-screens-2026-11-13.md)",
            "patterns": {
                "dup": DUP,
                "dup_building": DUP_BUILDING,
                "levels": LEVELS,
            },
            "listings_read": len(read),
            "rows_described": int(known.sum()),
            "rows_marked": int(frame.duplex.sum()),
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
    print(json.dumps(duplex(args.src, args.out)["duplex"], indent=2))


if __name__ == "__main__":
    main()
