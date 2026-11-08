# Pricing of #2 at 704 Degraw Street

This folder holds the numbers for a pricing explainer of unit #2 at 704 Degraw Street in Park
Slope, Brooklyn. StreetEasy spells the street "De Graw". I took every number from the served
fit's saved draws. Nothing here started a fit or changed the site.

- `data.json` has the listing history, the term-by-term split, the predictive distributions,
  the monthly path and the comparables, with thinned draws for histograms.
- `extract.py` rebuilds it (`draws`, then `json`). The `draws` step reads every kept draw in a
  3 GB scope.
- `page/` holds the explainer's source. `python3 page/build.py data.json` writes
  `explainer.html`.

## The listings

The archive holds five StreetEasy listings for the unit
(`unit:ac77b9bf-4ce8-53e4-be11-544241fc8783`). I also ran a top-up scrape of the Prospect Park
area (run-0018, about $0.02 of OxyLabs credit). It found nothing new for the unit.

| listing | live | asks | status | in the fit | model median | percentile |
|---|---|---|---|---|---|---|
| 2866025 | 2019-09-10 to 10-02 | $3,850 | rented | yes (PSIS-LOO) | $3,150 | 97th |
| 3139150 | 2020-07-24 to 10-01 | $3,850, cut five times to $2,790 | rented | yes (PSIS-LOO) | $3,554 | 2nd |
| 4217824 | 2023-08-22 to 09-24 | $4,500 | no longer available | yes (PSIS-LOO) | $4,189 | 68th |
| 4327072 | 2024-01-18 to 03-06 | $4,500 | rented | held out | $4,370 | 68th |
| 5061442 | 2026-06-11 to 06-16 | $4,700 | rented 07-01 | held out | $5,231 | 15th |

Every ad lists 2 bedrooms, 1 bath and 4 rooms, with no size and no floor plan. The ad text puts
the unit on the 2nd floor, but the coded floor is unresolved. Keller Williams Realty Empire
listed the 2026 ad with a $20 application fee, a $4,700 deposit and no concession. PLUTO has the
building (BBL 3009490035) as class C0, built 1901, 3 floors, 3 apartments and 2,700 residential
sq ft.

## The fit

The served run is
`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-slopemin3-unitnu4-all-scraped-v1-rows-e694a775-a40`,
with 1,000 kept draws over 2 chains. I used it because it is the served model and it covers the
row: the unit and its building both have their own draws. The run holds out a random 11% of rows
(seed 20260922), so the June 2026 ad and the 2024 ad are held out while the 2019, 2020 and 2023
ads trained it. The run's convergence gate did not pass (largest group R-hat 1.095 on the unit
effects), which was already true of the served model.

My rebuild of the fitted rent from the draws matches the published bundle to within 0.1%.

## The price

| | median | 80% | 95% | ask percentile |
|---|---|---|---|---|
| fitted rent | $5,231 | | $4,343 to $6,243 | |
| one ad, own unit | $5,232 | $4,576 to $5,968 | $4,214 to $6,456 | 15th |
| bundle's held-out interval | $5,231 | $4,574 to $5,968 | $4,212 to $6,460 | 15th |
| one ad, new unit | $5,164 | $4,380 to $6,083 | $3,961 to $6,680 | 22nd |

The ask of $4,700 sits inside the 80% range, toward its low end.

## Term by term

Log points add up to the log rent. The typical row is the median row outside Manhattan in June
2026 whose building and unit both have draws: a 3-bed, 2-bath at 762 Madison Street in
Stuyvesant Heights, asking $4,200 and fitted at $4,152.

| term | #2 | 95% | typical row | difference |
|---|---|---|---|---|
| market, June 2026 | 8.527 ($5,049) |  | 8.528 | -0.001 |
| neighbourhood (Park Slope) | -0.288 |  | -0.595 | +0.307 |
| bedrooms (2) | +0.179 |  | +0.330 | -0.151 |
| building's own walk | +0.146 | -0.106 to +0.410 | -0.032 | +0.182 |
| building class (C0) | -0.053 |  | -0.053 | 0 |
| building's own level | +0.036 | -0.115 to +0.187 | +0.028 | +0.013 |
| size not stated | -0.024 |  | -0.024 | 0 |
| building's own slopes | +0.014 | -0.079 to +0.116 | -0.066 | +0.083 |
| unit's own effect | +0.010 | -0.076 to +0.127 | +0.006 | +0.006 |
| bathrooms (1) | 0 |  | +0.158 | -0.158 |
| built 1901 | 0 |  | +0.027 | -0.027 |
| no outdoor space | 0 |  | +0.023 | -0.023 |

The remaining terms (elevator, building status, laundry, floor, ad text, building size, bedroom
curve, views, air, relisting) are each under 0.01 for #2. The full table, with every term's typical
value and difference, is in `data.json` and on the page. Term medians add to 8.554; the median
of the total is 8.562.

The building's level, walk and slopes together add +0.203 (95% +0.023 to +0.40). The model learned
them from #2's three training ads, the only rows it has for the building. They account for most
of the gap between the model's $5,231 and the $4,500 median ask of nearby walk-ups.

The two chains agree on every term. The largest gap between chain medians is 0.18 of a posterior
sd (building size); for the total it is 0.07.

## The monthly path

The own-unit median for June of each year: $3,147 (2014), $3,721 (2019), $3,481 (2020), $4,470
(2023), $4,633 (2024), $4,938 (2025), $5,231 (2026), and $5,152 in October 2026. The ask rose 4%
from January 2024 to June 2026, while the model's market trend rose 0.13 log points (14%).

## Comparables

I took 2-bed, 1-bath units in buildings built before 1940 with 5 floors or fewer, within half a
mile, priced since June 2025, keeping the latest ask per unit. That gives 443 units with a median
ask of $4,400 (quartiles $3,995 and $5,000). The 109 priced May to July 2026 had a median of
$4,500. StreetEasy's own page for the area shows a 2-bed median of $5,300 over 151 listings, a
pool with no filter on age or bath count.

| unit | priced | ask | sq ft | miles |
|---|---|---|---|---|
| 710 De Graw Street #1 | 2026-06-25 | $6,800 |  | 0.01 |
| 710 De Graw Street #1GF | 2026-07-16 | $6,250 |  | 0.01 |
| 679 De Graw Street #2 | 2026-06-12 | $4,900 | 950 | 0.03 |
| 705 Sackett Street #2 | 2025-08-30 | $3,600 |  | 0.03 |
| 168 5th Avenue #2C | 2026-05-14 | $4,295 |  | 0.04 |
| 168 5th Avenue #2B | 2026-07-14 | $4,195 |  | 0.04 |
| 168 5th Avenue #4D | 2025-12-20 | $3,995 |  | 0.04 |
| 684 De Graw Street #1 | 2026-07-15 | $6,000 | 1800 | 0.04 |
| 685 Sackett Street #2 | 2025-10-28 | $5,500 | 1000 | 0.04 |
| 158 5th Avenue #4L | 2026-06-04 | $4,799 | 1200 | 0.05 |

The full list of the nearest 16, with dates, distances and the model's estimates, is under
`raw.comps` in `data.json`.

## Caveats

- No ad states a size, so the size-unknown column applies (-2.4%). PLUTO's 2,700 sq ft over
  three apartments suggests about 900 sq ft each. I changed no coded field.
- The coded floor is unresolved even though every ad says 2nd floor. Coding it would move the
  price by about a percent, and ad text alone does not back a correction under the project's
  rules.
- The 2020 ad's last ask of $2,790 fell below the 2nd percentile. That row pulls the unit's own
  effect down, and the building terms carry the rest of the unit's level.
- The ad left the market five days after it went live. That fits an ask at or below what the
  unit could fetch.
- The weekly `apartments-streeteasy-topup.service` has been stopped since a SIGTERM on Oct 17.
