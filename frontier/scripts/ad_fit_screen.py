"""Runs `rentfrontier.adfit.screen` on a dataset under the current data rules,
rows the rules hold out left out, and writes the hits nobody has read yet
(`adfit.read_ids`) to OUT.jsonl for review, tier A first. The output carries
no rent. Each hit gets its whole ad and page read, and the read goes into a
reads file (`adfit.READS`). Non-keep verdicts go into the next version of the
matching data rule. Then the dataset's cohort goes into `adfit.SCREENED`.

Usage: ad_fit_screen.py DATASET OUT.jsonl [EVIDENCE.jsonl ...]

The evidence files default to NB9's description sources.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import corrections as c
from rentfrontier import adfit, autoselect, data, descriptions, features


def main(dataset, out, *evidence):
    frame = data.load(Path(dataset))
    rules = sorted(autoselect.current_rules(), key=autoselect._rule_order)
    kept, held = data.apply_rules(frame, np.zeros(len(frame), bool), rules)
    f = kept[~np.asarray(held)].reset_index(drop=True)
    paths = evidence or features._NB9_DESCRIPTIONS.values()
    token = descriptions.SOURCES.set(tuple(Path(p) for p in paths))
    try:
        text = descriptions.attach(f)
    finally:
        descriptions.SOURCES.reset(token)
    coords = pd.read_parquet(features.lot_registry()).drop_duplicates("building")
    hits = adfit.screen(
        f, text.fillna("").map(c.plain).str.lower(), coords.set_index("building")
    )
    new = hits[~hits.audit_id.isin(adfit.read_ids())] if len(hits) else hits
    if len(new):
        new = new.sort_values(["tier", "building", "unit_id", "period"])
    print("rules", ",".join(rules))
    print("rows", len(f), "hits", len(hits), "unread", len(new))
    if len(hits):
        print(hits.groupby("tier").size().to_dict())
        print(hits.explode("flags")["flags"].value_counts().to_dict())
    new.to_json(out, orient="records", lines=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
