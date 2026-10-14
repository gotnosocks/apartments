# Latest ask and a price screen (2026-10-14)

Until this change every NB8 row was priced at its listing's first ACTIVE ask
(`historical_dataset.py`, the earliest own ACTIVE event). Ben wants each
listing at its most current price. `latest-ask-v2` reprices the rows, and
`quarantine-v13` drops the two rows a price screen found on the new prices.
C needs a refit under both.

## Building the latest ask

`python -m rentfrontier.latest_ask` reads each listing's last capture in the
granular crawls and walks its `pricing.priceChanges` in date order.

1. It skips changes dated on the listing's off-market day. Landlords often type
   a placeholder ($10,000, $1,000, $500) into the price on the day they take a
   listing down, for example at 110 9th Ave #3L, 30 E 14th #2B and 352 E 13th
   #9. Real cuts fall on earlier days. 18,671 listings had at least one change
   skipped this way.
2. It keeps every change of a listing still on the market, and any change on
   the day the listing went up, so a typo fixed the same day gives way to the
   fix.
3. It takes the last change it kept.

It then runs two checks against the row's first ask.

- A latest ask more than twice or under half the first is more likely a typo or
  a sale price in one of the two. The builder takes whichever of the two is
  nearer the median of the building's other rows with the same bedroom count.
  Without such rows it keeps the first ask.
- When the page's `pricing.price` matches no change and sits 9 to 11 times off
  the chosen ask, one of them has a dropped or added digit, and the builder
  takes the nearer of the two in the same way.

The file is `/data1/apartments/external/latest-ask/20261014-a7cb48b/`, built
from commit a7cb48b with a clean tree.

| How the price was chosen | Rows |
|---|---|
| last kept change | 214,785 |
| first ask, nearer the building | 223 |
| no capture, first ask kept | 122 |
| latest ask, nearer the building | 25 |
| page price, digit | 1 |

73,424 of 215,156 rows change price: 58,725 go down and 14,641 go up. The
median change is 4.7%, and 26 rows move by more than 2x.

Of the rows from the low-rent review in #728:

- One Madison goes from $1,400 to $14,000, the last ask before it came down.
- 15 E 17th #4 goes from $1,000 to $10,000. Every event says $1,000, while the
  page price and its JSON-LD say $10,000, so the digit check takes the page
  price.
- 57 1st Ave #3C goes to $2,750.
- 260 Park Ave S #2D, 300 E 2nd #B and 635 E 9th #GR keep their asks.

145 rows end at exactly $10,000. Their median first ask is $11,000, so they are
real cuts and not placeholders.

### Against `tune-latestask-v1`

`tune-latestask-v1` (#706) reads `final_ask` from the listing outcomes table,
which takes the page price or the last change with no off-market filter. It
picks up placeholders and sale prices, and its 2x guard then throws away real
10x corrections along with them, keeping One Madison at $1,400 and 15 E 17th at
$1,000. That made it a tuning rule only. The new builder applies the
off-market filter first, so the two checks decide only a few hundred rows.

## Price screen (quarantine-v13)

Ben allows price as a signal for anomalies. `price_mismatch_screen.py` applies
the current rules with `latest-ask-v2`. It then compares each row's log ask
with two medians, each leaving the row out:

1. the unit's other rows with the same bedroom count;
2. the building's other rows with the same bedroom count.

The row's factor is the smaller of the two distances. Requiring both to
disagree matters: on the unit alone, most hits were different apartments
under one label with a different bedroom count.

| Factor over | Rows |
|---|---|
| 2.5 | 10 |
| 3 | 2 |
| 4 | 1 |

I read all 10 hits over 2.5 with their ads
(`config/reviews/quarantine-v13-read-20261014.txt`) and quarantined the two over 3:

- **32 E 1st St #3D**, 2024-12, 2BR at $2,990, factor 4.0. The ad is a teaser
  for the building's 2-bedrooms in general ("other similar units available").
- **221 E 11th St #4C**, 2025-01, coded a studio at $8,495, factor 3.5. The ad
  offers a renovated 3-bedroom with two baths.

The eight between 2.5 and 3 stay in. Two Roselyn 1BRs from February 2019 sit
at about $3,570. 226 E 10th #7 is a 1BR at $7,495. 780 Greenwich #6H at
$15,000 reads as a 2BR duplex coded 1BR. 225 W 20th #5E has a net effective ask
of $2,175. The rest are 2BRs at 72 Bedford and 140 W 4th from 2014 to 2020.
None is clearly the wrong apartment or the wrong price. 780 Greenwich is a
bedroom question for a later `bedrooms-ad` version.

The medians take in a unit's later listings as well as its earlier ones. A
quarantine of rows read by hand can use them, because the rows it drops are
named in a reviewed file. A model feature could not.

Three earlier screen hits drop out under latest asks:

- 240 W 10th #2A was $28,000 and is now $3,550, its last ask before the
  off-market day.
- 15 E 17th #4 is fixed by the digit check.
- 47 E 30th #5 (a 1 to 18 month flexible lease) is no longer over a factor of
  3.

## What changes for a fit

- `latest-ask-v2` changes the target on a third of the rows. A run under it
  scores PSIS-LOO against different prices than a run without it, so the pair
  measures the target change and the board cannot use it as a model
  comparison.
- `quarantine-v13` drops 2 more rows than v12.
- A per-event price table, with one row per price observation and the same
  flags, comes in a follow-on PR.
