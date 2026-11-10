"""Reasons to read an ad twice before calling its low ask a deal.

The Deals table ranks the ads on the market by how low each ask is for the apartment. A model
of asks cannot tell a bargain from an ad whose ask is low for a reason the model does not
know, and the top of the table collects the second kind. On 2026-11-10, 12 of 22 ads read
from the first 40 were such: seven income-restricted or affordable-program units, an office
suite, an apartment open only to the building's owners, an ask net of a free month, a
free-rent offer the dataset had not parsed and a doubtful bed count
(`docs/notes/drift-2026-11-10.md`).

A caution is a short code on a row of the table. It says why the ask may not be what it
looks like, and the page leaves cautioned ads out of its list unless asked for them. A
caution never changes an ad's score or the model: it is read at publish time from the ad's
own latest text and from the dataset's rows.

- `income`: the text says the apartment is income-restricted or in an affordable-housing
  program. An ad with no text to read takes the dataset's `income_restricted` flag.
- `not_home`: the text offers an office or a commercial space.
- `owners_only`: the text opens the apartment only to the building's owners.
- `takeover`: the text offers the rest of someone's lease (a takeover, an assignment or a
  reassignment), not a new one.
- `beds`: the apartment's ads in the dataset carry more than one bedroom count, or the
  pieces the dataset split the apartment into are two or more bedrooms apart.
- `off_market`: the ad's status is temporarily off the market.

The text patterns were chosen by reading: 237 of the 6,774 ads on the market of 2026-11-09
matched a wider set of candidates, each was read and classed, and an alternative was kept
when nearly all its matches were right (the note has the count for each). What was dropped
and why: "household income" (17 of 33 right; brokers ask for it), "minimum income" (the
40-times-the-rent rule), "income guidelines", "affordable apartment" and "affordable home"
(sales talk), "private office" and "office space" (1 of 79 right; a building's co-working
room, a home office), "owners only" (the gym), and every pattern for a room in a share (0
of 67 right: "two bedrooms available", "A/C per room"). Review then added guards for
ordinary wording the day's ads did not happen to hold: "income requirement: 40x the rent",
"no HPD violations", "not for commercial use".

A second reading the same day fixed `takeover` and dropped a caution for a bedroom count
in the text that differs from the record. Of the 6,774 ads, 100 matched a wider set of
candidates for a takeover and 82 were read: "lease takeover" and "take over the lease" (5
matches, all 5 the rest of a lease), "lease assignment" and "assign the lease" (4 of 4)
and "lease reassignment" (4 of 5; the other is a leasing office's stray header) are kept,
14 ads in all. Dropped: "sublet" and "sublease" (6 of 28;
"sublets ok" is a building's policy), "lease ends" and "lease expires" (4 of 7; a new
lease's own end date), and "short-term" (6 of 42 read; "no short term rentals"). For the
bedroom count, 573 ads name in their text only counts that differ from the record's, and
of 80 read 10 described the apartment itself: the rest gave the building's mix of units
("studio, one, and two-bedroom layouts") or a "cardio studio". One in eight is no caution.

The dataset's own `income_restricted` flag uses an older list
(`features.DESCRIPTION_FLAGS`): it was right for 22 of the 30 market ads it flagged, the
other 8 quoting one fee schedule ("optional for income restricted units"), and it missed
33 of the 55 ads the readers classed as income-restricted. It is a model input, so it
changes only with a refit; a row that has a text takes its caution from the text alone.
"""

from __future__ import annotations

import re

OFF_MARKET = "TEMPORARILY_OFF_MARKET"
# The usual rule that a tenant earn forty times the rent, within a sentence of the words
# "income requirement": an ordinary ad's wording, not a program's.
_FORTY = r"(?![^.\n]{0,90}(?:\d ?x\b|\btimes\b))"
# Matched on the text as `plain` leaves it: lowercase, single spaces, plain hyphens.
TEXT = {
    "income": (
        # A fee schedule several buildings quote: "optional for income restricted units".
        r"(?<!optional for )income[- ]restrict"
        rf"|income (?:requirement|qualif)\w*+{_FORTY}"
        r"|income (?:range|limit|eligib)"
        r"|(?:maximum|max)\.? (?:annual |household |allowable |allowed )?income"
        r"|\bhpd\b(?! violation)"
        r"|affordable (?:unit|housing|income)"
        r"|housing connect|housing lottery|(?<!mon )(?<!bel )\bami\b"
    ),
    "not_home": r"professional suite|your practice|(?<!not for )(?<!no )commercial use",
    "owners_only": r"only to (?:current )?(?:owners|shareholders)",
    "takeover": (
        # "No lease assignments", "cannot re-assign the lease": a building's rule. The
        # guard reads only the word right before the phrase, so "lease assignments are
        # not permitted" and "lease assignment fee: $500" still match.
        r"(?<!\bno )(?<!not )(?<!re-)\b(?:lease[- ]take[- ]?over"
        r"|tak(?:e|ing)[- ]?over (?:of )?"
        r"(?:(?:my|the|our|a|an|this|existing|current) )?(?:\w+ )?lease"
        r"|lease[- ](?:re-?)?assignment"
        r"|(?:re-?)?assign(?:ment of|ing)? (?:my |the |our )?lease)"
    ),
}
# Every code, in the order a row lists them.
CODES = (*TEXT, "beds", "off_market")
_COMPILED = {code: re.compile(pattern) for code, pattern in TEXT.items()}
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015"), "-")


def plain(text: str) -> str:
    """`text` in lowercase with every run of white space a single space and every dash a
    hyphen, so a pattern's literal space and hyphen meet what an ad's author typed."""
    return re.sub(r"\s+", " ", text.lower().translate(_DASHES))


def from_text(text) -> list[str]:
    """The codes an ad's description gives. A missing text gives none."""
    if not isinstance(text, str):
        return []
    low = plain(text)
    return [code for code, pattern in _COMPILED.items() if pattern.search(low)]


def ordered(codes) -> list[str]:
    """`codes` once each, in the order of `CODES`."""
    have = set(codes)
    return [code for code in CODES if code in have]
