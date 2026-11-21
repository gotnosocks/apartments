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
- `rooms_up`: the ad codes more bedrooms or more baths than the apartment's previous ad in
  the dataset (`rentfrontier.drift_building_bedtext_layout.changes`). The model adds its
  whole step for the extra room and the ask rises by less. Of the 60 ads at the top of the
  list of 2026-11-17 that brokers read, 7 were such and none of the 7 read as a sound deal
  (`docs/notes/low-outliers-2026-11-18.md`).
- `net_ask`: the page shows a rent already net of free months that the record does not
  code (`net_ask`), so the table compares a net ask with the model's gross rent. Brokers
  reading the first 100 uncautioned ads of 2026-11-18 found 2 such; the rule marks 11 ads
  of that table, 3 of them in its first 100 (`docs/notes/net-ask-caution-2026-11-18.md`).
- `deposit_net`: the record's flat security deposit is `DEPOSIT_RATIO` or more times the
  page price and is that price grossed up for free months the record does not code
  (`deposit_net`). New York caps a deposit at one month's rent (2019), so a deposit above
  the price says the lease rent is the deposit and the page shows a net rent. A deposit
  equal to the ad's first ask is a cut that left the deposit at the old price, and is not
  marked. Over the 6,502 ads of the table of 2026-11-20, 88 had an uncoded deposit 2% or
  more above the page price that fits a net rent, against 211 whose deposit was the first
  ask; the fits gathered at the top of the page, 5 in the first 60 (8.3%) and 12 in the
  first 300 against 0.7% to 0.8% further down, and by building (The Lightwell Dumbo, 733
  Lincoln). A ratio under 1.05 also fits half a month on a 13-month lease or a stale
  deposit from an intermediate price, so the mark starts at 1.05
  (`docs/notes/deals-top-read-2026-11-21.md`). At 1.05 it marks 75 ads of that table, 50
  with no other caution, 4 of them in the first 60 of the default view and 11 in the
  first 300. The deposit is read from the record the ad's text comes from
  (`rentfrontier.descriptions.record_descriptions`); an ad with no deposit there is not
  marked.
- `raised`: another ad of the building, opened in the year before the table's day,
  stands 15% or more above its first ask (`raised`). An earlier ad of the same apartment
  counts; the ad itself does not. Such buildings open
  low and raise: of the held-out first asks 15% or more under the model's prediction, 52%
  in a marked building ended 15% or more above the first ask against 13% elsewhere, on
  the half of buildings the rule was not chosen on. That test counted raised ads of other
  units, closed before the ad opened; the count here also takes raised ads still open,
  which one backtest day supports, and earlier ads of the same apartment, which the
  history test did not cover (`docs/notes/raise-caution-2026-11-18.md`).
- `thin_level`: the model's level for the ad's building is high and rests on few ads:
  the posterior mean of the building's level is over 0.3 and the building has 5 or fewer
  ads among the fit's training rows (`thin_level`). A level like that often comes from a
  few odd rows, and the model then prices the building's next ad too high. On the latest
  split's 189,647 held-out ads, with the buildings cut in two halves, 14.4% and 14.1% of
  such ads (90 and 99 ads) were below the model's 5% point against 5.9% of all, and their
  mean gap was -0.070 and -0.056 (`docs/notes/thin-level-caution-2026-11-20.md`). The
  level is fitted on training rows only and the ad is held out, so no ask of the ad
  enters; earlier ads of the ad's own apartment are training rows and count.
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
    # A lease under 12 months by its length in months ("6-month lease", "10 mo term",
    # "nine month sublet"). Both halves of the latest split's held-out buildings hold an
    # excess of low asks with it, though one scan printed both halves at once
    # (docs/notes/short-lease-2026-11-21.md). The guard in front keeps "13-month" and
    # "1.5 month" from matching on their last digit; the one after "rental" keeps out fees.
    "short_lease": (
        r"(?<![\d.-])\b(?:[1-9]|1[01]|one|two|three|four|five|six|seven|eight|nine|ten"
        r"|eleven)[- ]?(?:month|mo)s?[- ](?:lease|term|stay|sublet"
        r"|rental(?! (?:fee|deposit|bonus|credit|concession|incentive)))"
    ),
}
# Every code, in the order a row lists them.
CODES = (
    *TEXT,
    "beds",
    "rooms_up",
    "net_ask",
    "deposit_net",
    "raised",
    "thin_level",
    "off_market",
)
# Free months and lease lengths, in months, that `net_ask` tries.
NET_FREE = (1, 2, 3)
NET_LEASES = (*range(12, 19), 24)
# `deposit_net` marks a deposit this many times the page price or more, that is the page
# price grossed up for `DEPOSIT_FREE` months free over a lease of `DEPOSIT_LEASES` months,
# within the larger of `DEPOSIT_TOLERANCE` dollars and `DEPOSIT_SHARE` of the price.
DEPOSIT_RATIO = 1.05
DEPOSIT_FREE = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
DEPOSIT_LEASES = tuple(range(12, 25))
DEPOSIT_TOLERANCE, DEPOSIT_SHARE = 2.0, 0.002
# `raised` counts an ad whose ask is this far above its first ask, opened within this many
# days of the table's day.
RAISE, RAISE_DAYS = 0.15, 365
# `thin_level` marks a building whose level's posterior mean is over `THIN_LEVEL` and
# which has `THIN_ADS` or fewer ads among the fit's training rows.
THIN_LEVEL, THIN_ADS = 0.3, 5
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


def net_ask(first_ask, page_price, months_free):
    """A boolean array, true where an ad's page price looks net of free months the record does not code.

    A landlord's gross rent is nearly always a round number, and a net rent seldom is. The
    mark needs all of: no coded free months; a first ask that is a multiple of 25; a page
    price below it whose last digit is none of 0, 5 and 9; and a page price within a dollar
    of the first ask less `NET_FREE` months spread over a lease of `NET_LEASES` months."""
    # The site's tests read this module's codes in an environment with no numpy.
    import numpy as np

    first, page = np.asarray(first_ask, float), np.asarray(page_price, float)
    coded = np.nan_to_num(np.asarray(months_free, float)) > 0
    with np.errstate(invalid="ignore"):
        gross = (np.abs(first - np.round(first / 25) * 25) < 0.01) & (first > page)
        odd = ~np.isin(np.round(page) % 10, (0, 5, 9)) & np.isfinite(page)
        fits = np.zeros(first.shape, bool)
        for lease in NET_LEASES:
            for free in NET_FREE:
                fits |= np.abs(first * (lease - free) / lease - page) <= 1.0
    return ~coded & gross & odd & fits


def deposit_net(deposit, first_ask, page_price, months_free):
    """A boolean array, true where an ad's flat security deposit says its page price is net
    of free months the record does not code.

    The mark needs all of: a deposit (NaN where the record has no flat one); no coded free
    months; a deposit `DEPOSIT_RATIO` or more times a positive page price; a deposit other
    than the ad's first ask, which would be a cut; and a deposit that, spread as
    deposit * (L - m) / L for m of `DEPOSIT_FREE` and L of `DEPOSIT_LEASES`, comes within
    the larger of `DEPOSIT_TOLERANCE` dollars and `DEPOSIT_SHARE` of the page price."""
    import numpy as np

    dep, first, page = (np.asarray(v, float) for v in (deposit, first_ask, page_price))
    coded = np.nan_to_num(np.asarray(months_free, float)) > 0
    with np.errstate(invalid="ignore"):
        # A product, so a deposit of exactly `DEPOSIT_RATIO` counts whatever the rounding.
        over = (page > 0) & (dep >= page * DEPOSIT_RATIO - 1e-9)
        tolerance = np.maximum(DEPOSIT_TOLERANCE, DEPOSIT_SHARE * page)
        fits = np.zeros(dep.shape, bool)
        for lease in DEPOSIT_LEASES:
            for free in DEPOSIT_FREE:
                fits |= np.abs(dep * (lease - free) / lease - page) <= tolerance
    cut = np.isclose(dep, first)
    return ~coded & over & ~cut & fits


def raised(building, unit, listing, first_day, first_ask, ask, day):
    """A boolean array, true where the ad's building has a raised ad other than the ad.

    The arrays hold every row of the dataset, one entry each: its building, its unit, its
    ad's listing id, the day the ad opened, its first ask and its ask on `day`. A raised
    ad opened in the `RAISE_DAYS` up to `day`, has a known unit, and asks `RAISE` or more
    above its first ask. An ad is marked when its building has a raised ad with another
    listing id, so an earlier raised ad of the ad's own apartment counts. No ask of the ad
    itself is read."""
    import numpy as np
    import pandas as pd

    d = pd.DataFrame({"building": np.asarray(building), "listing": np.asarray(listing)})
    age = (pd.Timestamp(day) - pd.DatetimeIndex(first_day)).days.to_numpy()
    first, now = np.asarray(first_ask, float), np.asarray(ask, float)
    # A product, so a rise of exactly `RAISE` counts whatever the rounding.
    up = (first > 0) & (now >= first * (1 + RAISE) - 1e-9)
    up &= (age >= 0) & (age <= RAISE_DAYS) & pd.notna(np.asarray(unit, object))
    ads = d[up].drop_duplicates()
    count = d.building.map(ads.building.value_counts()).fillna(0).to_numpy()
    own = d.merge(ads.assign(own=1), on=["building", "listing"], how="left").own
    return count - own.fillna(0).to_numpy() > 0


def thin_level(level, train_ads):
    """A boolean array, true where an ad's building has a high level resting on few ads.

    `level` is the posterior mean of the level of each ad's building (`bld`, in log rent
    above the zone's surface) and `train_ads` the count of the building's ads among the
    fit's training rows, every unit's. The mark needs a level over `THIN_LEVEL` and
    `THIN_ADS` or fewer ads. A building with no level is not marked."""
    import numpy as np

    level, count = np.asarray(level, float), np.asarray(train_ads, float)
    with np.errstate(invalid="ignore"):
        return (level > THIN_LEVEL) & (count <= THIN_ADS)
