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

Counted over all kept rows (`s2/N/conc_all.py`, `conc_year.py`), the wording with no
recorded free months is on 94,867 of the 799,732 rows dated through 2019 (11.9%) and on
25,230 of the 205,600 rows of 2020 (12.3%). From 2021 it is on 586 to 1,549 rows a year,
at most 1.3%. The structured field came into use during 2020: recorded free months are on
0.2% of the held-out ads through 2019, 14.7% of those of 2020, 25.5% of 2021 and 9.7%
from 2023. The 1,642 held-out ads of 2020 with the wording alone have a median gap of
-0.020, against +0.000 for that year's ads with no concession, and the 2,626 through
2019 have -0.011 against -0.004. So the parsed column would act on about 120,000 training rows
from the years before listers had the field, and on few rows since. In 2021 the wording
alone is on 116 held-out ads, and the 13,468 ads with no concession in record or text
are covered 0.729, so net rents typed with the terms in the text do not account for that
year's spread.

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

I computed the covariance a second time with a script written apart from D5's
(`s2/N/d5check.py`). It gives 0.00941 over 1,500 sq ft (5,841 ads, bootstrap 0.00821 to
0.01059, slope 0.443) and 0.00053 at 500 to 1,000 sq ft (60,466 ads), against the 0.00965
and 0.00070 above. By size it is 0.0005 to 0.0008 under 1,000 sq ft, 0.0013 at 1,000 to
1,250, 0.0027 at 1,250 to 1,500, 0.0060 at 1,500 to 2,000 and 0.0158 over 2,000, so it
grows from 1,000 sq ft on with no step at 1,500. It is 0.0087 when the previous ad is
within 2 years and 0.0100 when it is over 4 years back.

The unit's previous ask is in training, so a fit with the right prior for
the unit leaves the held-out gap uncorrelated with the previous ask's deviation. A
positive covariance then measures history the fit held and did not use, and where the fit
used part of it the covariance understates the variance of the lasting deviation. An
error of the model's median common to both asks enters both gaps as well. For mid-sized
units the reference group's 0.0005 is the most it can be. For large units the pairs of
different apartments in a building, in the paragraph above, have a quarter of the
covariance of a unit with its own previous ask, so the common error is at most that
part.

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
against 0.2% to 0.8% in the other rows. The previous ad's ending then adds 86. The single
shift is specific to the held-out ads and would move the open ads of a market run the
wrong way ("The level of the held-out gap").

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
moved faster than the fitted drift. The counts under "Concessions stated in the text"
limit the first account to 2020, and to a small part of it: concession wording with no
recorded free months is on 12.3% of that year's rows and on under 1% of 2021's. The 1,642
held-out ads of 2020 with the wording are covered 0.730 against 0.762 for the 11,139 with
no concession, so bringing them to the 0.826 of other years would raise 2020's coverage
by about 0.01. 2021's ads with no concession at all are covered 0.729.

Weak points of the measurement: the factors come from held-out ads (cross-fitting by
building changed them little), the t density approximates the fit's predictive
distribution, the months are measured on unit pages while a fit would measure them on its
unit ids, and the count-changed row is a new unit to the fit. The candidates L1, L2 and
Y1 under "Fits for after the sprint" carry the predictions.

## Units with no ad in training

The Deals page scores open ads, and about a third of them belong to units with no ad in
training. The 80% range covers fewer of their asks than it should. I split those ads to
learn how much of the shortfall comes from the data (relabeled reposts, placeholder pages)
and how much from the model. The scripts are in
`/data1/apartments/tmp/outlier-sprint/s2/N/`, with their output in `out/`. They read the
per-ad output of the two market runs: n9 scores the 6,774 ads open on 2026-11-09 at their
current asks, and j9, the backtest of 2025-11-10, scores the 9,346 ads open on that day at
their final asks.

| the prediction rests on | n9 ads | n9 coverage of the 80% range | j9 ads | j9 coverage |
|---|---:|---:|---:|---:|
| training ads of the unit | 4,518 | 0.807 | 6,178 | 0.805 |
| the building's other units | 1,990 | 0.732 | 2,845 | 0.767 |
| the area, in a building new to training | 266 | 0.658 | 323 | 0.678 |

I split the ads of the second row. Where a figure below takes the second and third rows
together (2,256 ads in n9), it says so. n9's asks are still open, and an ask long on the
market is one nobody has taken: among the 2,256, the ads open 46 to 120 days have a
median gap of +0.042 with 25% above the range, against -0.001 for ads open under 15 days.
j9's asks are final, so where the two runs differ I go by j9.

**Data causes.** Each of the candidates accounts for little.

- The label standard of "Reposts under a new label" fails 132 of j9's 2,845 labels and
  121 of n9's 1,990. The range covers those ads 0.818 and 0.826 of the time, against
  0.765 and 0.724 for ads with passing labels and 0.763 and 0.721 on lots with thin
  records. Relabeled reposts are about 5% of the new units and do not produce the
  shortfall.
- Placeholder pages are rare. Of the 912 ads found in the text-flag table among n9's
  2,256, 15 have a description of 0 to 3 characters, and the range covers 12 of them.
- A page whose previous ad has another bedroom count is a new unit to the fit. n9 holds
  307 such ads among its building-basis and area-basis ads, covered 0.645 (`new8.py`).
  Where the count went down (138 ads) the median gap is +0.027, and the median ask is
  0.8% under the page's previous ask of two years earlier. Where it went up (169 ads)
  the median gap is -0.018. The ask keeps part of the level of the earlier count, which
  fits a recount of the same rooms better than another apartment on the page. No ad was
  read for this.
- Among n9's 2,256, coverage shows no pattern by the building's age (0.70 to 0.75 across
  groups). By lister it runs from 0.53 to 0.90 among those with 20 or more of the ads:
  Douglas Elliman's 75 ads are covered 0.59 with a median gap of +0.07, Bushburg's 62 are
  covered 0.60 with -0.087, and Skyhigh's 48 are covered 0.88. I did not follow the
  listers further.

**Bedrooms.** The fit gives every new unit the same sd for its unit term, 0.075. The
column "sd needed" is the unit sd at which the predictive sd would equal the sd of the
group's gaps (taken from their 10th and 90th percentiles), with the fit's location and
noise variances left as they are.

| bedrooms | j9 ads | j9 coverage | j9 sd needed | n9 ads | n9 coverage | n9 sd needed |
|---|---:|---:|---:|---:|---:|---:|
| studio | 505 | 0.784 | 0.085 | 306 | 0.788 | 0.085 |
| 1 | 1,050 | 0.818 | 0.072 | 687 | 0.782 | 0.086 |
| 2 | 872 | 0.733 | 0.102 | 642 | 0.707 | 0.112 |
| 3 | 323 | 0.693 | 0.118 | 257 | 0.630 | 0.144 |
| 4 or more | 95 | 0.663 | 0.128 | 98 | 0.633 | 0.161 |

The shortfall belongs to the apartments with 2 or more bedrooms. Coverage falls with the
count for units with training ads too (0.840, 0.812, 0.798, 0.754 and 0.698 in n9), by
less. Within j9's 2-or-more-bedroom ads coverage falls with the size of the lot: 0.786
on lots under 10 apartments, 0.764 on lots of 10 to 49, and 0.662 on lots of 50 or more
(656 ads, 23.5% above the range, median gap +0.026). I did not separate the lot's size
from the building's lister or age. Studios and 1-bedrooms on lots of 50 or more are
covered 0.822. By stated size, j9's coverage runs 0.932 under 600 sq ft, 0.838 at 600 to
900, 0.748 at 900 to 1,200, 0.708 at 1,200 to 1,600 and 0.555 over 1,600 (110 ads, median
gap +0.092). 2,244 of the 2,845 ads state no size, so a scale reading size alone would
leave 79% of the new units where they are.

**New units of a building miss together.** I took the covariance of the gaps (clipped at
0.4 either way) over pairs of new units in a building, weighting a building by its ads
(`new7.py`, with variants in `new9.py`). The intervals run from the 5th to the 95th
percentile of a bootstrap over buildings.

| pairs | j9 covariance | n9 covariance |
|---|---:|---:|
| two units of 2 or more bedrooms | 0.0082 (0.0058 to 0.0109) | 0.0085 (0.0059 to 0.0112) |
| two studios or 1-bedrooms | 0.0021 (0.0013 to 0.0028) | 0.0040 (0.0029 to 0.0052) |
| a unit of each class | 0.0013 (-0.0002 to 0.0030) | 0.0010 (-0.0009 to 0.0028) |

The variance of the clipped gap of 2-or-more-bedroom new units is 0.0164 in j9 and 0.0215
in n9, so half of it in j9 is common to the building's other large new units, and little
of that is shared with the building's small ones. The result holds with a single ad kept
per building, count and ask (0.0084 in j9, 0.0072 in n9), which removes template ads
posted at one price, and in buildings with at most 10 new units (0.0060 and 0.0087). In
j9's buildings with over 10 new units it is 0.0141.

Part of the shared gap is on record before the ad opens. For each new unit I took the
median ask of the building's training ads of the same count in the two years before the
scoring day, moved to the scoring month with a citywide index, less the model's median
for the new unit (`sib.py`, `sib2.py`). The new unit's gap follows that difference with a
slope of 0.290 in j9's 1,162 ads of 2 or more bedrooms (R2 0.087) and 0.392 in n9's (R2
0.130); for 3 or more bedrooms the slopes are 0.373 and 0.599. Those ads are the subset
with a same-count ad of the building in the two years, and their pair covariance is
0.0067 in j9 and 0.0075 in n9, under the table's 0.0082 and 0.0085 for all large new
units. Taking the fitted part out lowers it to 0.0051 and 0.0060. So within the subset
the building's earlier asks for the count predict about a quarter of the shared gap, and
the rest is common to the units on the market at the same time. The 2-or-more-bedroom
new units with no same-count ad of the building in two years are covered 0.598 in j9 (127
ads) against 0.731 for those with one, and 0.492 in n9 (130 ads) against 0.708.

`out/top-j9.log` lists j9's 40 buildings with the largest product of the absolute mean
gap and the count of new units of 2 or more bedrooms. Ten of them have 7 or more such
units: The Seren (17 units at a mean gap of -0.118), Union Channel (10, +0.109), 420
Carroll (7, +0.167), 12 Halsey St (8, +0.127), Atelier Condominium (7, -0.117), Tribeca
House (9, -0.084), 50 West 66 Street (8, +0.076), The Cedar Tower (8, -0.057), The
Stanwix (9, -0.052) and Lawrence Tower (22, +0.040). Union Channel, 420 Carroll and 12
Halsey St have a single lister on their new units and The Seren has two. Buildings with
3 to 5 units have larger means (Carnegie House +0.273, Hanover House +0.227) on fewer
ads.

**Reading.** A building's level and its quarterly path are common to its apartments of
every size, and the model's size and bedroom terms are common to an area. When a
building's 2-bedrooms rent high against its studios, by a better line or larger rooms,
the fixed part has no term for that premium, and a unit with training ads holds it in
its unit term. A new unit starts at the building's level with an sd of 0.075, and the
premium of its class is missing from its median. The leasing office of a large building
may also set a price for each floor plan type and change it from one season to the next,
which the earlier ads cannot predict. That would explain the three quarters of the shared
gap left after the building's earlier asks. I did not test it against ad text or a rent
roll.

The candidates U4 (a unit scale by bedroom count) and U3 in its second definition (a
building level for its larger apartments) follow under "Fits for after the sprint". The
measurements rest on two scoring days, each with its own fit of the served design, and
on asks still open in n9.

## The level of the held-out gap

The served median is above the held-out asks: the median gap is -0.0049, 53.5% of the
asks are below the median, and the yearly medians run from -0.0019 (2020) to -0.0112
(2022). A level error of that size would go into every row of the Deals page, so I looked
for its cause (`s2/N/lvl1.py` to `lvl6.py`, output in `s2/N/out/`). In 2022 and 2023
most of it comes from the ads the split holds out, a base of about -0.4% in the other
years is unexplained, and the open ads of the single backtest do not show it.

**Each unit's last ad.** The latest split holds out the newest ad of a unit, so every
held-out ad is one with no later ad of its unit in the data. The rescoring of "The years
2020 and 2021 on training rows" removed training rows and scored them the way the fit
scores held-out ads, and its tables hold the median deviation of each set
(`s2/Y/tables_mix.log`):

| rows | to 2019 | 2020 to 2022 | 2023 on |
|---|---:|---:|---:|
| the fit's held-out ads | -0.0049 | -0.0056 | -0.0044 |
| A: newest ads the split's draw left in training | -0.0046 | -0.0074 | -0.0057 |
| B: second-newest ads, the newest being held out | -0.0024 | -0.0015 | -0.0006 |
| C: a row drawn from the unit's earlier ones | +0.0013 | +0.0041 | +0.0043 |

Set B is the closest comparison. The check predicts its rows from the unit's earlier ads
alone, as the fit predicts a held-out ad, and each of its rows was followed by a later
ad. Its median is +0.0001 in 2022 and -0.0015 in 2023. The held-out ads of those years
have -0.0108 and -0.0079 in the same rebuild (the fit's own draws give -0.0112 and
-0.0081). Predicting forward from a unit's earlier ads does not produce the offset, then.
It is found in the ads with no later ad of their unit.

By lease phase the sets agree where the lease cycle acts and part elsewhere. For returns
within 3 months sets A and B have -0.0123 and -0.0101. At 10 months or more set B is
between -0.0018 and +0.0013 and set A between -0.0022 and -0.0056. The low asks of the
fast returns come with the phase (candidate L2), and the remaining offset with being a
unit's last ad.

**The same pattern with no model.** For each ad whose unit has an ad of the same count at
least 10 months earlier, I took the change in log ask since that ad, less the change of a
monthly median index for the neighbourhood and count (citywide where the cell is thin).
The table holds the median of that relative change by the months until the unit's next
ad (`lvl2.py`).

| months until the unit's next ad | ads of 2022 | ads of 2023 |
|---|---:|---:|
| 0 to 2 | -0.0227 | -0.0193 |
| 3 to 9 | -0.0235 | -0.0221 |
| 10 to 17 | -0.0282 | -0.0242 |
| 18 to 29 | -0.0370 | -0.0308 |
| 30 or more | -0.0394 | -0.0367 |
| no later ad | -0.0562 | -0.0448 |

The index is a median over all ads and rises with the newer stock, so every row is
negative, and the rows are read against each other. The longer an apartment stayed out of
the ads afterwards, the less its ask had risen. Against all followed ads, the ads with no
later ad rose 2.3 points less in 2022, 1.7 less in 2023, 0.9 less in 2024, 1.1 less in
2025 and 1.3 less in 2026. In 2015 to 2019 the difference is between +0.1 and -0.5
points, and in 2017 to 2019 the first and last rows of the table are 0.4 to 0.7 points
apart, against 3.4 and 2.6 in 2022 and 2023. In 2020 and 2021 the order turns over: the
ads followed within 9 months had risen most.

The whole distribution moves. For 2022 and 2023, the ads followed within 9 months and the
ads never followed have -0.196 and -0.221 at the 10th percentile, -0.022 and -0.049 at
the median, and +0.138 and +0.106 at the 90th. A small subgroup, such as regulated
apartments with no flag, would move a tail and leave the median. The gradient is the same
among the rows with the rent-stabilized flag off (-0.022 at 0 to 9 months, -0.035 at 18
or more, -0.049 with no later ad). The flag is on 2.6% to 3.2% of last ads against 1.6%
to 2.1% of followed ads in 2021 to 2025, and the flagged last ads of 2022 and 2023 have
-0.073, so regulated apartments with no flag may add to the pattern. I cannot bound their
part.

Across the 12 years from 2015 the held-out median follows the difference between last and
followed ads with a slope of 0.18 and an intercept of -0.4% (correlation 0.63, about 40%
of the variance of 12 points). The selection as I measured it goes with the years'
departures from -0.4%, loosely, and leaves that base unexplained.

**Account.** I read the pattern as tenants staying. A tenant who took an apartment at a
rent low against its history would stay, and the apartment would be out of the ads for
years. An apartment asking a high rent would come back sooner, unrented within months or
vacated at the end of a lease. Sorting ads by the time until the unit's next ad would
then sort them by price, with the ads with no later ad at the low end. Asks rose fast and unevenly in 2022 and 2023, so the distance between the
landlords who followed the market and those who did not was widest then. A last ad's ask
is still a price a renter faced, so no row changes. The account predicts longer tenancies
at lower relative asks, and the dose-response in the table agrees with it. No record of
tenancies was used.

**Asks in training higher than a renter faced.** The coordinating session proposed the
closing raises and the earlier asks of repost chains as causes.

- A raise typed as the ad closed is on 3.08% of training rows (median raise 0.087) and
  3.38% of held-out rows (0.071), and from 2020 on 2.7% to 7.5% of a year's training
  rows (`lvl5.py`). The fit c1 took the full closing rewrite, the raises among its
  104,330 repriced rows. On the 178,704 held-out ads with unchanged asks it moves the
  median gap from -0.0057 to -0.0046 (`lvl6.py`): from -0.0038 to -0.0004 in 2020, from
  -0.0125 to -0.0116 in 2022 and from -0.0057 to -0.0045 in 2025. Closing asks in
  training account for about 0.1 point of the level, and 0.3 in 2020.
- The repost collapse drops 18,208 rows (0.96%), and an earlier ask of a chain stands a
  few percent over its last. Spread over a building's level that comes to a few
  hundredths of a point. No fit measured it.

**Open ads.** In the backtest j9, the ads of units with training ads have a median gap
of +0.0026 (SE 0.0012), with 48.2% of the final asks below the median. By days open on
the scoring day the median is +0.0018 at 0 to 14 days, +0.0034 at 15 to 45 and +0.0032
beyond. By months since the label's previous ad it is -0.0023 under 10 months (1,264
ads, SE 0.0026), +0.0006 at 10 to 29 (2,572 ads) and +0.0079 at 30 or more (2,276 ads,
SE 0.0021). New units have +0.0092 (SE 0.0027) and ads in buildings new to training
+0.0412 (SE 0.0117). n9, on asks still open, has +0.0083, +0.0045 and +0.0480. The open
ads of a day include the apartments soon to be back, and the held-out ads of the latest
split leave them out. On j9's single day the open ads do not have the -0.5%. Their
levels are +0.3% for units with history (+0.8% in n9, on asks still open), about +0.8% for units back after 30 months or more, +0.9%
for new units and +4% in new buildings, on a single backtest day.

**Sizes.** Of the -0.47%, closing asks in training give about 0.1 point and the fast
returns about 0.12 (13% of the held-out ads at about -0.9%). The rest goes with the
selection of last ads, which is largest in 2022 and 2023. Through 2019 the rescoring
supports the same split, with set B at -0.24% (about what its fast returns give) and the
newest ads at -0.46% to -0.49%. The model-free check supports less of it there, since
last and followed ads differ by under half a point in those years.

A change lowering the fit's level gains elpd on the latest split for a reason absent from
open ads, so I would check the level of a candidate on a backtest before reading such a
gain as a better median. The level terms of "Sizes of the explanations" (the single
shift, and part of the levels by phase) describe the held-out set in the same way.

## Ads coded 0 bedrooms across all listers

The batch on Real Street and M1 Ventures left the same question open for every other
lister. I went through the 336,205 kept ads coded 0 bedrooms with the scripts in
`/data1/apartments/tmp/outlier-sprint/s2/Z/`, sorting them by their text and by the
record's room count:

| class | marks | ads | decided in the ledger before |
|---|---|---|---|
| blank, 1 room | text under 30 characters or starting "draft", without "studio"; `roomCount` 1 | 4,759 | 568 |
| blank, more rooms | the same text; `roomCount` above 1 | 9,027 | 370 |
| count in the text | a longer text mentioning 2 to 5 bedrooms and never "studio" | 1,739 | 50 |
| one bedroom in the text | a longer text mentioning 1 bedroom alone, never "studio" | 5,935 | 565 |
| says studio | a longer text with "studio" | 255,070 | |
| other | a longer text with neither | 59,675 | |

In what follows an ad is counted when it has a typed count of 1 or more, or codes 0 with
a text of 80 characters or more outside the third class. An ad's page is its unit page,
and two ads are near when they opened within 730 days of each other.

### Most blank ads coded 0 are studios

For each ad with a near counted ad on its page I asked whether those ads are all studios.

| class | ads with a near page ad whose page ads are all studios |
|---|---|
| typed 1 or more | 1.1% |
| says studio | 91.5% |
| other | 89.6% |
| blank, 1 room | 63.5% |
| blank, more rooms | 68.6% |
| one bedroom in the text | 56.4% |
| count in the text | 29.8% |

Reading the two blank classes as mixtures of studios and larger apartments with the first
two rows as the pure cases puts studios at about 69% and 75% of them. Feeds and brokers
post many studios with no description, so excluding every blank ad coded 0 would remove
about 9,000 real studios. The room count separates little inside the class: typed studios
have 1 room in 30% of ads and 1.5 to 2 in 63%, and a typed ad with 1 room is a studio in
68% of cases and a one-bedroom in 32%. At 2.5 to 3 rooms 3% of typed ads are studios, and
under 1% above that.

The form default belongs to a few listers. Among each lister's blank ads coded 0 with a
near page ad, the share with only studios on the page:

| lister | blank ads with a near page ad | share with only studios there |
|---|---|---|
| Stuyvesant Heights Realty Corp | 64 | 3% |
| Real Street Inc | 382 | 4% |
| Constantinos Kaimakliotis | 16 | 6% |
| Capital Ventures Group LLC | 44 | 18% |
| Skyhigh Realty NYC LLC | 47 | 21% |
| Corcoran | | 59% |
| City Wide Apartments | | 64% |
| REAL New York | | 76% |
| Compass | | 87% |
| Bozzuto, Icon | | 96% to 97% |

Stuyvesant Heights posts 176 of its 190 open blank ads with the form's own "Draft rental
description", and studios are 55 of its 1,239 ads with a typed count or a studio text. For
it and for Real Street I read a 0 on a blank form as an empty field. From Capital
Ventures on the shares rise without a break, so for the other listers a blank ad coded 0
is a studio more often than not, and each ad needs evidence of its own.

### Evidence for a count

I tested each kind of evidence on ads with a typed count, each left out of its own backing.

- **The building's one layout** (the rule of the earlier batch: at least 4 near counted
  ads on at least 3 pages, all with one count of 1 or more; at least 90% of the building's
  counted history with that count; the ad's opening ask within 15% of their median). On a
  sample of 60,000 counted ads it applies to 2,547 typed 1 or more and gives the typed
  count in 98.7% (97.2% without the ask condition). It applies to 4 of the sample's 7,566
  studios with a full text.
- **The page's other ads** (the near counted ads of the page all have one count of 1 or
  more, and the ad's ask is within 15% of their median). The page gives the typed count in
  93.5% of cases with one page ad and 96% to 97% with several, at every distance in time up to
  two years. It applies to 75% of typed ads of 1 or more with a near page ad and to 2% of
  typed studios, so a blank ad to which it applies is a studio in about 6% to 8% of cases. The
  listers who post blank forms do worse than the feed on their own typed ads:

  | lister | typed ads to which the page rule applies | page gives the typed count |
  |---|---|---|
  | all listers with 200 or more, median | | 95.6% |
  | Corcoran, Compass | | 96% |
  | City Wide Apartments | 4,353 | 90% |
  | PadRabbit LLC | | 89% |
  | Skyhigh Realty NYC LLC | | 87% |
  | Stuyvesant Heights Realty Corp | 280 | 85% |
  | Real Street Inc | 1,062 | 81% |

  With one page ad, a lister under 90% and a building of mixed layouts the page is right
  in 70% to 86% of cases. A set from the page alone would therefore be right in about 85%
  of the blank ads, which is too low for a set and high enough to say the coded 0 is wrong.
- **The text with the page.** On 150,000 typed ads of 1 or more the page rule applies to
  44,567. Where a text without "studio" mentions the page's count (28,653 ads), the typed
  count equals it in 98.5%, in 97.4% for listers under 90% on the page rule alone, and in
  99.2% where the text mentions that count and no other. Where the text mentions other
  counts only (2,243 ads) the page is right in 41.7%.

A Sonnet reader then went through the 224 open ads of the third class to which the
building rule or the page rule applies with a count their text mentions, and said for
each whether the text gives the apartment itself that count. It did for 195. The other 29
are flex wording ("convert the space into a huge one bedroom or a large two bedroom", 25
ads), a building's list of layouts (3) and a text giving two counts (1).

### The entries

`pipeline/ledger/2026-11-12-outlier-sprint-zero-coded-feedwide.ndjson` has 755 lines on
749 ads in 512 buildings:

| ads | decision | evidence |
|---|---|---|
| 75 blank ads (57 with 1 room, 18 with more) | bedrooms set to the building's count: 1 on 34, 2 on 20, 3 on 15, 4 on 5, 5 on 1 | the building's one layout, 50 buildings |
| 6 of those | baths set with the bedrooms | the record has the form's 1 bath and every backing ad has the same other count |
| 195 ads with the count in the text | bedrooms set: 1 on 6, 2 on 138, 3 on 44, 4 on 7 | the text, read by Sonnet, with the building's one layout (40) or the page's other ads (155) |
| 264 blank ads of Stuyvesant Heights (187) and Real Street (77) | excluded as `bedrooms_unknown` | the lister's form default; no building evidence for a single count |
| 215 blank ads of other listers (137 with 1 room, 78 with 2.5 rooms or more) | excluded as `bedrooms_unknown` | the page's other ads have a count of 1 or more at a matching ask, and neither they nor the building settle which |

The first and third rows correct an empty or wrong field toward what the unit's own
building or page shows the renter was offered. The exclusions remove ads whose count
field is empty: Real Street's excluded ads with more than 1 room are those with 3 rooms or
more, and its 20 with 2 rooms stay. For the last row the page rule is the evidence against
the 0 and the lister's own page score is the reason no count is set.
On four of these pages (4253410, 4261306, 3105440 and 4596910) every counted ad within
two years codes a studio, so those blank ads may be real studios. An exclude only removes
the row, so I left them in.

A first draft set 119 blank ads from the building's one layout. I then looked for ads in
the same buildings whose text calls the apartment a studio, and 14 buildings hold one.
At 216 E 28th St, BH Brokerage posts "Studio" on the same unit pages where Vickers
Realty posts blank forms at matching asks, and the building's typed 1-bedroom ads come
from a single lister. At 437 W 48th St a Brown Harris Stevens ad for 4D describes a studio
with a separate kitchen. In such a building the counted ads give the typed count, while
the studios reach the data as zeros, so a typed majority shows nothing about the blank
ads. I dropped the 42 sets in those 14 buildings, and their ads stay coded 0. The
reviewer then ran the same check on unit labels and found 348 E 51st St, where one lister
posts pages labelled "studio" and "stu" with zeros asking $3,000 to $3,500 against a
1-bedroom median of $4,500. I dropped its 2 sets as well. That leaves 75 sets in 50
buildings with no studio in an ad's text or a unit's label.

13,788 ads of the three classes stay as they are (the table counts 13,744 before the 44 dropped sets):

| reason | blank, 1 room | blank, more rooms | count in the text |
|---|---|---|---|
| no near counted ad on the page | 2,842 | 6,081 | 1,107 |
| the page's near ads are studios | 724 | 1,732 | 166 |
| the page's near ads disagree | 58 | 172 | 54 |
| the ask is more than 15% from the page's | 112 | 286 | 76 |
| 2 rooms or fewer, or fewer rooms than the page's count needs | | 232 | |
| a lister whose blank ads with a near page ad have only studios there in 80% of cases or more | 10 | 1 | |
| the text mentions other counts than the page's | | | 62 |
| the Sonnet read (flex, layouts of the building) | | | 29 |

The ads left in the third class price as studios: their 85 held-out ads have a median gap
of 0.000, against +0.26 for the 3 held-out ads among the 195 sets. Most of them repeat a
building's boilerplate or offer a temporary wall. The 5,935 studio-coded ads mentioning one bedroom
also stay. 2,886 of them have junior, alcove, convertible or flex wording, and the class
has a median held-out gap of +0.02 without that wording and 0.00 with it, so the model
prices them like studios already.

31 of the 793 ads of the first draft are among the held-out ads of the latest split, with a median gap of
+0.06 and 0.07% of all squared gaps. Since the batch corrects features on so few held-out
ads, a fit's scores will not move with it.

The studio shares of the blank classes come from a mixture reading, which
assumes that blank studios have page neighbors like those of studios with a text. The
215 exclusions of the last row rest on the same reading: about 6% to 8% of them would be
real studios. I read 25 of the Sonnet verdicts against their quotes and none of the full texts.
No floor plan was fetched. Blank ads with a typed count of 1 or more were not examined.

## Blank ads in buildings with no studio

PR #1325 left about 12,250 blank ads coded 0, because their page's other ads and their
building gave no single count. For these I took up a weaker question. Rule A asks whether
the building has a single layout. Rule B2 asks only whether the building has any studios.
It applies to an ad when:

1. the building's counted ads within two years of it (the ad itself left out) number at
   least 4 on at least 3 pages, and all of them code 1 bedroom or more;
2. at least 90% of the building's counted ads over its whole kept history code 1 or more;
3. the ad's ask lies between 0.85 times the lowest of those nearby asks and 1.15 times the
   highest;
4. over the building's whole kept history, with the ad left out, no typed ad codes 0
   bedrooms, no ad coded 0 has text calling its apartment a studio, and no unit label names
   a studio. Blank forms coded 0 do not count against the building, since their 0 is the
   empty field, and neither do ads coded 0 whose text names 1 bedroom. Seven excludes are in
   buildings with such an ad. The text exists only for ads coded 0, so an ad coded 1 or more
   that calls its apartment a studio goes unseen.

The first draft of PR #1326 used only the first three tests. Its reviewer found 123 of its
413 buildings with an ad that calls the apartment a studio, and 130 excludes on unit pages
where another ad codes the unit 0. At 240 E 82nd St 19F, City Wide's own 2017 ad for the
unit says "HUGE studio". Those ads are studios, so the fourth test now drops them.

I scored the rule on ads whose count was typed, so the answer is known. It applies to 38.3%
of the typed ads with 1 bedroom or more (629,640 of 1,644,852), and to 0.30% of the ads whose
text calls the apartment a studio (757 of 255,070). By rooms the rates are 23.6% and 0.20%
for 1 room, 38.6% and 0.34% for more. With studio shares among blank forms of 63.5% (1 room)
and 68.6% (more rooms), that mix puts real studios at about 1.5% and 2% of the blank ads the
rule applies to. The mix does not describe the blank ads well, though. It predicts the rule
would apply to about 9% of 1-room blank ads, and it applies to 18%. So I also checked the
asks:

- the matched blank ads ask a median 1.00 times the median of their building's 1-bedroom
  asks within two years;
- in buildings with both, over all years, the median typed studio ask is 0.83 times the
  median 1-bedroom ask. The second reviewer, matching each studio to the 1-bedrooms within
  two years, got 0.79.

I dropped the 64 matched ads that ask less than 0.85 times their building's 1-bedroom median.
For 100 of the excludes the building has no 1-bedroom ask within two years, so only the
range of its counted asks checks their price. Townsend's 12 at 187 Green St are among them;
their asks match the building's 2-bedrooms.
The rule does not say which count above 0 is right, so every match becomes an exclude and
none becomes a set.

Of the 952 blank ads rule B matched, rule B2 and the price check keep 412 in 245 buildings,
283 with 1 room and 129 with more, as `bedrooms_unknown` excludes in
`pipeline/ledger/2026-11-12-outlier-sprint-zz-blank-rule-b.ndjson`. Skyhigh posted 58 of
them, Gold & Appel 50, Townsend 34, PadRabbit 22, Rennit 16 and Bold New York 15. City Wide's
274 fall to 14, since most of its buildings carry a studio somewhere in their history. Of the 412, 5 are held out, with a median gap of +0.043.

## The top of the Deals list

1259 Jefferson Ave 1A tops `deals.json` with an ask of $7,250 against a median of $26,848.
Skyhigh Realty posted 10 of the building's 15 training ads on blank forms coded 0, asking
$4,650 to $6,950, the same range as its typed 2- and 3-bedroom ads. The model reads them as
Bushwick studios at about $6,800 and raises the building level about 3.7 times. The default
page already hides the ad, since it carries the beds caution and has no training ad for the
unit. Rule B2, above, excludes all 10 of those blank ads.

I counted how often the sprint's findings touch the top of the default view (the page as a
renter sees it). Blank zeros that make up at least 10% of a building's rows, priced at 0.85
or more of its counted ads, reach 1 of the top 100 deals, 3 of the top 200 and 7 of the top
500. Sprint ledger entries in the building reach 5, 10 and 24. Closing-raise rows (60 of the
top 100) and repost links (36) are too common in buildings to serve as a caution.

Sonnet readers checked the default top 60 against their records, along with the 6 deals past
rank 60 in buildings with heavy blank zeros (`tmp/outlier-sprint/s3/deals/summary.csv`). They
judged 10 real, 36 false and 20 unclear. The record is right for most of the false ones:

- 15: the building's ads with the same count ask about the same as the deal, and the median
  follows pricier lines in the building, those with more baths or more space.
- 12: the unit's own ads or rents of the last year or two ask about the same as the deal.
  The model has no training ad for 3 of these units (the top deal, a micro studio at 640
  Lexington Ave that rented at $2,450 in February, is one). For the other 9 it has 1 to 9
  training ads of the unit and still puts the median 14% to 39% above the ask.
- 3: the ask is net of free months. The target is the net-effective ask, so the model
  scores these as intended.
- 3: a record error (a bath count, a bedroom count flipped between ads, a repost under
  another label).

A caution built from the ledger would hide at most the 3 deals with record errors, so I left
the page as published. The 12 deals whose own unit history matches the ask point at the
model. For 3 of them the fit has none of the unit's past ads. For the other 9 it has them
and still puts the median well above them: the model pulls these units toward their
building and their features more than their own asks justify. The section "Previous asks far over the model"
measured the same pattern on held-out ads: the slope of the gap on the unit's previous
ask, moved by the market index, is +0.14 near zero and +0.69 past a deviation of 0.3, and
units with no coded size keep 42% to 62% of a large deviation. Six of the 9 state no size,
so U4, a unit scale by bedroom count, is the fit that bears on them.

## The random read's data errors, checked against records

Readers of the random 200 ads (s2/M) called 30 of them data errors. I checked each call
against the coded rows of the unit's other ads and the ad's own text.

- 12 net-effective asks: the record stores a gross price and a net-effective rent, and the
  dataset takes the net-effective one by design, so none is an error.
- 3 closing prices: 2 already fall under the closing-raise rule in the served dataset. The
  third, 3136047, moved 7% on the day it rented, under the rule's threshold.
- 4 corrections with another ad of the unit and the ad's own text behind them:
  - 3824486 to 1 bedroom: 3 other ads on the same unit page code 1 and the text describes
    a one-bedroom.
  - 3463808 to 3 bedrooms: the unit's earlier ad with the same text codes 3. The 4 counts a
    possible conversion.
  - 3584278 to 1 full and 1 half bath: the unit's ad three days earlier codes 1 full and 1
    half, and both texts give 1.5.
  - 4827114 to 1 full bath: the unit's earlier ad codes 1 full bath. Only this ad's text
    gives the half bath, so its half-bath field keeps its recorded 0.
- The remaining 11 have backing on one side only (text against a single other ad, or no
  other ad), so they stay as coded.

The 4 corrections are at the end of the rule B2 ledger file.

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
- **Ledger, ads coded 0 bedrooms across all listers.** The file
  `2026-11-12-outlier-sprint-zero-coded-feedwide.ndjson` has 755 lines on 749 ads, described
  under "Ads coded 0 bedrooms across all listers": 270 bedroom sets (75 blank forms from
  their building's one layout, 195 ads whose text gives the count with the building or the
  page agreeing), 6 bath sets and 479 `bedrooms_unknown` excludes (264 blank forms of
  Stuyvesant Heights Realty and Real Street, 215 blank forms of other listers whose page
  has a count of 1 or more at a matching ask). About 12,250 blank ads coded 0 stay, most of
  them studios.
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

- **Ledger, rule B2 and the random read.** The file
  `2026-11-12-outlier-sprint-zz-blank-rule-b.ndjson` excludes 412 blank ads as
  `bedrooms_unknown` in buildings with no studio anywhere in their history, and sets 2
  bedroom counts and 2 bath counts from the random read's record check.

## Fits for after the sprint

Ben ruled out Modal fits for the rest of the sprint. These wait, each with its predictions
written in its note before launch. `docs/TODO.md` carries the full list with the smaller
candidates from the text flags.

1. c3, the narrowed closing dataset with b9's 6-chain design
   (`docs/notes/closing-asks-2026-11-11.md`). It takes the place of c2.
2. The income flag, on c3's winner's dataset (`docs/notes/income-flag-2026-11-11.md`).
3. No fit for the sprint's ledger entries by themselves. They change about 1,650 of the
   pipeline's 1,985,235 kept ads (about 1,210 of them excluded), join 32 pairs of unit pages
   and move 69 ads off shared unit records, which is negligible under the rule against
   refits for small data changes.
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
8. U1, a unit scale growing with size. The mean already reads a unit's size
   (`unit:log_size_rel` with its flags for imputed and unknown sizes), and the scales read
   none, so the size first goes to the sampler's unit steps through a module of its own.
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
   The new units give a second definition, a level per building for its apartments of 2
   or more bedrooms, which needs no size (79% of the backtest's new units state none).
   The two are fitted apart and the better one kept. Predicted for the bedroom-class
   level: an sd across buildings of 0.03 to 0.06; the pair covariance of the gaps of
   2-or-more-bedroom new units in a backtest falls from 0.0082 to between 0.0055 and
   0.0070, since the building's earlier asks predict a quarter of it where the building
   has a same-count ad; their coverage
   rises by 0.01 to 0.03; elpd on the latest split gains under 150, the held-out units
   there having histories of their own.
10. U2, a Student-t distribution for the unit's lasting level, on U1's winner. It tests
    whether the levels the normal prior gives up are a tail every size has. Predicted: its
    degrees of freedom come out over 8 once U1 is in, and elpd moves by less than 100,
    which would close the candidate.
11. U4, a unit scale by bedroom count: the sd of a unit's lasting level is multiplied by a
    factor for 2 bedrooms and a factor for 3 or more, with 1 for studios and 1-bedrooms.
    It runs ahead of U1, since every row has a count and no dataset column is needed, and
    U1 then tests whether size adds to the count. Predicted: factors of 1.2 to 1.6 for 2
    bedrooms and 1.4 to 2.0 for 3 or more; coverage of 2-or-more-bedroom new units in a
    backtest moves from 0.72 to between 0.76 and 0.80, and of studios and 1-bedrooms by
    less than 0.01; on the latest split, coverage of ads with 3 or more bedrooms rises
    from about 0.75 and elpd gains 100 to 500. No free check stands behind the elpd
    range. The factors are fitted on units with several ads, and the new units' need
    (0.10 to 0.16 against 0.075) includes the gap their building's large units share, so
    a factor at the low end with U3 taking the rest is the likelier outcome.
12. Backtests on two more scoring days (2024-11-10 and 2025-05-10), each a fit of the
    served design with the later rows set aside. The level and coverage of open ads rest
    on the single day of j9. Predicted: the median gap of open ads of units with training
    ads is between -0.003 and +0.006 on both days; new units are covered 0.74 to 0.79;
    new units of 2 or more bedrooms 0.68 to 0.76. A median outside that range would
    reopen the question of a level error on the Deals page.

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
- The served median is 0.47% above the held-out asks. "The level of the held-out gap"
  puts most of that on the split holding out each unit's last ad, with about 0.1 point
  from closing asks in training. Still open: the base of about -0.4% in years when last
  and followed ads differ little (2014 to 2018), the part of regulated apartments with no
  flag, and the level of open ads on more than the single backtest day.
- Coverage is 0.745 for held-out ads of 2020 to 2022 against 0.826 before and after, and
  training rows show the same. The cause is open between asks scattered around each
  apartment's level in those years and apartments moving faster than the fitted drift.
  Net asks typed into the price field are part of 2020 alone (25,230 rows with a
  concession in the text and none recorded) and of the years through 2019.
- Buildings whose new 2-or-more-bedroom units miss together. I read no ad of The Seren or
  the other buildings listed there, so the account of floor plan prices set by the
  office is untested.
- Pages whose previous ad has another bedroom count (307 open ads in n9, covered 0.645).
  The asks fit a recount of the same rooms, and no ad was read.
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
