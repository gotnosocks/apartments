# Pricing of 5S at 165 Church Street

This folder holds the numbers for a pricing explainer of unit 5S at 165 Church Street in Tribeca.
I took them from the served fit's saved draws. Nothing here started a fit or changed the site.

- `data.json` has the listing history, the term-by-term split, the predictive distributions and
  the monthly path, with thinned draws for histograms.
- `extract.py` rebuilds it (`draws`, then `json`). The `draws` step reads every kept draw in a
  3 GB scope in about 3 minutes.

## The listing

I found a single StreetEasy listing for the unit, 4722434. Its record shows these events:

| date | event | ask |
|---|---|---|
| 2025-04-29 | created, price set | $12,500 |
| 2025-04-30 | active | $12,500 |
| 2025-05-05 | in contract, price raised | $13,500 |
| 2025-05-08 | active again | $13,500 |
| 2025-05-13 | rented (no rented price given) | |

The ad lists 5 bedrooms, 3 full baths, 2,000 sq ft, 9 rooms, the 5th floor, a virtual doorman,
laundry in the building, central air and city views. Its text opens with "No Fee" and offers
no concession. The building went up in 1938 and has 6 stories and 10 apartments. PLUTO codes
it D7, an elevator building, and it lies in the Tribeca South Historic District. The other
units in the building and ten Tribeca comparables are under `raw` in `data.json`.

## The fit

I used the served model, the m7 all-scraped run
(`m7-nocurves-...-unitnu4-all-scraped-v1-rows-e694a775-a40`, summary bundle `-6d3f401`, live
site build `20261019T212735034421Z-edc3d22a`). It covers Tribeca, and 5S's row is among its
training rows. The `latest-ask-v8` rule prices that row at the latest ask, $13,500, and keeps
the listing's first date, 2025-04-30. The run kept 1,000 draws over 2 chains. My rebuilt
fitted rent matches the bundle's to within 0.01% for 5S and for the comparison row.

For the comparison I took the in-fit Manhattan row of April 2025 with the median fitted rent,
out of 6,232 such rows. That turns out to be a one-bedroom at 379 East 10th Street in the East
Village, with a $4,495 ask and a $4,559 fitted rent.

## Terms

The model's log rent is a sum of terms. Each entry in `terms` gives the term for 5S, for the
comparison row and their difference. Each of these comes as the posterior median with 10/90
and 2.5/97.5 percentiles in log points, the matching multipliers, per-chain medians and 200
draws. The terms are sorted by the size of the difference. `columns` splits the feature terms
into their columns, and `market_parts` splits the market term.

| term | what it measures | 5S | vs comparison |
|---|---|---|---|
| market | offset, intercept, market trend and the daily season at the ask date | 8.452 | +0.003 |
| bedrooms | five or more bedrooms against one | +0.598 (x1.82) | +0.598 |
| bathrooms | three full baths against one | +0.271 (x1.31) | +0.271 |
| neighbourhood | Tribeca against Chelsea | +0.232 (x1.26) | +0.368 |
| building_drift | the building's own walk over time, at April 2025 | -0.116, 95% -0.252 to +0.037 | -0.122 |
| building | the building's level against its attributes and neighbourhood | -0.047, 95% -0.189 to +0.074 | -0.056 |
| building status | historic district | +0.040 | +0.031 |
| building size | height, apartment count, space per apartment, lot density | +0.029 | +0.037 |
| building era | built 1930-1959, against 1900-1929 | +0.027 | +0.020 |
| rooms beyond bedrooms | four or more | +0.019 | +0.011 |
| elevator | elevator not stated in the ad | -0.010 | -0.010 |
| floor | log floor | +0.009 | +0.001 |
| description | flags from the ad text (renovated, no fee, high ceilings) | +0.008 | +0.001 |
| bedroom_market_curve | the 3+ bedroom group's own market curve | -0.008 | -0.008 |
| building_feature_slopes | the building's own slopes on size, baths and floor | -0.007, 95% -0.059 to +0.047 | -0.026 |
| unit | the unit's own effect, from its single listing | +0.006, 95% -0.061 to +0.071 | -0.040 |
| relisting | first listing of the unit | +0.004 | +0.001 |
| size | square feet against the bedroom count's median | 0.000 | +0.024 |

The size term is zero for 5S because 2,000 sq ft sits at the training median for its bedroom
group. The comparison row states no size, and its "size unknown" column costs it 2.4%.

The top five terms for 5S, ranked by size, are bedrooms, bathrooms, Tribeca, building drift
and the building level. Against the comparison row, Tribeca moves up to second place
(+0.368), because the East Village sits 0.136 below Chelsea.

For every term the two chain medians differ by less than the term's posterior sd, so no term
shows chain disagreement. The largest spread is in the unit term, about 0.1 sd.

## Predictive distribution of the ask

| | median | 80% | 95% | where $13,500 falls |
|---|---|---|---|---|
| in-sample (5S's own unit draw) | $13,449 | $12,442 to $14,492 | $11,636 to $15,540 | 0.53 |
| new unit (unit level from the prior) | $13,372 | $12,086 to $14,777 | $11,170 to $16,009 | 0.55 |
| PSIS-LOO, from the bundle (site's numbers) | $13,257 | $11,834 to $14,745 | $10,963 to $15,875 | 0.59 |

The noise is Student-t with a scale of 0.033 and 2.2 degrees of freedom. The unit prior has a
scale of 0.037 and 4 degrees of freedom. The leave-out version is the one to quote as an
out-of-sample check, since the in-sample fit has already seen the $13,500.

`monthly_path` prices the same apartment, with its columns held fixed, in each month from
2014. It moves the trend, the bedroom-group curve, the building walk and the season. Its
median comes out at $13,138 in June 2024, $13,406 in April 2025, $13,631 in May 2025 (the month
of the raise), $14,195 in May 2026 and $14,103 in October 2026.

## Caveats

- The $13,500 ask dates from the day the listing went into contract. It may be the agreed rent
  rather than an ask that tested the market. The model dates it to the listing's first day.
- Every five-bedroom unit in the building lists 2,000 to 2,200 sq ft with 9 rooms, about 400
  sq ft per bedroom. The bedroom count drives most of the premium, so a miscoded count would
  move the estimate more than anything else. I found no correction or quarantine entry for the
  building, and I changed no field.
- The ad leaves the elevator unstated, which costs 1%. PLUTO's D7 code says the building has
  one.
- PLUTO lists the lot as 99 Chambers Street with 18 units in all, 10 of them residential.
- A DOB alteration certificate is dated 2025-04-28, a day before the listing went up.
- The building level and drift are the widest terms. With 13 rows in 12 years the building
  has few rows to pin its own level, and together they take about 15% off the price that
  Tribeca and the unit's columns would give. A 95% interval on either term includes zero.
