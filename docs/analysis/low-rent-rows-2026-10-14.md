# Six rows under $1,500 with two or more bedrooms (2026-10-14)

The AR(1) fit thread found that one row, 15 East 17th Street #4, drives that fit's unit-effect
R-hat failure. That row is a five-bedroom listed at $1,000 in May 2018; the same apartment listed
at $12,000 in 2022. The thread screened NB8 for rows under $1,500 with two or more bedrooms and
found six, none of them left out by a current rule. Quarantine screens have to be rent-blind, so I
used the rents only to pick these six. For each one I read the ad text, the coded fields and the
listing's StreetEasy event history (every status and price event on the listing), looking for a
reason that has nothing to do with the rent.

The rows come from NB8 on the current rules (`baths-ad-v3, bedrooms-ad-v3, fields-review-v3,
quarantine-v12, unit-labels-v15, unit-reviews-v1, unit-splits-v4`). The event histories come from
the `event_mentions` shards of the seven neighbourhoods' canonical-url-v1 datasets under
`/data1/apartments/archive/datasets/`. The scripts are in `low-rent-rows-2026-10-14/`. They read
the row frame that `size-predictability-2026-10-12/export.py` writes, and they run in this order:
`screen.py`, `check.py`, `narrow.py`, `draft.py` and `mag.py`.

## The six rows

| Row | Ask | Beds | What the ad and the events show | Verdict |
|---|---|---|---|---|
| 15 E 17th St #4, May 2018 | $1,000 | 5 | A whole 2,000 sq ft loft with 2 baths. The listing went active, in contract and off the market at $1,000, with no price change. | Stays: no rent-blind reason |
| One Madison #14A, Sep 2017 | $1,400 | 2 | A whole two-bedroom. The advertiser changed the ask to $14,000 on the day it went up. | Stays (see below) |
| 57 1st Ave #3C, Jun 2017 | $1,240 | 2 | A whole two-bedroom, "perfect for shares". The advertiser changed the ask to $2,750 on the day it went up. | Stays (see below) |
| 260 Park Ave S #2D, Feb 2022 | $1,233 | 3 | The description reads "aaaa". The listing went active and was delisted on the same day, with no other events. | Stays (see below) |
| 300 E 2nd St #B, Sep 2019 | $1,179 | 2 | A whole two-bedroom in a rent-stabilized building, with a credit and income check. Active and delisted the same day. | Stays: rent stabilization is a reason for a low rent, not an error |
| 635 E 9th St #GR, Sep 2020 | $1,450 | 3 | A three-bedroom basement unit. It rented at the ask a month later. | Stays: no rent-blind reason |

None of the ads offers a room, a share at a per-person price, a weekly or nightly price, a short
stay, parking or storage, or a fee in place of the rent. None of the coded fields (`furnished`,
`short_term`, `concession`) is set. The bedroom counts agree with the ad text.

## The patterns, tested across NB8

The event histories show two patterns among the six. I ran each over every NB8 row to see
whether it picks out implausible asks. To judge each screen, I compared each row's ask with the
median ask of the same apartment's other listings. I counted a row as far off if the two differ
by more than a factor of two. The rent appears only in that judgement, not in the screens.
Across all rows with another listing to compare against, 0.85% are far off.

| Screen | Rows | Rows with another listing | Far off |
|---|---|---|---|
| The ask changed on the day the listing went up | 5,061 | 4,086 | 1.15% |
| The listing went off the market the day it went up | 4,658 | 3,337 | 1.59% |
| Only events: active and delisted, both on one day | 904 | 452 | 3.98% |
| Placeholder text ("aaaa", "draft", "n/a", ".", "test") | 5,206 | 3,575 | 2.13% |
| Placeholder text, and withdrawn the day it went up with no other events | 77 | 37 | 8.1% (3 rows) |

Every screen catches mostly plausible asks. The broad screens would drop 4,000 to 5,000 rows to
remove about 50 far-off ones. The narrowest screen, which catches 260 Park Avenue South, hits 77
rows; of the 37 that can be compared, 34 sit within a factor of two of their apartment's other
listings. None of these screens is a better rule than the current quarantine, so I am not adding
a quarantine version.

**Same-day price changes.** At One Madison and 57 1st Avenue, StreetEasy shows the advertiser
correcting the ask within the day. Across NB8, 5,061 initial asks change on their first day. The
median change is 2.8%, 257 change by more than 20%, and 29 change by more than a factor of two.
Pricing each row at the ask it stood at by the end of its first day would fix both rows, and the
other 27 like them, without leaving any row out. That changes the price the model fits, though, as
`tune-finalask-v1` and `tune-latestask-v1` do. A fit on a different price can't be compared with
C by paired ELPD, so this is a question of price basis for Ben, not a quarantine rule.

## What this means for the AR(1) fit

15 East 17th Street #4 has no rent-blind reason to leave it out. Its ad describes the whole
apartment, the listing went into contract at $1,000, and the coded fields are clean. A $1,000 ask
for a 2,000 sq ft five-bedroom may well be a missing zero, but the only evidence for that is the
rent. Leaving it out would be a rent-based exception, which is Ben's decision.
