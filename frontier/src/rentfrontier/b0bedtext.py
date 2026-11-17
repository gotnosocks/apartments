"""Write a B0 dataset with the bedroom count each ad's text states beside the coded count.

    python -m rentfrontier.b0bedtext SRC OUT

On 2026-11-16 a screen of L2's held-out ads (`docs/notes/bed-text-2026-11-16.md`) found the
ads L2 prices far too high often coded with a bedroom more than their text describes. Some
are flex units: "flex 2", "junior 1", "convertible 3", a one-bedroom with a pressurized
wall. Others state a smaller size outright while the coded field holds a larger one: a
"studio duplex" coded as a one-bedroom, a "1 bed + home office" coded as a two-bedroom.

I read the description of each listing's latest record, as `b0outdoorsize` does, and add
four columns to a copy of SRC, with every column of SRC left as it was:

- `bed_text`: the size the text states for the unit, NaN where it states none, states
  sizes on both sides of the coded count, or lists sizes of several units. Where several
  stated sizes lie below the coded count I keep the largest, and where they lie above it
  the smallest, so the column holds the stated size nearest the coded one.
- `bed_text_fewer`: every stated size is below the row's coded `bedrooms`.
- `bed_text_more`: every stated size is above the coded count and the text has no flex
  wording.
- `bed_flex_at`: the text has flex wording for a count equal to the coded one, so the coded
  count includes a room made by a wall, an alcove or a conversion.

A listing whose latest record has no description longer than `b0data.MIN_DESCRIPTION`
characters gets NaN and false. The reader takes the text and the coded bedroom count and
nothing else, so no rent enters a column.

The reader works in three passes over the lowercased text:

1. FLEX finds flex wording and the count it carries, where it carries one. "Junior 4"
   counts as 2 and "junior 1", "alcove studio" and "sleeping alcove" as 1. I blank each
   match so the next pass does not read "flex 2 bedroom" as a plain two-bedroom.
2. BED finds a count before a bedroom word. I sort each match by its surroundings:
   - a list of different counts ("1, 2 and 3 bedrooms"), a count after "studios to", a
     plural ("1 bedrooms", "two-bedrooms") or wording about other units goes to the offered
     sizes;
   - a room of the unit ("one bedroom has a king bed", "the second bedroom") is skipped,
     and so is a count right after "a", "an" or "the" ("is a 3 bedroom"), at some cost in
     ads read;
   - the rest are the unit's own stated sizes.
3. STUDIO finds "studio" as a size, which needs a describing word before it or a unit word
   after it. An amenity ("yoga studio", "art studio") or a firm ("designed by ... studio")
   is skipped.

A text with any offered size gets no `bed_text`, since its sizes may belong to other units.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .b0data import MIN_DESCRIPTION, sha256

COLUMNS = ("bed_text", "bed_text_fewer", "bed_text_more", "bed_flex_at")
# How far before and after a match the surrounding checks look, in characters.
BEFORE, AFTER = 70, 60
# A stated size this close to blanked flex wording belongs to that wording.
NEAR_FLEX = 12

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―"), "-")
_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "a": 1,
    "single": 1,
}
_N = r"(?:[1-6]|one|two|three|four|five|six)"
_BEDW = r"(?:bed ?rooms?|beds?|br'?s?|bd'?s?|bdrm?s?|bedrms?)"
_SEP = r"(?:- and |- or |-, |- to | ?, ?| ?& ?| and | ?/ ?| or | to |, and |, or | ?- ?| ?\+ ?)"

FLEX = re.compile(
    rf"\b(?:flex(?:ed|ible)?|conv(?:erted|ertible|ertable|\.)?|junior|jr\.?)[- ]?(?P<a>{_N})\b"
    r"(?! ?(?:min|block|month|year|car|person|people|closet|bath|famil|unit|stor|floor|\.5|1/2))"
    rf"|\bconvert(?:ed|s|ible|able)? (?:in)?to (?:an? |a true |a real )?(?:\w+ )?"
    rf"(?P<b>{_N})[- ]?{_BEDW}"
    rf"|\b(?P<c>{_N})[- ]?(?:{_BEDW})?[ /-]*(?:flex|convertible|convertable|conversion)\b"
    rf"|\bflex(?:ed|ible)? (?:to|into|as|for) (?:an? )?(?:\w+ )?(?P<d>{_N})[- ]?{_BEDW}"
    rf"|\b(?:convertible|convertable|converted|flex|junior|jr\.?|alcove)[- ]"
    rf"(?P<e>{_N}|a|single)?[- ]?{_BEDW}"
    r"|\bjunior[- ](?P<j>4|four|1|one)\b|\bjr\.?[- ]?(?P<k>4|1)\b"
    r"|\b(?:temporary|pressurized|flex|partition|bookshelf) walls?\b|\bwall(?:ed)? up\b"
    r"|\balcove studio\b|\bsleep(?:ing)? (?:alcove|area|nook)\b"
    r"|\bhome office ?/ ?(?:2nd|second|3rd|third) bed"
)
BED = re.compile(
    rf"(?<![\d.$,#-])(?<!\d/)(?<!\d )(?P<list>(?:{_N}{_SEP}){{0,4}})(?P<n>{_N})"
    rf"[- ]?(?:true |real |full )?{_BEDW}\b(?!\.com)"
)
STUDIO = re.compile(
    r"\b(?P<pre>[\w'/]+ )?studio\b"
    r"(?P<post>s| space| room| area| lighting| light| quality| sized)?"
)
AMENITY = re.compile(
    r"(?:yoga|art|arts|pilates|fitness|dance|music|recording|spin|spinning|cycling|golf|media|"
    r"photo|photography|design|boxing|ballet|barre|artist|artists|artist's|podcast|rehearsal|"
    r"training|exercise|pottery|movement|sound|production|peloton|pet|grooming|craft|maker|"
    r"film|tv|television|universal|chelsea|silvercup|kaufman|steiner|broadway|meditation|"
    r"wellness|workout|aerobics|aerobic|cycle|gym|creative|painting|ceramics|flex|performance|"
    r"practice|screening|teaching|karaoke|jam|band|game|gaming|kids|children's|demo|"
    r"demonstration|cooking|culinary|private|coworking|work|working|content|stretching|"
    r"stretch|mma|karate|trx|hiit|kickboxing|pilates/yoga|yoga/pilates|rumble|equinox|"
    r"soulcycle|orangetheory|architecture|architectural|interior|tattoo|hair|beauty|nail|"
    r"makeup|portrait|rental|leasing) $"
)
STUDIO_BEFORE = re.compile(
    r"\b(?:this|spacious|large|huge|bright|sunny|renovated|beautiful|charming|cozy|massive|"
    r"true|oversized|big|lovely|gorgeous|stunning|floor|luxury|modern|furnished|quiet|corner|"
    r"facing|sized?|sf|ft|loft|fee|bedroom|duplex|penthouse|garden|level|adorable|cute|"
    r"amazing|perfect|great|new|unique|elegant|stylish|affordable|deal|unit|#\w+|apartment) $"
)
STUDIO_AFTER = re.compile(
    r"^ ?(?:apartment|apt|unit|loft|duplex|home|residence|condo|co-?op|with|w/|\+|plus|"
    r",? ?1 bath|/ ?1 ?ba|in (?:the |a |prime )|located|available|for rent|features|offers|"
    r"boasts)"
)
STUDIO_FIRM = re.compile(
    r"(?:\b(?:or|as|by|of|at|from|and|&|firm|architects?|designed?|design) (?:[\w'.]+ )?|/)$"
)
STUDIO_LIST = re.compile(
    rf"^(?: ?, ?| ?& ?| and | ?/ ?| or | to | ?- ?| ?\+ ?)(?:{_N})\b"
)
ROOM_AFTER = re.compile(
    r"^ (?:comes|has|is|fits|features|offers|can|with|boasts|includes|faces|easily|"
    r"comfortably|accommodates|on|while|overlooks|enjoys|gets|also|could|was|will|currently|"
    r"at the|in the|facing|being|size|sized|(?:is )?large enough|w/|"
    r"and (?:the |one |another )|& (?:the |one ))"
)
ROOM_BEFORE = re.compile(
    r"(?:\b(?:in|of|the|each|every|per|either|another|other|only|just|least|as|into|a|an|"
    r"second|2nd|third|3rd|main|primary|master|additional|extra|plus|\+|both|all|these|those|"
    r"other units?|also (?:have|available)|similar|available:?|into an?|like an?|as an?|"
    r"for an?) |\$\d[\d,]* (?:for|per) )$"
)
OTHER_BEFORE = re.compile(
    r"(?:available|other|also|more|additional|similar|multiple|several|various|"
    r"ask (?:me )?about|inquire about|call (?:me )?for|contact (?:me|us) for|"
    r"we (?:also )?have|selection of|variety of|mix of|range of|choose from|offering|offers|"
    r"consist(?:s|ing) of|comprised of|collection of|featuring|inventory)[^.!\n]{0,60}$"
)
OTHER_AFTER = re.compile(
    r"^[^.!\n]{0,40}(?:(?:are|is) (?:also )?available|apartments|units|residences|homes|"
    r"layouts|floor ?plans|options)\b"
)
STUDIOS_TO = re.compile(
    r"\bstudios?(?: apartments?)?"
    r"(?: ?, ?| ?& ?| and | ?/ ?| or | to | through | ?- ?| ?\+ ?|, and )$"
)
ONE_BEFORE = re.compile(
    r"\b(?:is|are|through|has|have|with|upstairs|downstairs|floor|level|features?|includes?|"
    r"offers?|contains?) $"
)


def plain(text: str) -> str:
    """`text` lowercased, with each dash made a hyphen and each run of whitespace a space."""
    return re.sub(r"\s+", " ", text.lower().translate(_DASHES))


def _count(word: str) -> int:
    word = word.strip()
    return _WORDS[word] if word in _WORDS else int(word)


def flex_counts(low: str) -> tuple[set[int], bool, str]:
    """The counts carried by the flex wording of `low`, whether `low` has any flex wording,
    and `low` with each match blanked by "~"."""
    counts: set[int] = set()
    masked = list(low)
    found = False
    for m in FLEX.finditer(low):
        found = True
        masked[m.start() : m.end()] = "~" * (m.end() - m.start())
        named = [v for v in m.groupdict().values() if v]
        if m.group("j") or m.group("k"):
            counts.add(2 if _count(m.group("j") or m.group("k")) == 4 else 1)
        elif named:
            n = _count(named[0])
            counts.add(2 if n == 4 and m.group(0).startswith(("junior", "jr")) else n)
        elif "alcove studio" in m.group(0) or "sleep" in m.group(0):
            counts.add(1)
    return counts, found, "".join(masked)


def stated_sizes(masked: str) -> tuple[set[int], set[int]]:
    """The sizes `masked` states for its own unit, and the sizes it offers in lists or with
    wording about other units. `masked` is the third value of `flex_counts`."""
    own: set[int] = set()
    offered: set[int] = set()
    for m in BED.finditer(masked):
        before = masked[max(0, m.start() - BEFORE) : m.start()]
        after = masked[m.end() : m.end() + AFTER]
        if "~" in before[-NEAR_FLEX:] or "~" in after[:NEAR_FLEX]:
            continue
        counts = [_count(x) for x in re.findall(_N, m.group("list"))] + [
            _count(m.group("n"))
        ]
        word = masked[m.start("n") : m.end()]
        if m.group("list") and len(set(counts)) > 1:
            offered.update(counts)
        elif STUDIOS_TO.search(before) or (
            word.endswith("s") and (counts[-1] == 1 or "-" in word)
        ):
            offered.update(counts)
        elif ROOM_AFTER.match(after) or ROOM_BEFORE.search(before):
            continue
        elif m.group("n") == "one" and (
            ONE_BEFORE.search(before) or after.startswith(" to ")
        ):
            continue
        elif OTHER_BEFORE.search(before) or OTHER_AFTER.match(after):
            offered.update(counts)
        else:
            own.update(counts)
    for m in STUDIO.finditer(masked):
        lead = len(m.group("pre") or "")
        before = masked[max(0, m.start() - BEFORE) : m.start() + lead]
        after = masked[m.end() : m.end() + AFTER]
        plural = m.group("post") == "s"
        if m.group("post") and not plural:
            continue
        if not plural and not (
            STUDIO_BEFORE.search(before) or STUDIO_AFTER.match(after)
        ):
            continue
        if STUDIO_FIRM.search(before) or AMENITY.search(before):
            continue
        if "~" in masked[max(0, m.start() - 8) : m.end() + 8]:
            continue
        if (
            plural
            or OTHER_BEFORE.search(before)
            or OTHER_AFTER.match(after)
            or STUDIO_LIST.match(after)
        ):
            offered.add(0)
        else:
            own.add(0)
    return own, offered


def read(text: str) -> tuple[list[int], list[int], bool]:
    """For a description `text`: the sorted sizes it states for its own unit (empty when it
    offers any size of another unit), the sorted counts of its flex wording, and whether it
    has flex wording. A text no longer than MIN_DESCRIPTION characters gives two empty lists
    and False."""
    if not isinstance(text, str) or len(text.lower()) <= MIN_DESCRIPTION:
        return [], [], False
    flex, found, masked = flex_counts(plain(text))
    own, offered = stated_sizes(masked)
    return ([] if offered else sorted(own)), sorted(flex), found


def code(own: list[int], flex: list[int], found: bool, bedrooms: float) -> dict:
    """The values of COLUMNS for a row coded with `bedrooms`, from the three values `read`
    gives for its listing's text."""
    out = {"bed_text": math.nan, "bed_text_fewer": False, "bed_text_more": False}
    out["bed_flex_at"] = bedrooms in flex
    if own and bedrooms == bedrooms:
        if max(own) < bedrooms:
            out["bed_text"], out["bed_text_fewer"] = float(max(own)), True
        elif min(own) > bedrooms:
            out["bed_text"], out["bed_text_more"] = float(min(own)), not found
        elif len(own) == 1:
            out["bed_text"] = float(own[0])
    return out


def latest_reads(path: Path, ids: set[str]) -> dict[str, tuple]:
    """For each listing in `ids` with a record in the records file `path`, `read` of the
    description of its latest record. The latest record is picked as
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
                seen[i] = (t, *read(str(listing.get("description") or "")))
        del raws
    return {i: v[1:] for i, v in seen.items()}


def bedtext(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    reads = latest_reads(Path(records["path"]), set(frame.listing_id.astype(str)))
    none = ([], [], False)
    coded = pd.DataFrame(
        [
            code(*reads.get(i, none), b)
            for i, b in zip(
                frame.listing_id.astype(str), frame.bedrooms.astype("float64")
            )
        ],
        index=frame.index,
    )
    frame["bed_text"] = coded.bed_text.astype("float64")
    for c in COLUMNS[1:]:
        frame[c] = coded[c].astype(bool)
    # OUT is made after the read of the records, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "bedtext": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "the bedroom count stated in the description of the listing's latest "
            "record, beside the coded count (docs/notes/bed-text-2026-11-16.md)",
            "patterns": {
                "flex": FLEX.pattern,
                "bed": BED.pattern,
                "studio": STUDIO.pattern,
                "amenity": AMENITY.pattern,
                "studio_before": STUDIO_BEFORE.pattern,
                "studio_after": STUDIO_AFTER.pattern,
                "studio_firm": STUDIO_FIRM.pattern,
                "studio_list": STUDIO_LIST.pattern,
                "room_after": ROOM_AFTER.pattern,
                "room_before": ROOM_BEFORE.pattern,
                "other_before": OTHER_BEFORE.pattern,
                "other_after": OTHER_AFTER.pattern,
                "studios_to": STUDIOS_TO.pattern,
                "one_before": ONE_BEFORE.pattern,
            },
            "windows": {"before": BEFORE, "after": AFTER, "near_flex": NEAR_FLEX},
            "listings_read": len(reads),
            "rows_with_bed_text": int(frame.bed_text.notna().sum()),
            "rows_by_flag": {c: int(frame[c].sum()) for c in COLUMNS[1:]},
            "rows_flex_or_fewer": int((frame.bed_flex_at | frame.bed_text_fewer).sum()),
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
    print(json.dumps(bedtext(args.src, args.out)["bedtext"], indent=2))


if __name__ == "__main__":
    main()
