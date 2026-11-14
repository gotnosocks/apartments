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
