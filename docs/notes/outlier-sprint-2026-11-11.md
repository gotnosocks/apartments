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
  The gap rises with that deviation, with slopes of 0.17 and 0.10. The model draws each
  unit's lasting level from a normal distribution, which pulls an unusual unit too far back
  to its building. A Student-t unit level would let such units keep more of their own
  history.
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

## What I changed

- **Ledger, PR #1307.** Of the readers' proposals, 46 corrections had independent evidence: 15
  excludes, 15 bedroom sets, 5 bath sets, 3 size sets and 8 ask sets, each backed by another
  ad for the unit, a stated size or a floor plan. I dropped 13 proposals: ask sets with no
  other ad at the new level, excludes resting on ad text alone, and bedroom sets the unit's
  other ads contradict. None of the ask sets turns a net ask gross.
- **Closing asks.** Some of the readers' price typos and placeholders were prices typed on the
  day an ad went off market, and 9,748 of the diagnostics ads (5.0%) take a change dated on or
  after that day. `rentfrontier.b0closing` reprices 104,330 rows at the last ask before
  that day. The 4-chain fit c1 gained 589.5 elpd (SE 107.7) on the unchanged held-out ads
  and missed the gate on the walk's hyperparameters, so the 6-chain refit c2 is queued
  (`docs/notes/closing-asks-2026-11-11.md`).
- **Income flag.** The income-restricted flag missed 9 of the 13 lottery and HPD ads the
  readers found. `rentfrontier.b0income` widens it to 2,590 rows; a Sonnet check of 80 added
  rows found no market ads. Its fit follows c2 (`docs/notes/income-flag-2026-11-11.md`).

## Open leads

- A Student-t unit level, for the units whose own history sits far from their building.
- Wider noise for large units and the top of the price range.
- Unit records shared by two apartments ("different unit", 16 ads). A unit record holding
  asks for a 2BR and a 4BR duplex needs splitting at the source, not a fit term.
- Commercial spaces and rooms get through the pipeline's filters. The ledger now excludes 12 of
  the 13 the readers found, and a text rule could catch the rest.
