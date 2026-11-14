# Market disagreement: a second outcome for L1's misses (2026-11-14)

S16 (`blind-spots-2026-11-14.md`) drew L1's largest held-out misses by the gap alone, and noise
in the ask and data errors filled much of that draw. In this screen I sort the misses by a
second outcome, the ad's time on the market and its price cuts. When L1 calls an ad cheap and
the ad leaves in days with no cut, the market and L1 agree. When L1 calls an ad cheap and the ad
stays for months and gets cut, renters are reacting to a fault missing from L1's columns. When
L1 calls an ad dear and the ad is gone in days, renters are paying for a quality missing from
them. I draw ads from those corners, hand them to blind Sonnet readers as S16 did, and count the
causes against an agreement group and random controls.

The screen runs against L1's saved fit, the pool `drift-building-phase-b0-latest-9a7830fb-l1`,
and its dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`, on the latest split.
Nothing is fit, nothing goes to Modal, and no photo or OxyLabs page is fetched. The scripts are
in `docs/notes/market-disagreement-2026-11-14/` and write to
`/data1/apartments/tmp/market-disagreement-2026-11-14/`.

## Design, fixed before any outcome was computed

### The ask and the gap

A row of L1's dataset carries the ad's latest ask, net of free months, dated at the day that
ask was set (`latest_ask`, `latest_day`). The market reacts from the ad's first day, so I move
each held-out ad back to its first ask:

- the first ask comes from the ads file of the pipeline (`first_ask`, `first_day`), and I put it
  on a net basis with `drift_deals.first_net`, as `drift_deals validate` does;
- L1's predictive median belongs to the row's day, so I shift it by the change in L1's weekly
  city walk and its season curve (posterior means) between the row's day and the first day.
  The building's quarterly path and the spatial terms stay at the row's day;
- the gap is the log net first ask less the shifted median, and z is the gap over
  s = (q75 - q25) / 1.349 from `pred_scores.npz`, S16's scale.

An ad with a first ask equal to its latest ask keeps the dataset's own gap. I report the share
of ads moved.

### The outcomes, the cutoff and the censoring rule

The pipeline fetched its last ad pages on 2026-10-19. I keep the held-out ads with a first day
on or before 2026-07-21, 90 days earlier, so that every kept ad was watched for at least 90
days.

- Days on the market: the ads file's `off_day` less `first_day`, as `validate` computes it,
  capped at 90. An ad still on at the fetch counts as 90. With the cap in place no kept ad is
  censored.
- Cut: 1 when the ad's price history (S3's records table, `price_changes`) holds a decrease
  within 90 days of the first day, else 0. When the history is missing I fall back on
  `validate`'s rule, a net final ask more than 0.1% under the net first ask.
- Ending: the ad's last status in the ads file, kept as a descriptive column.

I drop ads with a missing first day or first ask, a negative duration, or a first day more than
7 days after the row's day.

### The fit on the gap

For each outcome (log of 1 + capped days, and the cut indicator) I fit, on one half of the
buildings and predict on the other (`hash(building) % 2`, the fold of the causal screens):

1. the mean of the outcome in the borough by bedroom (0, 1, 2, 3+) by calendar quarter cell,
   shrunk toward the fold's mean with weight n / (n + 20);
2. a piecewise-linear curve in z with knots at the tenths of z, fit by least squares on the
   outcome less its cell mean.

The residual is the outcome less cell mean less curve. The disagreement score D is the mean of
the two residuals, each divided by its standard deviation. A positive D says that the market
was slower than the gap predicts.

I report the dose-response by tenth of the gap: median days, mean capped days, the share cut,
the share gone within 7 days, and the share still on at 90 days.

### The draw

All groups come from the kept ads, with at most 3 ads from a building in each group, seed
20261114, and no ad in more than one group.

| Group | Pool | Order |
|---|---|---|
| A, cheap and slow | lowest tenth of z | largest D first |
| B, cheap and fast (agreement control) | lowest tenth of z, ending RENTED | smallest D first |
| C, dear and fast | highest tenth of z, ending RENTED | smallest D first |
| R, random controls | all kept ads | random |

Each group gets 100 ads. Ties in D are broken at random. The fast groups need a RENTED ending
so that an ad pulled in a day by its broker does not count as a fast rental. I freeze the draw
with its SHA-256 before building any dossier.

### The readers

Sonnet readers get about 25 dossiers each: the building's address, the unit label, the
neighborhood, the row's date, the coded fields of S16 and the ad's latest description with
dollar figures masked. They get no ask, no ask or status history, no days on the market and no
group. The causes, fixed here before the draw:

- from S16: `duplex_multilevel`, `penthouse_top_floor`, `private_outdoor`, `views`,
  `renovation`, `furnished_short_term`, `shared_room`, `income_restricted_program`,
  `garden_basement`, `size_mismatch`, `luxury_building_missed`, `utilities_fees_included`,
  `data_error`, `none_apparent`;
- `unit_fault`: a fault of the unit, found by a renter on a visit or in the photos: dark or
  facing a shaft or a wall, noisy, a walk-up on a high floor, a railroad layout, a windowless
  or interior bedroom, flex walls, no closet, a tiny kitchen, a shower in the kitchen, needs
  work. It takes in S16's `layout_fault`;
- `building_block_fault`: a fault of the building or the block: construction next door, a bar
  or a club downstairs, a highway, an elevated train, a run-down building, no laundry near;
- `terms`: sublet, short or odd lease length, lease takeover, a broker fee or other up-front
  cost, a move-in date far off, a tenant in place, restrictions on guarantors, pets or shares;
- `wrong_unit_joined`: the text describes another unit than the address and fields do, or
  several units share the ad;
- `staged_relist`: the text shows a relist, a placeholder, a "coming soon" or bait for other
  units, so that the ad's dates do not measure the time on the market of a single unit.

`renovation` keeps its S16 meaning, a renovated unit; a unit needing work goes to `unit_fault`.
I map causes coined by readers onto this list, or to new names, before opening the key, and
record the file's SHA and time, as S16 did.

### The bar

A cause is flagged for a disagreement group (A or C) when it has at least 5 reads there and
its share there is at least twice its share in B and at least twice its share in R. A share of
zero in a control passes. I give each share a building-clustered SE and each difference a
clustered SE. For each flagged cause I write a text or field pattern, count its rows in L1's
dataset, and report its held-out gap and spread under L1 outside the 400 drawn ads.

## Predictions, written before any outcome was computed

When I wrote these I had computed nothing on days, cuts or endings of the held-out ads. I had
read the k6 backtest of `drift_deals validate`, on another model and all ads: 27 to 28 median
days and 18% cut in the lowest tenth of the first ask's place, 61 to 62 days and 60% cut in the
highest. I had read S16's results.

1. **Dose-response in days.** The median of days rises from the lowest tenth of the gap to the
   highest, with at most 1 of the 9 steps falling (75%). The lowest tenth has a median of at
   most 25 days and the highest at least 40 (60%).
2. **Dose-response in cuts.** The cut share of the highest tenth is at least twice that of the
   lowest (80%), and at least 40% against at most 20% (55%).
3. **Strength.** The Spearman correlation of the gap with capped days is between 0.15 and 0.35
   (60%).
4. **The lowest tenth is slower than the second.** The lowest tenth of the gap has more days or
   more cuts than the second tenth, because data errors and program ads collect there (45%).
5. **Cheap and slow.** `income_restricted_program`, `terms`, `shared_room` and
   `furnished_short_term` together make up at least 25% of group A (55%), and at least one of
   them is flagged (65%).
6. **Faults.** `unit_fault` has at least 8 reads in A (50%) and is flagged there (35%).
   `building_block_fault` is flagged in A (15%).
7. **Data errors.** `data_error` and `wrong_unit_joined` together are at most 25% of A (60%),
   and neither is flagged in A (60%), since a data error makes an ad cheap in B as well.
8. **Dear and fast.** At least one of `renovation`, `luxury_building_missed`, `views`,
   `private_outdoor`, `size_mismatch` and `duplex_multilevel` is flagged in C (50%).
   `furnished_short_term` is flagged in C (30%).
9. **Relists.** `staged_relist` is flagged in A or C (20%).
10. **None apparent.** `none_apparent` is the most common cause in B and in R (75%), and in A
    (50%).
11. **The bar.** Between 2 and 5 cause-and-group pairs are flagged (60%), with my guess at 3.
12. **Patterns.** At least one flagged cause gets a pattern with a held-out mean gap of at
    least 0.03 in absolute value outside the draw, with the sign of its group (50%).

## The kept ads and the dose-response

All times below are New York time on 2026-11-14.

`m1_outcomes.py` starts from L1's 189,647 held-out ads. 189,616 have a first day and a net
first ask, 178,596 of those opened on or before 2026-07-21, and 178,595 are kept after one ad
with a negative duration is dropped. Every kept ad has a price history in S3's records table,
so the fallback rule for cuts was not used.

The dataset row carries the ad's latest ask. For 29.8% of the kept ads the net first ask
differs from it by more than 0.1%, and for 31.3% the ask or its day differs. Among those, the
shift of L1's median back to the first day has a median size of 0.005 log points.

| Tenth of z | z | Median gap | Median days | Mean days, capped | Cut | Gone in 7 days | On at 90 days |
|---|---|---|---|---|---|---|---|
| 1 | under -1.30 | -0.121 | 12 | 19.8 | 15.7% | 36.1% | 3.3% |
| 2 | -1.30 to -0.78 | -0.064 | 13 | 20.3 | 15.7% | 33.4% | 3.1% |
| 3 | -0.78 to -0.45 | -0.038 | 14 | 21.5 | 17.3% | 31.5% | 3.4% |
| 4 | -0.45 to -0.18 | -0.019 | 14 | 21.8 | 19.0% | 30.1% | 3.4% |
| 5 | -0.18 to 0.06 | -0.004 | 14 | 23.1 | 21.5% | 28.0% | 4.2% |
| 6 | 0.06 to 0.31 | 0.011 | 15 | 23.9 | 24.4% | 27.3% | 4.5% |
| 7 | 0.31 to 0.59 | 0.028 | 16 | 25.7 | 28.9% | 24.7% | 5.1% |
| 8 | 0.59 to 0.94 | 0.047 | 18 | 27.2 | 33.6% | 22.8% | 5.9% |
| 9 | 0.94 to 1.50 | 0.074 | 21 | 30.2 | 39.6% | 20.6% | 8.1% |
| 10 | over 1.50 | 0.135 | 26 | 35.6 | 49.3% | 17.2% | 12.5% |

Days and cuts both rise with the gap at every step. The Spearman correlation of z is 0.18 with
capped days and 0.23 with the cut. The curve is flat below the median and steep above it: an
ad asking under L1's median leaves about as fast at 12% under as at 2% under, and an ad asking
13% over is cut half the time. The cross-fitted fit (418 cells, then the curve in z) takes up
8.0% of the variance of log days and 8.7% of the variance of the cut, so most of an ad's time
on the market is left in the residuals, and D is a noisy score for a single ad.

## The draw

`m2_draw.py` froze `draw.parquet` at 15:45, SHA-256
`3014d1349f75a974f4c72713f61f0af0dc43733eb23ce9f52e9b4e251457b376`. The cap of 3 ads per
building passed over no ad in any group.

| Group | Ads | Buildings | Median gap | Median days | Days of 0 | Cut | Ending RENTED |
|---|---|---|---|---|---|---|---|
| A, cheap and slow | 100 | 94 | -0.111 | 95 | 0% | 100% | 46% |
| B, cheap and fast | 100 | 97 | -0.126 | 0 | 78% | 0% | 100% |
| C, dear and fast | 100 | 94 | 0.148 | 0 | 66% | 0% | 100% |
| R, random | 100 | 99 | 0.023 | 14 | 4% | 29% | 49% |

Ranking by D pushed the fast groups to its floor. Most ads of B and C were marked rented on
the day they opened, and I come back to that under the weaknesses.

## The reads

`m3_fields.py` wrote 16 batches of 25 dossiers, 374 of the 400 with a description over 80
characters (98, 90, 92 and 94 in A, B, C and R). 16 Sonnet readers ran 4 at a time and each
returned 25 labels. They coined 5 names over 6 reads. Before opening the key I mapped
`loft_character` and `loft_skylight_high_ceilings` to `loft_ceilings_period`,
`income_flag_contradicted` to `data_error`, kept `rent_stabilized`, and put
`private_park_key_access` under `other_building_feature` (`m4_score.py`, labels SHA-256
`5f8e548f05a344524af423d44065cdc84947552ea2ee1e15411f878d484b08ad`, mapped at 15:49).

Reads by cause and group, each out of 100, with the building-clustered SE of the share in
points:

| Cause | A cheap, slow | B cheap, fast | C dear, fast | R random | Flag |
|---|---|---|---|---|---|
| `none_apparent` | 47 (5.3) | 40 (4.9) | 22 (4.4) | 40 (4.9) | |
| `renovation` | 12 (3.3) | 11 (3.2) | 22 (4.4) | 27 (4.5) | |
| `terms` | 12 (3.3) | 12 (3.2) | 8 (2.7) | 5 (2.2) | |
| `unit_fault` | 3 (1.7) | 14 (3.5) | 6 (2.4) | 2 (1.4) | |
| `duplex_multilevel` | 7 (2.6) | 0 | 12 (3.3) | 6 (2.4) | C |
| `utilities_fees_included` | 4 (2.4) | 4 (2.0) | 7 (3.2) | 3 (1.7) | |
| `private_outdoor` | 4 (2.0) | 1 (1.0) | 6 (2.4) | 7 (2.6) | |
| `views` | 3 (1.7) | 6 (2.7) | 4 (2.0) | 0 | |
| `data_error` | 0 | 4 (2.0) | 4 (2.0) | 1 (1.0) | |
| `size_mismatch` | 1 | 1 | 2 | 4 | |
| `wrong_unit_joined` | 3 (1.7) | 0 | 1 | 0 | |
| `staged_relist` | 2 | 0 | 1 | 1 | |
| `garden_basement` | 0 | 1 | 1 | 2 | |
| `penthouse_top_floor` | 0 | 2 | 1 | 0 | |
| `furnished_short_term` | 0 | 0 | 2 | 1 | |
| `rent_stabilized` | 0 | 2 | 0 | 0 | |
| `loft_ceilings_period` | 1 | 0 | 0 | 1 | |
| other (4 causes, 1 read each) | 1 | 2 | 1 | 0 | |

`duplex_multilevel` in C is the only pair over the bar: 12 reads against 0 in B and 6 in R.
C less B is 12 points (SE 3.2), and C less R is 6 points (SE 4.0), so the flag rests on the
agreement control much more than on the random controls.

Group A flags nothing. Its largest named causes, `renovation` and `terms`, are as common in B.
`duplex_multilevel` has 7 reads in A against 0 in B (difference 7 points, SE 2.6) and misses
the bar on R's 6. `wrong_unit_joined` has 3 reads in A and none in B or R, under the floor of
5 reads.

The table has a contrast I did not set a bar for. `unit_fault` has 14 reads in B against 3 in
A (difference 11 points, SE 3.9) and 2 in R. Of the 14, 8 are walk-ups on floor 4 or higher
and 3 are railroad layouts. Those ads ask far under L1's median and are marked rented at once.
The ask already carries the fault's discount, and renters take the unit at that ask. L1 has
columns for the floor of a walk-up (`unit:walkup_f2` to `unit:walkup_f6`), so the walk-up
reads say that its walk-up discount is too small for these units, or that the coded floor is
wrong (one read: a fifth-floor unit coded on floor 2). L1 has no column for a railroad layout.

`terms` splits by kind. Of B's 12 reads, 8 are an ask already net of free months, a credit or
a gift card with no `months_free` coded, against 3 of A's 12. A's others are fees billed on
top of the rent (421a surcharges and amenity fees, 3 reads), flexible lease lengths (2 reads),
a sublease, a rate good only for an immediate start, a broker fee and a landlord's limits on
tenants.

## The pattern for the flagged cause

`m5_pattern.py` uses S7's unit-level duplex match (`dup_unit`: `duplex` or `triplex` in the
latest description, unless the text calls the building a duplex). It marks 108,481 rows of
L1's dataset (98,150 training rows and 10,331 held-out ads) in 69,369 units of 17,757
buildings. On the 10,306 held-out ads outside the draw:

- the mean gap is -0.003 (clustered SE 0.001) and the median -0.008;
- the spread of the gap is 1.37 times that of the other held-out ads;
- 72.0% of the asks fall inside L1's 80% interval, against 80.3% of the others;
- the pattern marks 7.3% of the lowest tenth of z and 7.3% of the highest, against 4.6% to
  5.0% of the 4 middle tenths.

On the kept ads outside the draw, the market outcomes of duplex ads against other ads:

| Tenth of z | Duplex ads | Median days | Cut | Mean D (SE) |
|---|---|---|---|---|
| lowest | 1,297 | 13 against 12 | 18.0% against 15.1% | 0.072 (0.022) |
| highest | 1,300 | 24 against 26.5 | 43.8% against 50.1% | -0.047 (0.026) |
| all | 9,753 | 15 against 15 | 27.4% against 26.4% | 0.033 (0.011) |

A duplex ad in the highest tenth is cut less often than its neighbors there, and a duplex ad
in the lowest tenth is cut more often. Both lean the way the reads do, with a small size. L1
puts duplex asks at the right level on average and too narrowly, as S7 and S14 found.

## Predictions, scored

1. Days rise at all 9 steps: hit. The lowest tenth has a median of 12 days (hit), and the
   highest 26, under the 40 I set: miss. The k6 backtest's 61 days does not carry over to the
   held-out ads of the latest split.
2. The cut share of the highest tenth is 3.1 times that of the lowest, 49.3% against 15.7%:
   both parts hit.
3. Spearman 0.18: hit.
4. The lowest tenth has 15.73% cut against 15.66% in the second, and fewer days. The letter
   of the prediction hits on 0.07 points; I count it a miss.
5. The four causes come to 12% of A, all of them `terms`, and none is flagged: both parts
   miss. `income_restricted_program`, `shared_room` and `furnished_short_term` have no read in
   A.
6. `unit_fault` has 3 reads in A and no flag: both parts miss. `building_block_fault` is not
   flagged, as I gave 85%.
7. `data_error` and `wrong_unit_joined` are 3% of A and unflagged: both parts hit.
8. `duplex_multilevel` is flagged in C: hit. `furnished_short_term` is not, as I gave 70%.
9. `staged_relist` is not flagged, as I gave 80%.
10. `none_apparent` leads B, R and A: both parts hit.
11. A single pair is flagged, under the 2 to 5 I set: miss.
12. The duplex pattern's mean gap is -0.003: miss.

My predictions for group A assumed that the program, shared and furnished ads of S16's
underpriced misses would sit on the market. They are missing from A altogether. A draws from
the whole lowest tenth, with a median gap of -0.11, and S16's misses started at -0.18.

## Candidate causal factors, ranked

1. **Levels in a unit (duplex, triplex, mezzanine).** Arrow: noise, and a level term to split
   it. The asks spread 1.37 times wider with a mean gap near zero, the pattern is 1.6 times
   as common in both end tenths as in the middle, and the market backs part of the high asks
   (fewer cuts in the highest tenth) and rejects part of the low ones (more cuts in the lowest
   tenth). 4 of A's 7 reads describe a mezzanine or a sleeping loft, and none of C's 12 does
   (their notes mention a triplex, a penthouse duplex and a garden unit joined to its
   basement), so the split between a full level and a loft platform is the data needed: S7's
   match plus a second pattern for `mezzanine`, `loft bed`, `sleeping loft`, and the level
   count from floor plans where fetched.
2. **Concessions written only in the text (net-effective asks, credits, gift cards).** Arrow:
   level. 8 of B's 12 `terms` reads are asks net of free months with no `months_free` coded.
   The row's ask is then on another basis than L1 expects, the ad looks cheap, and the market
   takes it at once. Data needed: a text match for free months and net-effective wording on
   rows with `months_free` of zero, feeding the existing net-ask conversion.
3. **Fees on top of the ask (421a surcharge, amenity and utility billing).** Arrow: level,
   and the time path through cuts. 3 reads in A and 2 in R. The ask understates the cost, the
   ad looks cheap to L1, and it stays and is cut. Data needed: a text match for surcharge and
   mandatory monthly fees; the amount is rarely stated.
4. **Walk-up floor and railroad layout.** Arrow: level. 14 reads in B against 3 in A and 2 in
   R. The market agrees with the low ask, so the miss is L1's. Data needed: a check of the
   coded floor against the floor stated in the text for walk-ups, and a `railroad` text flag.
   L1 already has the walk-up floor columns, so the first step is to read their fit on floors
   4 to 6.
5. **Wrong unit or sample photos.** Arrow: noise. 3 reads in A, 0 in B and R, and 2
   `staged_relist` reads in A whose text says the unit is already rented. The counts are too
   small to act on. Data needed: a text match for "similar unit", "photos of" and "has been
   rented".

## Weaknesses of the design

- The fast groups are ads marked rented on day 0 or 1 (78% of B and 66% of C at day 0). A
  same-day RENTED status is more likely a deal recorded after the fact, or an ad opened to
  record one, than a renter reacting to the ad in hours. For those ads the ask is close to a
  closed price, so B and C say more about asks that closed than about speed. Ranking by D
  within a middle band of days (2 to 7) would separate the two.
- D takes up under 9% of the variance of either outcome, and every ad of A has D near its
  ceiling: 90 days and a cut. A is then mostly a group of stale ads. Its 47 `none_apparent`
  reads against R's 40 suggest that the reason for the slow market is missing from the ad
  text, as a fault in the photos or on a visit would be.
- Readers see the text and the codes, with no photos or floor plans. Dark units, views of a
  wall and noise seldom appear in a broker's text, so `unit_fault` is biased toward faults a
  broker admits: stairs and railroad layouts.
- The held-out ads of the latest split are the newest ad of units with earlier ads. L1 knows
  those units' earlier asks, the gaps are small (the lowest tenth has a median of -0.12), and
  a unit's lasting fault is already in its earlier asks. Faults would show more on units with
  no history.
- The flag bar ran over 2 disagreement groups and about 20 causes with 100 reads a group. The
  single flag has a difference from R of 1.5 SEs.
- The readers' walk-up rule (floor 4 or higher counts) flags a quality L1 has columns for, so
  part of B's `unit_fault` count is not missing from L1.
- The cut uses the page price, so a concession added later is not counted as a cut.
