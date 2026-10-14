# Screens for every new dataset

Before a new dataset's rules merge, we run two rent-blind screens on it under the current data
rules and read every hit. Each screen writes only the hits that nobody has read yet. A test fails
when a registered dataset (`DATASET_NB9` or later) is missing from the screen's cohort list, so
registering a dataset brings both screens with it.

| screen | command | cohort list | reads |
|---|---|---|---|
| Brooklyn ads on Manhattan buildings | `frontier/scripts/brooklyn_screen.py DATASET OUT.jsonl` | `config/reviews/brooklyn-screened.txt` | `brooklyn-misjoins-*.jsonl` and the quarantine read lists |
| Ads that don't fit their unit | `frontier/scripts/ad_fit_screen.py DATASET OUT.jsonl` | `config/reviews/ad-fit-screened.txt` | `config/reviews/ad-fit-reads-*.jsonl` |

## Ad fit

`rentfrontier.adfit` came out of the five one-bedroom asks at 110 W 26th St (quarantine-v18). They
carried the building's loft labels with no square footage, at a third of the lofts' asks, and
nothing caught them until a fit failed to converge on the building. The screen flags each row on
size, on the ad's words and on price, then sorts its hits into tiers:

1. A: size and price together.
2. B: words for a room share, a bath or kitchen shared with other units, a nightly or short
   stay, or a neighbourhood more than 3 km from the building.
3. C: a stated size far from the unit's other stated sizes.
4. D: price alone.

When a row states no size, the screen infers one from its bedroom count. These inferred-size
flags put a row in tier A when its price is far as well, and in no tier on their own: a random
sample of 30 of them on NB9 was all studios and one-bedrooms in buildings where only the big
units list a size, plus big units with no size. That change took NB9's tier C from 2,224 hits
to 156. A shared bath counts alone only in a studio or a one-bedroom. For two bedrooms or more,
the ad has to say the bath is shared with other units or tenants, since most hits there were
bedrooms sharing the apartment's own bath. The screen leaves out "communal kitchen" as well, since
most ads use it for a building amenity.

We read the tiers in that order. For each hit we read the whole ad and the page fields (the
address the agent typed, the lister, the stated size, photos, days on market), and we add a line
to the reads file:
- the row's ids, flags and tier;
- the verdict: `keep`, a quarantine action, `brooklyn_misjoin`, a unit split or relabel, or a
  bedroom or size correction;
- for any verdict but `keep`, the quote from the ad (`quote_source: ad`) or from the page
  (`quote_source: page`) behind it, and the reason.

`adfit.verdict_problems` rejects a non-keep read whose quote is empty or only a price, and a test
runs it over every recorded read. Price can flag a row for reading, but the hold-out has to rest
on something the ad or the page says. Unread hits stay in the data. Non-keep verdicts go into
the next version of the matching rule (quarantine, unit labels or fields), and its PR checks that
version number against the latest merges first.
