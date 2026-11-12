# Outlier sprint (2026-11-11 to 2026-11-12)

Ben asked for a day of chasing the ads the model prices worst, on the view that an ad far from
its prediction usually has a cause the model does not observe. I worked from the served fit,
`drift-building-b0-latest-67d14e17-b9`, and its diagnostics table
(`/data1/apartments/site/diagnostics/ads.parquet`, 195,423 ads). There `gap` is the log ask
minus the log predictive median.

## Where the squared gaps go

The squared gaps are concentrated. The top 1% of ads by |gap| carry 25% of the sum of squared
gaps, and the top 5% carry 49%. A few groups stand out from screening the table by unit,
building and history:

- Units over 1,500 sq ft have no mean bias, but their 80% intervals cover only 62% to 70% of
  asks, against a predictive sd of 0.13 to 0.19. Among units large for their bedroom count
  (size more than 40% over the bedroom median), coverage falls from 0.69 to 0.60.
- The top decile of predicted rent has an sd of 0.111 against 0.078 overall, and its 80%
  coverage is 0.76.
- Where the unit's previous ask sits more than 0.3 above the model's median, the gap
  averages +0.05 to +0.19 and 80% coverage is 0.58 (previous ask under a year old) and 0.46
  (one to three years). These ads are 1.3% of the total and carry 8.7% of the squared gaps.
  The gap rises with that deviation, with slopes of 0.17 and 0.10. This first screen mixed
  market movement and a defect of the diagnostics' previous ask with the units' own levels.
  "Previous asks far over the model" below separates them and replaces these figures.
- 114 ads ask within 5% of the unit's previous ask yet sit more than 0.4 from the median.
  At 53 E 75th St, units 1A and 2A both ask $35,000 against a median of $8,900. Here the
  unit's own history agrees with the ask, so the model is missing something about the unit.

## Reading the extremes

I read the 150 ads furthest over the median and the 150 furthest under, with a Sonnet reader
per batch of 25. Each reader had the ad's text, its photos and floor plan where stored, the
unit's other ads and the building's other units. They classed each ad as a data error, a
quality the model does not observe, or a pricing choice by the lister. These 300 ads carry
8.0% of all squared gaps.

| cause | ads | share of the 300 ads' squared gaps | over the median | under |
|---|---:|---:|---:|---:|
| data error | 102 | 42.4% | 29.1% | 13.3% |
| unobserved quality | 72 | 29.6% | 19.2% | 10.3% |
| pricing | 105 | 20.8% | 9.0% | 11.7% |
| unclear | 21 | 7.3% | 2.8% | 4.5% |

Broken down by the readers' codes, with codes carrying at least 1.5% of the squared gaps:

| cause | code | ads | share |
|---|---|---:|---:|
| data error | wrong bedrooms | 32 | 12.9% |
| data error | price typo or placeholder | 16 | 9.0% |
| pricing | aggressive ask | 25 | 7.6% |
| unclear | | 21 | 7.3% |
| unobserved quality | income-restricted | 13 | 6.7% |
| data error | ad for a different unit | 16 | 5.7% |
| pricing | other | 30 | 5.2% |
| pricing | deep cut | 34 | 5.1% |
| data error | commercial space | 8 | 4.2% |
| unobserved quality | layout or size | 11 | 3.7% |
| unobserved quality | duplex or triplex | 5 | 3.7% |
| unobserved quality | penthouse or top floor | 9 | 3.4% |
| data error | stale or test listing | 5 | 2.9% |
| data error | wrong building | 7 | 2.7% |
| data error | room or share | 5 | 2.5% |
| unobserved quality | other | 6 | 2.4% |
| unobserved quality | outdoor space | 6 | 2.3% |
| unobserved quality | renovation | 6 | 1.8% |
| pricing | concession | 11 | 1.7% |
| unobserved quality | view | 2 | 1.5% |

Cases from each cause, picked by the size of the gap:

| listing | gap | cause | what the reader found |
|---|---:|---|---|
| 3685434 | -1.95 | price typo | The ask of $971 is the unit's size. Its other ads state 970 to 971 sq ft, and the record's living area holds the $6,700 rent. |
| 2944442 | +1.19 | stale or test | A repeated placeholder text at $12,000 for a garden 1BR whose history runs $3,500 to $3,800. |
| 4809642 | +1.04 | wrong size | Coded as a studio with no size. The floor plan shows a full-floor loft, and a 2023 ad for the unit gives 2,700 sq ft. |
| 4314997 | -1.03 | different unit | A 2BR of 800 sq ft sharing a unit record with the building's 3,400 sq ft duplex. |
| 3765161 | -1.68 | income-restricted | A lottery unit at River Watch at $846, where market neighbors ask about $5,000. |
| 1680346 | +1.36 | triplex | An elevator townhouse triplex with three fireplaces, at the same $35,000 its earlier ad asked. |
| 1772811 | +1.12 | view | A Trump Tower unit with Central Park views, asking $28,000 to $40,000 across its ads. |
| 2979408 | +0.95 | aggressive ask | $25,000 for 6 days, for a unit that rented at $9,250 in 2017 and asked $13,500 in 2021. |
| 1344014 | -0.85 | market shift | A studio asking what it asked from 2010 to 2014, judged against the building's later asks. |

## Residuals by text flag

I scanned each ad's description for 31 flags (the model's `DESCRIPTION_FLAGS` and patterns
added for the sprint, `/data1/apartments/tmp/outlier-sprint/qual/flags.parquet`) and
compared the served fit's held-out gaps with and without each flag inside buildings, with
standard errors clustered by building. Tables for every flag are in
`/data1/apartments/tmp/outlier-sprint/s2/C/results.md`. 191,547 of the 195,423 ads have a
description on file, and 99.5% of those belong to a unit with an earlier training ad.

Every flag effect is small. Those past |t| 3.2 lie between -0.010 and +0.013, against a gap
sd of 0.083, so none of them accounts for a visible share of the squared gaps. They are worth
reading for the processes they point at. Since the model learns a unit's lasting level from
its earlier ads, a quality present in all of a unit's ads should leave no gap. I found gaps
left by three processes:

1. the quality changed between the unit's ads;
2. the unit level is shrunk toward the building, which leaves part of a premium in the gap
   when the model has no column for the quality or the column is not filled;
3. a group of ads follows a price path of its own.

To tell the first from the second I ran a switch test on the 190,129 ads with a previous ad
for the same unit (`s2/C/switch.py`). "On" is the mean gap of ads with the word whose
previous ad lacked it, less that of ads lacking it both times. "Off" is the mean gap of ads
lacking the word whose previous ad had it, less that of ads with it both times.

| flag | within building | on (t) | off (t) |
|---|---:|---:|---:|
| gut renovation | +0.0067 | +0.0116 (11.2) | -0.0012 |
| renovated | +0.0066 | +0.0093 (11.1) | -0.0020 |
| washer and dryer in unit | +0.0055 | +0.0103 (9.1) | -0.0015 |
| dishwasher | +0.0032 | +0.0065 (7.4) | +0.0011 |
| furnished | +0.0071 | +0.0090 (4.9) | 0.0000 |
| private outdoor space | +0.0090 | +0.0084 (6.8) | -0.0053 (-3.5) |
| penthouse | +0.0082 | +0.0082 (4.6) | |
| full floor | +0.0124 | +0.0077 (2.9) | |
| walk-up | -0.0043 | -0.0051 (-3.8) | +0.0076 (4.2) |
| concession | -0.0061 | -0.0078 (-5.3) | +0.0040 (2.4) |
| rent stabilized | -0.0093 | -0.0129 (-6.0) | -0.0021 |
| luxury | +0.0015 | +0.0050 (4.6) | |
| gym | -0.0001 | +0.0039 (3.7) | |
| doorman | -0.0006 | +0.0029 (2.9) | |

Duplex, loft, townhouse, fireplace, garden level, private entrance and no fee show no switch
effect.

**The lister.** Luxury, gym and doorman are traits of the building, and a building does not
gain a doorman between two ads. Their "on" effects of +0.003 to +0.005 measure the ad: a
lister who writes more about the unit is also asking more for it. The gap rises steadily
from the second to the ninth decile of description length. I take about +0.004 as the
baseline to subtract from any "on" effect below.

**Work done between tenancies.** Renovated, gut, washer and dryer, and dishwasher switch on
with +0.007 to +0.012 and switch off with about zero. An owner who renovates between
tenancies raises the ask, while the model still holds the unit at the level of its old ads.
A later ad dropping the word leaves the work in place, which is the zero on the "off" side.
Net of the lister baseline the step is about +0.005 to +0.007. The raw material can date it:
the first ad of the unit with the words, a change in the photos, and DOB alteration filings
by BIN.

**Rent stabilization.** The model has a column from this same pattern, and stabilized ads
still sit 0.009 under their buildings' other ads. By year the difference in mean gap between
stabilized ads and others is -0.011 (2019), +0.010 (2020), +0.004 (2021), -0.023 (2022),
-0.011, -0.010, -0.013 and -0.017 (2023 to 2026). A stabilized unit's rent moves by the Rent
Guidelines Board's yearly increase, so it stayed up while the market fell in 2020 and 2021
and it has trailed the market since 2022. A coefficient fixed over time prices the average
of those years and misses each of them. A candidate term lets stabilized units follow a
share of their area's path. The DHCR building lists give a source for the flag apart from
ad text.

**Concessions stated in the text.** 5,502 held-out ads mention a concession while their
record holds no free months, with a mean gap of -0.0107. I parsed the prices and terms
their texts state (`s2/C/conc.py`, `conc3.py`):

| the text | ads | mean gap | median step from the unit's previous ask |
|---|---:|---:|---:|
| states a net price equal to the ask | 197 | -0.037 | -0.070 |
| states a gross price equal to the ask | 118 | +0.020 | +0.013 |
| states a price matching neither (median 1.091 times the ask) | 1,711 | -0.022 | -0.046 |
| says the advertised price is net | 1,009 | -0.009 | -0.021 |
| states free months and no price | 1,233 | -0.003 | 0.000 |
| other wording | 1,234 | -0.003 | +0.029 |
| ads with recorded free months, for comparison | 18,921 | -0.004 | -0.041 |
| ads with no concession | | -0.004 | +0.030 |

In most of these ads the lister typed the net rent as the price, so the ask is already on the
basis the pipeline gives every ad with recorded terms. Netting them again would be wrong:
it would move the 1,233 ads with free months and no price from a gap of -0.003 to -0.106.
The negative gap of the net-priced ones is the concession itself. For an ad with recorded
terms the model's free-months column absorbs it, and for these ads that column is zero.
The repair is an added column holding the free months parsed from the text, with the ask
left alone. Only the 118 ads whose ask equals the gross price their text states carry a
gross ask, and ad text alone is no ground for changing a price, so they stay.
This corrects a lead from the closing-ask second look, where I had proposed netting these
ads.

**Coded fields left empty by the lister.** The text flag carries its effect where the coded
field is false: private outdoor space +0.0154 where the field is false and +0.0029 where it
is true, penthouse +0.0058 and -0.0024, dishwasher +0.0064 and -0.0011. Listers describe
a terrace in words and leave the box unchecked. The premium is a lasting one, and the gap is
the part the unit level's shrinkage leaves. An added text column for each would carry it.
Furnished is the extreme case: the record's furnished rent is set on none of the held-out
ads' records and the model's furnished column has no training row set, while 8,064 held-out
ads say furnished in their text (+0.0071 within building, +0.0090 on switching on). The
"off" effect of private outdoor space (-0.0053) may come from unit records shared by two
apartments.

**Full floor and walk-up.** Full floor has no column and shows +0.0124 within building. It
can also be measured from the count of units per floor in a building's unit labels. Walk-up
in the text shows -0.0043 within buildings and -0.0084 where no elevator is coded; the text
gives the flight count where the record's floor is missing.

**One-off layouts.** Duplex, private entrance, loft, penthouse, townhouse and full floor
shift the spread of the gap more than its level. Their 80% intervals cover 0.767, 0.779 and
0.797 of asks for units with 1, 2 and 3 or more training ads, against 0.800, 0.814 and 0.831
for other units. Inside size bins the flag adds little: coverage is 0.707 with and without
it at 1,500 to 2,500 sq ft, and 0.632 against 0.611 above 2,500. The flagged share rises with
size, from 13% under 700 sq ft to 70% over 2,500. Price paths inside an ad, days on market
and the spread of the step from the previous ask are the same for flagged and other units,
so I found no sign of listers searching for the price of an unusual unit. The low coverage
of these flags is the low coverage of large units.

Not established: ads lacking short-term wording whose previous ad had it show +0.0144 (t
2.9, 1,041 ads), and I have no account of it.

## Large units

Tables and the readers' output are in `/data1/apartments/tmp/outlier-sprint/s2/D/results.md`.
"Large" here is a model size over 1,500 sq ft, or a size more than 40% over the bedroom
median (500, 715, 1,022, 1,350 and 1,800 sq ft for 0 to 4 or more bedrooms). The group has
9,858 held-out ads, 5.0% of the ads and 13.4% of the squared gaps. Their 50%, 80% and 95%
intervals cover 0.415, 0.688 and 0.890 of asks, against 0.525, 0.807 and 0.951 for all ads.
I went through four candidate processes.

**Record errors.** Sonnet readers went through 120 of these ads, sampled by position in the
interval and weighted back to the group. They found a record error in 22.7% (90% bootstrap
range 15.6% to 30.1%): a size coded too large in 15.0%, wrong bedrooms in 6.1%, a wrong price
or a wrong unit in 3.0%. No read ad had a size coded too small. The sizes that are too large
come from three places:

- the pipeline filled the size from another ad of the unit with another bedroom count, or
  from the unit's line when no ad of the unit states a size (weighted error share 0.41 for
  line fills on 6 ads read, 0.33 for unit fills on 20, 0.11 for stated sizes on 94);
- the lister's figure counts a terrace, a roof deck or a lower level;
- two apartments share a unit record.

Removing the ads with a record error moves the 80% coverage from 0.688 to 0.713, so record
errors account for about a fifth of the shortfall against 0.807.

**A level the model gives up too easily.** This is the process the checks support. Inside
size bins I regressed the gap on the deviation `d` of the unit's previous ask from the
model's median. The slope is the share of that deviation the model failed to carry:

| size (sq ft) | slope of gap on d | slope, previous ask under 1.5 years old |
|---|---:|---:|
| under 500 | 0.02 | 0.06 |
| 1,000 to 1,500 | 0.10 | 0.22 |
| 1,500 to 2,000 | 0.19 | 0.35 |
| 2,000 to 3,000 | 0.34 | 0.57 |
| over 3,000 | 0.54 | 0.72 |

Over 3,000 sq ft, carrying the previous ask forward has a smaller median absolute error than
the model (0.102 against 0.130), while under 1,000 sq ft the model is far ahead (0.048
against 0.073). Large units whose previous ask is within 0.05 of the model cover 0.780 at
80%, and those with |d| over 0.3 cover 0.521. The share of the deviation left in the gap
rises with size inside a single band of `d` as well (0.09, 0.25 and 0.41 across three size
groups at `d` of 0.2 to 0.3). Among units whose stated sizes agree across their ads it runs
from 0.12 to 0.69 across the size groups, so the pattern holds where the sizes are sound.

The causal account: large apartments differ from one another in ways the record does not
hold (a second level, a terrace, a full floor, a finish), and those differences are worth
more in rent than the differences among one-bedrooms. The model draws every unit's lasting
level from a normal distribution with a single scale (`unit_sd` and `drift_sd` together give
about 0.074). For a unit with one or two earlier ads sitting 0.3 from its building, the
posterior prices most of that distance as noise, since a level of four standard deviations
is less likely under the normal prior than a noisy ask under the Student-t noise. Among the
54 read ads outside the 80% interval with no record error, 39 of the 53 with a previous ask
missed on the side of the previous ask.

**Building or area.** The building share of the gap variance among large units is 0.144.
The mean gap of large units by neighbourhood shows a pattern: large units are over-predicted
in low-rent areas (East Harlem -0.067, Bushwick -0.045) and under-predicted around the park
(Central Park South +0.071, Lincoln Square +0.056). This accounts for about 3% of the large
units' gap variance. A separate time path for large units accounts for about 1%.

**Price.** Inside every band of predicted rent, large units cover 0.67 to 0.69 at 80% and
the other units 0.81 to 0.82, up to the 95th percentile. In a regression of the log absolute
standardized gap, log size has a coefficient of +0.183 (se 0.009) and log predicted rent
-0.039 (0.008). The low coverage of the top price decile reported above is the low coverage
of its large units.

## Previous asks far over the model

193,257 held-out ads have a previous ask, and 1.35% of them have one more than 0.3 above the
model's median. About two thirds of that group is market movement: 1,283 of the 1,958 with a
previous training ad of the same unit are dated 2020 or 2021 and follow an ask from before
the pandemic dip. I moved each previous ask to the held-out quarter with a repeat-ad index.
After that, 1,291 of the 1,958 fall to 0.3 or under, with a mean gap of about +0.02. The
adjusted group over 0.3 holds 0.64% of ads and 8.0% of squared gaps.

Readers went through 80 of its ads. In 40% of the adjusted group, the previous ask belongs
to another configuration of the apartment: the diagnostics table takes `prev_ask` from the
market build's history, and that history crosses the pieces the model treats as separate
units. This is a defect of the diagnostics and has no effect on the fit. The summary
earlier in this note (1.3% of ads, 8.7% of squared gaps, slopes of 0.17 and 0.10) mixed it
with the market movement, and the figures here replace it.

Among the ads whose previous ad is a training ad of the same unit (1,183 ads, mean gap
+0.187, cov80 0.369), the read gives unit quality 44%, market timing 25%, the model low for
the building or line 10.5%, a closing-day raise on the previous ad 6.5%, and other causes
under 5% each. The slope of the gap on the adjusted deviation is +0.14 between -0.1 and
+0.1, +0.26 from 0.1 to 0.3 and +0.69 beyond 0.3. The 280 units whose earlier asks all sit
over 0.2 have a mean gap of +0.144.

The share of the deviation the next ad keeps depends on the unit. Small units with a coded
size keep 11% to 18% of a deviation beyond 0.3: for them a high previous ask was mostly a
price the lister did not repeat. Units with no coded size keep 42% to 62%, rising with
bedrooms and with predicted rent (from 0.29 to 0.72). Low previous asks are mostly not
repeated: beyond -0.3, 67% to 73% of ads return to the model.

These checks describe where the model's uncertainty falls short. They do not say why a
given large unit asks more than its building. The next section takes that up.

## Observed attributes of large units

The coordinating session asked for this check before a unit scale growing with size became
the lead candidate: if the attributes the ads record explain a large unit's lasting
deviation, they belong in the model ahead of a wider prior. The work is in
`/data1/apartments/tmp/outlier-sprint/s2/D5/` (`results.md`, `tables.md`, `numbers.json`,
scripts). It reads held-out output only.

The sample S is the 5,999 held-out ads over 1,500 sq ft whose unit has a previous ask with
the same bedroom count (3,075 buildings). For each ad I took the gap of its ask from the
model's median and the gap `da` of the unit's previous ask, moved to the held-out quarter,
from the same median. The covariance of the two is the variance of the part of the
deviation present in both asks. It is 0.00965 in S (building bootstrap 0.00842 to 0.01101),
a persistent sd of 0.098 in log rent. In the 61,818 ads of 500 to 1,000 sq ft it is
0.00070, an sd of 0.026.

I predicted the mean of the two gaps from 97 attribute columns in eight families (text
flags, building, floor, the ad, size against the building's other units, outdoor space and
views, area by size, baths), fitting on nine tenths of the buildings and predicting the
tenth. The explained persistent share is the covariance of the prediction with each gap,
averaged, over the covariance above.

| predictor | explained persistent share | permutation null, 95th pct | persistent sd left |
|---|---:|---:|---:|
| ridge | 9.0% (bootstrap 7.9% to 10.3%) | 0.6% | 0.094 |
| boosted trees | 15.9% (13.7% net of prediction noise) | 1.7% | 0.091 |

The null moves whole blocks of attribute rows between buildings with equal ad counts. Both
predictors beat it by a wide margin. The share is 7.8% and 14.3% among the 4,357 ads whose
sizes agree across the unit's ads or are stated, so wrong sizes do not produce it, and 7.3%
and 12.8% over 1,000 sq ft.

Alone, text flags explain 4.3%, building attributes 4.2%, floor 2.1%, ad attributes 1.9%,
relative size 1.6%, outdoor space and views 1.1%, area by size 0.7%. Each passes its null.
Baths alone explain nothing, and leaving them out of the full set costs 2.2 points, mostly
through baths per 1,000 sq ft. The coefficients with the largest t values on the mean gap
are a dishwasher (-0.020, t -4.3, flagged on 4,786 of the ads), the floor as a share of the
building's height (+0.055, t +3.7), loft in the text (-0.016), walk-up in the text (-0.033
on 107 ads) and townhouse in the text (+0.015). Distance to a station and to a park add
nothing.

The slope of the gap on `da` goes from 0.488 (se 0.020) to 0.473 after I subtract the ridge
prediction from both, and to 0.455 after the trees. So the recorded attributes explain a
real share, and a small one: they take the persistent sd from 0.098 to 0.091 at best, and
the reference group's 0.026 stays far away. A unit scale growing with size (U1 under "Fits
for after the sprint") remains the candidate for most of the pattern, with no check of
its own behind it yet. The attributes
enter as level terms for all units, which the text-flag section already lists, and I do not
put them ahead of U1.

A check added after the first results: pairs of different large units in one building share
25% of the covariance (1,000 buildings, 3,924 ads, bootstrap 15% to 37%; 22% in the
checked-size sample). The building attributes reach 4.2%, so a building-level term for
large units has room the attributes do not use. It is the candidate after U1.

Weak points. The OLS, ridge and trees are hand-written numpy, since `sklearn` does not
import in the venv; `test_lib.py` checks them against direct solutions. The trees' null has
60 draws on one fold seed. The attributes are the ones the ads and the city's records
hold. A second level, a full floor or a renovation shows in the floor plan and the photos,
which no check here read, so the result bounds the recorded attributes and leaves the
unrecorded ones open.

## Unit records holding two apartments

The first reads met 16 ads sitting on another apartment's unit record. I screened every fit
unit with two or more ads for signs of a second apartment, from the raw record values: two
clusters of stated sizes, bedroom or bath counts apart, differing floors, differing unit
labels on the records, two StreetEasy property ids on a page
(`/data1/apartments/tmp/outlier-sprint/s2/E/results.md`). The screen flags 57,517 of 397,980
units. Sonnet readers went through 141 of them by stratum, and I checked each two-apartment
verdict against the records and, for four, the floor plans.

| group | units | read | two apartments | with backing beyond text and counts |
|---|---:|---:|---:|---:|
| pages joined by the history layer | 317 | 19 | 14 | 13 |
| record labels differ | 291 | 22 | 14 | 13 |
| size and a bedroom apart | 394 | 12 | 6 | 4 |
| two sizes, each stated in two or more ads | 94 | 7 | 1 | 1 |
| two sizes, the second stated once | 3,150 | 14 | 0 | 0 |
| bedroom counts two or more apart | 73 | 8 | 0 | 0 |
| weak signals alone (rooms, baths, property id, house number) | 52,026 | 42 | 2 | 0 |

The rows overlap: every label case found sits among the history-layer units.

The readers' finds come from two processes.

1. **The history layer joins pages StreetEasy itself confused.** `analysis.label_units` joins
   two unit pages when an ad on one carries a page history listing an ad placed on the
   other. StreetEasy keeps that history by property id, and a broker can move a property
   record from one apartment to the next. Level Group's ad for Riverbank 9H came off on
   2014-06-03, the day its ad for 20H went up under the same property id. The same happened
   at 452 Amsterdam Ave (4S to 2N, 2014-08-04) and 82 Marcy Ave (3A to 3B, 2015-04-14), and
   the plans of both pairs show different apartments. In other cases a single ad went out
   under the neighbor's property id. 14 of the 19 history-layer units read hold two
   apartments, which scales to about 234 of the 317 (175 to 276).
2. **A lister reuses a page.** A broker advertising several apartments of a building files
   an ad under whichever unit page is at hand: a 485 sq ft studio on the page of The Aspen's
   682 sq ft unit 525, the full-floor apartment 10 of 249 E 50th St typed as 1D. A size
   difference together with a bedroom difference finds these in half the units read. A size
   difference alone does not (0 of 14): it marks a typo, outdoor space added to the size,
   or a building-wide figure.

Scaled by stratum, the main signals hold about 475 shared records, about 290 with
independent evidence. The weak signals cannot be bounded with 7 reads a stratum, and the
280,638 unflagged units were not sampled. Sizes are stated on 28% of ads, so the screen
misses shared records whose ads state none. Of the eight shared units the large-unit reads
found by other routes, the main signals had flagged three and the weak ones two more.

The cost to the fit is small. The high-precision groups hold 343 of the 188,649 held-out
ads in the diagnostics file (0.18%) and 0.30% of the summed squared gap. The fit already cuts a page into pieces
at a change of bedroom count (`analysis.history_splits`), so two apartments share a unit
level only when their counts agree.

I wrote 24 `split_unit` entries covering 69 ads: 15 undo history-layer joins, 5 take a
reused page's stray ad out, and 4 come from the large-unit reads. Each rests on plans,
stated sizes, matching line units, or the two pages' ads running at once. Seven units the
readers called shared got no entry because the reads rest on a single size, coded counts or
text.

A split of a whole page repairs that unit until the next ad arrives on the page and the
history layer joins it again. The lasting repair is a rule in the history layer requiring
the two pages' labels to agree up to spelling, which is in `docs/TODO.md` for Modeling.

## The corrections, a second look

The first run of the sprint put 46 corrections in the ledger (#1307). Pass 2 read 600 more
ads from further down the list of gaps and added 59 (#1315): 27 bedroom sets, 12 bath sets,
5 size sets, 5 ask sets and 10 excludes. A second session then went back over both files
and over the ads around them.

### An apartment changes over the years

Most of the sprint's bedroom sets rest on another ad of the same unit coding the count the
text describes. That backing assumes the unit page held the same apartment on both dates.
Reading whole unit histories showed three ways it fails:

- a renovation between the ads (1218 Halsey St 1 was a 1 bedroom pass-through until 2023
  and a 2 bedroom duplex with a basement after),
- a wall put up or taken down, so a 2 bedroom of 2020 is a 4 bedroom in 2025,
- two apartments advertised under a single page.

So another ad of the unit backs a correction when it runs close in time to the corrected
ad, or when the two ads show the same configuration (the same text, the same baths and
room count, a plan). An ad years away with different baths or a renovation in between
backs nothing. I tabulated all 119 `set` entries of the sprint against the months to their
nearest backing ad (`/data1/apartments/tmp/outlier-sprint/s2/F3/timegaps.parquet`): 45 had
no backing ad within 24 months and no plan, stated size or line evidence.

Six merged entries were in doubt before that table existed, and I went through each unit's
timeline (`s2/D4/results.md`):

| entry | verdict | basis |
|---|---|---|
| 3120127, bedrooms 0 to 4 | retracted | The backing ads date from 34 and 60 months later, code another bath count, and the later says "Brand New renovated". The twin unit A codes 2 bedrooms in 2020 and 2021 and 4 in 2025 and 2026. |
| 3690051, bedrooms 0 to 2 | retracted | The page belongs to The Rheingold (below), and its other ads code 0, 2, 1 and 2 bedrooms at $1,992 to $4,650. |
| 1968147 | holds | Its own 2017 plan shows three bedrooms, and every ad codes 948 sq ft. |
| 3235069 | holds | A 2019 ad has the same text and codes 2 bedrooms and 2 baths. |
| 3729047 | holds, with moderate confidence | Two other listers code 5 bedrooms in 2014 and 2025 with the same baths. The corrected ad's lister codes 0 on every ad of its feed. |
| 3592144 | holds, and gains a bath set | Ads 9 days before and 25 days after at the same ask code 3 bedrooms and 1.5 baths. The record's 4 baths were copied from the building's 4 bedroom lines. |

Both ads come out of the data with the reason `bedrooms_unknown`. 3690051 sits on a page
of The Rheingold, and its text offers a "2 bed/2 bath" and a showing of any unit in the
building, so the coded 0 is not a count and the page does not say which apartment the ad
offered. For 3120127, every ad of the unit and of its twin with a count codes 2 or more,
and no ad near 2020 says which count it was.

To see how fast pages change, I took every pair of consecutive kept ads on a page with
both counts at least 1, and the share of pairs whose counts differ:

| months between the ads | pairs | counts differ | when the earlier ad codes 3 or more |
|---|---|---|---|
| under 12 | 228,655 | 13.2% | 19.2% |
| 12 to 24 | 258,937 | 8.9% | 15.1% |
| 24 to 36 | 156,217 | 9.2% | 16.4% |
| 36 to 48 | 83,980 | 10.7% | 19.3% |
| 48 to 72 | 76,374 | 12.6% | 23.4% |
| over 72 | 35,263 | 17.3% | 31.0% |

Between 9% and 13% of pairs differ at every distance under four years, and the share
reaches 17% past six years (31% for the larger apartments). So time adds about 8 points
over six years, and most of the disagreement is there from the first year: listers who
count the same rooms differently, and pages holding two apartments. The first year
stands above the two after it because of its pairs 3 to 9 months apart ("The lease
cycle" below). A line at 24 months is a cautious one. The larger
risk for a backing ad at any distance is that floor of 9% to 13%, which a read of the
unit's whole history is there to catch.

#### The timeline audit

A second pass (`/data1/apartments/tmp/outlier-sprint/s2/T/results.md`) took the other 44
rows of those 45. Sonnet readers extracted the layout statements of every ad on each unit's
page, 178 ads, and each entry was judged on the dates and the texts.

| verdict | rows | basis |
|---|---|---|
| holds | 28 | 12 where the corrected ad has the same text, room count and baths as the backing ad, 10 where the corrected ad's own text agrees with the backing, 3 where two other listers code the count before and after, and the 3 ask sets |
| fails | 14 | 219 E 23rd St #19 (5 rows), 15 W 103rd St 1D (3), 307 Troy Ave #3 (2), 1627 Pacific St 4A (2), 226 7th Ave 2L (2) |
| unclear | 2 | 438 W 52nd St GF |

- At 219 E 23rd St #19 no ad from 2014 to 2019 gives a count. The first with a count
  (2020-12) codes 3, and the ads saying 2 begin in 2023 with "renovated" added.
- At 15 W 103rd St 1D the manager's own 2021 ad codes 3 for the same "6RM/1.5 bath", and
  the ads saying 4 follow a gut renovation reported in 2022-12.
- At 438 W 52nd St GF the backing ads are 62 to 110 months younger, call the apartment a
  duplex for the first time and no longer mention its garden.
- The other three units carry ads posted with a blank form (below), and each unit's last
  ad with a count is 28 to 79 months older.

Six of the 16 rows were merged entries, and the other 10 sat in the sibling file before
its PR. I retracted the six and removed the ten. For 13 of the ads the count stays
unbacked: the text or the unit's other ads show the coded 0 is not a count (a "5 room
duplex", a "6 room apartment", a blank form on a unit whose every counted ad says 3 or
4), and no ad near in time says which count is right. Those 13 come out as
`bedrooms_unknown`, the reason the October reviews gave such rows. Both ads of 226 7th Ave
2L keep their counts on line evidence, which the first entries had not used: unit 3L one
floor up codes 2 bedrooms and 2 baths within 13 months on either side, as do all 27 of the
building's ads with a count. The same ads back bath sets of 2 for both. I had rebuilt the
ad of 307 Troy Ave #3 from 2024-01 the same way, on Real Street's ads of two other pages
15 and 16 months earlier, and the review of the ledger PR excluded it: the building has 3
counted ads within two years of it, coding 3, 3 and 1 bedrooms.

The audit rests on an assumption about Centennial Properties' feed. Its ads say "newly
renovated" in 5 of 75 cases in 2019 and 42 of 104 in 2020, and "beautifully renovated ...
with modern updates" in 43 of 69 in 2021. The audit read those as template wording. If
they report real work, the entries for 346 E 18th St A, 410 E 13th St 1F and 6C and 147
Avenue A 1R move from holding to unclear. Two smaller flaws stand in merged entries whose
values hold: the entries for 5184341 (97 Chambers St #4) cite no line of the ad's own text,
which is what backs them, and one cited ad (2516123) describes "79 Reade st ... Unit 3A".

### The Rheingold

10 Monteith St (The Rheingold) came up through 3690051. Its brokers post ads offering "any
unit in the building" under whichever unit page they pick. 431 of the building's 592 pages
with two or more kept ads hold two or more bedroom counts (61 of the 76 on the fifth
floor), and 3,771 ads sit on such pages. Across all buildings 20% of such pages hold two
or more counts (84,483 of 424,168), and in loft buildings listers code the same space as
0, 1 or 2 bedrooms, so the share alone would not settle it. Here the ads' own text and
asks from $1,992 to $4,650 on a single page do. A page of this building does not identify
an apartment. The fit cuts each page at a change of bedroom count, so a unit level there
mixes apartments of a single count, and a previous ask may belong to another apartment
of that count.

### Sibling ads

A correction fixes one ad, and the unit's other ads often carry the same wrong value. For
the 80 `set` entries of the two merged files (asks left out), I listed each unit's other
ads coding the value the entry corrected away from: 58 rows on 42 units. Sonnet readers
read each with the unit's whole history, and I checked every accept against the evidence
rule and the timeline.

Of the 58 rows, 39 became a set (33 bedroom sets and 6 size sets), I rejected 18 and
the last was in the ledger already. The rejections were ads whose text or dates did not
match the corrected ad's (another configuration, a renovation between, a page shared
with another apartment). The timeline audit above then failed 10 of the 39 bedroom
sets, ads posted with a blank form among them (below). The sibling file as merged, after
the audit and the review of the ledger PR, holds 31 entries: 23 bedroom sets, 6 size
sets and 2 bath sets.

One of them shows a limit of the coded count. The 2021 ad of the ground floor duplex 1F
at 330 E 6th St is Centennial's, with the count left empty, and Centennial's ad of the twin
1R six months later codes 4 bedrooms for the same 6 rooms. REAL New York has advertised
both duplexes since 2022. It coded 4 on 1R at $9,500 in September 2022, then 3 at $7,495
on the labels 1F, 1E and 1R over the winter ("TRUE 3BR" with "3 bedrooms with windows and
closets"), then 4 again from April 2023 and 5 in May 2025. The rooms did not change over
those months. The lister chose which of them to call bedrooms, and the count went down
together with the ask. The set takes 4, the count Centennial typed for the twin that year,
and the model's bedroom column carries the lister's choice along with the apartment. I
had first written that two listers counted the rooms differently, and the reviewer of the
ledger PR found every one of those ads to be REAL New York's.

### Ads posted with a blank form

Six rows of the audit belong to a class the reads had treated ad by ad. Real Street Inc
and M1 Ventures post many ads with the form's fields empty, and a blank form reaches the
data as 0 bedrooms, 1 bath and 1 room. Real Street's blank ads carry a text of one to
three characters ("h", "j", "."). M1 puts a paragraph of legal boilerplate on every ad,
filled in or blank. The ads are offers of apartments: their opening asks continue each
unit's earlier asks.

| lister | kept ads | blank text | of those, coded 0 bedrooms | median ask of those |
|---|---|---|---|---|
| Real Street Inc | 4,764 | 1,763 (3 characters or fewer) | 626 | $3,250, against $2,673 for its 296 studios with a full text |
| M1 Ventures | 144 | 129 (boilerplate or empty) | 70 | $6,925 |

42 of Real Street's 626 are among the held-out ads. Their median gap is +0.28 and they
hold 0.56% of all squared gaps, on 0.02% of the ads. Its 1,137 blank-text ads with a typed
count have a median gap of +0.03.

Real Street posts an apartment again every week or two under a changed unit label. At 471
Chauncey St it advertised a 3 bedroom apartment from August to November 2021 on the pages
"1a", "1l", "1", "1b", "1r", "1h" and "1d", an ad every two weeks at $2,200 to $2,499. At
645 Knickerbocker Ave it advertised the building's 4 bedroom apartment at $5,500 in the
summer of 2023 on the pages "parlor", "1" and "a", then with blank forms at $4,999 on page
"2a", $5,000 on page "2" and $4,500 on pages "1" and "3". The session's first read of the
ad on page 2a (4262695) took it for a draft. It offers another apartment than the page's 1
bedroom, and it comes out as `bedrooms_unknown`. Its kept ads hold 239 runs of an opening
ask repeated on 3 or more labels within weeks, in 127 of its 664 buildings. A page of this
lister therefore says little about which apartment an ad offers, and the other ads of a
page do not back a count.

A batch over both listers' blank forms coded 0 follows from that
(`/data1/apartments/tmp/outlier-sprint/s2/P/results.md`). Of 768 kept ads, 47 had a ledger
entry already. For the other 721:

- 22 take the building's count. The building's counted ads within two years of the ad, at
  least 4 on at least 3 pages, all carry it, as do at least 90% of the building's counted
  ads over its history, and the ad's opening ask is within 15% of theirs. 349 Kent Ave has
  44 counted ads and every one codes 2 bedrooms. Ten of the 22 also take 2 baths where the
  backing ads all carry 2.
- 699 are excluded as `bedrooms_unknown`. In 584 of them the building's counted ads near in
  time carry more than one count.

I tested the building rule by applying it to the 4,043 ads of these listers with a typed
count, each left out of its own backing. It gave the typed count in 216 of 225 cases
(96.0%), and in 71 of 76 from 2023 on. The 15% ask condition came from trying variants on
those same ads, so the figure flatters the rule. On the other listers' ads in the same
buildings, which had no part in that choice, it gave 1,041 of 1,050. Three of the misses
have a text agreeing with the rule against the typed count. The ask enters as a veto
alone: an ad far from the building's asks is excluded, and no ad is set because of its
price. A rule setting a count from the page's own ads scored 112 of 116 on the same test.
I left it out, since the test rewards it for the sameness of a building's apartments, and
13 ads it would have set are excluded.

The reviewer of the ledger PR applied the same reasoning to four blank-form ads decided
earlier from the ads of their own page. The merged sets of 5074720 (697 DeKalb Ave 2R) and
5103577 (645 Knickerbocker Ave 4) are retracted, the sibling candidates 4011783 and 4322414
are dropped, and all four ads are excluded: 697 DeKalb's counted ads within two years of
4011783 code 2 bedrooms on 22 ads and 1 on 21. The merged set of 4125325 (1401 Dean St 1)
stays, since its record carries 3 full baths as the page's 4 bedroom duplex does, so that
form was filled in part and the record matches the apartment.

44 of the excluded ads are held out. Their median gap is +0.25 and they hold 0.44% of all
squared gaps. The batch leaves 125 Real Street ads coded 0 with a text of a word or two
("Desc", "Bushwick", "Studio") untouched. The lasting repair belongs in the pipeline,
which could treat a 0 from these forms as missing, and is listed in `docs/TODO.md`.

The reposting has a second effect apart from the counts: an apartment advertised on seven
labels becomes seven units for the fit, each with one ad. A screen for the practice across
all listers is described under "Reposts under a new label".

### Unit pages with variant labels

StreetEasy gives a unit a second page when a lister types its label another way ("3re" and
"unit3re", "14c" and "014c"). Of 19,481 page pairs in a building with labels equal after
normalizing, the pipeline's label rule already joins 93.7% for the fit. In a sample of 60
pairs, 56 were a single apartment by their coded fields, 3 differed in bedrooms and 1 by a
half bath. I wrote 32 `join_units` entries for pairs I read ad by ad. A wider rule belongs
in `label_key` and is listed in `docs/TODO.md` for Modeling.

### Large units

The reads of large units ("Large units" above) gave 12 entries with independent backing: 5
bedroom sets, 3 bath sets, 2 size sets and 2 excludes. The size sets each rest on a sum
the ad itself gives (1,250 sq ft inside plus a 500 sq ft roof coded as 1,700) or on the
unit's other ads stating the smaller figure. A third size set (3546605, from 1,581 to
1,383 sq ft) came out in review: its backing ads date from 2016 and its plan prints no
total. Four proposals were not written: one ad was
excluded already, one cited evidence left out ads coding the old value, one cited ads on
other pages, and one had no coded size to correct.

### Loose ends from the first session

- 5074720 carried a $4,000 ask typed on its closing day. The narrowed closing dataset
  reprices it at $3,500 and its sibling 4011783 at $2,875, so neither needs a ledger line
  for its ask. Both are blank-form ads and the ledger now excludes them.
- The diagnostics' `prev_day` disagreed with the fit's history for 79 market ads. In 38 the
  previous ad sits under another unit id in the other build, 28 are absent from the market
  build, and 13 were repriced or redated. All 79 come from differences between the market
  build and the fit's build, and the repair is the diagnostics item in `docs/TODO.md`.
- The commercial and room screen led to no pipeline rule: its matches sit near zero gap,
  and the clear cases are excluded in the ledger.

## Reposts under a new label

A lister takes an ad down and posts the apartment again the same day or the next morning.
When the new ad carries the old label, StreetEasy attaches it to the old unit page, where
a renter can read the earlier dates and asks. When the lister types a changed label (3F,
then 3G, then 3H), the site opens a fresh page with an empty history, and the pipeline
gives the repost a unit id of its own. Two brokerage guides, Hauseit's and NestApple's,
describe relisting under an altered unit number as a way to reset an ad's days on the
market. The Real Street pages under "Ads posted with a blank form" are one lister's
version of it.

### The screen

`/data1/apartments/tmp/outlier-sprint/s2/R/v2/build_links.py` pairs ads of one lister in
one building when bedrooms and baths match and the later ad opens on the earlier ad's
last day or the day after, each ad being the only such candidate for the other. I call
such a pair a handoff. 283,751 handoffs connect two different unit pages. The screen
keeps 64,953 of them as candidate reposts, in two cells:

- S1: a lot of 1 to 20 PLUTO apartments, with at least one of the two pages holding a
  single ad over all years and listers.
- S3: a larger lot or no PLUTO count, a single-use page, and labels with equal digits
  (or one label with no digits).

A kept link also has an earlier ad that did not end RENTED and passes the four guards
against lease-ups described in the script: the building is past its first months of
ads, no new-construction certificate falls near the later ad, the coded sizes (where
both ads have one) are within 2% of each other, and the lister has no run of rented ads
of that layout around a change of floor. The kept links form 42,686 chains of 108,261
ads.

### Photos, text and timing only nominate a link

A landlord with several apartments of one line reuses a photo set and a description for
each of them, and lets them one after another. The screen's own readings show it: in
pairs of two established pages on one floor of a small building, readers found two real
apartments under one set of photos and one text. Timing does not separate the two cases
either. The gap between the ads, the minutes between the closing of one ad and the
opening of the next, and the earlier ad's ending status are distributed alike for kept
links and for handoffs between two established labels.

The standard for a join, set by Ben on 2026-11-11, follows from that. Photos, text and
timing nominate a link. A join needs one of the two labels to fail an independent test
of being a real unit: absent from the city's records for the lot, and outside the
building's grid of floors and lines. A turnover above the apartment count, a label never
used again and a shared floor plan file support a join and do not make one. A link
between two real labels stays unlinked.

### The label standard as applied

`G/code/std.py` under `/data1/apartments/tmp/outlier-sprint/s2` applies the standard to
every handoff, and `R/v4/links_standard.parquet` holds its verdicts.

- City records of a lot: the apartment numbers in HPD complaints and violations (pulled
  for all 29,947 lots with a handoff), in marshals' eviction records, and the condo unit
  lots of the assessment roll.
- Grid: a label is parsed into a floor and a line (3F, F3, 12). The grid of a building
  holds every parsed label advertised there in two or more separate spells and every
  label in the lot's records. A label is on the grid when its line appears on another
  floor.
- A label passes when it is in the records, or was advertised in two or more spells, or
  is on the grid.
- A label fails when it passes none of these and the lot's records are adequate: they
  hold at least 75% as many apartment labels as PLUTO counts apartments. Below that
  level a real apartment is often missing from the records, so the label is undecided.
  A label with no grid position, or in a building with fewer than two other floors on
  its grid, is undecided too.
- A link is a join when either label fails, stays apart when both pass, and is
  undecided otherwise.

| verdict | kept links | share |
|---|---:|---:|
| join | 19,787 | 30.5% |
| apart: both labels pass | 16,381 | 25.2% |
| undecided: records too thin | 23,931 | 36.8% |
| undecided: no grid | 4,854 | 7.5% |

The joins are in 5,437 buildings. City records are too thin on 9,153 of the 16,629
buildings with a kept link (55%), holding 31,221 links, and 1,930 of the lots have no
apartment number in any of the three sources. By label change, the joins are mostly a
changed line on the same floor (11,331), followed by labels of another format (3,314),
a changed floor and line (2,976), a number with and without its letter (1,875), a
changed floor on the same line (257) and bare numbers on different floors (34).

To calibrate the two tests I ran them, with the spell rule left out, on labels
advertised in three or more spells, taking those for real units. They fail 0.7% of the
time on lots over 20 apartments and 3.2% on smaller lots, and the rate hardly moves
with the coverage of the lot's records. Single-use labels fail 24.7% and 52.7%.

The standard leaves many reposts unlinked:

- Bare numbers pass the grid easily. At 226 East 59th Street (16 apartments) the labels
  503, 500 and 510 count as on the grid, since other bare numbers are advertised there.
- A lot with thin records blocks even a plain series. At 309 West 84th Street (8
  apartments, 2 labels in the records) the run 2A1, 2A2 and on to 2A24 stays undecided.
- At 16 Monitor Street (24 apartments, 24 labels in the records) 3F to 3G, 3G to 3H and
  3H to 3I are joins, since no record and no other floor has a line G, H or I. At 1084
  Bedford Avenue (28 record labels for 22 apartments) 3A to 3AA and the run 1AA, 1AB,
  1F, 1AC, 1E are joins, while 1A to 1 and 1B to B1 stay apart.

Looser variants, not adopted:

- With adequacy at 50% of the apartment count: 26,104 joins, 16,381 apart and 22,468
  undecided.
- With the grid deciding alone on lots with thin records: 16,413 of the 23,931
  thin-record links have a label with a line on no other floor, which would bring the
  joins to 36,200. On those lots a label with three or more spells is off the grid 5.2%
  of the time in small buildings and 1.4% in big ones.

### Supporting evidence

Several tests are true of every kept link by the way the screen was built, and so say
nothing: the two ads do not overlap, the earlier ad is not marked rented, one label is
single-use (so it never returns), and the coded sizes agree. The tests below were not
used to build the screen.

- The ask carried across. The later ad opens at the earlier ad's last ask in 65.6% of
  joins, 61.2% of links between passing labels and 60.1% of thin-record links. The same
  label reposted within a day gives 72.9% on small lots, and two established apartments
  of a building advertised 8 to 30 days apart give 22.5%. Read as a mixture of those
  two, the kept links are 80% to 94% reposts, depending on the measure (equal asks,
  raises, moves over 5%).
- Floor plans. Where both ads carry a plan, the file is the same in 51.4% of joins and
  47.7% of links between passing labels. Readers given the plans of pairs with
  different files, and nothing else, called the layout the same in about 96% of kept
  links against 14% for pairs of established apartments.
- City records. On lots with adequate HPD coverage both labels of a kept link are in
  HPD for about 3% of links. With HPD holding about 72% of real labels, that puts links
  between two real apartments at 5% to 8% of the kept set.
- Inventory. Over all lots, the labels advertised exceed the apartments PLUTO counts by
  303,331, and 472,169 labels were used for a single ad.
- Readers. Sonnet readers given photos, text and histories with the statuses hidden
  called 3 of 91 joined links different apartments, 12 of 225 links between passing
  labels and 7 of 218 thin-record links
  (`/data1/apartments/tmp/outlier-sprint/s2/R/v3/results.md`).

The verdict groups behave alike on every one of these, so the standard withholds a join
from links it cannot certify, and nothing here says those links are different
apartments more often. Most of them are probably reposts. No test in hand says which.

### The dataset under the standard

`rentfrontier.b0chains` collapsed the chains built from the 19,787 joins and the
same-page handoffs between them (`C/links-std.parquet`, dataset `C/ds-std`): 12,368
chains, 18,208 rows dropped (0.96% of 1,896,471), 4,732 kept rows moved to an
established unit id, and 16,787 fewer unit ids (1.8%). The dropped rows' asks are at or
above the kept row's in 88% of cases (equal in 45%). The carried split keeps 188,600
of the 189,647 held-out ads.

The served fit's held-out scores hardly register the class. 404 held-out ads (0.21%)
have a training predecessor through a joined link under another unit id. They carry
0.15% of the summed squared gap, at an rms gap of 0.070 and a coverage of 0.827. Their
gap regressed on the predecessor's deviation has slope 0.76 (SE 0.06). Most of the
class is on the training side, where 21,910 chain rows are the only row of their unit.

An earlier version of this section counted 70,300 chains and 9.9% of the fit's units.
That count included every link of a wider screen, with photos and text as the evidence
of identity. Under the standard the certified part is 12,383 chains (12,368 of them
inside the served dataset's build) and 1.8% of unit ids.

I wrote no ledger entries for the class. The repair is a pipeline rule (the label
standard, then the collapse), and it waits for after the sprint (candidate R under
"Fits for after the sprint").

Weak points: the adequacy level of 75% is a choice, and the count of joins moves from
19,787 to 26,104 at 50%. The grid treats a bare number as a line of its own. PLUTO's
apartment count is the yardstick for coverage and is wrong for some lots. Readers'
verdicts and plan readings rest on the material a landlord reuses, so they count as
support only. The screen leaves out reposts after a RENTED ad and gaps of 2 days or
more, so 19,787 is a floor for the practice and no estimate of its size. The lister
field is the brokerage, so two agents of a firm in one building read as one lister.

## The lease cycle

In the count-change table under "An apartment changes over the years" the first year has
a higher share than the two years after it. Split by month, that row has a pattern: the counts differ in 18% of
pairs 3 to 9 months apart, against 6.6% at 12 months, 6.6% at 24 and 8.1% at 36. Most New
York leases run 12 or 24 months, so an apartment advertised again on the anniversary of
its previous ad is the ordinary case, and one advertised in between has had something
else happen to it. I checked the served fit's calibration on the same clock.

Months below run from the opening date of the page's previous kept ad to the opening date
of the held-out ad. A held-out ad whose bedroom count differs from the previous ad's is in
a row of its own, since the fit starts a new unit for it. The width is the median log
width of the 80% interval.

| months since the previous ad | held-out ads | inside the 80% interval | sd of the gap | mean gap | width | beyond 0.2 either way |
|---|---|---|---|---|---|---|
| 0 to 2 | 9,822 | 0.794 | 0.074 | -0.014 | 0.142 | 2.4% |
| 3 to 9 | 13,485 | 0.752 | 0.090 | -0.007 | 0.155 | 3.3% |
| 10 to 13 | 23,524 | 0.841 | 0.070 | -0.002 | 0.165 | 1.65% |
| 14 to 21 | 19,508 | 0.804 | 0.080 | -0.005 | 0.167 | 2.5% |
| 22 to 25 | 16,828 | 0.839 | 0.074 | -0.001 | 0.174 | 1.8% |
| 26 or more | 61,738 | 0.808 | 0.087 | -0.003 | 0.186 | 3.2% |
| count changed | 7,370 | 0.695 | 0.113 | -0.005 | 0.193 | 7.2% |
| no previous ad on the page | 43,148 | 0.815 | 0.084 | -0.004 | 0.162 | 2.75% |

The intervals cover 84% of asks at the two anniversaries and 75% in the months between
them. The fit's own width grows steadily with the time since the previous ad, as the
unit's Ornstein-Uhlenbeck deviation prescribes, while the realized spread peaks at 3 to 9
months. There the interval is 6% narrower than at 10 to 13 months and the sd of the gap
is 28% larger. So the fit is most confident about a returning apartment in the months
when its ask is least settled.

The pattern holds in every pairing of the two ads' seasons (0.72 to 0.79 at 3 to 9 months
against 0.82 to 0.85 at 11 to 13) and in every year from 2015 to 2026, where the ads 3 to
9 months after the previous one are covered 4 to 12 points less often than those at 10 to
13 months (2024: 0.751 against 0.873). Pairs of ads from one lister sharing photos show
it too (0.780 against 0.858), so pages holding two apartments do not produce it.

### The previous ad's ending

Months since the previous ad stand in for whatever happened to it. From the raw records'
status histories I took each previous ad's ending as the first off-market status after
its last ACTIVE event: a deal (RENTED or IN_CONTRACT), NO_LONGER_AVAILABLE, DELISTED, or
paused (TEMPORARILY_OFF_MARKET). Coverage of the 80% interval and the mean gap, by months
and ending:

| months | deal | no longer available | delisted | paused |
|---|---|---|---|---|
| 0 to 2 | 0.789, -0.013 | 0.810, -0.011 | 0.783, -0.018 | 0.787, -0.018 |
| 3 to 9 | 0.767, -0.003 | 0.757, -0.004 | 0.731, -0.013 | 0.735, -0.013 |
| 10 to 13 | 0.853, -0.002 | 0.826, +0.001 | 0.821, -0.007 | 0.833, -0.002 |
| 14 to 21 | 0.810, -0.005 | 0.804, -0.002 | 0.798, -0.010 | 0.779, -0.008 |
| 22 to 25 | 0.843 | 0.833 | 0.838 | 0.828 |
| 26 or more | 0.812, -0.003 | 0.803, 0.000 | 0.812, -0.011 | 0.798, -0.008 |

At 3 to 9 months the cells hold 5,303 ads after a deal, 3,436 after "no longer
available", 3,123 after a delisting and 1,623 after a pause. The months move coverage by 7
to 10 points within every ending, and the ending moves it by 2 to 4 points within a row
of months. So the ending is the smaller part. It does carry a direction: after a delisted
or paused ad the apartment returns about 1% lower against the fit's median in most rows.

Within 3 to 9 months I split further:

- **Run and cuts.** A previous ad delisted after 15 to 45 days with cuts is followed by
  coverage 0.681 and a mean gap of -0.018 (320 ads). Delisted after more than 45 days
  with cuts: 0.743 and -0.026 (331). A deal within 14 days and no cut: 0.776 and -0.003
  (2,509), still 8 points under the same ending at 10 to 13 months.
- **Time off the market.** About 87% of these apartments were off the market for more than
  90 days between the two ads. The apartments back within 31 to 90 days of a delisting
  have the lowest coverage (0.675, mean -0.022, 342 ads).
- **The previous ad's price path.** Where the previous ad was raised during its run, the
  return is lower against the fit: -0.032 after a deal at 0 to 2 months (292 ads), -0.018
  after a deal and -0.029 after a delisting at 3 to 9 months. This is the closing raise
  of `docs/notes/closing-asks-2026-11-11.md` seen from the next ad. After a delisting with
  cuts over 5% the return is -0.025 at 0 to 2 months and -0.013 at 3 to 9. After a deal
  with cuts over 5% it is at the fit's median.
- **Furnished.** With furnished wording in either ad, coverage at 3 to 9 months is 0.696
  (978 ads) against 0.756 without. The `lease_term` field is empty for nearly every ad,
  so stated lease lengths could not be used.

Sonnet readers read 128 pairs of ads blind to the model's numbers (78 at 3 to 9 months,
50 at 10 to 13, with 68 of the 128 drawn from gaps beyond 0.15). They called 72 of the 78
off-cycle pairs and 48 of the 50 anniversary pairs the same apartment, certainly or
probably. Their account of each return followed the status history: every return after a
deal at 10 to 13 months read as a lease ending on schedule, 21 of 27 returns after a deal
at 3 to 9 months as a short or broken lease, and nearly every return after another ending
as an apartment that had not rented. The texts added little to the record. A bedroom
count described differently between the two ads turned up in 7 of the 38 large off-cycle
gaps against 2 of the 20 random anniversary pairs, and a different lister in 14 of 38
against 3 of 20. The readers found the change in ask explained by the two ads in 16 of
20 random anniversary pairs and 21 of 40 random off-cycle pairs.

### Sizes of the explanations

To compare the explanations on one scale I approximated each ad's predictive density by a
t with 5 degrees of freedom scaled to the served 80% interval, fitted a scale factor (and
where stated a level shift) per group, and summed the gain in log density over the
held-out ads. The factors were fitted on half of the buildings and scored on the other
half, both ways.

| groups | gain, cross-fitted |
|---|---|
| a single factor | 49.5 |
| months (the eight rows above), scale | 878.4 |
| previous ending, scale | 526.0 |
| months by ending, scale | 915.1 |
| months by ending by run by cuts, scale | 914.5 |
| months by ads of the unit (1 to 2, 3 to 4, 5 or more), scale | 1,127.7 |
| a single factor and a single level | 596.1 |
| months, scale, beyond the single level | 868.7 |
| months, scale and level, beyond the single level | 1,106.6 |
| months by ending, scale and level, beyond the single level | 1,192.2 |
| calendar year, scale | 1,185.0 |
| months and three eras, scale | 1,997.8 |

About 381 of the ending's 526 come from the rows with no previous ad and a changed count,
which both groupings share. Among ads with a previous ad of the same count the months give
about 490 and the ending about 160, and the ending adds 37 to the months (915 against
878). The months carry most of the effect and the previous ad's outcome is the remainder.
The fitted factors are 1.13 at 3 to 9 months, 0.88 at 10 to 13, 0.89 at 22 to 25, 0.97 at
0 to 2 and 1.30 for a changed count.

The level rows show a second, smaller effect. The served median is 0.47% above the
held-out asks overall (mean gap -0.0047, about 1% in 2022 and 2023, near zero in 2026),
and a single shift is worth about 550. Beyond it, a level per row of months adds 238,
most of it from the apartments back within 3 months, which come 1.4% under the median
against 0.2% to 0.8% in the other rows. The previous ad's ending then adds 86.

The calendar year is as large as the lease cycle and nearly additive with it. Coverage
is 0.826 through 2019, 0.745 in 2020 to 2022 and 0.826 since 2023, with factors of 1.15
in 2020 and 1.18 in 2021 against 0.91 to 0.93 in 2024 to 2026. The extra spread of 2020
to 2022 is specific to the ad: neighbourhood-by-month means hold under 3% of the gap's
variance in that era, so the fit's time trend did not miss the market as a whole.

### The years 2020 and 2021 on training rows

A held-out ad is its unit's newest, so a held-out ad dated 2020 belongs to an apartment
not advertised since, and such apartments could differ from the rest. To separate the
era from that selection I scored training rows the way the fit scores held-out ads
(`/data1/apartments/tmp/outlier-sprint/s2/Y/`, `results.md`). The saved draws hold no
unit terms for training rows, so the check rebuilds them: the fixed part from the fit's
own design code and the posterior means of its coefficients, and the building paths and
unit terms from a Gibbs sampler run at the posterior means of the scalars. On the
held-out ads the rebuild gives a coverage of 0.805 against the fit's 0.808, and 0.821,
0.743 and 0.825 by era against 0.827, 0.746 and 0.828.

I then removed a training row from each of 160,673 units, reran the sampler on the rest
and scored the removed rows. Coverage of the 80% interval:

| rows | to 2019 | 2020 to 2022 | 2023 on |
|---|---|---|---|
| the fit's held-out ads | 0.827 | 0.746 | 0.828 |
| A: newest ads the split's draw left in training | 0.828 | 0.745 | 0.834 |
| B: second-newest ads, the newest being held out | 0.847 | 0.750 | 0.827 |
| C: a row drawn from the unit's earlier ones | 0.817 | 0.724 | 0.811 |

Set C rows have a later ad in the unit, and they cover 0.710 in 2020 and 0.697 in 2021
against 0.795 to 0.826 in 2014 to 2019 and 0.811 to 0.814 in 2023 to 2025. Stretching the
predictive spread until the interval covers 80% takes a factor of 1.37 and 1.41 for set
C in those years and 1.24 and 1.30 for the held-out ads, against 0.82 to 1.06 in the
other years. So the selection of each unit's newest ad does not produce the era's
spread. The asks of 2020 and 2021 are wider around the fit for apartments advertised
before and after as well. 2022 is nearer the other years on training rows (0.785 and
0.787 in sets B and C against 0.763 on held-out ads).

The lease phase holds up on the same rows: the removed rows 3 to 9 months after the
unit's previous row cover 0.748 to 0.761 in the three sets against 0.825 to 0.842 at 10
to 13 months.

The check does not separate ad-level noise from apartments moving faster than the
fitted drift allows (its time scale is 9.6 years). An apartment whose ask dropped in
late 2020 and recovered in 2021 reads as wide in both years under either account. The
rebuild is also a plug-in at the scalars' posterior means, with no draw-by-draw rebuild.

### Reading

An apartment back on its anniversary has been through a tenancy, and the landlord prices
the renewal of an offer the market accepted a year earlier. An apartment back in between
is either one whose tenancy ended early (39% of the 3 to 9 month returns follow a deal)
or one whose earlier ad came down with no deal recorded and whose price is still being
searched for. In both cases the previous ask is a weaker guide than its recency suggests,
and the fit treats it as a stronger one, since the deviation process knows only elapsed
time. The lower returns after a delisting, a pause or a raise agree with the search
account: the previous ad's last ask was a price nobody took.

The hypothesis going into this section came from the coordinating session: the outcome of
the previous ad would carry the miscalibration. It turned out to be the smaller part. The
months since the previous ad are worth 868.7 beyond the single level, and the previous
ad's ending adds 86 once months and levels are in.

Two parts of this account are not established. The records do not say whether an
apartment "no longer available" was let off the platform, so the split between broken
tenancies and unrented apartments is uncertain for a quarter of the returns. And the
cause of the spread of 2020 and 2021 is open. The training-row check above rules out the
selection of each unit's newest ad, and it leaves two accounts standing: asks of those
years scattered more around each apartment's level (net rents typed for some ads and
gross rents for others would do it, since free months were common then), or apartments
moved faster than the fitted drift.

Weak points of the measurement: the factors come from held-out ads (cross-fitting by
building changed them little), the t density approximates the fit's predictive
distribution, the months are measured on unit pages while a fit would measure them on its
unit ids, and the count-changed row is a new unit to the fit. The candidates L1, L2 and
Y1 under "Fits for after the sprint" carry the predictions.

## What I changed

- **Ledger, PR #1307.** Of the readers' proposals, 46 corrections had independent evidence: 15
  excludes, 15 bedroom sets, 5 bath sets, 3 size sets and 8 ask sets, each backed by another
  ad for the unit, a stated size or a floor plan. I dropped 13 proposals: ask sets with no
  other ad at the new level, excludes resting on ad text alone, and bedroom sets the unit's
  other ads contradict. None of the ask sets turns a net ask gross.
- **Ledger, PR #1315.** A second pass over the first session's reads and the ads next to
  them gave 59 corrections: 27 bedroom sets, 12 bath sets, 5 size sets, 5 ask sets and 10
  excludes.
- **Ledger, second look.** The files of 2026-11-12 hold the work described under "The
  corrections, a second look" (PR #1318): 31 sibling corrections, 12 from the large-unit
  reads, 32 `join_units` and 24 `split_unit` entries, 737 for the blank forms (22 bedroom
  sets, 10 bath sets, 703 excludes, 2 retractions) and the timeline file with 8
  retractions of merged entries, 15 `bedrooms_unknown` excludes and 3 sets. The retractions
  take back sets backed by an ad of the unit years away from the corrected ad, or by the
  page of a lister who relabels reposts.
  Ledger corrections reach a fit when the dataset is next rebuilt. The served fit b9 was
  fitted before all of them.
- **Closing asks.** Some of the readers' price typos and placeholders were prices typed on the
  day an ad went off market, and 9,748 of the diagnostics ads (5.0%) take a change dated on or
  after that day. `rentfrontier.b0closing` reprices 104,330 rows at the last ask before
  that day. The 4-chain fit c1 gained 589.5 elpd (SE 107.7) on the unchanged held-out ads
  and missed the gate on the walk's hyperparameters. The miss comes from four chains on a ridge
  they cross slowly, not from the data (`docs/notes/closing-asks-2026-11-11.md`).
  A second look at the records' event times narrowed the rewrite to the 59,026 rows whose
  ask is a raise typed within 5 minutes before the ad's off-market status event, or after
  it (`rentfrontier.b0closingraise`). No renter could answer such a price. Part of those
  raises carry the marks of a net rent replaced by the lease's gross rent, and the unit's
  other ads sit nearer the ask before them. Cuts and earlier raises keep the off-day price.
- **Reposts.** `rentfrontier.b0chains` (PRs #1319 and #1320) writes a dataset with each
  chain of reposts collapsed into the row of its last ad, and carries the source's
  held-out ads over so that a fit on it scores the ads the served fit scores. Run on the
  19,787 joins certified under "Reposts under a new label", it drops 18,208 rows. No
  served data changed: the collapse waits for the label standard to become a pipeline step.
- **Income flag.** The income-restricted flag missed 9 of the 13 lottery and HPD ads the
  readers found. `rentfrontier.b0income` widens it to 2,590 rows; a Sonnet check of 80 added
  rows found no market ads (`docs/notes/income-flag-2026-11-11.md`).

## Fits for after the sprint

Ben ruled out Modal fits for the rest of the sprint. These wait, each with its predictions
written in its note before launch. `docs/TODO.md` carries the full list with the smaller
candidates from the text flags.

1. c3, the narrowed closing dataset with b9's 6-chain design
   (`docs/notes/closing-asks-2026-11-11.md`). It takes the place of c2.
2. The income flag, on c3's winner's dataset (`docs/notes/income-flag-2026-11-11.md`).
3. No fit for the sprint's ledger entries by themselves. They change about 860 of the
   pipeline's 1,985,235 kept ads (about 730 of them excluded), join 32 pairs of unit pages and move 69
   ads off shared unit records, which is negligible under the rule against refits for small
   data changes.
   c3 reprices b9's dataset and does not read the ledger, so the entries first reach a fit
   when the pipeline next rebuilds the dataset for a market snapshot.
4. L1, a noise scale by lease phase. The ad-level scale is multiplied by a factor per
   group of months since the opening of the unit's previous ad in the dataset: no previous
   ad, under 3 months, 3 to 9, 10 to 13, 14 to 21, 22 to 25, 26 or more. The groups are
   known when an ad opens and read no rent. Predicted: the factor at 3 to 9 months is 1.15
   to 1.35 times the factor at 10 to 13; coverage of the 80% interval moves from 0.752 to
   between 0.775 and 0.805 at 3 to 9 months and from 0.841 to between 0.80 and 0.825 at 10
   to 13; elpd gains 400 to 900 on the latest split; the median's error moves by less than
   0.0005. The free check behind the range gave 878 ("The lease cycle").
5. Y1, a noise scale by calendar year. Predicted: factors of 1.10 to 1.22 for 2020 and
   2021 and of 0.89 to 0.95 for 2024 to 2026, against the all-years scale; coverage moves
   from 0.745 to between 0.775 and 0.80 for 2020 to 2022 and from 0.826 to between 0.80
   and 0.815 since 2023; elpd gains 600 to 1,300; the 80% interval of a current ad on the
   Deals page narrows by 5% to 9%. The free check gave 1,185. Training rows scored as
   held-out ads show the same spread in 2020 and 2021 ("The years 2020 and 2021 on
   training rows"), so the factors are not produced by which units the split holds out.
6. L2, a level per lease phase, on L1's winner. Predicted: -0.008 to -0.016 for an
   apartment back within 3 months, the other phases within 0.004 of each other, and an
   elpd gain of 100 to 300. A column for the previous ad's ending (delisted or paused
   against a deal) is a further candidate with a free-check gain of 86, and it needs the
   raw status histories carried into the dataset first.
7. R, the chains of reposts certified by the label standard, each collapsed into the row
   of its last ad under the chain's established unit id (`rentfrontier.b0chains` on the
   joins of "Reposts under a new label", scored with `--split carried`). The change drops
   18,208 rows (0.96%) and 16,787 unit ids. Predicted: elpd on the 188,600 shared
   held-out ads moves by less than 100 in either direction, which is under 2 SE; the
   median's error moves by less than 0.0003 and coverage by less than 0.002; the rms gap
   of the 65 held-out ads that lose a same-unit predecessor in their chain rises from
   0.043 to between 0.05 and 0.08. With a predicted change this small the collapse does
   not call for a fit of its own. It is a correction of the target (an ask the apartment
   did not rent at leaves the data) and can join the next rebuild of the dataset as a
   pipeline rule, once the label standard is a pipeline step with its city records.
8. U1, a unit scale growing with size. The model reads no size now, so the size the
   diagnostics use (`model_sqft`) first goes into the dataset through a module of its own.
   The sd of a unit's lasting level and of its drift are both multiplied by
   `exp(gamma * max(0, log(sqft / 1000)))`, with one `gamma` and a factor of 1 for a unit
   with no size. Predicted: `gamma` between 0.3 and 0.6; coverage of the 80% interval over
   1,500 sq ft moves from 0.69 to between 0.73 and 0.78; the slope of the gap on the
   previous ask's deviation in sample S of "Observed attributes of large units" falls from
   0.49 to under 0.30; coverage under 1,000 sq ft moves by less than 0.005; elpd gains 150
   to 500. The range for `gamma` comes from the slopes by size bin under a normal
   approximation with one earlier ad per unit. No free check stands behind the elpd range.
   Sizes filled from another ad or from the line were wrong in a third of the 26 filled
   ads read, and a wrong large size widens a small unit's prior, so the size column takes
   stated sizes and sizes agreeing across a unit's ads first.
9. U3, a building-level term for large units, on U1's winner: a coefficient per building
   on `max(0, log(sqft / 1000))`, drawn from a normal distribution around an area-level
   mean. Different large units of one building share 25% of the persistent covariance (15%
   to 37%), and the area pattern (large units over-predicted in low-rent areas) is about 3%
   of the large units' gap variance. Predicted: the persistent sd of sample S falls from
   0.098 to between 0.085 and 0.092, and elpd gains 50 to 250.
10. U2, a Student-t distribution for the unit's lasting level, on U1's winner. It tests
    whether the levels the normal prior gives up are a tail every size has. Predicted: its
    degrees of freedom come out over 8 once U1 is in, and elpd moves by less than 100,
    which would close the candidate.

Gate fits run 6 chains in three containers of 2. The reparameterization of the walk's
hyperparameters proposed earlier in the sprint is withdrawn: the scale step already slices
along their ridge, and c1's miss reads as a tail event of 4 chains
(`docs/notes/closing-asks-2026-11-11.md`, "The gate miss, second look"). A second pass of
the unit-level steps within each sweep is a sampler candidate with a timing pilot ahead of
any fit.

## Open leads

- The 52,026 units flagged by weak signals of a second apartment were read 42 times, and the
  280,638 unflagged units were not sampled. A wider read would bound the shared records
  left in the fit.
- Counts differ in 18% of page pairs 3 to 9 months apart against 6.6% at 12 months. No
  read has split those pairs between a recount of the same rooms and another apartment
  on the page.
- The served median is 0.47% above the held-out asks, about 1% in 2022 and 2023. The cause
  was not looked into.
- Coverage is 0.745 for held-out ads of 2020 to 2022 against 0.826 before and after, and
  training rows show the same. The cause is open between asks scattered around each
  apartment's level in those years and apartments moving faster than the fitted drift.
- Size fills from another ad of the unit or from the line were wrong in a third or more of
  the 26 filled ads read. The pipeline rule in `docs/TODO.md` needs a wider read first.
- Real Street's short-text ads with a typed count are also wrong in places (3974767 codes 1
  bedroom and 2 baths on a 3-bedroom page). Their 122 held-out ads have a median gap of
  +0.025, so the errors are few, and no screen for them exists.
- Commercial spaces and rooms get through the pipeline's filters. The ledger excludes the
  clear cases the readers found, and the screen's other matches sit near zero gap.
- The Rheingold and buildings like it, where brokers post any unit of the building under
  arbitrary unit pages (`docs/TODO.md`).
- The label standard leaves 28,785 nominated repost links undecided, 23,931 of them in
  buildings whose city records hold too few apartment numbers. A further record of real
  labels for those lots (DOB certificates of occupancy, rent registrations by apartment)
  would decide them (`docs/TODO.md`).
