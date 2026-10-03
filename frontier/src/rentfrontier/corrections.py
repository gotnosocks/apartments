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

Version 2 of both (`bedrooms-ad-v2`, `baths-ad-v2`; `--version 2`) is
stricter: half of the unit's other listings must record the ad's count; ads
placed in the other neighbourhood or on another avenue, with a bedroom range
or a rec room anywhere, with an adjectival count ("3 true bedrooms") that
disagrees, or a bare count on a unit with no other listing are left alone;
bath counts must fit the ad's own bedrooms.

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

from . import data, descriptions

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


def majority(frame: pd.DataFrame, field: str, value: pd.Series) -> pd.Series:
    """v2's corroboration: whether each row's unit, with units joined as
    unit-labels-v2 joins them, has no other listing, or at least half of its
    other listings record `value` for `field`."""
    units = data.merge_unit_aliases(frame).unit_id
    recorded = pd.to_numeric(frame[field], errors="coerce")
    others = units.groupby(units).transform("size") - 1
    counts = pd.Series(list(zip(units, recorded)), index=frame.index).value_counts()
    agree = pd.Series(list(zip(units, value)), index=frame.index).map(counts)
    return (others == 0) | (2 * agree.fillna(0) >= others)


# v2: an ad that places the apartment in the other neighbourhood, or on another
# avenue than its building's, was written for another apartment.
OTHER_NEIGHBOURHOOD = {
    "Chelsea": re.compile(r"(?:in|heart of) (?:the )?(?:west|greenwich) village"),
    "West Village": re.compile(r"(?:in|heart of) (?:the )?(?:west )?chelsea\b"),
}
ORDINALS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9,
    "tenth": 10, "10th": 10, "eleventh": 11, "11th": 11,
}  # fmt: skip
ON_AVENUE = re.compile(r"\bon (\w+) ave(?:nue)?\b")


def placed_elsewhere(frame: pd.DataFrame, text: pd.Series) -> pd.Series:
    """Whether an ad names the other neighbourhood as the apartment's, or puts
    it on another avenue than the one its building's slug ("202-8-avenue")
    names."""
    hood = pd.Series(
        [
            bool(OTHER_NEIGHBOURHOOD[n].search(t))
            if n in OTHER_NEIGHBOURHOOD
            else False
            for n, t in zip(frame.neighbourhood, text)
        ],
        index=frame.index,
    )
    avenue = frame.building.str.extract(r"^\d+-(\d+)-avenue")[0].astype(float)

    def other_avenue(t, a):
        named = {ORDINALS.get(w) for w in ON_AVENUE.findall(t)} - {None}
        return bool(named) and not np.isnan(a) and a not in named

    av = pd.Series(
        [other_avenue(t, a) for t, a in zip(text, avenue)], index=frame.index
    )
    return hood | av


# v2: counts with an adjective ("3 true bedrooms", "two king-size bedrooms")
# must agree with the others; a range anywhere in the ad ("3- 4 bedroom") or a
# rec room hedges it; a bare "3-bed" ad on a unit with no other listing is too
# thin to correct.
COUNT_V2 = re.compile(
    r"(?<![\d.])\b(one|two|three|four|five|[1-5])[- ]{0,2}"
    r"(?:true|real|full|actual|separate|large|king[- ]?size[d]?|queen[- ]?size[d]?)"
    r"[- ]bed(?:room)?s?\b"
)
DOUBT_V2 = re.compile(
    r"\d ?[-–—/] ?\d ?(?:bed|br|bd)|\b(?:one|two|three|four) ?[-–—] ?(?:two|three|"
    r"four|five) (?:bed|br)|rec(?:reation)? room|media room|family room"
)


def stated_counts_v2(text: str) -> set:
    """The bedroom counts an ad states with an adjective ("3 true bedrooms")."""
    return {float(WORDS.get(m.group(1), m.group(1))) for m in COUNT_V2.finditer(text)}


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


def bedroom_corrections(
    frame: pd.DataFrame, text: pd.Series, version: int = 1
) -> pd.DataFrame:
    """Rows whose ad clearly states another bedroom count than the record, the
    unit's other listings not contradicting it: audit_id, building, unit_id,
    recorded, corrected and the first sentence. Version 2 also needs half of
    the unit's other listings (units joined as unit-labels-v2) to record the
    ad's count, and refuses ads placed in the other neighbourhood or on
    another avenue."""
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
    if version >= 2:
        units = data.merge_unit_aliases(frame).unit_id
        alone = units.groupby(units).transform("size").eq(1)
        clear &= (
            majority(frame, "bedrooms", stated)
            & ~placed_elsewhere(frame, text)
            & ~text.str.contains(DOUBT_V2)
            & ~(alone & text.str.strip().str.len().lt(20))
            & text.map(lambda t: stated_counts_v2(t) <= {s for s in stated_counts(t)})
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


def bathroom_corrections(
    frame: pd.DataFrame, text: pd.Series, version: int = 1
) -> pd.DataFrame:
    """Rows whose ad states more bathrooms than the record: one count in the
    whole ad, above the record's full baths plus half its half baths and not
    their plain sum (an ad that counts a half bath as a bath), with no shared,
    powder-room, hedging or other-area words, the unit's other listings, if
    any, recording that count. Ads that state fewer are left alone: they
    often leave a half bath out. The ad's count sets the full and half baths.
    Version 2 also needs half of the unit's other listings to record the count,
    refuses ads placed elsewhere, ads whose own bedroom counts leave out the
    record's, and more than one bath beyond the bedrooms (a studio with two
    baths, a one-bedroom with 2.5): signs of another apartment's ad."""
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
    if version >= 2:
        beds = pd.to_numeric(frame.bedrooms, errors="coerce")
        # The ad's own bedroom counts must include the record's: otherwise
        # the ad (and its bath count) may be another apartment's.
        beds_agree = pd.Series(
            [not c or b in c for c, b in zip(text.map(stated_counts), beds)],
            index=frame.index,
        )
        clear &= (
            majority(frame, "bathrooms", stated)
            & ~placed_elsewhere(frame, text)
            & (stated <= beds + 1)
            & beds_agree
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


def _git(*args) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("kind", choices=["bedrooms", "baths"])
    parser.add_argument("--version", type=int, choices=[1, 2], default=1)
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
    build = {"bedrooms": bedroom_corrections, "baths": bathroom_corrections}
    rows = build[args.kind](frame, text, version=args.version)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.writelines(
            json.dumps(r, ensure_ascii=False) + "\n" for r in rows.to_dict("records")
        )
    provenance = {
        "rule": f"{args.kind}-ad-v{args.version}",
        "dataset": frame.attrs["dataset"],
        "dataset_observations_sha256": frame.attrs["source_sha256"],
        "descriptions": {str(p): data.sha256(p) for p in sources},
        "commit": _git("rev-parse", "HEAD"),
        "rows": len(rows),
        "by_change": {
            f"{a:g}->{b:g}": int(n)
            for (a, b), n in rows.groupby(["recorded", "corrected"]).size().items()
        },
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
