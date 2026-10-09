"""Rent-blind screen for the next quarantine version: quarantine_v10_screen.py's
checks over each screened neighbourhood of DATASET_NB6, every place measured
from that neighbourhood's own centre, with one fix to the far-place check. It
reads no rent, estimate or residual, and its output carries no rent.

The fix: v10 splits a far NTA name at its hyphens and brackets and matches
each part, so a part that is also part of a local name matched local text.
"Bedford-Stuyvesant" gave "stuyvesant", which hit "located in Stuyvesant Town"
in 56 Stuyvesant Town/PCV ads. Here a far part that occurs inside a local NTA
name (one whose centre is within FAR_KM of the neighbourhood's centre) is not
matched alone: only the far NTA's whole name is, written with a hyphen or a
space between its parts, or a common short form (SHORT_FORMS, e.g.
"Bed-Stuy"), or the part followed by a direction that is not itself in a local
name ("midtown east" and "midtown west" from Chelsea, not "midtown south").
Parts that occur in no local name match alone, as in v10.

Usage: quarantine_v12_screen.py config/reviews/nta-2020-centres.json OUT.jsonl [CACHE_ROOT]
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import quarantine_v10_screen as v10

from rentfrontier import corrections as c
from rentfrontier import data, descriptions

RULES = [
    "baths-ad-v3",
    "bedrooms-ad-v3",
    "fields-review-v3",
    "unit-labels-v13",
    "unit-reviews-v1",
    "unit-splits-v4",
]
# Each screened neighbourhood and the centre its places are measured from.
CENTRES = {
    "Chelsea": (40.7397, -74.0026),  # W 14th St and 8th Ave, as v10
    "West Village": (40.7397, -74.0026),
    "Stuyvesant Town/PCV": (40.7330, -73.9780),  # 1st Ave and E 20th St
}
FAR_KM = v10.FAR_KM
# Short forms of a whole NTA name (lower case), matched with the name.
SHORT_FORMS = {"bedford-stuyvesant": ["bed-stuy", "bed stuy", "bedstuy"]}
SKIP = {"north", "south", "east", "west", "central"}
EXTRA = ["brooklyn", "queens", "the bronx", "staten island", "new jersey"]


def _parts(name):
    return [p.strip().lower() for p in re.split(r"[-()]", name) if p.strip()]


def _stem(name):
    """An NTA name without its bracketed direction, e.g. "Bedford-Stuyvesant
    (West)" -> "bedford-stuyvesant"."""
    return re.sub(r"\s*\(.*?\)", "", name).strip().lower()


def far_places(areas, centre):
    """Place names to match in a neighbourhood centred at `centre`: each far
    NTA's name parts (at least 5 letters, not a bare direction), except a part
    that occurs inside a local NTA name, which is replaced by the whole name's
    spellings (see the module docstring)."""
    local = [
        a["ntaname"].lower()
        for a in areas
        if v10.km((a["lat"], a["lon"]), centre) <= FAR_KM
    ]
    names = set()
    for a in areas:
        if v10.km((a["lat"], a["lon"]), centre) <= FAR_KM:
            continue
        for part in _parts(a["ntaname"]):
            if len(part) < 5 or part in SKIP:
                continue
            if not any(part in name for name in local):
                names.add(part)
                continue
            stem = _stem(a["ntaname"])
            words = [w.strip() for w in stem.split("-") if w.strip()]
            names |= {"-".join(words), " ".join(words)}
            names |= set(SHORT_FORMS.get(stem, []))
            # The part with a direction is still a far place unless that, too,
            # is in a local name: "midtown east" and "midtown west" are far from
            # Chelsea, "midtown south" is not.
            names |= {
                f"{part} {d}"
                for d in sorted(SKIP)
                if not any(f"{part} {d}" in name for name in local)
            }
    return sorted(names | set(EXTRA))


def terms(nta, centre):
    """v10's checks (its far_place list discarded), with far_place from
    far_places for a neighbourhood centred at `centre`."""
    checks = v10.terms(nta)
    checks["far_place"] = [
        r"\b(?:in|located in|located on|heart of|apartment in|unit in) (?:the )?"
        r"(?:beautiful |historic |prime )?"
        + re.escape(n)
        + r"\b(?! (?:ave|avenue|st|street|sq|square|pl|place)\b)"
        for n in far_places(json.loads(Path(nta).read_text()), centre)
    ]
    return checks


def main(nta, out, cache_root=None):
    frame = data.load(
        data.DATASET_NB6, **({"cache_root": Path(cache_root)} if cache_root else {})
    )
    kept = data.apply_rules(frame, np.zeros(len(frame), bool), RULES)
    f = (kept[0] if isinstance(kept, tuple) else kept).reset_index(drop=True)
    f = f[f.neighbourhood.isin(list(CENTRES))].reset_index(drop=True)
    token = descriptions.SOURCES.set(
        (
            descriptions.SOURCE,
            descriptions.WV_SOURCE,
            descriptions.GV_SOURCE,
            descriptions.FGP_SOURCE,
            descriptions.STUY_SOURCE,
        )
    )
    try:
        text = descriptions.attach(f)
    finally:
        descriptions.SOURCES.reset(token)
    text = text.fillna("").map(c.plain).str.lower()

    # v10's guard: drop a hand-written term whose hits are all quarantine-v6 rows.
    is_earlier = f.audit_id.isin(data.quarantined(data.QUARANTINE_V6))
    rows, dropped = [], set()
    for hood, centre in CENTRES.items():
        here = f.neighbourhood.eq(hood).to_numpy()
        checks = {}
        for check, items in terms(nta, centre).items():
            keep = []
            for t in items:
                hit = text.str.contains(t)
                if check != "far_place" and hit.any() and (hit <= is_earlier).all():
                    dropped.add((check, t, int(hit.sum())))
                else:
                    keep.append(t)
            checks[check] = re.compile("|".join(f"(?:{t})" for t in keep))
        sub = text[here]
        hits = pd.DataFrame({k: sub.str.contains(rx) for k, rx in checks.items()})
        anyhit = hits.any(axis=1)
        print(
            hood,
            "rows",
            len(sub),
            "hits",
            int(anyhit.sum()),
            hits[anyhit].sum().to_dict(),
        )
        for i in hits.index[anyhit]:
            flags = [k for k in hits.columns if hits.at[i, k]]
            snippets = []
            for k in flags:
                m = checks[k].search(text[i])
                snippets.append(text[i][max(0, m.start() - 160) : m.end() + 160])
            rows.append(
                dict(
                    audit_id=f.at[i, "audit_id"],
                    hood=hood,
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
    print("dropped by the guard:", sorted(dropped))
    Path(out).write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    main(*sys.argv[1:])
