# Causal screens on L1 (2026-11-13)

Free checks on thelio against L1, the pool `drift-building-phase-b0-latest-9a7830fb-l1`, and
its dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`. No Modal job ran. The
scripts are in `docs/notes/causal-screens-2026-11-13/` and write their tables to
`/data1/apartments/tmp/sprint-20261113/`.

The gap is the log ask less L1's predictive median. Standard errors are clustered by building.
Where a check picks groups or fits means, it estimates them on one half of the buildings (split
by a hash of the building) and scores the other half, both ways.

## Summary

| screen | finding | fit |
|---|---|---|
| S3, the previous ad's ending | A relist within 2 months asks 1.4% to 2.0% under L1's median, and after a delisting or a pause the next ask sits 0.9% to 1.0% under | L2, a level per phase in the mean |
| S1, segment paths | Bedroom groups and zones moved on paths of their own in 2020 to 2023, worth 452 ± 50 elpd over a static offset | a walk for each bedroom group in each zone, around the citywide walk |
| S7, duplexes | Priced right on average, with asks scattered about 35% wider than others and 80% coverage of 0.72 | a scale factor on the noise for duplex units |
| S6, regulated rents | Units with the stabilized flag follow about 0.9 of the citywide walk | not now (20 to 60 elpd) |
| S2, the FARE Act | A stated renter's fee moved about 5% of ads before the Act by 1.4% to 1.7% | not on its own (20 to 80 elpd) |
| S7, outdoor space | Private outdoor space asks 1.2% over L1's median where either ad ran before 2021, and 0.1% where both ran later | none (-5 ± 19 elpd) |
| S4, competing supply | 0.2% within building in the top decile | none |
| S5, lease-up | No lease-up gap on L1; j9 prices buildings with few ads and a building's first year too low | none |
| S8, managers | A building's asks move with its manager's other buildings as much as with its neighbours | none |
| S10, Second Avenue Subway | About 0.5% for a stop 0.3 km closer | none |
| S11, negative amenity terms | 8 columns, none of them slow; the codes mix the apartment with the ad's writer | none |
| S9, school zones | not run | |

The fit candidates, in the order I would run them. Each elpd range is my prediction against L1
on the latest split, and each fit should cost about what L1 cost, $7.71. None is approved or
queued.

1. L2, L1 with a level per phase in the mean: 150 to 350 elpd, about 53 minutes. The previous
   ad's ending, as a later change on top of L2, adds 30 to 100 more.
2. The duplex scale factor: 150 to 300 elpd, and 80% coverage on duplex ads from 0.72 to 0.77
   or more. The dataset needs the duplex pattern as a column first.
3. Segment walks: 250 to 600 elpd. L1 ran within ten minutes of the hour cap, so a timing
   check on a subset comes first, or the deviations take quarterly steps.

L1T (`drift-building-phase-unitt`) gained 4,095 elpd over L1 as a free check and missed the
gate on R-hat. If a later L1T passes, I would put these changes on it instead. Its
heavy-tailed unit level may take up part of the duplex scatter, so the duplex range is the
one most likely to shrink.

I would make these data changes, all free, before the fits they feed: the duplex pattern as a column, a co-op flag
from PLUTO's building class for the j line, and amenity codes taken from all of a unit's ads.
A column for a building's turnover would test the j9 leads of S5. The local co-movement in S8
and S1 points at a path per neighbourhood, which `drift-local` tried before the building
path's sampler was fixed and has not been refit since.

## Predictions, written before each screen ran

- S1. Cross-fitted segment by quarter means remove under 15% of the excess squared gap of
  2020 to 2022, and coverage in those years moves by under 0.01. The segment repeat-ad indices
  predict the gap with a slope under 0.5. So the era's spread is scatter, which is Y1's
  account.
- S2. Ads stating a renter's broker fee fall to under 2% of new ads after June 2025. Before
  the Act, a no-fee ad asks 1% to 3% more than a fee ad of the same building and half-year.
  After it, an apartment whose previous ad charged a fee comes back 1% to 4% over L1's median
  against one whose previous ad said no fee, and before the Act that contrast is under 1%.
- S3. Under L1 the previous ad's ending still moves the level: after a delisting or a pause
  the next ask sits 0.5% to 1.5% under L1's median, and a cross-fitted level per ending and
  phase gains 50 to 150 elpd.
- S4. The building's other ads opened in the previous 60 days, per residential unit, lower the
  gap in the top decile by 0.5% to 1.5%. The neighbourhood's count against its own two-year
  mean moves the gap by under 0.3% across deciles.
- S11. Fewer than 10 of the amenity columns have a negative own coefficient with a 90%
  interval below zero, and none of them is among L1's slow quantities (bulk ESS over 1,000).
- S5. In new buildings, held-out ads opened within 12 months of the building's first ad sit
  1% to 3% under L1's median, and from 24 months on the gap is within 1% of zero, as in old
  buildings. A cross-fitted shift per age group and months gains under 50 elpd. On j9's new
  units the first-year gap is larger, 2% to 5% under the median.
- S6. Between two ads of a unit, units with the stabilized text flag follow 0.3 to 0.7 of the
  citywide walk, so their gap has a slope on the walk's change between -0.7 and -0.3. Lots
  where tax bills list stabilized units for half or more of the units, without the text flag,
  sit between -0.4 and -0.1. Lots never on the bills sit within 0.1 of zero.
- S7. Against the Sonnet readers, the duplex pattern has precision over 0.85 and recall over
  0.7. L1 has no duplex column, and a duplex ad asks 3% to 8% over L1's median within its
  building, with 1% to 4% left once L1's size term is counted. A stated outdoor size adds
  0.5% to 2% per doubling over the outdoor-type flags L1 already carries.
- S1, part C (written after parts A and B had run, which showed a segment by quarter shift
  gaining 583 elpd over a quarter shift). Most of that gain is a fixed offset of each
  segment: once a static segment mean is fitted first, the segment's own quarterly path adds
  under 150 elpd for the cell and under 75 for each single segment.
- S5, part B (written after S5 had run). j9's excess in buildings new to the data comes from
  their few training ads. Buildings with under 5 training ads sit 2% to 5% over j9's mean
  location and those with 100 or more within 1%, and within a count bin the first-year excess
  falls by half or more.
- S7, part B (written after S7 had run). A duplex is priced right on average but varies
  more: on L1 its 80% coverage is within 0.02 of other ads, and on j9's new units its squared
  gap is 1.1 to 1.4 times theirs. If private outdoor space gained value with the pandemic, a
  unit with the flag whose previous ad was before 2020 and whose held-out ad is from 2021 on
  sits 1% to 3% over other units with the same two periods, and with both ads from 2021 on
  the contrast is under 0.5%.
- S7, part C (written after part B had run, which found duplex ads with twice the squared gap
  of other ads on L1 and 80% coverage of 0.72). Half of that excess remains within building.
  Where the unit's previous ad does not match the duplex pattern or lists another bedroom
  count, the squared gap is twice that of duplex ads whose previous ad matches with the same
  bedrooms, and such pairs are 30% to 50% of duplex ads. The outdoor contrast grows with the
  years between the two ads, from under 0.3% within a year to 1% to 2% at four years or more.
- S7, part D (written after part C had run). A multiplier on L1's noise and unit sd for
  duplex ads, picked on the other half of the buildings, comes out at 1.3 to 1.5 and gains
  300 to 1,000 elpd on the 10,331 duplex ads. The same search on 10,000 other ads drawn at
  random picks 1.0 to 1.1 and gains under 20.
- S7, part E (written after parts B and C had run). A cross-fitted shift by the private
  outdoor flag within each pair of periods (the previous ad's and the held-out ad's, split at
  2020 and 2021) gains 30 to 120 elpd over a shift by the pair of periods alone.
- S5, part C (written after part B had run). Among j9's held-out new units in buildings with
  under 5 training ads, condo and co-op lots are over half and sit 5% to 10% over j9's mean
  location, and rental lots sit under 3% over it.
- S8. A manager's buildings in the other half explain 0.5% to 2% of the clipped held-out gap
  of its managed buildings, above the 95th percentile of the shuffles within neighbourhood,
  and gain 20 to 80 elpd. In a quarter, the gap follows the manager's other buildings with a
  slope of 0.1 to 0.3, about twice the slope on other managers' buildings within 1 km.
- S10. L1 has no transit column. Units whose straight-line distance to the nearest subway
  stop fell by 0.4 km or more when the Second Avenue line opened saw their asks rise 2% to 5%
  more between an ad before 2017 and an ad after than units with no gain, against pairs on the
  same side of the opening. The placebo at 2015 is within 1%. L1's held-out gap after 2017 has
  a slope on the gain under 2% per km, since building paths carry most of the step.

## S1: segment paths in 2019 to 2023

`s1_segments.py`, `s1b_paths.py`. I took L1's 73,025 held-out ads of 2019 to 2023, 45,818 of
them in 2020 to 2022. Their mean squared gap is 0.00839 in 2020 to 2022 against 0.00655 in
2019 and 2023 (0.00792 against 0.00620 with the gap clipped at 0.4), and 80% coverage is 0.736
against 0.803. Each segment's ads moved by the cross-fitted shrunk mean gap of their segment
and quarter:

| segments | share of the 2020-22 excess removed | elpd gain, 2019-23 | over the quarter shift | 80% coverage, 2020-22 |
|---|---|---|---|---|
| quarter only | 2.4% | 344 ± 33 | | 0.738 |
| bedrooms (0 to 3+) | 4.3% | 554 ± 42 | 210 ± 29 | 0.740 |
| Manhattan or not | 6.0% | 523 ± 47 | 178 ± 35 | 0.739 |
| lift, walk-up or unknown | 3.0% | 386 ± 33 | 41 ± 16 | 0.738 |
| stated size, four bins | 3.3% | 233 ± 35 | -111 ± 42 | 0.738 |
| bedrooms by zone by lift | 12.8% | 927 ± 63 | 583 ± 59 | 0.742 |

Part B built a repeat-ad index per segment from training pairs of consecutive ads in the
other half of the buildings. The held-out gap follows the segment's index change since the
unit's previous ad, less the citywide index's, with slopes of 0.45 ± 0.03 (bedrooms),
0.24 ± 0.01 (zone), 0.16 ± 0.03 (lift) and 0.27 ± 0.01 (the cell), on 67,936 ads (66,407 for
the cell).

The predictions held: the shifts remove at most 12.8% of the excess, coverage moves by
at most 0.006, and every slope sits under 0.5. The slopes sit well above zero, though, and the
cell shift gains 583 elpd over the quarter shift.

Part C fits the means one after another on one half of the buildings, each on what the
earlier ones left, and scores the other half: a quarter mean, then a static segment mean and a
quarter mean, then those two and a segment by quarter mean. The gain of the last design over
the middle one is the segment's own path, on the same 73,025 ads of 2019 to 2023.

| segments | static mean over the quarter mean | path over the static mean | path's spread (sd) |
|---|---|---|---|
| bedrooms | 36 ± 9 | 180 ± 20 | 0.40% |
| Manhattan or not | 16 ± 3 | 177 ± 32 | 0.63% |
| lift, walk-up or unknown | 40 ± 11 | 18 ± 7 | 0.15% |
| bedrooms by zone by lift | 111 ± 32 | 452 ± 50 | 1.06% |

The prediction missed for every segment but lift. A static offset accounts for the smaller
part of the shift's gain, and the paths of bedroom groups and zones account for most of it:
452 for the cell against the 150 I predicted, and 180 and 177 for bedrooms and zone against 75.
L1 already carries a path per building, but each one is shrunk toward zero on its own, so a
move shared by all studios or by all of Manhattan shows up only partly in it.

Verdict: a cause worth a fit. L1 moves every unit by one citywide walk, while studios, family
units, Manhattan and the other boroughs went through the pandemic and the recovery on paths
of their own. The change is a walk for each bedroom group in each zone, eight in all, as
deviations around the citywide walk with one shared step size. I expect 250 to 600 elpd over
L1 on the latest split, most of it from held-out ads of 2020 to 2023. Its parameters are a few
thousand weekly levels beside 935,000 unit levels, so the cost should stay near L1's $7.71.
L1 ran 3,165 s and 3,191 s in its two containers, though, within ten minutes of the hour cap,
so the fit needs a timing check on a subset before launch, or quarterly steps for the
deviations.

## S3: the previous ad's ending, with the months since it

`s3_ending.py`, `s3b_phase.py`. Each of L1's 189,647 held-out ads has an earlier ad of the
same unit, since the latest split holds out the newest ad of units with two ads or more. For
each I took the previous ad's last status from the raw status history and counted it only
where that status was dated before the held-out ad opened: rented or in contract (92,105),
no longer available (57,672), delisted (22,389) and temporarily off market (13,070), with
4,411 left undated. I also read the previous ad's price path: raised at some point, cut by 5%
or more by its end, or flat.

Mean gap in percent, by the months since the previous ad (L1's phase) and the previous ad's
ending. Clustered SEs run 0.05 to 0.25 points per cell.

| months since | ads | all | rented | no longer available | delisted | paused |
|---|---|---|---|---|---|---|
| 0-2 | 13,725 | -1.43 | -1.43 | -1.56 | -1.98 | -1.68 |
| 3-9 | 17,068 | -0.74 | -0.37 | -0.67 | -1.24 | -1.41 |
| 10-13 | 30,233 | -0.15 | -0.06 | -0.17 | -0.51 | -0.28 |
| 14-21 | 25,378 | -0.52 | -0.47 | -0.36 | -0.90 | -0.95 |
| 22-25 | 21,507 | -0.14 | -0.18 | 0.05 | -0.28 | -0.36 |
| 26+ | 81,736 | -0.38 | -0.40 | -0.15 | -0.90 | -0.90 |
| all | 189,647 | -0.44 | -0.34 | -0.27 | -1.00 | -0.89 |

I moved each held-out ad by the cross-fitted mean gap of its cell and rescored L1's
predictive:

| cells | elpd gain over L1 | over the constant | over phase |
|---|---|---|---|
| one cell (a constant) | 582 ± 37 | | |
| phase | 863 ± 49 | 281 ± 29 | |
| phase by ending | 937 ± 50 | | 74 ± 19 |
| phase by price path | 930 ± 50 | | 67 ± 17 |
| phase by ending by price path | 919 ± 50 | | 56 ± 25 |
| phase by ending by time off market | 927 ± 53 | | 64 ± 23 |

L1's predictive median sits above its held-out asks: the mean gap is -0.44% (SE 0.02), and a
constant shift of every ad gains 582 elpd. Part C breaks that offset down by year. On top of
the constant, a level per phase gains 281 ± 29, and 192 of it comes from the 13,725 ads
opened within 2 months of the previous ad. The 9,685 of them with a dated ending sit 1.4% to
2.0% under the median whatever that ending was, with 80% coverage of 0.73 to 0.75, and the
4,040 without one sit 0.82% under. L1 widens their scale by
8% over the 10-13 month phase and leaves their center at the unit's level.

After a delisting or a pause, the next ask sits 1.00% and 0.89% under the median, against
0.34% after a rental. In every phase but 0-2 the gap after a delisting or a pause runs 0.1
to 1.0 points under the gap after a rental. A unit's level in L1 comes from its earlier asks,
and an ad that ended in a delisting or a pause ended on an ask that did not rent, so the
unit's next ad comes back lower. The ending adds 74 ± 19 elpd over phase, the price path 67
± 17, and both together add no more than either alone.

Part C, `s3c_offset.py`, splits the common offset by the year of the held-out ad. Gaps are in
percent, with clustered SEs of 0.04 to 0.34 points:

| year | ads | mean gap | 80% coverage | the constant's elpd |
|---|---|---|---|---|
| 2014 to 2018 | 18,318 | -0.16 to -0.58 | 0.78 to 0.82 | 96 |
| 2019 | 8,051 | -0.10 | 0.84 | 8 |
| 2020 | 15,026 | -0.05 | 0.74 | -3 |
| 2021 | 18,211 | -0.28 | 0.72 | 58 |
| 2022 | 12,581 | -1.06 | 0.75 | 103 |
| 2023 | 19,156 | -0.91 | 0.79 | 115 |
| 2024 | 26,334 | -0.61 | 0.82 | 77 |
| 2025 | 34,428 | -0.51 | 0.82 | 94 |
| 2026 | 37,542 | -0.19 | 0.83 | 34 |

By quarter the gap shrinks from -0.80% in 2024Q1 to -0.11% in 2026Q3 and +0.08% in the 2,357
ads of 2026Q4 so far. A held-out ad is its unit's newest, so a held-out ad of 2022 belongs to
a unit with no ad in the years since, most likely because its tenant stayed. Tenants stay
more often on a lease signed at a low ask, while L1 takes its walk for 2022 from training ads,
each of them followed by another ad of the unit. The gap is largest for 2022 and 2023, when
asks rose fastest and a lease signed then soon looked cheap, and it fades in 2026, when a
held-out ad has had only months in which to be followed. I read most of the common offset as
this selection in the latest split. A model cannot learn it, since an ad carries no sign that
it will be its unit's last, so I count every shift in this note over the constant and leave
the constant out of the fit candidates.

Part D, `s3d_pairs.py`, tests that reading and asks whether a fit could learn the phase level
from training ads. I wrote no prediction for it before it ran. I paired every ad that has an
earlier ad of its unit with the one before it, 961,075 pairs, sorted the pairs by L1's own
`phase_index` (it agrees with L1's held-out phases on every ad), and took the change in log
latest ask. Then I took off the mean change of all pairs with the same quarters for the two
ads. In percent:

| months since | training pairs | mean change | held-out pairs | mean change | held-out less training, same quarters |
|---|---|---|---|---|---|
| 0-2 | 81,137 | -2.06 | 13,725 | -2.24 | -0.14 ± 0.07 |
| 3-9 | 82,440 | -0.75 | 17,068 | -0.42 | -0.28 ± 0.09 |
| 10-13 | 147,070 | +3.25 | 30,233 | +3.88 | -0.31 ± 0.06 |
| 14-21 | 116,391 | +3.43 | 25,378 | +4.39 | -0.38 ± 0.07 |
| 22-25 | 87,328 | +5.85 | 21,507 | +8.03 | -0.19 ± 0.07 |
| 26+ | 257,062 | +10.13 | 81,736 | +15.51 | -0.28 ± 0.05 |
| all | 771,428 | | 189,647 | | -0.27 ± 0.03 |

A relist within two months repeats the last ask in the median pair, and the mean pair comes
back 2.1% lower, in training pairs as in held-out ones. So a level for that phase has 81,137
training pairs to learn from. Against training pairs of the same quarters, held-out pairs come
back 0.27 points lower in every phase, which accounts for most of L1's 0.44% common offset and
fits the selection reading.

The phase level holds across the periods. Phase 0-2 sits 1.40% under the median for held-out
ads up to 2023 and 1.47% under from 2024, with 80% coverage of 0.76 and 0.75. The other phases
move with the period: 3-9 goes from -0.93% to -0.51%, 22-25 from -0.34% to +0.03%, and 26+
from -0.21% to -0.51%.

The first half of the prediction held: after a delisting the next ask sits 1.00% under the
median and after a pause 0.89%. The second half missed. I predicted 50 to 150 elpd for a level
per ending and phase, and it gained 937, since I had not counted on L1's common offset (582)
or on a level for the phase itself (281). The ending's own part, 74 ± 19 over phase, falls
inside the range.

Verdict: a cause worth a fit. The change is L2, L1 with a level per phase in the mean, six
levels beside 10-13 months. I expect it to gain 150 to 350 elpd over L1 on the latest split.
The previous ad's ending is a second, later change, worth 30 to 100 more. L2 adds one
seven-level vector to L1's mean on the same data and sampler, so it should cost about what
L1 cost, $7.71 for its two containers, and run near its 53 minutes.

## S4: competing supply when the ad is priced

`s4_supply.py`. Each count reads only the dates ads opened (the first ACTIVE event of the raw
status history, which every row of the dataset has). For each held-out ad I counted the
building's other units with an ad opened in the 60 days before its price date, per
residential unit of the lot in PLUTO, and the neighbourhood's ads opened in the 30 days before
it over the neighbourhood's mean 30-day count in the two years before (a log ratio, from 2016
on). The gap by decile, in percent, with the gap less its building's mean in brackets:

| decile | building's other ads per unit, 60 days | gap | within building | neighbourhood ratio | gap | within building |
|---|---|---|---|---|---|---|
| none | 0 (58,165 ads) | -0.62 | (-0.02) | | | |
| 1 | 0.0001 to 0.013 | -0.08 | (0.10) | -3.80 to -0.40 | -0.66 | (-0.11) |
| 2 to 8 | 0.013 to 0.20 | -0.17 to -0.45 | (-0.05 to 0.08) | -0.40 to 0.30 | -0.33 to -0.67 | (-0.12 to 0.10) |
| 9 | 0.20 to 0.41 | -0.46 | (0.01) | 0.30 to 0.41 | -0.30 | (0.05) |
| 10 | 0.41 to 49 | -1.05 | (-0.20) | 0.41 to 1.48 | -0.30 | (0.11) |

Clustered SEs of the decile gaps run 0.06 to 0.08 points.

| count | slope of the gap | within building | decile shift, elpd over the constant |
|---|---|---|---|
| building's other ads per unit | -0.17% ± 0.06 per unit | -0.18% ± 0.07 | 43 ± 20 |
| building's other ads, raw | 0.007% ± 0.002 per ad | -0.010% ± 0.005 | -26 ± 13 |
| neighbourhood ratio | 0.37% ± 0.06 per log unit | 0.29% ± 0.07 | 4 ± 10 |

In the top decile of the building count, where the building's other units opened 0.41 ads
or more per unit in the 60 days before, the gap sits 1.05% under the median, 0.6 points under
the mean of all ads. Almost all of that comes from which buildings fall in the decile, mostly
small ones where one or two other ads clear the bar: less the building's own mean, the top
decile sits 0.20% under. The neighbourhood ratio has the sign opposite a supply story. Asks
sit higher than L1 predicts in months when more ads than usual open nearby, by 0.37 points
from the bottom decile to the top, and a shift by its decile gains nothing over the constant.
The busy months are the summer ones, so the ratio probably reads demand more than supply.

The first prediction held on the raw gap and missed within buildings: the top decile sits
0.6 points under the mean, inside the 0.5% to 1.5% I predicted, but only 0.20% under once the
building's own mean is taken off. The second missed narrowly: the neighbourhood ratio moves
the gap by 0.37 points across deciles against my bound of 0.3, with the opposite sign to the
one I expected.

Verdict: nothing worth a fit now. A term for the building's competing ads would gain at most
the decile shift's 43 ± 20 elpd, about 2 SE, and the within-building effect is 0.2%.

## S2: the FARE Act

`s2_fare.py`. The GraphQL digests' `noFee` field reads false on all 131,912 ads that carry it,
so I read the fee from each listing's last description: the `no_fee` text flag, and my own
pattern for wording that puts a broker's fee on the renter. An ad with neither counts as
silent. L1 has no column for either.

Shares of the ads opened in each half-year:

| half | ads | renter's fee stated | no fee |
|---|---|---|---|
| 2023H1 | 71,925 | 7.2% | 12.9% |
| 2024H1 | 73,079 | 6.8% | 12.7% |
| 2024H2 | 75,381 | 5.8% | 13.2% |
| 2025H1 | 73,458 | 4.9% | 13.1% |
| 2025H2 | 72,227 | 1.8% | 11.4% |
| 2026H1 | 72,425 | 1.7% | 9.8% |
| 2026H2 to October | 46,880 | 1.5% | 8.4% |

By month, the fee share was 5.9% in May 2025, 3.2% in June, 2.1% in July and 2.3% in August,
and has stayed between 1.3% and 1.9% since September 2025. The no-fee wording also thinned,
from 13% to 8%, once a no-fee ad stopped standing out.

Within a building and half-year, held-out no-fee ads asked more than fee ads in the halves
with at least 30 fee ads in buildings holding both: 1.4% ± 1.2 in 2024H1, 1.7% ± 0.9 in
2024H2 and 1.6% ± 0.8 in 2025H1, against 0.6% ± 1.8 and -0.5% ± 2.4 in 2020H2 and 2021H1.
Units that switched show the same step. Before the Act, a held-out ad that stated a fee after
a no-fee ad sat 1.86% under L1's median (1,061 ads), against 0.59% for no fee after no fee,
and a no-fee ad after a fee ad sat 0.36% over (647 ads), against 0.99% under for fee after
fee.

For the Act itself I compared held-out ads whose previous ad stated a fee with those whose
previous ad said no fee. Before the Act the first group sat 0.23% ± 0.12 higher against
L1's median. After it, with almost no current ad stating a fee, the first group sat 0.80% ±
0.18 higher (2,428 ads against 8,266), so the Act moved that contrast by 0.57 points (about
± 0.22). A renter's fee runs from 8% to 15% of a year's rent, and the asks of units that
used to charge one rose by well under a tenth of that.

Two of the predictions held and two missed narrowly. The fee share fell under 2% of new ads
from September 2025, though July and August sat at 2.1% and 2.3%. The no-fee premium within
building and half-year was 1.4% to 1.7% in 2024 and 2025, inside 1% to 3%. After the Act
the units that used to charge a fee came back 0.80% over the others, under the 1% to 4% I
predicted, and before it the contrast was 0.23%, under 1% as predicted.

Verdict: a small feature, no cause for a fit on its own. A column for a stated renter's fee
would move about 5% of ads before the Act by 1.4% to 1.7% and almost none after it. I expect
20 to 80 elpd on the latest split, where most held-out ads are recent. The Act's own effect
on asks, 0.6%, is too small and too narrow for a model term.

## S11: amenity columns with a negative sign

`s11_signs.py`. L1 carries 53 amenity, feature, view and outdoor columns. For the 22 of them
coded on the ad or the unit it also carries a unit mean (`umean:`), the column's average over
the row and its unit's training rows priced earlier. So for those 22 the own coefficient
measures the change between ads of a unit, and its sum with the unit mean measures the
difference between units. The building columns carry only their own coefficient.

17 own coefficients have a negative median, and 8 have a 90% interval below zero. 8 sums are
negative, 7 of them with a 90% interval below zero. In percent of the ask:

| column | own, median [90%] | sum with the unit mean |
|---|---|---|
| ad:fireplace_wood | -0.98 [-1.41, -0.40] | +3.42 [+2.74, +3.96] |
| bld:amen_live_in_super | -0.53 [-0.64, -0.43] | |
| bld:elevator_unknown | -0.47 [-0.83, -0.16] | |
| ad:private_outdoor_patio | -0.33 [-0.44, -0.23] | +0.55 [+0.44, +0.64] |
| ad:feat_fireplace | -0.31 [-0.43, -0.17] | +1.96 [+1.84, +2.07] |
| ad:views_water | -0.27 [-0.43, -0.14] | +1.45 [+1.32, +1.60] |
| ad:feat_private_outdoor_space | -0.14 [-0.23, -0.03] | +2.77 [+2.69, +2.85] |
| ad:feat_hardwood_floors | -0.12 [-0.18, -0.06] | -0.66 [-0.73, -0.59] |
| ad:private_outdoor_roof_rights | +0.30 [+0.17, +0.42] | -2.04 [-2.15, -1.93] |
| ad:fireplace_decorative | +0.49 [+0.28, +0.69] | -0.62 [-0.85, -0.41] |
| ad:views_city | -0.02 [-0.14, +0.08] | -0.42 [-0.53, -0.32] |
| ad:private_outdoor_balcony | -0.03 [-0.11, +0.07] | -0.33 [-0.41, -0.25] |
| ad:views_park | -0.00 [-0.12, +0.13] | -0.27 [-0.38, -0.16] |
| ad:private_outdoor_garden | +0.16 [+0.05, +0.28] | -0.09 [-0.17, -0.01] |

All of them have split R-hat at most 1.004 and bulk ESS over 2,100.

Part B read the raw codes on L1's training rows. Five of the six negative own terms belong to
columns whose sum is positive: a unit with a fireplace, water views or a patio asks more than
one without, and among a unit's own ads the one stating the code asks a little less. The writer
of an ad decides whether it states a code. Hardwood floors changes between ads of a
unit in 42% of units with two ads or more, and 71% of PARTNER-source ads state it against 0.4%
of FEED ads. The view codes change in 30% to 36% of units and come mostly from PARTNER and
OWNER ads. L1 gives the source a level of its own, but the codes an agent adds to a fuller ad
still carry its part of the change between ads.

The negative sums follow the building stock. Roof rights appear in 11% of ads outside
Manhattan against 1% in Manhattan and in 12% of ads in buildings from 2010 on, so the code
marks new outer-borough buildings, which ask less than the other 2010 buildings L1 compares
them with. Hardwood floors and decorative fireplaces sit mostly in old buildings, 21% of ads
in buildings from before 1900 state a fireplace. A live-in super appears in 73% to 77% of
ads in buildings from 1940 to 1999, in 59% of Manhattan ads against 25% elsewhere, and its
share over buildings correlates 0.35 with the elevator code and 0.30 with the doorman code,
so it marks the mid-century elevator rentals.

The prediction held: 8 columns, under 10, and none of them is slow.

Verdict: nothing worth a fit. The ad-level codes mix the apartment with the writer of the ad.
Taking a unit's codes from all of its ads would separate them, which is a data change worth
making at some later fit rather than a fit of its own.

## S5: lease-up of new buildings

`s5_leaseup.py`. A building counts as new where PLUTO's year built is 2014 or later and its
first ad in L1's dataset opened within two years of that year (14,727 held-out ads), and old
where it was built before 2010 (165,435). For each held-out ad I counted the months since its
building's first ad opened. Mean gaps in percent with clustered SEs, for L1 and for j9's new
units:

| months since the building's first ad | L1, new | L1, old | j9 new units, new buildings | j9 new units, old buildings |
|---|---|---|---|---|
| 0-6 | -1.37 ± 0.43 (383) | -1.70 ± 0.22 (2,161) | +3.00 ± 0.69 (445) | +4.72 ± 1.34 (268) |
| 6-12 | -0.53 ± 0.35 (527) | -0.80 ± 0.27 (1,570) | +3.93 ± 0.84 (146) | -0.91 ± 1.60 (45) |
| 12-24 | -0.15 ± 0.28 (1,483) | -0.27 ± 0.13 (5,048) | +0.33 ± 1.50 (159) | -1.43 ± 1.17 (101) |
| 24-48 | -0.26 ± 0.16 (3,204) | -0.41 ± 0.08 (13,855) | -0.97 ± 1.43 (266) | +0.54 ± 0.96 (131) |
| 48+ | -0.61 ± 0.09 (9,130) | -0.42 ± 0.03 (142,801) | +0.91 ± 0.54 (665) | +0.85 ± 0.14 (6,424) |

A cross-fitted shift per group and months gains 572 ± 39 elpd over L1, -10 ± 14 over the
constant, and -6 ± 5 on the new buildings' ads.

The early gap in L1 is the same in old buildings as in new ones, and it comes from the lease
phase. A held-out ad within 6 months of its building's first ad follows an ad of its own unit
inside those months, so it falls in phase 0-2 or 3-9, where S3 put the gap at -1.43% and
-0.74%. j9 tells a different story: its new units in buildings new to the data ask 3% to 5%
over j9's median, in the 125 old buildings as much as in the 46 new ones. When few of a
building's ads exist, j9 sets its level close to what the building's attributes and place
predict, and buildings that have just come onto StreetEasy ask more than that. So the excess
points to a building's first appearance, after construction, a gut renovation or a change of
owner, rather than to lease-up.

The prediction missed. The first-year gap in new buildings averages -0.88% over 910 ads, just
under the 1% to 3% I predicted, and old buildings show the same gap, so it does not mark
lease-up. From 24 months on the gap sits within 1% of zero, and the shift gains under 50 elpd,
as predicted. On j9 the first-year gap has the opposite sign, +3.0% and +3.9% against the 2%
to 5% under the median I predicted.

Verdict: nothing worth a fit for lease-up. j9's early excess is a lead for the new-unit
model, the level of a building with few ads. A free check on j9 by the building's count of
training ads and PLUTO's alteration year comes before any term.

Part B (`s5b_j9level.py`) splits j9's 9,346 held-out new units by the building's count of
j9 training ads, and then by whether the ad opened within a year of the building's first ad.
The gap is from j9's mean location.

| training ads in the building | n | gap | first year | later |
|---|---|---|---|---|
| none | 84 | +9.2 ± 3.2% | +9.2 ± 3.2% (84) | |
| 1 to 4 | 331 | +5.1 ± 1.1% | +2.2 ± 2.2% (94) | +6.2 ± 1.2% (237) |
| 5 to 19 | 982 | +1.5 ± 0.5% | +3.3 ± 1.3% (154) | +1.1 ± 0.5% (828) |
| 20 to 99 | 2,834 | +1.3 ± 0.2% | +3.2 ± 0.6% (492) | +0.9 ± 0.2% (2,342) |
| 100 or more | 5,115 | +0.5 ± 0.2% | +3.3 ± 1.0% (145) | +0.4 ± 0.2% (4,970) |

By PLUTO's years, the first-year excess is +3.5 ± 0.6% for buildings built from 2010 (652
ads), +2.8 ± 1.5% for those altered from 2010 (108) and +4.5 ± 1.6% for older ones unaltered
since (209), against +0.1% to +1.0% later.

The prediction held in part. A building with few training ads does sit high: +5.9% over
the 415 ads with under 5, against a range of 2% to 5%, and +0.5% at 100 or more, within 1%.
But within a count bin the first-year excess does not fall at all: it is about +3.3% in every
bin from 5 ads up and in every age group. So j9 misses on the building level and on the first year separately. Its building level
shrinks toward a location map and attributes that sit too low for buildings with few ads, and the
first year after a building's first ad asks about 3% more whatever the building's count or
age. For an old, unaltered building the first ad in the data likely marks a renovation or a
new owner that PLUTO does not record. Part C checks whether the few-ad buildings are condos
and co-ops, rented by their owners one apartment at a time.

Part C (`s5c_class.py`) splits the same ads by PLUTO's building class: condo (class R),
co-op (C6, C8, D0, D4), rental (the other A, B, C, D and S classes) and other.

| training ads | rental | condo | co-op |
|---|---|---|---|
| under 5 | +5.6 ± 1.2% (308, 74%) | +7.5 ± 3.8% (58, 14%) | +10.8 ± 3.2% (38, 9%) |
| 5 to 19 | +0.9 ± 0.5% (727) | +4.1 ± 1.7% (140) | +2.3 ± 1.3% (68) |
| 20 to 99 | +1.1 ± 0.3% (2,273) | +2.5 ± 0.6% (354) | +1.2 ± 0.9% (160) |
| 100 or more | +0.1 ± 0.2% (3,293) | +1.2 ± 0.3% (1,490) | +2.0 ± 1.0% (136) |

The prediction missed on its main claim. Condos and co-ops are 23% of the few-ad ads, not over
half, and rental buildings with under 5 training ads still sit +5.6% over j9. Condos and
co-ops there sit about where I predicted, at +7.5 ± 3.8% (58 ads) and +10.8 ± 3.2% (38). Apart from that, an apartment in a condo or co-op
asks 1% to 4% more than j9 expects at every count, although j9 carries a condo flag, and
it has no co-op flag at all.

Verdict for S5: no lease-up term, and no fit from parts B and C alone. They leave leads
for the new-unit model. A co-op flag from PLUTO's building class is a data change for the
next fit of the j line, and the condo flag's size deserves a look there. The excess of
rental buildings with few ads and the first-year excess of about 3% both point at what a
building's first ads in the data mean: a vacancy after a long tenancy, a renovation, a new
owner. A column for the building's turnover, its ads per residential unit and year, would
test that, counting for each ad only the building's ads before it.

## S6: regulated rents and the Rent Guidelines Board

`s6_regulated.py`. L1 carries a unit from one ad to the next by the citywide walk, the same
for every unit. For each held-out ad I took the walk's change between the latest-ask days of
the unit's previous ad and this one (dL, from L1's kept draws) and the one-year guideline
change over the same span (dR), and regressed the gap on them in three groups. A slope b on
dL means the group's units move by 1 + b of the walk.

| group | ads | mean gap | slope on dL | within building | joint, dL | joint, dR |
|---|---|---|---|---|---|---|
| stabilized by the ad's text flag | 4,483 | -1.37% | -0.103 ± 0.013 | -0.078 ± 0.015 | -0.131 ± 0.016 | +0.16 ± 0.06 |
| lot half or more stabilized on the tax bills, no flag | 42,013 | -0.68% | -0.038 ± 0.004 | -0.037 ± 0.004 | -0.066 ± 0.005 | +0.16 ± 0.02 |
| lot never on the bills, no flag | 65,170 | -0.45% | -0.031 ± 0.003 | -0.027 ± 0.003 | -0.087 ± 0.004 | +0.29 ± 0.02 |

The slope on dL by the period of the held-out ad:

| group | 2016-19 | 2020-21 | 2022-23 | 2024-26 |
|---|---|---|---|---|
| text flag | | -0.16 ± 0.03 | -0.14 ± 0.03 | -0.08 ± 0.02 |
| stabilized on the bills | +0.11 ± 0.04 | -0.10 ± 0.01 | -0.07 ± 0.01 | -0.03 ± 0.01 |
| never on the bills | +0.21 ± 0.05 | -0.16 ± 0.01 | -0.04 ± 0.01 | -0.01 ± 0.00 |

Every group lags the walk a little, and the lag changes with the period, so part of each slope
comes from L1's single walk against the paths of segments, as in S1. On top of that, the
stabilized flag adds about -0.07 to the slope of the unregulated lots overall and -0.08 to
-0.10 from 2022 on. Flagged units follow about 0.9 of the walk where unregulated lots follow
nearly all of it. Their gap runs from +1.64% when the walk fell more than 5% between the two
ads to -3.20% when it rose more than 20%. Ads in lots with stabilized units on the bills but no
flag behave like the unregulated lots (-0.04 against -0.03), so most of the units advertised
there are deregulated or leave their status out. The guideline change does not separate the
groups: its joint coefficient is larger for the unregulated lots (+0.29) than for the flagged
units (+0.16), so it reads the period more than regulation.

The first two predictions missed: the flagged units' slope of -0.10 sits outside -0.7 to
-0.3, and the stabilized lots' -0.04 sits outside -0.4 to -0.1. The third held, with the
unregulated lots at -0.03, within 0.1 of zero.

Verdict: a small cause, not worth a fit now. The change would let flagged units follow a
fraction of the walk between their ads, one coefficient. Moving 2.4% of held-out ads by about a
tenth of the walk's change, I expect it to gain 20 to 60 elpd, near the 2 SE bar, at L1's
cost. The flag comes from ad text, and the tax bills count units by lot. A DHCR list by unit
would sharpen the groups, and none is on disk.

## S7: duplex apartments and stated outdoor sizes

`s7_text.py`, `s7_score.py`, with the reader prompt in `s7_reader_prompt.md` of the output
folder. I matched each listing's last description for the word duplex or triplex, dropping
ads that call the building a duplex or two-family house, or for wording of an apartment on two
levels (bi-level, spans two floors, internal staircase). The match marks 6.0% of the dataset's
1,790,425 rows and 5.4% of held-out ads. A second pattern reads a private outdoor size on 0.58%
of rows.

Sonnet readers labelled 400 ads from the text alone: 200 the pattern matched, 100 with a parsed
outdoor size, 50 unmatched ads with weaker words (upper or lower level, stairs, loft, mezzanine) and
50 other unmatched ads at random. The pattern's precision is 0.93 (186 of 200). None of the 100 unmatched ads is a
duplex, so recall comes out at 1.0, but 50 random reads leave its 95% lower bound near 0.5. The
parsed outdoor size agrees with the readers' within 5% on 78% of the 100.

Every held-out ad of L1 has an earlier ad of its unit, so the split by first ad that I planned
is empty on L1 and its unit level has a duplex's earlier asks to learn from. Against the rest
of the held-out ads:

| duplex ads | n | gap | over the rest | within building |
|---|---|---|---|---|
| all | 10,331 | -0.26% | +0.19 ± 0.12% | +0.06 ± 0.08% |
| with a stated size | 3,323 | -0.68% | -0.38 ± 0.21% | -0.46 ± 0.13% |
| without one | 7,008 | -0.06% | +0.46 ± 0.15% | +0.30 ± 0.10% |

A cross-fitted shift for duplex ads loses 24 ± 4 elpd against a constant shift of every
held-out ad. On j9, which carries no unit history for a new unit, 478 of its 9,346 held-out new
units match the pattern, and they sit +0.35 ± 0.70% over the rest and +0.25 ± 0.25% within
building, measured from j9's mean location.

Held-out ads with the private outdoor flag and a stated outdoor size number 681. Their gap does
not rise with the size: the slope is -0.02 ± 0.16% per doubling. Every bin from 100 square feet
up sits 1.8% to 2.5% over L1's median (about 1% within building), and the 68 ads under 100
square feet sit at -0.1%.

Scoring the predictions: precision over 0.85 held at 0.93. Recall over 0.7 held on the point
estimate, but the reads are too few to rule out 0.5. A duplex 3% to 8% over L1's median within
building missed, at +0.06 ± 0.08%, and 1% to 4% left once size is counted missed on both
models (-0.46 ± 0.13% on L1, +0.25 ± 0.25% on j9). The outdoor slope of 0.5% to 2% per doubling
missed.

For the level, nothing calls for a fit. L1 prices a duplex from its unit's earlier asks, and j9 prices a new duplex
from its stated size, bedrooms and building with no excess left over. The split by stated size
looks like L1's size term at work: a duplex without a stated size is larger than its
bedrooms suggest, and one with a stated size may count a lower level that renters value at
less than full rate. Both stay under 0.5%. I keep the duplex pattern as a data column for the
site and for later screens. Part B, below, checks the spread.

Part B (`s7b_spread.py`) compares the spread. On L1 the clipped squared gap of duplex ads is
0.0114 against 0.0059 for the rest (+0.0054 ± 0.0003), and L1's 80% interval covers 0.719 of
them, 0.083 ± 0.005 under the rest. On j9's new units it is 0.0182 against 0.0084 (+0.0099 ±
0.0016), but within building the excess on j9 is +0.0001 ± 0.0006. The prediction missed on
both: coverage is 0.08 under the rest, not within 0.02, and the ratio on j9 is 2.2 rather than
1.1 to 1.4.

Part C (`s7c_unitkey.py`) asks whether two ads of a duplex unit describe two apartments. On
L1, 38% of the excess remains within building (+0.0021 ± 0.0002).

| duplex ads, by the unit's previous ad | share | squared gap | 80% coverage |
|---|---|---|---|
| a duplex, same bedrooms | 79% | 0.0110 | 0.729 |
| not a duplex, same bedrooms | 18% | 0.0119 | 0.700 |
| a duplex, other bedrooms | 1.6% | 0.0172 | 0.559 |
| not a duplex, other bedrooms | 1.2% | 0.0216 | 0.504 |
| other ads, same bedrooms | | 0.0058 | 0.805 |
| other ads, other bedrooms | | 0.0184 | 0.540 |

By the lot's residential units the squared gap of duplex ads runs 0.0098 to 0.0140 against
0.0048 to 0.0081 for other ads, and coverage 0.70 to 0.72 against 0.80 to 0.81, in every size
from 1 to 5 units to over 100. The prediction came close on the share within building, 38% against the half I
predicted, and missed on the rest. Mismatched previous ads are 21% of duplex ads, not 30% to 50%, and
they miss by about as much as matched ones unless the bedrooms change, which raises the
squared gap for any ad. A duplex whose previous ad was the same duplex with the same bedrooms
still has twice the squared gap of other ads.

Correction, 2026-11-14 (`duplex-within-building-2026-11-14.md`). The within-building figure
above subtracts a building mean that includes the ad, so each square carries (n-1)/n of the
ad's variance about its building's center, and an ad alone in its building counts as zero. On
the 176,345 held-out ads in buildings with 2 or more, with each square times n/(n-1), the
duplex excess within building is +0.0039 ± 0.0002 against +0.0050 ± 0.0003 overall, a share of
0.78 (0.74 to 0.83 over 2,000 resamples of the buildings). The prediction that half of the
excess remains within building therefore missed on the high side, where I scored it above as
close. The same note recomputes part A's level within building, the two j9 figures, the outdoor
slope and S4's top decile, and every verdict holds.

Part D (`s7d_scale.py`) multiplies L1's noise scale and unit sd for duplex ads by m and
rescores its predictive. Picked on the other half of the buildings, m comes out at 1.3 in one
half and 1.4 in the other, and gains 255 ± 30 elpd on the 10,331 duplex ads. On 10,000 other
ads drawn at random the same search picks 1.0 both ways and gains nothing, and m of 1.1
already loses 31 there. The multiplier held in its range of 1.3 to 1.5, and the gain fell
short of 300 to 1,000. The control held.

L1 misses duplexes in the spread of their asks: they scatter about 35% wider around its
median than other asks, in small buildings and large ones, with the same
unit and bedrooms as before. A duplex has few comparable apartments, and that likely leaves
its landlord less sure of its price. L1 already puts the lease phase in its scale, and the
duplex belongs there in the same way.

Verdict: a cause worth a fit. The change is a scale factor on L1's noise for units the duplex
pattern matches, one coefficient, with the pattern added to the dataset as a column first. I
expect 150 to 300 elpd over L1 on the latest split, and 80% coverage on duplex ads to rise
from 0.72 to 0.77 or more. It adds a column and a coefficient to L1, so it should cost about
L1's $7.71 and run near its 53 minutes. A wider scale for other unusual units (penthouses,
garden apartments, a townhouse floor) is the next screen in this direction, and it is free.

Part B also compares held-out ads with the private outdoor flag, 12.2% of them, against other
ads with the same pair of periods: the period of the unit's previous ad and that of the
held-out ad, split at 2020 and 2021. In percent, with clustered SEs:

| previous ad | held-out ad | n | with the flag | flag over the rest |
|---|---|---|---|---|
| to 2019 | to 2019 | 26,365 | 2,745 | +1.25 ± 0.21 |
| to 2019 | 2020 | 12,626 | 1,409 | +1.83 ± 0.28 |
| to 2019 | 2021+ | 32,194 | 3,759 | +1.24 ± 0.18 |
| 2020 | 2020 | 2,390 | 257 | +0.17 ± 0.61 |
| 2020 | 2021+ | 19,341 | 2,237 | +0.86 ± 0.22 |
| 2021+ | 2021+ | 96,717 | 12,787 | +0.14 ± 0.08 |

Part C splits the same contrast by the years between the two ads: +0.48 ± 0.13% within a
year, +0.60 ± 0.11% at one to two years, +0.63 ± 0.12% at two to four and +0.81 ± 0.17% at
four or more. Part E (`s7e_outdoor.py`) moves each held-out ad by the cross-fitted mean gap of
its pair of periods, and then of its pair and the flag. The flag adds -5 ± 19 elpd to the
pair's 607 ± 43, most of which is the common offset of S3.

Scoring the predictions: with the previous ad before 2020 and the held-out ad from 2021, the
flag sits +1.24% over the rest, inside 1% to 3%, and with both ads from 2021 on it sits +0.14%,
under 0.5%. Both held, but the pandemic story they were meant to test did not: pairs with both
ads before 2020 show the same +1.25%. The contrast grows with the years between ads from 0.48%
to 0.81%, where I predicted under 0.3% and 1% to 2%, so both ends missed. The gain of 30 to 120
elpd missed at -5 ± 19.

Verdict for outdoor space: no fit. L1 prices a unit with private outdoor space about 1.2% low
when its held-out ad or the previous ad ran before 2021, and about right when both ran later,
as most held-out ads did. L1's outdoor terms stay fixed over time and draw mostly on recent
ads, so a premium larger before 2021 would show up this way. The shift moves about 5% of
held-out ads by a small fraction of L1's noise scale and gains nothing on the latest split.

## S8: buildings with the same manager

`s8_portfolio.py`. HPD's registration contacts are not on thelio, so I took the manager from
the ads. A building gets one where a lister placed at least half of its five or more ads,
`rentfrontier.lister.kind` reads the lister as a management company, and the same lister holds
two buildings or more this way. That gives 180 managers of 2,214 buildings.

For part A, I scored each managed building's clipped held-out gap with the shrunk mean of its
manager's buildings in the other half. The mean explains -0.07% of the clipped gap, against a
95th percentile of +0.02% over 50 shuffles of managers within neighbourhood, and the shift
loses 16 ± 12 elpd when I rescore L1's predictive with it (-24 ± 13 against a constant shift).
L1's building levels already hold whatever a manager's buildings share.

For part B, I took off each quarter's citywide mean gap and regressed a held-out ad's gap on
the mean over the manager's other buildings in the same quarter and on the mean over other
managers' buildings within 1 km, on 29,173 ads in 1,400 buildings.

| | manager's other buildings | other managers within 1 km |
|---|---|---|
| gap | 0.24 ± 0.03 | 0.24 ± 0.06 |
| gap less the building's mean | 0.24 ± 0.03 | 0.16 ± 0.07 |

Scoring the predictions: the explained share of 0.5% to 2% over the shuffles missed, as did
the gain of 20 to 80 elpd. The slope of 0.1 to 0.3 on the manager's other buildings held at
0.24. Twice the slope on nearby buildings missed: the two match on the gap, and within
building the gap between them, 0.08 ± 0.07, is within noise.

Verdict: no manager term. A building's asks move with its manager's other buildings in a
quarter about as much as with its neighbours, so the shared move is local rather than one of
ownership. That is the same lack S1 found by segment. L1 has a path per building and none for
a neighbourhood. `drift-local` added an AR(1) path per neighbourhood on 2026-11-10 and gained
952 elpd over `drift-building`, but both missed the gate with the building path's old sampler,
and `drift-local` was not refit after that sampler was fixed.

## S10: the Second Avenue Subway

`s10_secondave.py`. The line's stations at 72nd, 86th and 96th Streets opened on 2017-01-01.
For each building in the Upper East Side, Carnegie Hill, Upper Carnegie Hill, Yorkville, Lenox
Hill and East Harlem (227,503 ads) I took the straight-line distance to the nearest subway
stop with and without the new stops and called the difference the gain. Its median is 0.08
km, its 90th percentile 0.35 km and its 99th 0.43 km.

Part A reads raw asks only. For consecutive ads of a unit with both latest-ask days in 2014
to 2019 (39,929 pairs in 3,223 buildings, 14,883 of them spanning the opening), I took the
change in log ask less the mean change of the area's pairs with the same two quarters. Then I
regressed it on the gain, the gain times a flag for spanning pairs, and the flag. A placebo
repeats this on pairs of 2013 to 2016 with a pretend opening on 2015-01-01 (11,883 pairs).

| gain | spanning less other pairs, 2017 | placebo, 2015 |
|---|---|---|
| under 0.05 km | -0.28 ± 0.20% | -0.17 ± 0.27% |
| 0.05 to 0.2 km | -0.02 ± 0.22% | +0.09 ± 0.29% |
| 0.2 to 0.4 km | +0.33 ± 0.15% | +0.02 ± 0.22% |
| 0.4 km and over | +0.42 ± 0.51% (796 pairs) | +1.37 ± 1.02% (242) |
| per km of gain | +1.86 ± 0.75% | +1.56 ± 1.14% |

Part B reads L1's held-out gap in the area on the gain: -1.2 ± 1.2% per km for ads of 2017 to
2019 and +0.5 ± 0.4% per km from 2020.

Scoring the predictions: a rise of 2% to 5% at a gain of 0.4 km or more missed. Against units
with no gain it is +0.7%, within noise of zero and of the placebo. A placebo within 1% held
on the slope and missed in the top bin, where it is +1.37 ± 1.02%. L1's slope under 2% per km
held.

Verdict: no fit. The clearest contrast is the 0.2 to 0.4 km bin, which rose 0.6% against
units with no gain while its placebo stayed flat, so a station about 0.3 km closer was worth
about half a percent of rent on the Upper East Side, where the Lexington Avenue line already
ran within a short walk. L1's building levels absorb it. As a measure of what transit is
worth, it is small and leaves a wide margin.

## S9: school zones

Not run. Ben tabled school data on 2026-10-15, and its plan, DOE zone maps with School Quality
Reports, has not resumed.
