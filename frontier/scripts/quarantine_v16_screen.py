"""Rent-blind screen behind the Brooklyn rows quarantine-v16 adds to v15: the
NB9 rows under the rules of 2026-10-14 whose ads place the apartment by a
Brooklyn landmark, street or neighbourhood (Prospect Park, Parade Ground,
Cortelyou Road, Beverly Road, Ditmas, PLG, Park Slope and others). Several of
StreetEasy's Brooklyn addresses share a number and street name with a Manhattan
address ("37 East 21st Street", "300 7th Avenue"), and those rows carry the
Manhattan building. The screen reads no rent, estimate or residual, and its
output carries no rent. Every hit was read, with its building and no rent
shown, and the read list is config/reviews/quarantine-v16-read-20261014.txt.

Usage: quarantine_v16_screen.py OUT.jsonl
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import corrections as c
from rentfrontier import data, descriptions, features

RULES = [
    "baths-ad-v3",
    "bedrooms-ad-v3",
    "building-joins-v1",
    "fields-review-v3",
    "latest-ask-v4",
    "quarantine-v15",
    "west-coast-wings-v1",
    "unit-labels-v17",
    "unit-reviews-v1",
    "unit-splits-v4",
]
PLACES = (
    r"prospect park|parade grounds?|cortelyou|beverly road|ditmas|\bplg\b"
    r"|prospect[- ]lefferts|flatbush|park slope|windsor terrace|crown heights"
    r"|fort greene|clinton hill|bed[- ]?stuy|bushwick|greenpoint|sunset park|bay ridge"
)
NEAR = (
    r"(?:located|situated|nestled|heart of|in|near|minutes? (?:to|from|away from)"
    r"|mins? (?:to|from)|steps (?:to|from|away from)|close to|blocks? (?:to|from)"
    r"|walk to|across from|around the corner from)\s+(?:the |beautiful |prime "
    r"|historic |trendy |vibrant )?(?:" + PLACES + r")\b"
)


def main(out):
    frame = data.load(data.DATASET_NB9)
    kept = data.apply_rules(frame, np.zeros(len(frame), bool), RULES)
    f = kept[0][~np.asarray(kept[1])].reset_index(drop=True)
    token = descriptions.SOURCES.set(
        tuple(Path(p) for p in features._NB9_DESCRIPTIONS.values())
    )
    try:
        text = descriptions.attach(f)
    finally:
        descriptions.SOURCES.reset(token)
    text = text.fillna("").map(c.plain).str.lower()
    rx = re.compile(NEAR)
    hit = text.str.contains(rx)
    print("rows", len(f), "hits", int(hit.sum()))
    rows = []
    for i in f.index[hit]:
        m = rx.search(text[i])
        rows.append(
            dict(
                audit_id=f.at[i, "audit_id"],
                hood=f.at[i, "neighbourhood"],
                building=f.at[i, "building"],
                unit_id=f.at[i, "unit_id"],
                source_listing_id=str(f.at[i, "source_listing_id"]),
                period=str(f.at[i, "price_at"])[:7],
                snippet=text[i][max(0, m.start() - 200) : m.end() + 160],
                text=text[i][:3000],
            )
        )
    Path(out).write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    main(*sys.argv[1:])
