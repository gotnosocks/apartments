"""Runs `rentfrontier.brooklyn.screen` on a dataset under the current data
rules, rows the rules hold out left out, and writes the hits nobody has read
yet (`brooklyn.read_ids`) to OUT.jsonl for review. The output carries no rent.
Each hit gets its whole ad read: a confirmed one goes into
`brooklyn.MISJOINS` and the next quarantine version, and every read id goes
into that version's read list. Then the dataset's cohort goes into
`brooklyn.SCREENED`.

Usage: brooklyn_screen.py DATASET OUT.jsonl [EVIDENCE.jsonl ...]

The evidence files default to NB9's description sources.
"""

import sys
from pathlib import Path

import numpy as np

from rentfrontier import corrections as c
from rentfrontier import autoselect, brooklyn, data, descriptions, features


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
    hits = brooklyn.screen(f, text.map(c.plain).str.lower())
    new = hits[~hits.audit_id.isin(brooklyn.read_ids())] if len(hits) else hits
    print("rows", len(f), "hits", len(hits), "unread", len(new))
    new.to_json(out, orient="records", lines=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
