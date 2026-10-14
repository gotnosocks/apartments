# Latest ask and a price screen (2026-10-14)

Until this change every NB8 row was priced at its listing's first ACTIVE ask
(`historical_dataset.py`, the earliest own ACTIVE event). Ben wants each
listing at its most current price. `latest-ask-v2` reprices the rows, and
`quarantine-v13` drops the two rows a price screen found on the new prices.
C needs a refit under both.

## Building the latest ask

`python -m rentfrontier.latest_ask` reads each listing's last capture in the
granular crawls and walks its `pricing.priceChanges` in date order.

1. It skips placeholders. Landlords often type $10,000, $1,000 or $500 into the
   price on the day they take a listing down, for example at 110 9th Ave #3L,
   30 E 14th #2B and 352 E 13th #9. A change dated on or after the off-market
   day counts as a placeholder when it is more than twice or under half the ask
   before it, or a raise of more than 20% to exactly $10,000. Most changes on
   that day are real: of 18,793 first changes on or after it, 10,287 are raises
   within 20% and 5,566 cuts within 20%, so those count. $10,000 is the
   commonest price among the bigger raises (189 of them, against 92 for the
   next price), and 228 W 18th, 223 E 21st and 205 8th Ave each had $10,000
   typed over asks of $5,350 to $7,495. 576 listings had a change skipped.
2. It keeps every change of a listing still on the market, and any change on
   the day the listing went up, so a typo fixed the same day gives way to the
   fix.
3. Each row takes the last kept change dated from its own day up to the day of
   its listing's next NB8 row, so the 88 listings with two rows price each row
   from its own episode. A row with no change in those dates takes the change
   in effect on its day, and a row newer than the listing's last capture keeps
   its ask.

It then runs two checks against the row's first ask.

- A latest ask more than twice or under half the first is more likely a typo or
  a sale price in one of the two. The builder takes whichever of the two is
  nearer the median of the building's other rows with the same bedroom count.
  Without such rows it keeps the first ask. The median takes in later rows too;
  it decides about 250 rows.
- On a listing's last row, captured after the row, a page price
  (`pricing.price`) matching no change is the listing's current price. The row
  takes it within a factor of 2 of the kept ask. At 9 to 11 times off, one of
  them has a dropped or added digit, and the builder takes the nearer of the
  two in the same way.

A row keeps its `price_at`, the day its listing first asked.

The file is `/data1/apartments/external/latest-ask/20261014-003dd7d/`, built
from commit 003dd7d with a clean tree.

| How the price was chosen | Rows |
|---|---|
| last kept change | 214,562 |
| first ask, nearer the building | 228 |
| no capture, first ask kept | 122 |
| captured before the row, own ask kept | 113 |
| page price | 101 |
| latest ask, nearer the building | 29 |
| page price, digit | 1 |

79,791 of 215,156 rows change price: 57,873 go down and 21,918 go up. The
median change is 4.9%, and 30 rows move by more than 2x.

Of the rows from the low-rent review in #728:

- One Madison goes from $1,400 to $14,000, the last ask before it came down.
- 15 E 17th #4 goes from $1,000 to $10,000. Every event says $1,000, while the
  page price and its JSON-LD say $10,000, so the digit check takes the page
  price.
- 57 1st Ave #3C goes to $2,750.
- 260 Park Ave S #2D, 300 E 2nd #B and 635 E 9th #GR keep their asks.

### Against `tune-latestask-v1` and `tune-finalask-v1`

`latest-ask-v2` supersedes `tune-latestask-v1` (#706) and `tune-finalask-v1`
(#700/#704). Both were tuning rules only.

`tune-latestask-v1` reads `final_ask` from the listing outcomes table: the page
price or the last change, with no placeholder filter, and the row's first ask
whenever that is more than twice or under half of it. It changes 79,781 rows,
and `latest-ask-v2` changes 79,791. On 217 rows the two prices differ, and I
checked each group:

| Cause | Rows | Median difference | Over 2x |
|---|---|---|---|
| `latest-ask-v2`'s 2x or digit check, or a row newer than its listing's capture | 77 | 7.1% | 30 |
| `tune-latestask-v1`'s 2x guard kept the first ask, its `final_ask` being a placeholder | 72 | 3.7% | 0 |
| `latest-ask-v2` skipped a placeholder that `tune-latestask-v1` took | 62 | 53% | 5 |
| the outcomes table and the builder read different last captures | 6 | 5.8% | 0 |

The 30 rows over 2x are the corrections the 2x guard throws away, such as One
Madison and 15 E 17th. The 72 rows of the guard's group get the last real ask
before the placeholder in `latest-ask-v2`, close to the first ask. The 62 rows
of the placeholder group take $10,000 in `tune-latestask-v1` (49 of them) or a
price after a skipped one. Every difference comes from one of the intended
changes, apart from the 6 capture differences.

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
| 2.5 | 11 |
| 3 | 2 |
| 4 | 1 |

I read all 11 hits over 2.5 with their ads
(`config/reviews/quarantine-v13-read-20261014.txt`) and quarantined the two over 3:

- **32 E 1st St #3D**, 2024-12, 2BR at $2,990, factor 4.0. The ad is a teaser
  for the building's 2-bedrooms in general ("other similar units available").
- **221 E 11th St #4C**, 2025-01, coded a studio at $8,495, factor 3.5. The ad
  offers a renovated 3-bedroom with two baths.

The nine between 2.5 and 3 stay in. Two Roselyn 1BRs from February 2019 sit
at about $3,570. 226 E 10th #7 is a 1BR at $7,495. 780 Greenwich #6H at
$15,000 reads as a 2BR duplex coded 1BR. 225 W 20th #5E has a net effective ask
of $2,175. The rest are 2BRs at 72 Bedford, 140 W 4th and 142 W 4th from
2014 to 2020. The 142 W 4th ad is for a walk-up 2-bedroom at $2,325 in August
2020. None is clearly the wrong apartment or the wrong price. 780 Greenwich is a
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

## Sale records with a rental's id (latest-ask-v3)

StreetEasy numbers sale and rental listings separately, and the granular
crawls capture both, so 1,653 listing ids belong to a sale and a rental.
`latest_ask.py` and `listing_extras.py` kept each id's last capture of either
kind. For 210 NB8 rows that was a sale, with prices such as $899,000. The 2x
check in `latest-ask-v2` caught every one and kept the row's first ask, which
made up 210 of the 228 rows in "first ask, nearer the building". `lister.py`
already read rentals only.

Both builders now skip sale observations. The rebuilt file
(`/data1/apartments/external/latest-ask/20261014-9ae2b6e/`) gives:

| How the price was chosen | Rows |
|---|---|
| last kept change | 214,772 |
| no capture, first ask kept | 122 |
| captured before the row, own ask kept | 113 |
| page price | 101 |
| latest ask, nearer the building | 29 |
| first ask, nearer the building | 18 |
| page price, digit | 1 |

`latest-ask-v3` reads it. Against `latest-ask-v2` it changes 92 rows, each
from its first ask to its last rental ask, by a median of 4.4% and at most
23% of the v2 ask. That is under the 0.25% of rows `autoselect` treats as negligible, so a
fit on `latest-ask-v2` stays eligible under `latest-ask-v3`.

The listing extras rebuilt the same way
(`/data1/apartments/external/listing-extras/20261014-9ae2b6e/`) differ on NB8
rows in outdoor types for 86 rows and room count for 170. The nb8 sets keep
reading `NB8_EXTRAS_FILE`, since changing it would change hashed feature code.
The next neighbourhood's sets read a rebuilt file.
