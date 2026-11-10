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
- `beds`: the apartment's ads in the dataset carry more than one bedroom count.
- `off_market`: the ad's status is temporarily off the market.

The text patterns were chosen by reading: 237 of the 6,774 ads on the market of 2026-11-09
matched a wider set of candidates, each was read and classed, and an alternative was kept
when nearly all its matches were right (the note has the count for each). What was dropped
and why: "household income" (17 of 33 right; brokers ask for it), "minimum income" (the
40-times-the-rent rule), "income guidelines", "affordable apartment" and "affordable home"
(sales talk), "private office" and "office space" (1 of 79 right; a building's co-working
room, a home office), "owners only" (the gym), and every pattern for a room in a share (0
of 67 right: "two bedrooms available", "A/C per room").

The dataset's own `income_restricted` flag uses an older list
(`features.DESCRIPTION_FLAGS`): it was right for 22 of the 30 market ads it flagged, the
other 8 quoting one fee schedule ("optional for income restricted units"), and it missed
33 of the 55 ads the readers classed as income-restricted. It is a model input, so it
changes only with a refit; a row that has a text takes its caution from the text alone.
"""

from __future__ import annotations

import re

OFF_MARKET = "TEMPORARILY_OFF_MARKET"
# Matched on the lowercased text.
TEXT = {
    "income": (
        # A fee schedule several buildings quote: "optional for income restricted units".
        r"(?<!optional for )income[- ]restrict"
        r"|income (?:requirement|range|limit|eligib|qualif)"
        r"|(?:maximum|max)\.? (?:annual |household |allowable |allowed )?income"
        r"|\bhpd\b"
        r"|affordable (?:unit|housing|income)"
        r"|housing connect|housing lottery|\bami\b"
    ),
    "not_home": r"professional suite|your practice|commercial use",
    "owners_only": r"only to (?:current )?(?:owners|shareholders)",
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
