"""Reasons to read an ad twice before calling its low ask a deal.

The Deals table ranks the ads on the market by how low each ask is for the apartment. A model
of asks cannot tell a bargain from an ad whose ask is low for a reason the model does not
know, and the top of the table collects the second kind. On 2026-11-10, 12 of 22 ads read
from the first 40 were such: seven income-restricted or affordable-program units, an office
suite, an apartment open only to the building's owners, two asks net of free months and a
doubtful bed count (`docs/notes/drift-2026-11-10.md`).

A caution is a short code on a row of the table. It says why the ask may not be what it
looks like, and the page leaves cautioned ads out of its list unless asked for them. A
caution never changes an ad's score or the model: it is read at publish time from the ad's
own latest text and from the dataset's rows.

- `income`: the text says the apartment is income-restricted or in an affordable-housing
  programme, or the dataset's `income_restricted` flag is set.
- `not_home`: the text reads as an office or a commercial space.
- `owners_only`: the text opens the apartment only to the building's owners.
- `beds`: the apartment's ads in the dataset carry more than one bedroom count.
- `off_market`: the ad's status is temporarily off the market.

The text patterns were chosen by reading every ad on the market of 2026-11-09 that a wider
set of candidates matched, and keeping the alternatives that were right (the note has the
counts). The dataset's own `income_restricted` flag uses an older, narrower list
(`features.DESCRIPTION_FLAGS`) and is a model input, so it changes only with a refit.
"""

from __future__ import annotations

import re

OFF_MARKET = "TEMPORARILY_OFF_MARKET"
# Matched on the lowercased text.
TEXT = {
    "income": (
        r"income[- ]restrict"
        r"|income (?:requirement|range|limit|band|level|eligib|guideline|qualif)"
        r"|(?:maximum|minimum|max|min)\.? (?:annual |household |allowable |allowed )?income"
        r"|household income"
        r"|\bhpd\b"
        r"|affordable (?:unit|apartment|housing|home|income)"
        r"|housing connect|housing lottery|\bami\b"
    ),
    "not_home": (
        r"private offices?|professional (?:suite|space|office)|your practice"
        r"|(?:medical|dental|doctor'?s?) office"
    ),
    "owners_only": r"only to (?:current )?(?:owners|shareholders)|owners only",
}
# Every code, in the order a row lists them.
CODES = (*TEXT, "beds", "off_market")
_COMPILED = {code: re.compile(pattern) for code, pattern in TEXT.items()}


def from_text(text) -> list[str]:
    """The codes an ad's description gives. A missing text gives none."""
    if not isinstance(text, str):
        return []
    low = text.lower()
    return [code for code, pattern in _COMPILED.items() if pattern.search(low)]


def ordered(codes) -> list[str]:
    """`codes` once each, in the order of `CODES`."""
    have = set(codes)
    return [code for code in CODES if code in have]
