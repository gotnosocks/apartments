"""Write a B0 dataset with the free months each listing's ad text states, beside the coded
`months_free`, and whether the text calls the listed price net or gross.

    python -m rentfrontier.b0freetext SRC OUT

StreetEasy's concession field, `months_free` in the pipeline's ads file, is empty on most ads
whose description offers free rent: it was first filled in 2020, and many later ads leave it
blank too. This script reads the offer from the text into three new columns, and the text's
word on the listed price (net effective or gross) into a fourth. It leaves `months_free` and
the ask as they are, since ad text does not override a coded field in this project (Ben,
2026-10-04). A fit or a page using the new columns chooses how to combine them with the coded
ones.

The text is the description of each listing's latest record in the records file of SRC's
pipeline build (the manifest's `build.records`, checked against its SHA-256), picked by the
later of `collected_at` and `last_collected_at` as `b0duplex` picks it. The records carry no
title. `statements` finds every offer in the text:

1. a count of months or weeks with "free", "rent free", "free rent", "on us", "waived",
   "complimentary", "concession" or "abatement": "one month free", "2 FREE MONTHS", "1.5
   months of free rent", "a month and a half free", "a 1/2 month free", ".50 free month", "8
   weeks free", "60 days free", "1 month concession";
2. a free month named by its place in the lease: "first month free", "last month is free",
   "12th month free", "first and last month free", "13th and 14th months free" (two months),
   "FIRST TWO MONTHS OF LEASE AND LAST MONTH ARE FREE" (three months);
3. a bare "free month" (one month), and "13 months for the price of 12" (one month).

Weeks become months at 4 weeks a month, as in the coded field and in the ads' own net prices:
"8 WEEKS FREE! G 2900 N 2416" takes 2 of 12 months off 2900. The text column fills in for
`months_free` where that is empty, so it counts in the same units. Days become months at 365/12
days a month. Both stay unrounded, so 6 weeks free is 1.5 months and 45 days free is 1.479. A
whole count of 7 or more months ("12 month free", "11 months will be free", "the first 11
months and the last month is free") refers to the free month of the lease, so it counts one
month. An offer of parking, a gym, storage, WiFi, an amenity fee and the like is passed over
(`NON_RENT`), as is every "no fee" and "broker fee free", which state no months. A lease length
stated with an offer ("on a 13-month lease", "with a 14 month lease", "on a one-year lease",
"18 month term") comes from the offer's own clause: the first one after the offer and before
the next offer, or else the nearest one before it and after the previous offer.

Each offer gets a kind:

- `up_to`: "up to" or "as much as" right before the count, or a range ("1-2 months free"),
  which keeps its upper end;
- `conditional`: its clause ties it to a deadline ("if you sign by", "move in by", "leases
  signed before"), to the applicant ("for qualified applicants", "approved credit") or to
  some units only ("on select units");
- `exact`: any other offer.

"Limited time" and "new residents only" leave an offer exact, since the offer stands while
the ad runs. Where a text makes several offers, `choose` takes the one its sentence ties to
the listed price (`basis`: "net effective rent based on 1 month free", "rents shown include
1 month free", "1 MONTH FREE NET EFFECTIVE RENT LISTED"), then an exact one before a
conditional one before an up-to one, and the first in the text among those, since an ad states
its main offer first and its offers for longer leases after.

A text saying the building's concession leaves its unit out ("Incentives Do Not Apply.", "Unit
3K is excluded from all promotions/concessions", `UNIT_EXCLUDED`) gets kind `none` and 0
months, whatever it offers. A text with no offer gets kind `none` and 0 months when it denies
one ("no concessions", "no free month", "no free rent"), and kind `unstated` with no months
when it calls its price net effective or mentions free rent or a rent concession without a
count. A text stating a concession left out of the price ("1 month free, not reflected in the
price") counts as an offer: the free month is real, and only the price is gross.

`ask_basis` reads every text for its word on the listed price:

- `net` when it calls the price net effective ("net effective rent", "net rent", "NER") or
  ties an offer to the price ("rent reflects a month free", `basis`);
- `gross` when it calls the listed price gross ("gross rent advertised", "prices listed are
  the gross"), denies it is net effective ("not net effective"), or says the price leaves a
  concession out ("1 month free, not reflected in the price", "pricing listed does not include
  the free rent"; `LEFT_OUT`, with a concession word earlier in the sentence for its first
  form, so "utilities not included in the rent" says nothing);
- null when it says neither, or both.

A net effective mention right after "not", "no" or "never", as in "approvals are based on the
gross rent, not the net effective rent", counts as no mention of a net price.

OUT gets:

- `rows.parquet`: SRC's rows in SRC's order, with `months_free_text` (float64, NaN with no
  count), `free_lease_months` (float64, NaN with no lease stated) and `free_text_kind`
  (string: exact, up_to, conditional, none or unstated; null when the text says nothing of a
  concession) and `ask_basis_text` (string: net or gross; null when the text says neither or
  both) added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `free_text` entry giving
  SRC's path and rows SHA-256, the records file and its SHA-256, the rules and conversions,
  counts of rows by kind and of rows with more than one count of months in their text, and
  counts of rows by basis, including rows with a text saying both.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .b0data import sha256

WEEKS_PER_MONTH = 4.0
DAYS_PER_MONTH = 365 / 12
KINDS = ("exact", "up_to", "conditional", "none", "unstated")
# An exact offer is chosen over a conditional one, and both over an up-to one.
RANK = {"exact": 0, "conditional": 1, "up_to": 2}

WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "single": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "twenty": 20,
    "twenty-four": 24,
    "twenty four": 24,
    "thirty": 30,
    "forty-five": 45,
    "sixty": 60,
}
_WORD = (
    "(?:"
    + "|".join(sorted((re.escape(w) for w in WORDS), key=len, reverse=True))
    + r")\b"
)
_HALF = r"(?:1/2|½|a\s+half|one[- ]half)"
# A count: "2", "1.5", "1 1/2", "1½", "one (1)", "two and a half", "half a", "1/2", ".5".
NUM = (
    rf"(?:(?:\d{{1,2}}(?:\.\d{{1,2}}|\.\s5\b)?|{_WORD})(?:\s*\(\s*\d{{1,2}}(?:\.\d+)?\s*\))?"
    rf"(?:\s*(?:-|and)?\s*{_HALF})?|{_HALF}|half(?:\s+(?:of\s+)?a)?|\.\d{{1,2}}\b)"
)
_UNIT = r"(?P<u>months?s?|mos?\b\.?|mths?|mnths?|weeks?|wks?|days?)"
_FREE = r"(?:free|rent[- ]free|on\s+us|waived|complimentary|concessions?|abatement)"
_MONTH = r"(?:months?|mos?\b\.?|mths?|mnths?)"
_ORD = (
    r"(?:first|1st|second|2nd|third|fourth|last|final|\d{1,2}(?:st|nd|rd|th)|twelfth|"
    r"thirteenth|fourteenth|fifteenth|sixteenth|eighteenth|twenty-fourth)"
)
_OF_LEASE = r"(?:\s+of\s+(?:the\s+|your\s+|a\s+)?(?:lease|term))?"
_RENT = r"(?:['’]s)?(?:\s+(?:of\s+)?rent)?"
_NOT_LEASE = r"(?![\s-]*(?:leases?|terms?|occupancy|minimum|contract|commitment)\b)"
_BE = (
    r"(?:\s+(?:is|are|will\s+be|is\s+given|are\s+given|totally|absolutely|completely))*"
)

COUNT = re.compile(
    rf"(?P<up>\b(?:up\s+to|as\s+much\s+as|as\s+many\s+as)\s+(?:an?\s+)?)?"
    rf"(?<![\w$.,/])(?P<n>{NUM})[\s-]*(?:full\s+|additional\s+|extra\s+|whole\s+|entire\s+)?"
    rf"{_UNIT}(?P<half>\s+and\s+a\s+half)?(?:['’]s?)?\s*(?:\(\s*\w+\s*\)\s*)?"
    rf"(?:of\s+)?(?:rent\s+|in\s+rent\s+)?{_BE}\s*(?:for\s+)?{_FREE}\b",
    re.I,
)
FREE_COUNT = re.compile(
    rf"(?P<up>\b(?:up\s+to|as\s+much\s+as)\s+)?(?<![\w$.,/])(?P<n>{NUM})[\s-]+"
    rf"(?:free|complimentary|rent[- ]free)[\s-]+{_UNIT}",
    re.I,
)
FREE_RENT_FOR = re.compile(
    rf"\bfree\s+rent\s+for\s+(?:the\s+)?(?:first\s+)?(?P<up>up\s+to\s+)?(?P<n>{NUM})\s*{_UNIT}"
    rf"{_NOT_LEASE}",
    re.I,
)
CONCESSION_OF = re.compile(
    rf"\bconcessions?\s*(?:of|:|-|=)\s*(?P<up>up\s+to\s+)?(?P<n>{NUM})[\s-]*{_UNIT}"
    rf"{_NOT_LEASE}",
    re.I,
)
PLACE = re.compile(
    rf"\b(?:"
    rf"(?P<fl>{_ORD}\s*(?:and|&|\+|plus)\s*(?:the\s+)?{_ORD})\s+{_MONTH}{_RENT}{_OF_LEASE}"
    rf"|(?P<first>first|1st)\s+(?:(?P<fn>{NUM})\s+)?{_MONTH}{_RENT}{_OF_LEASE}"
    rf"(?P<last>\s*(?:and|&|\+|plus)\s+(?:the\s+)?(?:last|final)\s+{_MONTH}{_RENT}{_OF_LEASE})?"
    rf"|(?P<ord>{_ORD})\s+{_MONTH}{_RENT}{_OF_LEASE}"
    rf"){_BE}\s*(?:rent[- ]free|free|on\s+us|waived)\b",
    re.I,
)
FREE_PLACE = re.compile(
    rf"\bfree\s+(?:(?P<fl>(?:first|1st)\s*(?:and|&|\+)\s*(?:last|final))|(?P<ord>{_ORD}))\s+"
    rf"{_MONTH}",
    re.I,
)
BARE = re.compile(
    r"\b(?P<neg>no\s+|without\s+(?:a\s+|any\s+)?)?(?:an?\s+|the\s+)?(?:free|rent[- ]free)\s+"
    r"(?:month|mnth|mo)\b(?![\s-]+to[\s-]+month)",
    re.I,
)
PRICE_OF = re.compile(
    rf"\b(?P<a>{NUM})\s+months?\s+(?:of\s+rent\s+)?for\s+the\s+price\s+of\s+(?P<b>{NUM})\b",
    re.I,
)
# Things given free that are not rent, right after an offer's "free" or just before its count.
NON_RENT = (
    r"(?:parking|garage|gym|fitness|membership|amenit\w*|storage|wi-?fi|internet|cable|"
    r"broadband|utilit\w*|electric\w*|heat|hot\s+water|gas\b|laundry|bike|valet|cleaning|"
    r"maid|netflix|spotify|citi\s*bike|peloton|equinox|classpass|insurance|spa\b|pool|"
    r"lounge|club|locker|furniture|tv\b|phone|cabana|pick\s+up|pick\s+and\s+drop|drop[- ]?off)"
)
# Up to two words may come between an offer and the thing given ("6 months free on large
# storage", "6 months of free weekly cleaning"), but not a word joining a second offer.
_GAP = r"(?:(?!(?:and|plus|with|or|no|rent)\b)[\w'’-]+\s+){0,2}"
NON_RENT_AFTER = re.compile(rf"^\s*\(?\s*{_GAP}{NON_RENT}", re.I)
NON_RENT_BEFORE = re.compile(
    rf"{NON_RENT}\w*(?:\s+(?:spots?|spaces?|membership|fees?|units?|rooms?|access))?\s*[:-]?\s*"
    r"(?:\$[\d,.]+\s*(?:/\s*\w+|per\s+month|a\s+month)?\s*[:,-]?\s*)?"
    r"(?:with\s+|includes?\s+|including\s+|gets?\s+)?(?:the\s+|an?\s+)?$",
    re.I,
)
# "up to 2 months free", and a range "1-2 months free" or "1 to 2 months free".
UP_TO_BEFORE = re.compile(
    r"\b(?:up\s+to|as\s+much\s+as|as\s+many\s+as)\s+(?:an?\s+)?$"
    r"|(?<![\d.$,])\d{1,2}(?:\.\d{1,2})?\s*(?:-|to|or)\s*$",
    re.I,
)
CONDITION = re.compile(
    r"\bif\s+(?:you\s+|the\s+)?(?:sign|signed|apply|applied|move|rent|lease|take|submit|"
    r"approved|application)"
    r"|\bsign(?:ed|s)?\s+(?:by|before|within|no\s+later)"
    r"|\b(?:leases?|applications?|apps?|deposits?)\s+(?:are\s+|is\s+)?(?:signed|submitted|"
    r"received|approved|placed|made)\s+(?:by|before|within|on\s+or\s+before)"
    r"|\bappl(?:y|ied|ication)\s+(?:by|before|within)"
    r"|\bmove[- ]?ins?\s+(?:by|before|on\s+or\s+before|no\s+later)"
    r"|\bmoving\s+in\s+(?:by|before)"
    r"|\b(?:starting|beginning|commencing|starts?|begins?)\s+(?:by|before|on\s+or\s+before|no\s+later)"
    r"|\bor\s+(?:earlier|sooner)\s+move"
    r"|\bwithin\s+\d+\s+(?:hours|days)"
    r"|\b(?:well[- ])?qualified\s+(?:applicants?|tenants?|renters?|residents?|clients?)"
    r"|\b(?:approved|good|excellent|great)\s+credit"
    r"|\bselect\s+(?:\w+\s+)?(?:units?|apartments?|residences?|homes?|apts?|leases?)"
    r"|\bon\s+select\b|\bcertain\s+(?:units|apartments)",
    re.I,
)
LEASE = re.compile(
    rf"(?P<n>\d{{1,2}}|{_WORD})[\s-]*(?P<u>months?|mos?\b\.?|mths?|mnths?|years?|yrs?)"
    r"(?:['’]s?)?[\s-]*(?:(?:min(?:imum)?|long|lease)[\s-]+)?"
    r"(?P<what>leases?|terms?|occupancy|minimum|commitment|contract|stay)\b"
    rf"|\b(?:leases?|terms?)\s+(?:of|for)\s+(?P<n2>\d{{1,2}}|{_WORD})[\s-]*"
    r"(?P<u2>months?|mos?\b\.?|years?|yrs?)"
    rf"|\bon\s+an?\s+(?P<n3>\d{{1,2}}|{_WORD})[\s-]*(?P<u3>months?|mos?\b\.?|years?|yr)\b",
    re.I,
)
NEGATION = re.compile(
    r"\bno\s+(?:free\s+(?:months?|mnths?|rent|weeks?)|months?\s+free|(?:rent\s+)?concessions?|"
    r"specials?|incentives?)\b"
    r"|\bwithout\s+(?:a\s+|any\s+)?(?:concessions?|free\s+(?:months?|rent))"
    r"|\bconcessions?\s+(?:is\s+|are\s+|has\s+been\s+|have\s+been\s+)?(?:not\s+(?:available|"
    r"offered|applicable|being\s+offered)|ended|expired|discontinued)"
    r"|\bnot\s+offering\s+(?:any\s+)?(?:concessions?|free)"
    r"|\bno\s+longer\s+offer\w*\s+(?:a\s+|any\s+)?(?:concessions?|free)",
    re.I,
)
UNSTATED = re.compile(
    r"\bnett?[\s-]*effective|\bnet\s+(?:rent|price|pricing)\b|\bfree\s+rent\b"
    r"|\brent\s+concessions?\b|\bfree\s+months\b",
    re.I,
)
NOT_BEFORE = re.compile(r"\b(?:not|no|never|n['’]t|non)\s+(?:a\s+|the\s+)?$", re.I)
# Words before an offer tying it to the listed price ("net effective rent based on 1 month
# free", "rents shown include 1 month free", "advertised rent is with 6 weeks free"), words
# after it doing the same ("1 MONTH FREE NET EFFECTIVE RENT LISTED", "reflected in the
# price"), and words undoing the tie ("the price does not reflect the free month"). A net
# effective figure after an offer ("2 months free on 24 month leases, net effective $3,333")
# may belong to that offer alone, so it ties nothing.
BASIS = re.compile(
    r"nett?[\s-]*effective|\bnet\s+(?:rent|price|pricing|rate)|\bNER\b"
    r"|\bbased\s+(?:on|off|upon)\b|\breflect(?:s|ed|ing)?\b|\binclusive\s+of\b|\bfactored\b"
    r"|\b(?:prices?|rents?|rates?|pricing)\s+(?:shown\s+|listed\s+|advertised\s+)?"
    r"(?:includes?|including)\b"
    r"|\b(?:advertised|listed|shown)\s+(?:rents?|prices?|pricing)\s+(?:is|are)\b"
    r"|\b(?:rents?|prices?)\s+(?:advertised|listed|shown)\s+(?:is|are|with)\b",
    re.I,
)
BASIS_AFTER = re.compile(
    r"^\W*(?:\w+\W+){0,3}?(?:nett?[\s-]*effective|net|NER)\s*(?:rents?|prices?|pricing)?\s*"
    r"(?:is\s+|are\s+)?(?:listed|advertised|shown)"
    r"|\b(?:reflected|included|factored)\s+in\b",
    re.I,
)
NOT_BASIS = re.compile(r"\b(?:not|without|exclud\w*)\b|n['’]t\b", re.I)
# The building's concession leaves the ad's unit out: "Incentives Do Not Apply." ending its
# sentence, or "Unit 3K is excluded from all promotions/concessions". "Concessions will not
# apply to renewals" limits the offer to some leases, and leaves it in place.
UNIT_EXCLUDED = re.compile(
    r"\b(?:incentives?|concessions?|promotions?|specials?|offers?)\s+(?:do(?:es)?\s+not|"
    r"don['’]t|doesn['’]t|will\s+not|won['’]t)\s+apply"
    r"(?:\s+(?:to|for)\s+(?:this|the)\s+(?:unit|apartment|apt|residence))?\s*(?=[.!)*\n]|$)"
    r"|\b(?:this\s+)?(?:unit|apartment|apt|residence)\s+(?:#\s*)?(?:[\w-]{1,5}\s+)?(?:is\s+)?"
    r"(?:excluded\s+from|not\s+eligible\s+for|ineligible\s+for)\s+(?:the\s+|any\s+|all\s+)?"
    r"(?:\w+\s*/\s*)?(?:promotions?|concessions?|incentives?|specials?|offers?)",
    re.I,
)
# What a text says of its listed price. A net effective mention after "not", "no" or "never"
# is no claim of a net price; after "not" or "no" directly ("not net effective") it says the
# price is gross.
NET = re.compile(
    r"\bnett?[\s-]*effective|\bnet\s+(?:rent|price|pricing|rate)s?\b|\bNER\b", re.I
)
NOT_NET = re.compile(
    r"\b(?:not|no|isn['’]t|aren['’]t)\s+(?:a\s+)?nett?[\s-]*effective", re.I
)
GROSS = re.compile(
    r"\bgross\s+(?:monthly\s+)?(?:rents?|prices?|pricing|rates?)\s+(?:of\s+\$[\d,.]+\s+)?"
    r"(?:is\s+|are\s+)?(?:being\s+)?(?:advertised|listed|shown|displayed|posted|quoted)"
    r"|\b(?:rents?|prices?|pricing|rates?)\s+(?:(?:advertised|listed|shown|displayed|posted|"
    r"quoted)\s+)?(?:on\s+\w+\s+)?(?:is|are)\s+(?:the\s+)?gross\b",
    re.I,
)
LEFT_OUT = re.compile(
    r"\b(?:not|n['’]t)\s+(?:been\s+)?(?:included|reflected|factored|incorporated|calculated)"
    r"\s+(?:in(?:to)?|within)\s+(?:the\s+|this\s+)?(?:(?:posted|listed|advertised|shown|"
    r"displayed|asking|quoted|above|stated)\s+)?(?:price|rent|pricing|rate|amount)s?\b"
    r"|\b(?P<subject>price|rent|pricing|rate)s?\s+(?:[\w$,.]+\s+){0,3}?(?:does|do|did|will)\s*"
    r"(?:not|n['’]t)\s+(?:include|reflect|account\s+for)\w*\s+(?:the\s+|any\s+|a\s+)?"
    r"(?:[\w-]+\s+){0,3}?(?:free|concessions?|incentives?|specials?|discounts?|promotions?"
    r"|net)\b",
    re.I,
)
CONCESSION_WORD = re.compile(
    r"free|concession|incentive|special|discount|promotion|abatement|\bOP\b", re.I
)
# Text that may hold a statement; the rest is skipped unparsed.
PREFILTER = re.compile(
    r"free|concession|complimentary|on\s+us\b|waived|abatement|net[\s-]*effective|\bnet\s"
    r"|price\s+of",
    re.I,
)
BOUNDARY = re.compile(r"[!?;\n•|*]|<br|\.(?:\s|$)|\s-\s|\s{3,}")
SENTENCE = re.compile(r"[!?\n]|<br|\.(?:\s|$)")


@dataclass(frozen=True)
class Offer:
    start: int
    end: int
    months: float
    lease: float
    kind: str
    basis: bool = False


def number(text: str) -> float:
    """The value of a count matched by `NUM`."""
    t = re.sub(r"\(\s*[\d.]+\s*\)", " ", text.lower()).strip().replace(". 5", ".5")
    half = re.search(_HALF, t, re.I)
    if half:
        t = t[: half.start()].strip().rstrip("-").strip()
        t = re.sub(r"\s*and$", "", t).strip()
        # "a 1/2 month free" is half a month.
        return (number(t) if t not in ("", "a", "an") else 0.0) + 0.5
    if t.startswith("half") or t == ".5":
        return 0.5
    if t in WORDS:
        return float(WORDS[t])
    return float(t)


def months(n: float, unit: str) -> float:
    """`n` of `unit` (months, weeks or days) in months."""
    u = unit.lower()
    if u.startswith(("w",)):
        return n / WEEKS_PER_MONTH
    if u.startswith("d"):
        return n / DAYS_PER_MONTH
    if u.startswith("y"):
        return 12.0 * n
    return n


def clause(text: str, start: int, end: int) -> tuple[int, int]:
    """The bounds of the clause around `text[start:end]`, cut at `BOUNDARY`."""
    lo = 0
    for m in BOUNDARY.finditer(text, max(0, start - 300), start):
        lo = m.end()
    m = BOUNDARY.search(text, end)
    return lo, (m.start() if m else len(text))


def basis(text: str, start: int, end: int) -> bool:
    """Whether the sentence around `text[start:end]` ties the offer to the listed price, in
    the 120 characters before the offer or the 60 after it."""
    lo = max(0, start - 120)
    for m in SENTENCE.finditer(text, lo, start):
        lo = m.end()
    m = SENTENCE.search(text, end, end + 60)
    before, after = text[lo:start], text[end : m.start() if m else end + 60]
    if BASIS.search(before) and not NOT_BASIS.search(before):
        return True
    return bool(BASIS_AFTER.search(after)) and not NOT_BASIS.search(after)


def _place(m: re.Match) -> float:
    if m.group("fl"):
        return 2.0
    if m.groupdict().get("first"):
        n = number(m.group("fn")) if m.group("fn") else 1.0
        # "pay for the first 11 months and the last month is free" frees the last month.
        if n >= 7:
            return 1.0
        return n + (1.0 if m.group("last") else 0.0)
    return 1.0


def _found(text: str) -> list[tuple[int, int, float, bool]]:
    """Every count of free months in `text`: (start, end, months, up_to)."""
    found = []
    for pattern in (COUNT, FREE_COUNT, FREE_RENT_FOR, CONCESSION_OF):
        for m in pattern.finditer(text):
            n = number(m.group("n"))
            if m.groupdict().get("half"):
                n += 0.5
            value = months(n, m.group("u"))
            # "12 month free", "11 months will be free": a whole count of 7 or more months
            # names the month of the lease that is free, so it counts one month.
            if m.group("u")[0].lower() == "m" and value >= 7 and value == int(value):
                value = 1.0
            found.append((m.start(), m.end(), value, bool(m.group("up"))))
    for pattern in (PLACE, FREE_PLACE):
        for m in pattern.finditer(text):
            found.append((m.start(), m.end(), _place(m), False))
    for m in BARE.finditer(text):
        if not m.group("neg"):
            found.append((m.start(), m.end(), 1.0, False))
    for m in PRICE_OF.finditer(text):
        a, b = number(m.group("a")), number(m.group("b"))
        if a > b:
            found.append((m.start(), m.end(), a - b, False))
    # Of overlapping matches the longest stays, then the earliest.
    found.sort(key=lambda f: (f[0], f[0] - f[1]))
    kept: list[tuple[int, int, float, bool]] = []
    for f in sorted(found, key=lambda f: (f[0] - f[1], f[0])):
        if all(f[1] <= k[0] or f[0] >= k[1] for k in kept):
            kept.append(f)
    return sorted(kept)


def _lease(text: str, lo: int, hi: int, start: int, end: int) -> float:
    """The lease length in months stated nearest the offer at `start:end`, within
    `text[lo:hi]`."""
    best, gap = np.nan, None
    for m in LEASE.finditer(text, lo, hi):
        if m.start() < end and m.end() > start:
            continue
        n = m.group("n") or m.group("n2") or m.group("n3")
        u = m.group("u") or m.group("u2") or m.group("u3")
        try:
            value = months(number(n), u)
        except ValueError:
            continue
        if not 6 <= value <= 36:
            continue
        # A lease after the offer comes first ("2 months free on a 12 month lease or 3 months
        # free on a 24 month lease"), the nearest one before it only when none follows.
        d = m.start() - end if m.start() >= end else len(text) + start - m.end()
        if gap is None or d < gap:
            best, gap = value, d
    return best


def statements(text: str) -> list[Offer]:
    """Every offer of free rent in `text`, in text order."""
    offers = []
    found = [f for f in _found(text) if 0 < f[2] <= 12]
    for k, (start, end, value, up) in enumerate(found):
        if NON_RENT_AFTER.search(text[end : end + 40]):
            continue
        lo, hi = clause(text, start, end)
        matched = text[start:end].lower()
        if "rent" not in matched and NON_RENT_BEFORE.search(
            text[max(0, start - 60) : start]
        ):
            continue
        # The lease search stops at the neighbouring offers.
        llo = max(lo, found[k - 1][1]) if k else lo
        lhi = min(hi, found[k + 1][0]) if k + 1 < len(found) else hi
        if up or UP_TO_BEFORE.search(text[max(lo, start - 20) : start]):
            kind = "up_to"
        elif CONDITION.search(text, lo, hi):
            kind = "conditional"
        else:
            kind = "exact"
        lease = _lease(text, llo, lhi, start, end)
        offers.append(Offer(start, end, value, lease, kind, basis(text, start, end)))
    return offers


def choose(offers: list[Offer]) -> Offer:
    """The offer that applies to the ad: one tied to the listed price before one that is not,
    then exact before conditional before up-to, then the first in the text. A chosen offer
    with no lease takes the lease of another offer of the same months."""
    best = min(offers, key=lambda o: (not o.basis, RANK[o.kind], o.start))
    if np.isnan(best.lease):
        for o in offers:
            if o.months == best.months and not np.isnan(o.lease):
                return replace(best, lease=o.lease)
    return best


def parse(
    text: str | None, offers: list[Offer] | None = None
) -> tuple[float, float, str | None, int]:
    """`months_free_text`, `free_lease_months`, `free_text_kind` and the number of distinct
    counts of months offered in an ad's text. `offers`, when given, is `statements(text)`."""
    if not text or not PREFILTER.search(text):
        return np.nan, np.nan, None, 0
    if UNIT_EXCLUDED.search(text):
        return 0.0, np.nan, "none", 0
    offers = statements(text) if offers is None else offers
    if offers:
        best = choose(offers)
        return best.months, best.lease, best.kind, len({o.months for o in offers})
    if NEGATION.search(text):
        return 0.0, np.nan, "none", 0
    for m in UNSTATED.finditer(text):
        if not NOT_BEFORE.search(text[max(0, m.start() - 12) : m.start()]):
            return np.nan, np.nan, "unstated", 0
    return np.nan, np.nan, None, 0


def basis_stated(text: str | None, offers: list[Offer] = ()) -> str | None:
    """net or gross for what `text` says of its listed price, both when it says both, None
    when it says neither. `offers` is `statements(text)`, or empty when the text holds no
    offer."""
    if not text:
        return None
    net = any(o.basis for o in offers) or any(
        not NOT_BEFORE.search(text[max(0, m.start() - 12) : m.start()])
        for m in NET.finditer(text)
    )
    gross = bool(GROSS.search(text) or NOT_NET.search(text))
    for m in LEFT_OUT.finditer(text):
        if gross:
            break
        # "not included in the rent" says the price leaves a concession out only when the
        # concession comes earlier in its sentence.
        lo = max(0, m.start() - 150)
        for s in SENTENCE.finditer(text, lo, m.start()):
            lo = s.end()
        gross = bool(m.group("subject") or CONCESSION_WORD.search(text, lo, m.start()))
    return "both" if net and gross else "net" if net else "gross" if gross else None


def ask_basis(text: str | None, offers: list[Offer] = ()) -> str | None:
    """`ask_basis_text`: net or gross, or None when the text says neither or both."""
    b = basis_stated(text, offers)
    return None if b == "both" else b


def latest_parses(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each listing in `ids` with a record in the records file `path`, `parse` of the
    description of its latest record, indexed by listing_id. The record texts of a row group
    are read only for the records kept, and only the parses are kept."""
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
        # As in `b0duplex`, a record with no time is never a listing's latest.
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
            # A listing twice in a row group keeps its later record.
            if i in seen and seen[i][0] >= t:
                continue
            listing = json.loads(raw) if raw else {}
            text = str(listing.get("description") or "")
            offers = statements(text) if PREFILTER.search(text) else []
            seen[i] = (t, *parse(text, offers), basis_stated(text, offers))
        del raws
    return pd.DataFrame(
        [(i, *v[1:]) for i, v in seen.items()],
        columns=["listing_id", "months", "lease", "kind", "offers", "basis"],
    ).set_index("listing_id")


def free_text(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if out.exists():
        raise FileExistsError(out)
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    lid = pd.read_parquet(src / "rows.parquet", columns=["listing_id"]).listing_id
    read = latest_parses(Path(records["path"]), set(lid.astype(str)))
    frame = pd.read_parquet(src / "rows.parquet")
    lid = frame.listing_id.astype(str)
    frame["months_free_text"] = lid.map(read.months).astype(float).to_numpy()
    frame["free_lease_months"] = lid.map(read.lease).astype(float).to_numpy()
    frame["free_text_kind"] = pd.array(lid.map(read.kind).to_numpy(object), "string")
    stated = lid.map(read.basis)
    frame["ask_basis_text"] = pd.array(
        stated.where(stated != "both").to_numpy(object), "string"
    )
    offers = lid.map(read.offers).fillna(0).to_numpy(int)
    # OUT is made after the read of the records, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    kind = frame.free_text_kind
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "free_text": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "records": {"path": records["path"], "sha256": records["sha256"]},
            "text": "the description of the listing's latest record, by the later of "
            "collected_at and last_collected_at; the records carry no title",
            "rule": "free months stated in the text as a count of months, weeks or days "
            "with free, a free month named by its place in the lease, a bare free month "
            "or N months for the price of M; a whole count of 7 or more months read as "
            "the free month of the lease (1 month); offers of parking, gyms, storage and "
            "other non-rent things passed over; kind up_to after 'up to' or for a range "
            "(its upper end), conditional with a "
            "deadline, qualification or select units in the clause, else exact; of several "
            "offers one tied to the listed price, then the exact, then conditional, then "
            "up_to one first in the text; none "
            "(0 months) when the text denies a concession and makes no offer, or says the "
            "building's concession leaves the unit out; unstated "
            "when it calls the price net effective or mentions free rent with no count; "
            "weeks at 4 to the month, as months_free counts them "
            "(rentfrontier.b0freetext)",
            "basis_rule": "ask_basis_text net when the text calls the price net effective "
            "or ties an offer to it, gross when it calls the listed price gross, denies it "
            "is net effective or says the price leaves a concession out; null when it says "
            "neither or both",
            "weeks_per_month": WEEKS_PER_MONTH,
            "days_per_month": DAYS_PER_MONTH,
            "coded_field": "months_free and latest_ask are not read or changed",
            "listings_read": len(read),
            "rows_by_kind": {k: int((kind == k).sum()) for k in KINDS},
            "rows_with_months": int(frame.months_free_text.gt(0).sum()),
            "rows_with_lease": int(frame.free_lease_months.notna().sum()),
            "rows_with_several_offers": int((offers > 1).sum()),
            "rows_by_basis": {
                b: int((stated == b).sum()) for b in ("net", "gross", "both")
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
    print(json.dumps(free_text(args.src, args.out)["free_text"], indent=2))


if __name__ == "__main__":
    main()
