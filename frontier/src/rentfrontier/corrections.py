"""Corrections overlay: listing fields the listing's own ad contradicts,
corrected in place by a data rule (`data.DATA_RULES`), one JSON line per row
with the ad's words as evidence. Rows are kept; only the field changes.

Bedrooms (`bedrooms-ad-v1`): the ad's first sentence states a bedroom count
("Sunny 2-bedroom ...", "Studio ..."), one more or one fewer than the record,
every count the ad states anywhere is that count, the ad has no flex,
conversion or other-area words and no hedge ("or", "plus", a range) in its
first sentence, and the unit's other listings, if any, record that count too.
Rows a quarantine already drops are left to it. The ad's count replaces the
record's:

    python -m rentfrontier.corrections bedrooms --out config/corrections/<file>

reads the analytical dataset and both description evidence files
(`descriptions.SOURCE`, `descriptions.WV_SOURCE`) and writes the file and its
provenance beside it. Refuses a dirty tree.

Floors (`floors-ad-v1`, `... floors --out ...`): rows with no floor get the
floor their unit's other listings record, or the one its ads place the
apartment on (`floor_corrections`).

Baths (`baths-ad-v1`, `... baths --out ...`): the ad states one bathroom
count, more than the record's full baths plus half its half baths and not
their plain sum, with no shared, powder-room, hedging or other-area words; the
unit's other listings, if any, record that count; rows a quarantine drops are
left to it. Its count sets the full and half baths.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, descriptions, features

# A bedroom count ("2-bedroom", "two  bed", "3br", "1 bdrm", "studio"); a half
# count ("1.5 bedroom") is none.
COUNT = re.compile(
    r"(?<![\d.])\b(?:(one|two|three|four|five|[1-5])[- ]{0,2}"
    r"(?:bed(?:room)?s?|bdrms?|br|bd)\b|(studio)\b)"
)
WORDS = {"studio": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
# A sentence ends at . ! or ? before a space, or at a line break.
SENTENCE_END = re.compile(r"(?<=[.!?])\s|[\r\n]|<br\s*/?>")
# Words anywhere in the ad that make its bedroom count a matter of use, not of
# rooms: flex and converted rooms, offices, dens, nooks, alcoves.
ROOM_USE = re.compile(
    r"\bflex|convert|could be|can be|set up as|used as|use as|utiliz|\bjr|"
    r"junior|alcove|offic|\bden\b|study|guest|nursery|baby|bonus|"
    r"extra (?:room|bed)|additional (?:room|bed)|interior room|small bedroom|"
    r"sleep|nook|loft|upper level|two level|split|potential|possible|partition|"
    r"divid|windowless|wall|roommate|room in a|"
    r"\b(?:two|three|2|3)[- ]room|\bconv\b|"
    r"(?:art|artist|yoga|recording|dance|photo|music|design|fitness|exercise) studio"
)
# Words in the first sentence that hedge its count: "or", "plus", ranges and
# lists of counts, sizes ("the size of a one bedroom").
HEDGE = re.compile(
    r"\bor\b|\bplus\b|\+|\d ?[-–—/] ?\d|\d,? (?:and|&) ?\d|\d, ?\d|"
    r"\b(?:one|two|three|four|\d) to (?:two|three|four|five|\d)\b|"
    r"size of|as (?:large|big) as|large as|equivalent|representation|fits a|"
    r"duplex|triplex|currently"
)

# Places outside Chelsea and the West Village: an ad written for another
# apartment.
ELSEWHERE = re.compile(
    r"brooklyn|bushwick|williamsburg|queens|astoria|bronx|harlem|"
    r"upper (?:east|west)|jersey|hoboken"
)
TAG = re.compile(r"<(?!br\b)[^>]*>")


def plain(text: str) -> str:
    """Ad text with HTML entities decoded and tags other than <br> removed."""
    return TAG.sub(" ", html.unescape(text))


def corroborated(frame: pd.DataFrame, field: str, value: pd.Series) -> pd.Series:
    """Whether each row's unit has no other listing, or another of its listings
    records `value` for `field`."""
    recorded = pd.to_numeric(frame[field], errors="coerce")
    others = frame.groupby("unit_id").audit_id.transform("size") - 1
    keys = pd.Series(list(zip(frame.unit_id, recorded)), index=frame.index)
    counts = keys.value_counts()
    wanted = pd.Series(list(zip(frame.unit_id, value)), index=frame.index)
    return (others == 0) | wanted.map(counts).fillna(0).gt(0)


def _count(m: re.Match) -> float:
    word = m.group(1) or m.group(2)
    return float(WORDS.get(word, word))


def first_sentence(text: str) -> str:
    return SENTENCE_END.split(text.strip(), maxsplit=1)[0][:200].lower()


def stated_counts(text: str) -> set:
    """Every bedroom count the ad states, in any sentence."""
    return {_count(m) for m in COUNT.finditer(text.lower())}


def first_count(text: str) -> float:
    """The bedroom count the ad's first sentence states, or NaN."""
    m = COUNT.search(first_sentence(text))
    return _count(m) if m else np.nan


def bedroom_corrections(frame: pd.DataFrame, text: pd.Series) -> pd.DataFrame:
    """Rows whose ad clearly states another bedroom count than the record, the
    unit's other listings not contradicting it: audit_id, building, unit_id,
    recorded, corrected and the first sentence."""
    text = text.fillna("").map(plain).str.lower()
    stated = text.map(first_count)
    recorded = pd.to_numeric(frame.bedrooms, errors="coerce")
    counts = text.map(stated_counts)
    first = text.map(first_sentence)
    clear = (
        stated.notna()
        & recorded.notna()
        & (stated - recorded).abs().eq(1)
        & counts.map(len).eq(1)
        & ~text.str.contains(ROOM_USE)
        & ~text.str.contains(ELSEWHERE)
        & ~first.str.contains(HEDGE)
        & corroborated(frame, "bedrooms", stated)
        & ~frame.audit_id.isin(data.dropped_rows())
    )
    rows = frame.loc[clear, ["audit_id", "building", "unit_id"]].copy()
    rows["action"] = "correct_bedrooms"
    rows["field"] = "bedrooms"
    rows["recorded"] = recorded[clear].astype(float)
    rows["corrected"] = stated[clear].astype(float)
    rows["evidence"] = first[clear]
    return rows.reset_index(drop=True)


# A bathroom count ("2 bath", "1.5 baths", "two full bathrooms", "2ba").
BATHS = re.compile(
    r"(?<![\d.])\b(one|two|three|four|[1-4])(?:\.(5))?[- ]{0,2}(?:full )?"
    r"(?:bath(?:room)?s?|ba)\b"
)
# Words that make a bath count a matter of sharing or of counting a half bath.
BATH_HEDGE = re.compile(
    r"\bor\b|\bplus\b|\+|shared|share|common|hall bath|down the hall|"
    r"powder|half|\d ?[-/] ?\d ?(?:bath|ba)|\d,? (?:and|&) ?\d|"
    r"also (?:for rent|available)|other (?:units?|apartments?)"
)


def bath_counts(text: str) -> set:
    """Every bathroom count the ad states."""
    return {
        float(WORDS.get(m.group(1), m.group(1))) + (0.5 if m.group(2) else 0.0)
        for m in BATHS.finditer(text.lower())
    }


def bath_sentence(text: str) -> str:
    """The first sentence of the ad that states a bathroom count."""
    for sentence in SENTENCE_END.split(text.strip().lower()):
        if BATHS.search(sentence):
            return sentence.strip()[:200]
    return ""


def bathroom_corrections(frame: pd.DataFrame, text: pd.Series) -> pd.DataFrame:
    """Rows whose ad states more bathrooms than the record: one count in the
    whole ad, above the record's full baths plus half its half baths and not
    their plain sum (an ad that counts a half bath as a bath), with no shared,
    powder-room, hedging or other-area words, the unit's other listings, if
    any, recording that count. Ads that state fewer are left alone: they
    often leave a half bath out. The ad's count sets the full and half baths."""
    text = text.fillna("").map(plain).str.lower()
    counts = text.map(bath_counts)
    stated = counts.map(lambda c: next(iter(c)) if len(c) == 1 else np.nan)
    full = pd.to_numeric(frame.full_baths, errors="coerce")
    half = pd.to_numeric(frame.half_baths, errors="coerce").fillna(0)
    recorded = full + 0.5 * half
    clear = (
        stated.notna()
        & full.notna()
        & (stated > recorded)
        & (stated != full + half)
        & ~text.str.contains(BATH_HEDGE)
        & ~text.str.contains(ELSEWHERE)
        & corroborated(frame, "bathrooms", stated)
        & ~frame.audit_id.isin(data.dropped_rows())
    )
    rows = frame.loc[clear, ["audit_id", "building", "unit_id"]].copy()
    rows["action"] = "correct_baths"
    rows["field"] = "baths"
    rows["recorded"] = recorded[clear].astype(float)
    rows["corrected"] = stated[clear].astype(float)
    rows["full_baths"] = np.floor(stated[clear]).astype(int)
    rows["half_baths"] = (stated[clear] % 1 > 0).astype(int)
    rows["evidence"] = text[clear].map(bath_sentence)
    return rows.reset_index(drop=True)


# Floors (`floors-ad-v1`): rows with no floor (no listed floor, no plausible
# label floor) get one from evidence about that apartment: a floor its other
# listings record, or a phrase whose subject is the apartment itself. Ads for
# multi-level units are left out (their floors are levels), and evidence is
# pooled per unit, so every listing of an apartment gets the same floor.
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
}  # fmt: skip
_NTH = r"(\d{1,2})(?:st|nd|rd|th)|(" + "|".join(ORDINALS) + ")"
# The apartment as a sentence's subject: "the apartment", "this sunny one
# bedroom", "unit 4b"; not "the laundry room" or "the second bedroom".
_SUBJECT = (
    r"(?:(?<!another )(?<!identical )(?<!storage )(?<!similar )"
    r"\b(?:apartment|apt|unit|residence|home)\b(?: #?[a-z]?\d{1,2}[a-z]?\b)?"
    r"|\bthis (?:\w+ ){0,3}?(?:apartment|apt|unit|home|residence|studio|loft|"
    r"one[- ]bedroom|two[- ]bedroom|\d ?(?:bed(?:room)?|br)))"
)
_ON = r"(?: is| sits)? (?:located |situated )?on the "
APARTMENT_FLOOR = re.compile(
    rf"{_SUBJECT}{_ON}(?:{_NTH}) (?:floor|fl)\b|\b(?:{_NTH})[- ](?:floor|fl)\.? "
    rf"(?:apartment|apt|unit|studio|walk[- ]?up|loft|home|residence|corner|rear|"
    rf"front|(?:one|two|three|[123])[- ]?(?:bed(?:room)?|br)\b)"
)
TOP_FLOOR = re.compile(
    rf"{_SUBJECT}{_ON}top floor\b|\btop[- ]floor (?:apartment|apt|unit|studio|loft|"
    r"home|residence|walk[- ]?up|penthouse|(?:one|two|three|[123])[- ]?"
    r"(?:bed(?:room)?|br)\b)"
)
GROUND_FLOOR = re.compile(
    rf"{_SUBJECT}{_ON}ground floor\b|\bground[- ]floor (?:apartment|apt|unit|studio|"
    r"loft|(?:one|two|[12])[- ]?(?:bed(?:room)?|br)\b)|\bgarden[- ](?:level|"
    r"apartment|apt)\b"
)
# Units whose ads give levels, not the apartment's floor.
MULTI_LEVEL = re.compile(
    r"duplex|triplex|multi[- ]?level|split[- ]level|\b(?:two|three|four|[234])[- ]"
    r"(?:level|stor(?:y|ey))s?\b|\blevels\b|upstairs|downstairs|"
    r"(?:entire|whole) (?:town ?)?house|single[- ]family|"
    r"\b(?:five|six|seven|[5-7])[- ]?bed(?:room)?s?\b"
)
BELOW_GROUND = re.compile(r"basement|below (?:grade|street)|lower level|sunken")


def floor_evidence(text: str, height: float) -> tuple[float, str, str]:
    """(floor, source, sentence) from the first sentence of an ad that places
    the apartment: "ad" for "located on the 4th floor" or "third floor
    walk-up", "top" for "top floor" (the building's height), "ground" for
    ground floor or garden level (1). NaN when the ad places it nowhere, on two
    floors, or is for a multi-level unit."""
    if MULTI_LEVEL.search(text):
        return np.nan, "", ""
    found = []
    for sentence in SENTENCE_END.split(text.strip()):
        for m in APARTMENT_FLOOR.finditer(sentence):
            n, word = m.group(1) or m.group(3), m.group(2) or m.group(4)
            found.append((float(n) if n else float(ORDINALS[word]), "ad", sentence))
        if TOP_FLOOR.search(sentence) and height >= 1:
            found.append((float(np.floor(height)), "top", sentence))
        if GROUND_FLOOR.search(sentence) and not BELOW_GROUND.search(text):
            found.append((1.0, "ground", sentence))
    if not found or len({f for f, _, _ in found}) > 1:
        return np.nan, "", ""
    floor, source, sentence = found[0]
    return floor, source, sentence.strip()[:200]


def floor_corrections(
    frame: pd.DataFrame, text: pd.Series, floor: pd.Series, height: pd.Series
) -> pd.DataFrame:
    """Rows with no floor (`floor` NaN, as the features read it) whose
    apartment the evidence places, pooled over the unit's listings (units
    joined as unit-labels-v2): the floor its listings record, else the floor
    its ads place it on (`floor_evidence`). The unit's floors and evidence
    must agree within one floor and, where MapPLUTO has the building's
    height, be at most one above it. Every unknown-floor listing of such a
    unit gets the floor."""
    text = text.fillna("").map(plain).str.lower()
    units = data.merge_unit_aliases(frame).unit_id.fillna(frame.audit_id)
    found = pd.DataFrame(
        [floor_evidence(t, h) for t, h in zip(text, height)],
        index=frame.index,
        columns=["floor", "source", "sentence"],
    )
    pool = pd.concat([floor, found.floor]).groupby(pd.concat([units, units]))
    spread = pool.max() - pool.min()
    recorded = floor.groupby(units).agg(
        lambda s: s.mode().min() if s.notna().any() else np.nan
    )
    # The unit's floor from its ads: the most common floor of its best kind
    # of evidence (ad over top over ground), the lowest on a tie.
    rank = found.source.map({"ad": 0, "top": 1, "ground": 2})
    best = found[found.floor.notna()].assign(rank=rank, unit=units)
    best = best[best["rank"].eq(best.groupby("unit")["rank"].transform("min"))]
    from_ad = best.groupby("unit").floor.agg(lambda s: s.mode().min())
    first = (
        best[best.floor.eq(best.unit.map(from_ad))]
        .sort_values(["unit", "floor"], kind="stable")
        .drop_duplicates("unit")
        .set_index("unit")
    )
    unit_floor = recorded.fillna(from_ad)
    corrected = units.map(unit_floor)
    # A row's own evidence sets its own floor (within the unit's spread).
    own_floor = found.floor.where(units.map(recorded).isna())
    corrected = own_floor.fillna(corrected)
    limit = height + 1
    clear = (
        floor.isna()
        & corrected.ge(1)
        & units.map(spread).le(1)
        & ~(limit.notna() & corrected.gt(limit))
        & ~frame.audit_id.isin(data.dropped_rows())
    )
    by_unit = first
    has_record = units.map(recorded).notna()
    source = pd.Series(
        np.where(
            has_record,
            "unit",
            found.source.where(found.floor.notna(), units.map(by_unit.source)),
        ),
        index=frame.index,
    )
    own = found.floor.notna() & ~has_record
    evidence = pd.Series(
        np.where(
            has_record,
            "the unit's other listings record floor "
            + corrected.fillna(0).astype(int).astype(str),
            np.where(
                own,
                found.sentence,
                "another listing of this apartment: "
                + units.map(by_unit.sentence).fillna(""),
            ),
        ),
        index=frame.index,
    )
    rows = frame.loc[clear, ["audit_id", "building", "unit_id"]].copy()
    rows["action"] = "correct_floor"
    rows["field"] = "listed_floor"
    rows["recorded"] = None
    rows["corrected"] = corrected[clear].astype(int)
    rows["source"] = source[clear]
    rows["evidence"] = evidence[clear]
    return rows.reset_index(drop=True)


def _git(*args) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("kind", choices=["bedrooms", "baths", "floors"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    frame = data.load()
    sources = (descriptions.SOURCE, descriptions.WV_SOURCE)
    token = descriptions.SOURCES.set(sources)
    try:
        text = descriptions.attach(frame)
    finally:
        descriptions.SOURCES.reset(token)
    if args.kind == "floors":
        token = features._LOTS.set((features.NB_REGISTRY_FILE, features.NB_PLUTO_FILE))
        try:
            floor = features.row_floor(frame)
            height = pd.to_numeric(
                features.building_lots(frame).numfloors, errors="coerce"
            ).set_axis(frame.index)
        finally:
            features._LOTS.reset(token)
        rows = floor_corrections(frame, text, floor, height)
    else:
        build = {"bedrooms": bedroom_corrections, "baths": bathroom_corrections}
        rows = build[args.kind](frame, text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.writelines(
            json.dumps(r, ensure_ascii=False) + "\n" for r in rows.to_dict("records")
        )
    provenance = {
        "rule": f"{args.kind}-ad-v1",
        "dataset": frame.attrs["dataset"],
        "dataset_observations_sha256": frame.attrs["source_sha256"],
        "descriptions": {str(p): data.sha256(p) for p in sources},
        "commit": _git("rev-parse", "HEAD"),
        "rows": len(rows),
        "by_change": (
            {k: int(n) for k, n in rows.source.value_counts().items()}
            if args.kind == "floors"
            else {
                f"{a:g}->{b:g}": int(n)
                for (a, b), n in rows.groupby(["recorded", "corrected"]).size().items()
            }
        ),
    }
    args.out.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print(f"{len(rows)} rows -> {args.out}")
    print(
        np.unique(frame.loc[frame.audit_id.isin(rows.audit_id)].building).size,
        "buildings",
    )


if __name__ == "__main__":
    main()
