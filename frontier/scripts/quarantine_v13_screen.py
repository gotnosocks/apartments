"""Rent-blind screen: quarantine_v12_screen.py over each screened neighbourhood
of DATASET_NB7, with one more fix to the far-place check. It reads no rent,
estimate or residual, and its output carries no rent.

The fix: a far NTA name part that is also a word of a screened building's name
named a local building, not a far place. Brooklyn's NTA "Madison" gave
"madison", which hit "situated in the madison parq" and "in madison house" in
13 NoMad ads. Here such a part is not matched alone, only with its borough
("madison, brooklyn", "madison brooklyn"), or within the far NTA's whole
name and its short forms, as v12 does for a part inside a local NTA name
("bedford-stuyvesant", "bed-stuy" from West Village, whose Bedford St
buildings name "bedford").

Usage: quarantine_v13_screen.py config/reviews/nta-2020-centres.json OUT.jsonl [CACHE_ROOT]
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import quarantine_v10_screen as v10
import quarantine_v12_screen as v12

from rentfrontier import corrections as c
from rentfrontier import data, descriptions

RULES = v12.RULES
# Each screened neighbourhood and the centre its places are measured from.
CENTRES = {
    **v12.CENTRES,
    "NoMad": (40.7455, -73.9886),  # Broadway and W 28th St
}


def building_words(buildings):
    """The words of building slugs ("madison-parq" -> {"madison", "parq"})."""
    return {w for b in buildings for w in str(b).lower().split("-") if w}


def far_places(areas, centre, buildings=()):
    """v12's far places, except that a bare far part that is a word of a
    local building's name is matched only with its borough or in the far
    NTA's whole name."""
    names = set(v12.far_places(areas, centre))
    words = building_words(buildings)
    for a in areas:
        if v10.km((a["lat"], a["lon"]), centre) <= v12.FAR_KM:
            continue
        boro = a.get("boroname", "").lower()
        for part in v12._parts(a["ntaname"]):
            if part in names and part in words:
                names.discard(part)
                if boro:
                    names |= {f"{part}, {boro}", f"{part} {boro}"}
                stem = v12._stem(a["ntaname"])
                whole = [w.strip() for w in stem.split("-") if w.strip()]
                if len(whole) > 1:
                    names |= {"-".join(whole), " ".join(whole)}
                names |= set(v12.SHORT_FORMS.get(stem, []))
    return sorted(names)


def terms(nta, centre, buildings=()):
    """v12's checks, with far_place from far_places."""
    checks = v12.terms(nta, centre)
    checks["far_place"] = [
        r"\b(?:in|located in|located on|heart of|apartment in|unit in) (?:the )?"
        r"(?:beautiful |historic |prime )?"
        + re.escape(n)
        + r"\b(?! (?:ave|avenue|st|street|sq|square|pl|place)\b)"
        for n in far_places(json.loads(Path(nta).read_text()), centre, buildings)
    ]
    return checks


def main(nta, out, cache_root=None):
    frame = data.load(
        data.DATASET_NB7, **({"cache_root": Path(cache_root)} if cache_root else {})
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
            descriptions.NOMAD_SOURCE,
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
        for check, items in terms(nta, centre, f.building[here].unique()).items():
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
