"""Rent-blind screen behind quarantine-v9: generic ad-text checks over every
Greenwich Village, Gramercy Park and Flatiron row. It reads no rent, estimate or
residual, and its output carries no rent.

The vocabulary is generic on purpose. Places are the names of NYC's 2020
Neighborhood Tabulation Areas (NYC Open Data 9nt8-h7nd; names and the mean of
each area's boundary points in config/reviews/nta-2020-centres.json), taken whole from that
list: any part of a name whose area's centre lies over 2.5 km from Union Square,
after "in", "located in" or "heart of" and not followed by street, avenue or square.
The other checks are plain category words. As a guard against a term fitted to
rows found earlier by rent (quarantine-v7 and v8), every term is counted, and
one whose hits are all v7 or v8 rows is dropped before the screen runs.

Usage: quarantine_v9_screen.py config/reviews/nta-2020-centres.json OUT.jsonl [CACHE_ROOT]
"""

import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import corrections as c
from rentfrontier import data, descriptions

RULES = [
    "baths-ad-v2",
    "bedrooms-ad-v2",
    "fields-review-v3",
    "quarantine-v6",
    "unit-labels-v11",
    "unit-reviews-v1",
    "unit-splits-v4",
]
HOODS = ["Greenwich Village", "Gramercy Park", "Flatiron"]
UNION_SQUARE = (40.7359, -73.9911)
FAR_KM = 2.5


def km(a, b):
    dy = (a[0] - b[0]) * 111.2
    dx = (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def far_places(path):
    names = set()
    for a in json.loads(Path(path).read_text()):
        if km((a["lat"], a["lon"]), UNION_SQUARE) <= FAR_KM:
            continue
        for part in re.split(r"[-()]", a["ntaname"]):
            part = part.strip().lower()
            if len(part) >= 5 and part not in {
                "north",
                "south",
                "east",
                "west",
                "central",
            }:
                names.add(part)
    names |= {"brooklyn", "queens", "the bronx", "staten island", "new jersey"}
    return sorted(names)


def terms(nta):
    """Each check is a list of terms; a row hits a check if any term matches."""
    return {
        "far_place": [
            r"\b(?:in|located in|located on|heart of|apartment in|unit in) (?:the )?"
            r"(?:beautiful |historic |prime )?"
            + re.escape(n)
            + r"\b(?! (?:ave|avenue|st|street|sq|square|pl|place)\b)"
            for n in far_places(nta)
        ],
        "far_street": [
            r"\b(?:e|w|east|west)\.? ?(?:4[0-9]|[5-9][0-9]|1[0-9][0-9])(?:st|nd|rd|th)?\.? (?:st|street)\b"
        ],
        "nonresidential": [
            r"commercial (?:space|unit|lease|use|tenant)",
            r"retail (?:space|use)",
            r"office (?:space|suite|use)",
            r"medical (?:office|space)",
            r"professional office",
            r"store ?front",
            r"showroom",
            r"restaurant space",
            r"non[- ]residential",
            r"not (?:for |a )?residential",
            r"zoned (?:for )?commercial",
        ],
        "shared_bath": [
            r"shared (?:bath|bathroom|toilet|shower|kitchen)s?\b",
            r"(?:bath|bathroom|toilet)s? (?:is |are )?shared",
            r"share (?:a |the )?(?:bath|bathroom|toilet|kitchen)",
            r"(?:hallway|common) (?:bath|bathroom|toilet)",
        ],
        "room_share": [
            r"\broom for rent",
            r"\broom in an? (?:apartment|apt|shared)",
            r"private (?:bed)?room (?:in|available)",
            r"(?:looking for|seeking) (?:a |one )?room ?mate",
            r"room ?mate wanted",
        ],
        "multi_unit": [
            r"both (?:apartments|units)",
            r"two (?:separate )?(?:apartments|units) (?:for|together)",
            r"(?:entire|whole) (?:building|townhouse) for (?:rent|lease)",
        ],
        "short_stay": [
            r"nightly",
            r"per night",
            r"minimum stay",
            r"short[- ]term (?:rental|stay|lease)s? only",
            r"corporate (?:housing|rental)",
            r"vacation rental",
            r"summer (?:sublet|rental)",
            r"(?:\d|one|two|three|four|five|six) (?:week|month)s? (?:only|sublet|sublease)",
        ],
    }


def main(nta, out, cache_root=None):
    frame = data.load(
        data.DATASET_NB5, **({"cache_root": Path(cache_root)} if cache_root else {})
    )
    kept = data.apply_rules(frame, np.zeros(len(frame), bool), RULES)
    f = (kept[0] if isinstance(kept, tuple) else kept).reset_index(drop=True)
    f = f[f.neighbourhood.isin(HOODS)].reset_index(drop=True)
    token = descriptions.SOURCES.set(
        (
            descriptions.SOURCE,
            descriptions.WV_SOURCE,
            descriptions.GV_SOURCE,
            descriptions.FGP_SOURCE,
        )
    )
    try:
        text = descriptions.attach(f)
    finally:
        descriptions.SOURCES.reset(token)
    text = text.fillna("").map(c.plain).str.lower()

    earlier = data.quarantined(data.QUARANTINE_V8) - data.quarantined(
        data.QUARANTINE_V6
    )
    is_earlier = f.audit_id.isin(earlier)
    checks, dropped = {}, []
    for check, items in terms(nta).items():
        keep = []
        for t in items:
            hit = text.str.contains(t)
            # Place names come whole from the NTA list, so only hand-written terms are guarded.
            if check != "far_place" and hit.any() and (hit <= is_earlier).all():
                dropped.append((check, t, int(hit.sum())))
            else:
                keep.append(t)
        checks[check] = re.compile("|".join(f"(?:{t})" for t in keep))
    print("dropped by the guard:", dropped)

    hits = pd.DataFrame({k: text.str.contains(rx) for k, rx in checks.items()})
    anyhit = hits.any(axis=1)
    print("rows", len(f), "hits", int(anyhit.sum()))
    print(hits[anyhit].sum().to_dict())
    rows = []
    for i in f.index[anyhit]:
        flags = [k for k in hits.columns if hits.at[i, k]]
        snippets = []
        for k in flags:
            m = checks[k].search(text[i])
            snippets.append(text[i][max(0, m.start() - 160) : m.end() + 160])
        rows.append(
            dict(
                audit_id=f.at[i, "audit_id"],
                hood=f.at[i, "neighbourhood"],
                building=f.at[i, "building"],
                unit_id=f.at[i, "unit_id"],
                source_listing_id=str(f.at[i, "source_listing_id"]),
                unit_label=f.at[i, "unit_label"] if "unit_label" in f else None,
                period=str(f.at[i, "period"])[:7],
                flags=flags,
                snippets=snippets,
                text=text[i][:5000],
            )
        )
    Path(out).write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    main(*sys.argv[1:])
