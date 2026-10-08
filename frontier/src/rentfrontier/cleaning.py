"""What the served fit's data rules do to the rows, one rule at a time.

    python -m rentfrontier.cleaning RUN --out cleaning.json

Applies the run's data rules (`data.apply_rules`, in the same order) to its
dataset one by one, and after each records the rows, units and buildings left,
the rows dropped, the fields changed on rows that stay, and two checks on a
unit's history: how often a unit's next listing has another bedroom count, and
how often its rent moves by more than 40%. Both should fall as units are joined
and split right. The site's research story reads the file.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import data

FIELDS = (
    "bedrooms",
    "full_baths",
    "half_baths",
    "square_feet",
    "listed_floor",
    "elevator",
    "doorman",
    "laundry",
    "pets",
)
JUMP = math.log(1.4)


def family(rule: str) -> str:
    for prefix, name in (
        ("unit-labels-", "join"),
        ("unit-reviews-", "join"),
        ("unit-splits-", "split"),
        ("quarantine-", "drop"),
        ("tune-", "drop"),
    ):
        if rule.startswith(prefix):
            return name
    return "correct"


def history(frame: pd.DataFrame) -> dict:
    """Consecutive listings of the same unit: how many, and the shares whose
    bedroom count differs or whose rent moves by more than 40%."""
    f = frame.sort_values(["unit_id", "price_at"], kind="stable")
    same = (f.unit_id.to_numpy()[1:] == f.unit_id.to_numpy()[:-1]) & (
        f.price_basis.to_numpy()[1:] == f.price_basis.to_numpy()[:-1]
    )
    beds = f.bedrooms.to_numpy()
    rent = f.log_rent.to_numpy()
    pairs = int(same.sum())
    if not pairs:
        return {"pairs": 0, "bed_changes": None, "big_jumps": None}
    bed = (beds[1:] != beds[:-1]) & same
    jump = (np.abs(rent[1:] - rent[:-1]) > JUMP) & same
    return {
        "pairs": pairs,
        "bed_changes": float(bed.sum() / pairs),
        "big_jumps": float(jump.sum() / pairs),
    }


def counts(frame: pd.DataFrame) -> dict:
    return {
        "rows": int(len(frame)),
        "units": int(frame.unit_id.nunique()),
        "buildings": int(frame.building.nunique()),
        **history(frame),
    }


def _same(a: pd.Series, b: pd.Series) -> np.ndarray:
    return ((a == b) | (a.isna() & b.isna())).to_numpy()


def changed(before: pd.DataFrame, after: pd.DataFrame) -> dict:
    """Rows that stay, by field, whose value the rule changed."""
    b = before.set_index("audit_id")
    a = after.set_index("audit_id")
    keep = a.index.intersection(b.index)
    out = {}
    for field in FIELDS:
        if field in a and field in b:
            n = int((~_same(a.loc[keep, field], b.loc[keep, field])).sum())
            if n:
                out[field] = n
    return out


def steps(frame: pd.DataFrame, rules) -> dict:
    out = {"start": counts(frame), "steps": []}
    for rule in rules:
        after = data.DATA_RULES[rule](frame)
        out["steps"].append(
            {
                "rule": rule,
                "family": family(rule),
                "dropped": int(len(frame) - len(after)),
                "changed": changed(frame, after),
                **counts(after),
            }
        )
        frame = after
    return out


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run", help="a run name under the runs directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(
        (data.OUTPUT_ROOT / "runs" / args.run / "result.json").read_text()
    )
    rules = data.recorded_rules(record)
    frame = data.load(Path(record["dataset"]))
    doc = {"run": args.run, "dataset": Path(record["dataset"]).name}
    doc.update(steps(frame, rules))
    args.out.write_text(json.dumps(doc, indent=1) + "\n")


if __name__ == "__main__":
    main()
