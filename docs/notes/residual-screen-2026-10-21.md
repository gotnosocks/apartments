# Residual screen against fields the model leaves out, 2026-10-21

Ben asked whether fields we already have, such as the identity labels, line up with the model's
error. I took the frontage run (`building-zones-front-b0-latest-9652d249-dense-w650`, see
`building-zones-front-2026-10-21.md`) and its 1,706,837 training rows on the latest split, and
for each row I rebuilt the posterior median of every part of the mean from the saved draws.
The target is

    T = log ask - (walk + season + unit steps + flags + zone level + x' gamma)
      = error + building effect + map value, demeaned within each zone

so `T` holds everything the model leaves to location and to the building, plus the error. Its
variance is 0.0625 (0.0666 in Manhattan, 0.0569 in Brooklyn + Queens). Each `x' gamma` term the
model already has (elevator, condo, doorman, roof height, frontage bands, corner) is taken out
first, so a field shows up here only for what it adds beyond those terms.

Nothing in this note changes a model or runs a fit. The scripts are in
`residual-screen-2026-10-21/`, and the field tables, level means and joint coefficients are on the
data page at https://claude.ai/artifact/18EAWB1h8yYdZPvtGsTHod.

## How I scored a field

For each field I cut its values into levels (bands for numbers, at most 40 levels, any level with
fewer than 200 ads lumped into "(other)") and regressed `T` on the level dummies. The score is
the adjusted R², the share of `T`'s variance the field explains. I computed it for
- every ad, then Manhattan and Brooklyn + Queens alone;
- every ad within its 500 m grid cell, then within its tax block, by demeaning `T` and the dummies
  in each cell. A field that only tracks where a building stands drops toward zero here, and one
  renters pay for keeps its share;
- every building, on the mean of `T` over its ads, weighted by ads, with the building's most
  common level.

The fields came from five sources:
1. the pipeline's ad and unit tables: unit label, floor parse, stated size, laundry, doorman,
   HVAC, pets, views, windows, lease term, months free, the identity and relabel fields;
2. each ad's latest raw StreetEasy record: listing source and broker, StreetEasy's amenity,
   feature and outdoor codes, photo, plan and video counts, description length;
3. regular expressions on the ad description: renovated, luxury, quiet, noise, views and so on;
4. MapPLUTO and LPC: year built, year altered, building class, historic district, landmark,
   residential units, built FAR;
5. the frontage table and the street network: width and corner, the avenue a building faces,
   NYC DOT truck routes (local or through) and the travel lanes of the widest street faced.

## Identity labels

The identity fields explain nothing. `identity_reasons`, `exclusion_reasons`, `fate` and
`label_fate` have a single value on every training row, because the pipeline drops flagged rows
before the model sees them. A unit whose relist, label or split unit differs from its own label
explains 0.03% of `T` or less, and so does the number of records per ad. I found no sign that
the identity rules leave mislabelled units in a way the error picks up.

## Fields alone

70 of the 122 fields explain more than 0.5% of `T` across all ads, and 60 still do within a tax
block. Ranked by the all-ads share, with the within-block share alongside:

| field | all ads | Manhattan | BK+Q | within 500 m | within tax block | buildings |
|---|---|---|---|---|---|---|
| size against the bedroom median | 13.4% | 17.6% | 7.6% | 13.1% | 11.1% | 14.2% |
| laundry type | 11.3% | 12.2% | 10.5% | 10.7% | 9.2% | 14.6% |
| washer/dryer (StreetEasy feature) | 10.4% | 10.9% | 9.9% | 9.6% | 8.4% | 13.8% |
| floor plans attached | 7.9% | 8.1% | 9.0% | 5.2% | 3.2% | 11.4% |
| description length | 7.2% | 6.0% | 9.4% | 4.8% | 3.9% | 11.0% |
| listing source | 6.1% | 6.3% | 7.7% | 3.8% | 2.7% | 8.6% |
| gym | 6.1% | 6.9% | 5.0% | 5.2% | 3.1% | 7.9% |
| year built | 5.7% | 8.9% | 3.8% | 3.1% | 1.9% | 7.6% |
| dishwasher | 5.6% | 5.5% | 5.7% | 5.0% | 4.2% | 9.3% |
| building class | 5.5% | 6.1% | 6.7% | 3.1% | 1.8% | 7.3% |
| broker | 5.2% | 4.9% | 8.1% | 3.2% | 2.2% | 8.0% |
| building floor count | 5.1% | 5.8% | 8.2% | 4.9% | 3.1% | 6.8% |
| storage space | 4.8% | 5.1% | 4.5% | 2.9% | 1.7% | 6.9% |
| concierge | 4.7% | 5.6% | 3.9% | 3.2% | 1.7% | 6.5% |
| floor band | 4.1% | 4.7% | 5.1% | 3.5% | 2.1% | 5.1% |
| doorman type (listing) | 3.7% | 5.4% | 2.5% | 2.9% | 1.6% | 5.3% |
| frontage width and corner | 3.6% | 3.9% | 3.6% | 2.5% | 1.5% | 4.8% |
| unit label type | 2.7% | 2.8% | 2.9% | 2.2% | 1.9% | 2.6% |
| historic district | 2.8% | 2.8% | 2.8% | 0.2% | 0.1% | 3.7% |
| travel lanes, widest faced | 1.4% | 1.7% | 2.0% | 1.2% | 0.9% | 1.9% |
| truck route faced | 1.0% | 0.8% | 1.5% | 0.2% | 0.2% | 1.3% |
| "quiet" in the text | 0.0% | 0.2% | 0.2% | 0.1% | 0.1% | 0.1% |
| "noise" or "traffic" in the text | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

The data page has all 122 rows.

Size leads, and the model has no size term. I measured it as the log of the stated square feet
less the median for the ad's bedroom count, and only 26% of ads state a size. Against the ads with
no size, an apartment 22% to 49% above its bedroom median sits 23% above the model, and one more
than 49% above sits 64% above it. The bed and bath steps take out the average size of a 2-bed,
and the size spread within a bed count goes to the building effect and the error.

In-unit laundry sits 13.6% above the model and in-building laundry 2.9% below it, against 7.4%
below for ads that give no laundry. A dishwasher and private outdoor space follow
the same pattern at a smaller size. They are unit features, which the building effect cannot
carry when units in one building differ.

Floor plans, description length, photo counts and the broker describe how the ad is presented.
They track the same quality the physical fields measure, and they lose more of their share within
a tax block than the unit features do.

Historic district and truck routes are location proxies: 2.8% and 1.0% across all ads, 0.1% and
0.2% within a tax block.

## Joint OLS

I fit every field together on 600,000 ads drawn at random, once with every field and once with
only the apartment and building fields (the listing source, broker, media counts, description
length, fees, lease and concessions left out). I dropped the floor status and floor-by-elevator
fields, which duplicate the floor bands, and the StreetEasy "any outdoor" and "any view" flags,
which duplicate their codes.

| fields | all ads | Manhattan | BK+Q | within 500 m | within tax block |
|---|---|---|---|---|---|
| apartment and building | 39.1% | 47.1% | 36.1% | 36.7% | 31.0% |
| every field | 42.7% | 50.9% | 39.5% | 39.9% | 33.9% |

The apartment and building fields explain 31% of what is left within a tax block, where the map
value is nearly constant. The ad presentation fields add 3 to 4 points over them.

The largest coefficients of the apartment and building fit, in log points, each against its
field's most common level:

| term | all ads | within tax block | ads |
|---|---|---|---|
| size more than 49% over the bedroom median (against no size stated) | +39.9 | +31.6 | 12,988 |
| size 22% to 49% over | +17.0 | +14.1 | 19,344 |
| size 11% to 22% over | +8.3 | +7.0 | 19,584 |
| in-unit laundry (against in-building) | +10.0 | +7.4 | 173,980 |
| penthouse label | +11.7 | +11.3 | 7,733 |
| doorman full-time, from the listing (against not stated) | -11.8 | -9.2 | 88,702 |
| more than 300 residential units (against 6 to 10) | -9.6 | -9.7 | 74,087 |
| building class R, condo (against C, walk-up) | -8.3 | -9.6 | 91,922 |
| historic district | +11.7 | +2.6 | 84,010 |
| corner on a 61 to 80 ft street (against mid-block, 40 ft or less) | +9.7 | +6.8 | 47,572 |
| fireplace | +6.2 | +4.2 | 27,069 |
| no dishwasher | -4.5 | -3.0 | 270,900 |
| children's playroom | +6.1 | +3.0 | 71,972 |
| 4 travel lanes faced (against 1) | -8.8 | -0.2 | 89,227 |
| 5 or more travel lanes faced | -11.5 | -0.5 | 35,495 |
| truck route, through (against none) | +5.5 | -3.2 | 25,327 |
| truck route, local | +3.8 | -0.4 | 145,012 |

The doorman, condo and large-building terms come out negative because the model already gives
doorman buildings +20% and condos +15%. Once the joint fit has the gym, concierge, size and
laundry, it takes part of that credit back.

## Streets and noise

Through truck routes are the one street measure here with a within-block sign matching Ben's
prior: a building on a through route rents 3.2% below its tax block (25,327 ads). Facing 4 or
more travel lanes costs 9 to 12 log points across the city and under 2 within a 500 m
cell, so wide roads run through cheaper parts of the map without a price of their own within a
block.

Corners stay positive within a tax block after the frontage run's corner term, by 2% to 11% per
ad depending on the width faced. Per building, with each building counted once, the corner terms
within a block fall to between -0.4% and +2.7%, apart from corners on streets over 80 ft at
+5.4%. Corner buildings carry a median of 9 training ads against 6 for the others, so the
per-ad premium comes from large corner buildings with many ads, and the model, which fits its
corner term across buildings, finds almost none. "Quiet" appears in 8% of ads and explains nothing,
and "noise" or "traffic" appears in 0.2% of ads.

## Next steps

The data change with the clearest payoff is a size term: stated square feet against the
bedroom median, with a flag for no size, which needs the 74% of ads with no size handled through
the floor plans and the unit lines. In-unit laundry and dishwasher come next as unit columns.
Both wait on Ben's fit hold.
