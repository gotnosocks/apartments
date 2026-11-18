# A Deals caution for an ad coding more rooms than the apartment's previous ad

Written at 10:15 AM ET on 2026-11-18. No fit.

The broker read of 2026-11-18 (`docs/notes/low-outliers-2026-11-18.md`) found apartments at
the top of the Deals table whose earlier ads coded fewer rooms: a studio relisted as a
one-bedroom, a dining room counted as a fourth bedroom, a second bath in the fields. Of the
60 top deals the readers saw, 7 code more bedrooms or more baths than the apartment's
previous ad, and the readers called none of the 7 a sound deal against 11 of the other 53.

`drift_deals._cautions` now gives such an ad the code `rooms_up`. It calls
`drift_building_bedtext_layout.changes` on the run's rows and takes the columns
`ad:beds_up_prev` and `ad:baths_up_prev`: the ad's coded bedrooms, or its baths with a half
bath as 0.5, are above those of the latest training ad of the same apartment, with the
pieces of a split unit read together. Rents play no part in the code, and scores stay as
they were. The page leaves a cautioned ad out of its list unless asked, as with every other
code.

The existing `beds` code marks an apartment whose ads inside one piece carry more than one
bedroom count, or whose pieces are two or more bedrooms apart in either direction.
`rooms_up` adds the one-bedroom step up and every bath step up. An ad two bedrooms above
its previous ad takes both codes.

`caut.py` in this note's folder counts the code on the served model's two runs.

Backtest as of 2025-11-10 (`heldbed-j`, 9,346 open ads, cautions without ad texts):

| Open ads | Ads | First ask in the lowest tenth | Of those, later cut | Later raised | Median days on market |
|---|---|---|---|---|---|
| `rooms_up`, no other caution | 317 | 50 (15.8%) | 32.0% | 30.0% | 21 |
| no caution | 8,564 | 506 (5.9%) | 15.6% | 37.9% | 27 |
| another caution | 465 | 42 (9.0%) | 19.0% | 35.7% | 32 |

A `rooms_up` ad is 2.7 times as likely as an uncautioned ad to be a Deals candidate, and
the landlord later cut the ask on twice the share of those candidates (16 of 50 against
79 of 506). A cut on an ask the model already called cheap suggests the model's price was
too high.

Market of 2026-11-09 (`heldbed-m`, 6,774 ads, cautions without ad texts as well): 328 ads take the code, 201 of them with no
other caution. Among ads with no other caution it marks 0 of the first 20, 6 of the first
60, 13 of the first 100 and 24 of the first 200, against 2.6% of ads with `below_share`
between 0.25 and 0.75.

The page's words for the code are "lists more bedrooms or baths than the apartment's
previous ad", with the chip "more rooms than before".
