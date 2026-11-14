"""Write a B0 dataset with the stated size of each unit's private outdoor space.

    python -m rentfrontier.b0outdoorsize SRC OUT

L1 reads the six private outdoor types and the private-outdoor feature from the listing
codes, so it prices a 40 sq ft balcony like a 600 sq ft terrace. Many ads state the size in
their description. S7 (`docs/notes/causal-screens-2026-11-13.md`) matched a number of square
feet next to an outdoor word, and its matches also caught building roof decks, gardens shared
by the building and interior sizes. This module reads the size with a tighter match
(`docs/notes/outdoor-size-2026-11-14.md`) and adds two columns to a copy of SRC:

- `outdoor_sqft`: the stated area of the unit's private outdoor space in square feet, or NaN;
- `outdoor_sqft_src`: how the area was read, one of SRC_CODES, or "" with no area.

The text is the description of each listing's latest record, picked as `b0textflags` picks
it. `plain` turns each line break and `<br>` tag into a " | " boundary and each curly
apostrophe into a straight one, then lowercases the text with `cautions.plain`. For each
AREA, a number followed by a unit of square feet, I look for a private outdoor NOUN on
either side:

1. number first: the NOUN starts within NUMBER_FIRST_WORDS words after the unit, and none of
   the words between is in NOT_ADJECTIVE ("500 sq ft wrap-around terrace", "800 sf of
   private outdoor space");
2. noun first: the NOUN ends within NOUN_FIRST_WORDS words before the number, and every word
   between is in CONNECTORS ("a terrace measuring approximately 500 sq ft", "garden (900
   sf)").

Then I drop the area when:

- a word after the unit makes it an interior, lot or building size (INTERIOR, "terrace of
  300 sq ft and 1,200 sq ft of living space" keeps the 300 alone);
- the noun is a place or a unit type ("garden level", "garden apartment", "terrace doors",
  "Carroll Gardens", "Hudson Yards");
- SHARED words come just before or inside the phrase ("the building's 2,000 sq ft garden"),
  with no PRIVATE word after them, or SHARED_AFTER words follow it ("a roof deck of 3,000 sq
  ft for all residents"). The windows stop at a clause break or a connective (`_CLAUSE`);
- a negation comes just before the phrase ("no 300 sq ft balcony");
- its sentence says only some units of the building have such a space (SELECT, "some
  apartments with 440 to 600 sq ft terraces");
- the noun is a roof deck, rooftop or sun deck, or the area comes in a building's
  amenities, and no PRIVATE word comes in the sentence up to the phrase or in the clause
  after it. A roof deck with a size and nothing about its owner is usually the building's.
  The area counts as an amenity when its sentence has an AMENITY word, or when an AMENITY
  word comes in the CONTEXT characters before it with no UNIT_HEAD word after that, as in
  a list under "building features include:". "Private" before an amenity noun ("the
  building's private restaurant") is not a PRIVATE word.

Of the areas left, I drop those outside PLAUSIBLE and count them. An ad with one distinct
value gets it, with the code `number_first`, `noun_first` or `range` (a range "300-400 sq ft"
reads as its midpoint). An ad with several distinct values gets:

- `total`: the largest, when it is stated for outdoor space in general ("1,000 sq ft of
  outdoor space with a 600 sq ft terrace"), carries a total word ("a combined 900 sq ft"), or
  equals the sum of the others within 3%;
- `sum`: otherwise, the sum of the distinct values ("a 300 sq ft terrace and a 200 sq ft
  balcony" reads as 500). A value stated twice counts once.

A sum above PLAUSIBLE's top, and an ad whose areas all fall outside PLAUSIBLE, get NaN with
the code `implausible`. A listing whose latest record has no description longer than
`b0data.MIN_DESCRIPTION` characters gets NaN and "", as do listings missing from the records.
Both columns come from the ad's own text and read no price. They stay text features added
beside the coded fields, since ad text never overrides a coded field (Ben, 2026-10-04).

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with the two columns added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and an `outdoorsize` entry
  giving SRC's path and rows SHA-256, the patterns and windows, the listings read, the
  rows with a description, the rows by code, the rows with an area dropped as implausible,
  and the quantiles of the area.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import cautions
from .b0data import MIN_DESCRIPTION, sha256

PLAUSIBLE = (20.0, 5000.0)
NUMBER_FIRST_WORDS = 4
NOUN_FIRST_WORDS = 6
# How far around a phrase the shared, private and negation checks look, in characters.
WINDOW = 60
SRC_CODES = ("number_first", "noun_first", "range", "total", "sum", "implausible")
DROPS = (
    "interior",
    "not_space",
    "shared",
    "shared_after",
    "negated",
    "select",
    "roof",
    "amenity",
    "implausible",
)

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
# "sq. ft." keeps its last period, while "sq ft." ends a sentence.
_UNIT = (
    r"sq\.\s?(?:ft|feet|foot)\b\.?|s\.f\.?|sq(?:uare)?[\s-]?(?:feet|foot|ft)\b"
    r"|sq\s?/\s?ft\b|sqft\b|sq\.?\s?f\b|sf\b|ft2\b|ft²|sft\b"
)
AREA = re.compile(
    rf"(?<![\d$,.])(?P<n>{_NUM})(?:\s?(?:-|to)\s?(?P<m>{_NUM}))?\s?\+?\s?(?:{_UNIT})"
)
NOUN = re.compile(
    r"\b(?:"
    r"(?P<roof>roof[\s-]?(?:top|deck|terrace|garden)s?|rooftops?|sun[\s-]?decks?)"
    r"|(?P<generic>(?:outdoor|outside|exterior)(?: living| entertaining)? (?:space|area)s?)"
    r"|(?P<terrace>terraces?)|(?P<balcony>balcon(?:y|ies))|(?P<patio>patios?)"
    r"|(?P<garden>(?<!carroll )(?<!kew )(?<!sunnyside )(?<!botanic )(?<!botanical )"
    r"(?<!square )(?<!community )(?<!beer )(?<!forest )gardens?)"
    r"|(?P<yard>(?<!navy )(?<!hudson )(?<!rail )(?<!court )(?:back|front|rear|side)?[\s-]?"
    r"yards?)"
    r"|(?P<deck>decks?)"
    r")\b"
)
# A noun followed by one of these names a floor, a unit type or a door.
_NOT_SPACE = re.compile(
    r"^(?:-facing|-view|[\s-]?(?:level|floor|fl\b|apartment|apt|unit|duplex|triplex|home"
    r"|residence|style|views?|rooms?|suite|entrance|door|doors|condo|co-?op|rental|studio"
    r"|loft|townhouse|brownstone|building|complex|city|district|access|exposure|furniture"
    r"|lighting|1br|2br|3br|bedroom|bed|(?:one|two|three|four)[\s-]bed))\b"
)
# Words that can't stand between the unit and the noun of a number-first area.
NOT_ADJECTIVE = frozenset(
    "and or plus with w in at on near by from to for the a an this that which is are was "
    "has have had does do not no but nor as also including includes include excluding "
    "apartment apt unit home residence loft duplex triplex penthouse condo coop co-op "
    "studio bedroom bedrooms br bed beds bath baths room rooms interior indoor inside "
    "living internal livable liveable layout floor floors level lot building house "
    "townhouse brownstone property footprint space spaces office retail commercial store "
    "total combined".split()
)
# Words that may stand between the noun and the number of a noun-first area.
CONNECTORS = frozenset(
    "of is are that which measuring measures measure measured spanning spans span "
    "totaling totalling totals total at about approximately approx approx. apprx apprx. "
    "appx appx. around roughly nearly almost over more than just under close to a an "
    "whopping alone offering offers with boasting boasts featuring features size sized "
    "additional extra another generous huge massive sprawling spacious large impressive "
    "incredible enormous oversized outdoor private ~ ( : - +/- +".split()
)
_TOKEN = re.compile(r"[a-z][a-z'-]*\.?|\+/-|[~(:+-]|\S")
# A clause break or a connective that ends the checks' windows.
_CLAUSE = re.compile(
    r"[|•·*!?;,]|\.(?:\s|$)|\b(?:and|plus|but|while|whereas|also|as well as|in addition"
    r"|&)\b"
)
_SENTENCE = re.compile(r"[|•·*!?;]|\.(?:\s|$)")
# The optional word between the unit and the interior word is an adjective ("of total
# living space"), so it is neither an outdoor word nor a connective or article ("terrace
# 450 sq ft and interior 930 sq ft", "900 s.f. the apartment features").
INTERIOR = re.compile(
    r"^\s?(?:\)\s?)?(?:of\s|in\s)?"
    r"(?:(?!(?:outdoor|outside|exterior|open-air|al ?fresco|and|or|plus|with|the|a|an|this"
    r"|that|your|its)\b)[a-z'-]+\s)?"
    r"(?:interior|indoor|inside|living|internal|livable|liveable|apartment|apt|unit|home"
    r"|loft|duplex|triplex|penthouse|condo|co-?op|studio|residence|house|townhouse|brownstone|building|lot|parcel|footprint|bedroom"
    r"|one[\s-]bedroom|two[\s-]bedroom|three[\s-]bedroom|[1-6][\s-]?(?:br|bed)|retail"
    r"|commercial|office|store|space inside|floor ?plan|layout)\b"
)
SHARED = re.compile(
    r"\b(?:shared?|sharing|common|communal|residents?'?|tenants?'?|building'?s\b"
    r"|building (?:has|have|features|offers|boasts|includes|provides|amenities)"
    r"|amenit(?:y|ies)|community|public|neighbou?rs?'?|everyone|all units"
    r"|(?<!direct )(?<!private )(?<!exclusive )(?<!granting )(?<!giving )access to)\b"
)
# A sentence with one of these words describes the building, and so does a list item when
# one of them comes in the CONTEXT characters before it with no UNIT_HEAD word after it. An
# area there needs a PRIVATE word in its own scope (`_private_scope`).
AMENITY = re.compile(
    r"\b(?:amenit(?:y|ies)|residents?'?|tenants?'?|lounge|fitness|gym|club|clubhouse"
    r"|concierge|building'?s|building (?:has|have|features|offers|boasts|includes|provides"
    r"|highlights))\b"
)
UNIT_HEAD = re.compile(
    r"\b(?:residence|apartment|unit|home|interior)s? (?:features|highlights|details"
    r"|amenities)\b|\bresidences?\s?[|:]|\bin-?unit\b"
    r"|\b(?:this|the|your)(?: [a-z0-9,'-]+){0,4} (?:apartment|apt|unit|home|residence"
    r"|penthouse|duplex|triplex|loft)\b"
    r"|\b(?:apt|apartment|unit|residence|ph)\.?\s?#?\s?\d+[a-z]?\b"
)
CONTEXT = 300
# An area offered by some units of the building, not by this one.
SELECT = re.compile(
    r"\b(?:some|select|certain|many|most|several|numerous)(?: of (?:the|our))? (?:apartments"
    r"|apts|units|homes|residences|lofts|penthouses)\b|\bin select\b"
)
SHARED_AFTER = re.compile(
    r"\b(?:shared|sharing|common|communal|residents?|tenants?|amenit(?:y|ies)|everyone"
    r"|neighbou?rs?|(?:open|available|accessible) to (?:all|every|the building|the public))\b"
)
# "private" before an amenity noun ("the building's private restaurant") and "exclusively
# for residents" describe the building, so neither counts.
PRIVATE = re.compile(
    r"\b(?:private(?:ly)?(?! (?:dining|restaurant|gym|fitness|lounge|club|event|party"
    r"|screening|cabanas?|pool|spa|theat(?:er|re)|cinema|parking|garage|storage|chef|park)\b)"
    r"|exclusive(?:ly)?(?! (?:for|to) (?:residents|tenants|members|the building)\b)"
    r"|own|your|personal|keyed|penthouse|duplex|triplex|upstairs"
    r"|this (?:unit|apartment|apt|home|residence|penthouse))\b"
    r"|direct access|accessed (?:from|through|via)"
)
NEGATION = re.compile(
    r"\b(?:no|without|lacks?|lacking|zero|nor)(?: (?:a|an|any|the|private|outdoor|real))*"
    r"\s?$"
)
TOTAL = re.compile(r"\b(?:total(?:ing|ling|s)?|combined|in all|altogether|overall)\b")


def plain(text: str) -> str:
    """`text` as `cautions.plain` leaves it, after each line break and `<br>` tag becomes
    " | ", so a match never runs from one line into the next, and each curly apostrophe
    becomes a straight one."""
    text = re.sub(r"\r?\n|<br\s*/?>", " | ", text, flags=re.I)
    return cautions.plain(text.replace("\u2019", "'").replace("\u2018", "'"))


def _number(s: str) -> float:
    return float(s.replace(",", ""))


def _kind(m: re.Match) -> str:
    return next(k for k, v in m.groupdict().items() if v is not None)


def _clause_before(low: str, at: int) -> str:
    s = low[max(0, at - WINDOW) : at]
    cut = [m.end() for m in _CLAUSE.finditer(s)]
    return s[cut[-1] :] if cut else s


def _clause_after(low: str, at: int) -> str:
    s = low[at : at + WINDOW]
    m = _CLAUSE.search(s)
    return s[: m.start()] if m else s


def _sentence(low: str, start: int, end: int) -> str:
    a, b = low[max(0, start - 3 * WINDOW) : start], low[end : end + 3 * WINDOW]
    cut = [m.end() for m in _SENTENCE.finditer(a)]
    m = _SENTENCE.search(b)
    return (a[cut[-1] :] if cut else a) + low[start:end] + (b[: m.start()] if m else b)


def _private_scope(low: str, start: int, end: int) -> str:
    """The sentence up to the end of the phrase, and the clause after it: a PRIVATE word
    later in the sentence ("a 5,000 sq ft roof deck with private cabanas") belongs to
    something else."""
    a = low[max(0, start - 3 * WINDOW) : start]
    cut = [m.end() for m in _SENTENCE.finditer(a)]
    return (a[cut[-1] :] if cut else a) + low[start:end] + _clause_after(low, end)


def _amenity_list(low: str, start: int) -> bool:
    """True when an AMENITY word comes in the CONTEXT characters before `start`, after the
    last UNIT_HEAD word there ("building features include: | 24-hour concierge | 4,000 sq
    ft landscaped terrace")."""
    s = low[max(0, start - CONTEXT) : start]
    amenity = [m.end() for m in AMENITY.finditer(s)]
    unit = [m.end() for m in UNIT_HEAD.finditer(s)]
    return bool(amenity) and amenity[-1] > max(unit, default=-1)


def _number_first(low: str, area: re.Match) -> re.Match | None:
    """The noun of a number-first area: the first NOUN after the unit, within
    NUMBER_FIRST_WORDS words that are all adjectives."""
    after = low[area.end() : area.end() + WINDOW]
    noun = NOUN.search(after)
    if noun is None:
        return None
    gap = _TOKEN.findall(after[: noun.start()])
    if len(gap) > NUMBER_FIRST_WORDS:
        return None
    if any(not re.fullmatch(r"[a-z][a-z'-]*", t) or t in NOT_ADJECTIVE for t in gap):
        return None
    return noun


def _noun_first(low: str, area: re.Match) -> re.Match | None:
    """The noun of a noun-first area: the last NOUN before the number, with at most
    NOUN_FIRST_WORDS CONNECTORS between."""
    before = low[max(0, area.start() - WINDOW) : area.start()]
    nouns = list(NOUN.finditer(before))
    if not nouns:
        return None
    noun = nouns[-1]
    gap = _TOKEN.findall(before[noun.end() :])
    if len(gap) > NOUN_FIRST_WORDS or any(t not in CONNECTORS for t in gap):
        return None
    return noun


def areas(low: str) -> list[dict]:
    """Each AREA of the plain text `low` with a NOUN on either side, as a dict with the
    area's `value` in square feet, its noun's `kind`, its `src` (number_first, noun_first or
    range), whether a TOTAL word comes with it, and `drop`: None for a private outdoor area
    of plausible size, else the first check it fails (one of DROPS)."""
    found = []
    for area in AREA.finditer(low):
        noun = _number_first(low, area)
        if noun is not None:
            src, start = "number_first", area.start()
            end = area.end() + noun.end()
            rest, interior = low[end:], False
        else:
            noun = _noun_first(low, area)
            if noun is None:
                continue
            src = "noun_first"
            base = max(0, area.start() - WINDOW)
            start, end = base + noun.start(), area.end()
            rest = low[base + noun.end() :]
            interior = bool(INTERIOR.match(low[area.end() :]))
        kind = _kind(noun)
        phrase = low[start:end]
        before, after = _clause_before(low, start), _clause_after(low, end)
        near = before + " " + phrase
        shared = [m.end() for m in SHARED.finditer(near)]
        sentence = _sentence(low, start, end)
        private = bool(PRIVATE.search(_private_scope(low, start, end)))
        amenity = bool(AMENITY.search(sentence)) or _amenity_list(low, start)
        n = _number(area["n"])
        if area["m"] is not None:
            m = _number(area["m"])
            value, src = ((n + m) / 2, "range") if n < m else (m, src)
        else:
            value = n
        checks = {
            "interior": interior,
            "not_space": bool(_NOT_SPACE.match(rest)),
            "shared": bool(shared) and not PRIVATE.search(near[shared[-1] :]),
            "shared_after": bool(SHARED_AFTER.search(after)),
            "negated": bool(NEGATION.search(low[max(0, start - WINDOW) : start])),
            "select": bool(SELECT.search(sentence)),
            "roof": kind == "roof" and not private,
            "amenity": amenity and not private,
            "implausible": not PLAUSIBLE[0] <= value <= PLAUSIBLE[1],
        }
        found.append(
            {
                "value": value,
                "kind": kind,
                "src": src,
                "total": bool(TOTAL.search(near)),
                "drop": next((k for k, v in checks.items() if v), None),
            }
        )
    return found


def combine(found: list[dict]) -> tuple[float, str]:
    """The area and code of an ad from its `areas`, as the module's docstring gives them."""
    ok = [f for f in found if f["drop"] is None]
    if not ok:
        bad = any(f["drop"] == "implausible" for f in found)
        return (math.nan, "implausible") if bad else (math.nan, "")
    values = sorted({round(f["value"], 1) for f in ok})
    if len(values) == 1:
        return values[0], ok[0]["src"]
    big, rest = values[-1], sum(values[:-1])
    tops = [f for f in ok if round(f["value"], 1) == big]
    if any(f["kind"] == "generic" or f["total"] for f in tops) or abs(big - rest) <= (
        0.03 * big
    ):
        return big, "total"
    total = float(sum(values))
    return (total, "sum") if total <= PLAUSIBLE[1] else (math.nan, "implausible")


def outdoor_area(text: str) -> tuple[float, str, int]:
    """The area and code for a description `text`, and how many of its private outdoor
    areas fell outside PLAUSIBLE. A text no longer than MIN_DESCRIPTION characters gets NaN
    and ""."""
    if not isinstance(text, str) or len(text.lower()) <= MIN_DESCRIPTION:
        return math.nan, "", 0
    found = areas(plain(text))
    value, src = combine(found)
    return value, src, sum(f["drop"] == "implausible" for f in found)


def latest_areas(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each listing in `ids` with a record in the records file `path`, whether the
    description of its latest record is longer than MIN_DESCRIPTION characters, and
    `outdoor_area` of that description. The latest record is picked as
    `b0textflags.latest_flags` picks it."""
    seen: dict[str, tuple] = {}
    file = pq.ParquetFile(path)
    names = set(file.schema_arrow.names)
    times = [c for c in ("collected_at", "last_collected_at") if c in names]
    for group in range(file.num_row_groups):
        head = file.read_row_group(group, columns=["listing_id", *times])
        lid = [str(x) for x in head["listing_id"].to_pylist()]
        at = [
            max((t for t in ts if t is not None), default=None)
            for ts in zip(*(head[c].to_pylist() for c in times))
        ]
        keep = [
            i in ids and t is not None and (i not in seen or seen[i][0] < t)
            for i, t in zip(lid, at)
        ]
        if not any(keep):
            continue
        raws = file.read_row_group(group, columns=["raw_listing_json"]).filter(
            pa.array(keep)
        )
        rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
        for (i, t), raw in zip(rows, raws["raw_listing_json"].to_pylist()):
            if i not in seen or seen[i][0] < t:
                listing = json.loads(raw) if raw else {}
                text = str(listing.get("description") or "")
                known = len(text.lower()) > MIN_DESCRIPTION
                seen[i] = (t, known, *outdoor_area(text))
        del raws
    return pd.DataFrame(
        [(i, *v[1:]) for i, v in seen.items()],
        columns=["listing_id", "known", "outdoor_sqft", "outdoor_sqft_src", "dropped"],
    ).set_index("listing_id")


def outdoorsize(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    lid = frame.listing_id.astype(str)
    read = latest_areas(Path(records["path"]), set(lid))
    known = lid.map(read.known).eq(True).to_numpy()
    frame["outdoor_sqft"] = lid.map(read.outdoor_sqft).astype("float64").to_numpy()
    frame["outdoor_sqft_src"] = lid.map(read.outdoor_sqft_src).fillna("").to_numpy(str)
    dropped = lid.map(read.dropped).fillna(0).to_numpy() > 0
    # OUT is made after the read of the records, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    sqft = frame.outdoor_sqft.dropna().to_numpy()
    codes = frame.outdoor_sqft_src.value_counts()
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "outdoorsize": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "the stated private outdoor area in the description of the "
            "listing's latest record (docs/notes/outdoor-size-2026-11-14.md)",
            "patterns": {
                "area": AREA.pattern,
                "noun": NOUN.pattern,
                "not_space": _NOT_SPACE.pattern,
                "not_adjective": sorted(NOT_ADJECTIVE),
                "connectors": sorted(CONNECTORS),
                "interior": INTERIOR.pattern,
                "shared": SHARED.pattern,
                "shared_after": SHARED_AFTER.pattern,
                "amenity": AMENITY.pattern,
                "unit_head": UNIT_HEAD.pattern,
                "select": SELECT.pattern,
                "private": PRIVATE.pattern,
                "negation": NEGATION.pattern,
                "total": TOTAL.pattern,
                "clause": _CLAUSE.pattern,
                "sentence": _SENTENCE.pattern,
            },
            "windows": {
                "number_first_words": NUMBER_FIRST_WORDS,
                "noun_first_words": NOUN_FIRST_WORDS,
                "window": WINDOW,
                "context": CONTEXT,
            },
            "plausible": list(PLAUSIBLE),
            "listings_read": len(read),
            "rows_described": int(known.sum()),
            "rows_with_area": int(len(sqft)),
            "rows_by_code": {c: int(codes.get(c, 0)) for c in SRC_CODES},
            "rows_with_an_area_dropped_as_implausible": int(dropped.sum()),
            "area_quantiles": {
                str(q): float(np.quantile(sqft, q)) if len(sqft) else None
                for q in (0.1, 0.25, 0.5, 0.75, 0.9)
            },
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(outdoorsize(args.src, args.out)["outdoorsize"], indent=2))


if __name__ == "__main__":
    main()
