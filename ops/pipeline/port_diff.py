"""Compare two dataset folders row by row, for a chain rule moving into the pipeline.

    python ops/pipeline/port_diff.py BEFORE AFTER --rules NAME,... [--after-rules NAME,...]
        [--within DATASET] [--report FILE]

BEFORE is a folder written by `observations.py` from a build without the port, and AFTER one
written the same way from a build with it. A fit on BEFORE applies the chain rules in
`--rules`, and a fit on AFTER applies those in `--after-rules`, none by default. Each list
follows the order a fit gives them. The script checks how far the two agree:

1. It loads both folders with `rentfrontier.data.load`, its cache in a temporary folder, and
   applies each side's rules with `rentfrontier.data.apply_rules`, which checks their order as a
   fit does. A port of one rule among the unit rules leaves the others in both lists, so the
   counts compare the rows both fits would read. Built in one go, the loader's list of 1.75 million rows of the dataset of all
   scraped areas would take most of thelio's memory. So the script first writes the loader's
   cache file in chunks of 100,000 rows, flattened with the loader's own function, and the
   loader then reads that file.
2. It matches the rows by `audit_id` and counts the rows of one side alone.
3. For each column both sides hold, it counts the matched rows whose values differ, a column
   at a time. Two missing values count as the same. It lists up to 10 pairs of values per
   column with their rows, and the audit IDs of 20 rows, those within DATASET first.
4. It counts the rows with any difference, or on one side alone, against the larger side's
   rows. A share up to `NEGLIGIBLE_SHARE` (0.25%) of `rentfrontier.autoselect` calls for no
   refit, and a larger one makes the port a data change of its own.

With `--within DATASET`, it splits each count by whether DATASET holds the row's audit ID.
The rules filling fields from ads' texts hold NB9's rows alone, so for them DATASET is NB9.
`--report FILE` saves the counts as JSON.

The script compares values alone. A fit draws its held-out rows by position within each
dataset, so the two folders' held-out flags differ wherever a row is missing from one of them,
and the script passes `apply_rules` empty held-out masks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from itertools import islice

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]


def frontier():
    """The chain's `rentfrontier.data`, from this checkout."""
    src = str(REPO / "frontier" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from rentfrontier import data

    return data


def load(data, folder: Path, cache_root: Path, chunk: int = 100_000):
    """`data.load(folder)`, after writing its cache file in chunks of `chunk` rows."""
    source = folder / "observations.jsonl"
    digest = data.sha256(source)
    cache = cache_root / "cache" / f"observations-{digest[:16]}-{data.SCHEMA}.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    tables = []
    with open(source) as f:
        while lines := list(islice(f, chunk)):
            rows = [data._flatten(json.loads(line)) for line in lines if line.strip()]
            tables.append(
                pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False)
            )
    pq.write_table(pa.concat_tables(tables, promote_options="permissive"), cache)
    del tables
    return data.load(folder, cache_root=cache_root)


def differs(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    missing_a = pd.isna(a)
    missing_b = pd.isna(b)
    equal = np.array([x == y for x, y in zip(a, b)], dtype=bool)
    return ~((missing_a & missing_b) | (equal & ~missing_a & ~missing_b))


def compare(
    before: Path,
    after: Path,
    rules: list[str],
    within: Path | None,
    negligible: float,
    after_rules: list[str] = (),
) -> dict:
    """The counts of the module docstring, with a share up to `negligible` as negligible."""
    data = frontier()
    tmp = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    with tempfile.TemporaryDirectory(dir=tmp, prefix="port-diff-") as cache:
        ours = load(data, after, Path(cache))
        theirs = load(data, before, Path(cache))
    theirs, _ = data.apply_rules(theirs, np.zeros(len(theirs), dtype=bool), rules)
    ours, _ = data.apply_rules(ours, np.zeros(len(ours), dtype=bool), after_rules)
    held = set()
    if within is not None:
        held = {
            audit_id
            for (audit_id,) in duckdb.sql(
                "SELECT audit_id FROM read_json(?, columns = {audit_id: 'VARCHAR'})",
                params=[str(within / "observations.jsonl")],
            ).fetchall()
        }

    def split(ids: pd.Series) -> dict:
        inside = int(ids.isin(held).sum())
        counts = {"rows": len(ids)}
        if within is not None:
            counts.update({"within": inside, "outside": len(ids) - inside})
        return counts

    ids = pd.Index(ours.audit_id)
    common = ids.intersection(pd.Index(theirs.audit_id))
    at_ours = ids.get_indexer(common)
    at_theirs = pd.Index(theirs.audit_id).get_indexer(common)
    columns = [
        c
        for c in ours.columns
        if c in theirs.columns and c not in ("audit_id", "log_rent")
    ]
    fields, changed = {}, np.zeros(len(common), dtype=bool)
    for column in columns:
        after_values = ours[column].to_numpy(dtype=object)[at_ours]
        before_values = theirs[column].to_numpy(dtype=object)[at_theirs]
        mask = differs(before_values, after_values)
        if not mask.any():
            continue
        changed |= mask
        found = pd.DataFrame(
            {
                "audit_id": common[mask],
                "before": before_values[mask].astype(str),
                "after": after_values[mask].astype(str),
            }
        )
        found["within"] = found.audit_id.isin(held)
        pairs = found.groupby(["before", "after"]).within.agg(["size", "sum"])
        pairs = pairs.sort_values("size", ascending=False).head(10)
        fields[column] = {
            **split(found.audit_id),
            "pairs": [
                {"before": b, "after": a, "rows": int(n)}
                | ({} if within is None else {"within": int(w)})
                for (b, a), (n, w) in pairs.iterrows()
            ],
            "examples": found.sort_values("within", ascending=False)
            .audit_id.head(20)
            .tolist(),
        }
    before_alone = theirs.audit_id[~theirs.audit_id.isin(common)]
    after_alone = ours.audit_id[~ours.audit_id.isin(common)]
    total = max(len(ours), len(theirs))
    rows = int(changed.sum()) + len(before_alone) + len(after_alone)
    return {
        "before": {"folder": str(before), "rows": len(theirs), "rules": rules},
        "after": {"folder": str(after), "rows": len(ours), "rules": list(after_rules)},
        "within": None if within is None else str(within),
        "matched": len(common),
        "before_alone": split(before_alone),
        "after_alone": split(after_alone),
        "changed": {
            **split(pd.concat([pd.Series(common[changed]), before_alone, after_alone])),
            "share": rows / total,
            "negligible": rows <= negligible * total,
        },
        "fields": fields,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--after-rules", default="")
    parser.add_argument("--within", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    frontier()
    from rentfrontier.autoselect import NEGLIGIBLE_SHARE

    rules = [r for r in args.rules.split(",") if r]
    after_rules = [r for r in args.after_rules.split(",") if r]
    result = compare(
        args.before, args.after, rules, args.within, NEGLIGIBLE_SHARE, after_rules
    )
    text = json.dumps(result, indent=2)
    if args.report:
        args.report.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
