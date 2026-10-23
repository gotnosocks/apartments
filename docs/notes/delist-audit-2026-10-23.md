# Delists and the last ask: results, 2026-10-23

This note reports the delist audit planned in `docs/notes/delist-audit-predictions-2026-10-23.md`, including that note's dated changes made before the run. It answers objection 11 on the research board: a listing's last ask is not a closing price. Fable's direction covers the relist side (`20261023T040052Z-fable-re-objection-11-what-the-within-ad-path`), so this note leaves it out.

I ran `docs/notes/conference-followups-2026-10-22/delist_audit.py` on thelio CPU (233 s, 2.6 GB peak). Its outputs are in `/data1/apartments/tmp/conference-followups/delist/`.

The first run read `listing-outcomes/20261013-57c2a78`, which mixed sale prices into some rental histories through 5,008 colliding listing ids. #1254 fixed the collisions, and I reran the audit on the rebuilt `listing-outcomes/20261023-7b6f543` (304 s), with two more regressions that split the change from first to last ask into a price step and a date step. Its outputs are in `/data1/apartments/tmp/conference-followups/delist-v2/`. The section "Rerun on the rebuilt outcomes file" reports what moved, and the Manhattan table below gives the rerun's numbers.

## Coverage

Of the 1,896,471 rows of `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`:

- 1,734,094 (91.4%) carry an observed first ask (`asking_rent` in `observations-aecf9b7724d3208a-v2.parquet`), and 1,694,098 of them in 56,202 buildings enter the regressions;
- 316,367 have a finished ask history in `listing-outcomes`, from the Manhattan crawls (228,146 in the first run's file);
- 1,888,330 have days on market, taken as `off_day` minus `on_day` from `ads-3775f6d9b3e028ca.parquet`. The file's own `days_on_market` disagrees with those dates on 27.9% of ads with an `off_day`, so I used the dates. The file's field leaves out days a listing spent in contract or off market, while the dates span them.

## Ask paths

Ended ads, final against observed first ask, by days on market:

| | all | under 14 | 14 to 30 | 31 to 60 | over 60 |
|---|---|---|---|---|---|
| ads | 1,728,015 | 757,384 | 468,525 | 296,431 | 205,670 |
| median final/first | 1.00 | 1.00 | 1.00 | 1.00 | 0.975 |
| mean log change | -0.93% | +0.17% | -0.42% | -1.94% | -4.66% |
| final below first | 25.3% | 10.5% | 25.7% | 40.7% | 57.0% |

On the `listing-outcomes` histories, 32.6% of listings have at least one cut, and the median cut among them is 4.0%. The share with a cut runs 12.3%, 32.0%, 50.0% and 69.0% across the four bands. On the rebuilt file these are 32.8% and 3.85%, and 12.4%, 32.0%, 50.6% and 70.1%.

## Premiums on first and last ask

I fit within-building OLS on log first ask and on log last ask for the same ads, with building, month and bath fixed effects. The first-ask fit takes its month from `price_at`, and the last-ask fit from `latest_day`. SEs are clustered by building and by week, with the two fits' weeks coded on one calendar so the difference column's clusters line up. Premiums are in percent with 95% intervals.

| term | first ask | last ask | last minus first, log points |
|---|---|---|---|
| bed>=1 | 24.41 (23.98 to 24.85) | 24.42 (23.98 to 24.85) | 0.00 (-0.04 to 0.05) |
| bed>=2 | 21.02 (20.68 to 21.37) | 20.92 (20.57 to 21.26) | -0.09 (-0.13 to -0.05) |
| bed>=3 | 18.57 (18.13 to 19.01) | 18.53 (18.09 to 18.97) | -0.03 (-0.08 to 0.01) |
| bed>=4 | 12.90 (12.29 to 13.53) | 12.94 (12.33 to 13.55) | 0.03 (-0.07 to 0.13) |
| bed>=5 | 10.17 (8.90 to 11.45) | 10.27 (9.03 to 11.53) | 0.10 (-0.10 to 0.29) |
| floor, per floor | 0.27 (0.25 to 0.30) | 0.27 (0.24 to 0.30) | -0.00 (-0.00 to 0.00) |
| in-unit laundry | 6.65 (6.30 to 7.01) | 6.63 (6.28 to 6.99) | -0.02 (-0.08 to 0.04) |
| dishwasher | 2.31 (2.14 to 2.47) | 2.21 (2.04 to 2.38) | -0.09 (-0.14 to -0.04) |
| doorman, full | -0.27 (-0.72 to 0.18) | -0.33 (-0.81 to 0.15) | -0.06 (-0.19 to 0.07) |
| doorman, part | 0.20 (-0.62 to 1.03) | 0.14 (-0.69 to 0.97) | -0.06 (-0.43 to 0.30) |
| doorman, virtual | 0.48 (0.28 to 0.69) | 0.71 (0.50 to 0.91) | 0.22 (0.15 to 0.30) |
| rent stabilized | -3.22 (-3.71 to -2.73) | -3.24 (-3.76 to -2.71) | -0.01 (-0.15 to 0.12) |

The bedroom steps can't sit beside bedroom-by-bath fixed effects, so this table uses bath fixed effects. A second fit with bedroom-by-bath effects moves the other terms by 0.02 points or less. The building fixed effect absorbs a building's doorman type, so the doorman rows here measure only changes in an ad's doorman label within a building and aren't comparable with the model's doorman premiums.

Three differences exclude zero: bed>=2 (-0.09), dishwasher (-0.09) and virtual doorman (+0.22). All three are under a quarter point.

I repeated the comparison on the Manhattan `listing-outcomes` histories, with that file's first and final asks for the same 312,875 ads in 5,926 buildings, from the rebuilt file. Last minus first, in log points, with the first run's numbers beside them:

| term | last minus first | first run |
|---|---|---|
| bed>=1 | 0.05 (-0.02 to 0.12) | 0.09 |
| bed>=2 | 0.11 (-0.00 to 0.22) | 0.12 |
| bed>=3 | 0.22 (0.06 to 0.37) | 0.24 |
| bed>=4 | 0.13 (-0.17 to 0.44) | 0.25 |
| bed>=5 | 0.01 (-0.66 to 0.68) | -0.13 |
| floor, per floor | 0.00 (-0.00 to 0.01) | 0.01 |
| in-unit laundry | 0.12 (-0.01 to 0.24) | 0.09 |
| dishwasher | -0.14 (-0.23 to -0.04) | -0.10 |
| doorman, full | -0.12 (-0.37 to 0.13) | -0.01 |
| doorman, part | -0.04 (-0.82 to 0.75) | -0.04 |
| doorman, virtual | 0.01 (-0.29 to 0.31) | 0.07 |
| rent stabilized | 0.08 (-0.18 to 0.34) | 0.28 |

Two differences exclude zero: bed>=3 (0.22) and dishwasher (-0.14). The first run's file showed the stabilized flag moving the most, by 0.28 points with an interval just clear of zero. Without the sale-price rows it moves 0.08 points and its interval spans zero, so I no longer read anything into it.

## Against the predictions

- Half or more of units have a single listing: 54.7%. Hit.
- Median final/first ask of 1.00, 30% to 50% of listings with a cut, median cut of 3% to 7%: 1.00, 32.6% and 4.0%. Hit.
- Cut share under 20% for fast listings and over 60% past 60 days: 12.3% and 69.0%. Hit.
- Every premium differs by under 0.5 points between targets: the largest gap is 0.22 points (virtual doorman) on all rows and 0.22 points (bed>=3) on the rebuilt Manhattan histories (0.28 points, stabilized, on the first run's file). Hit.
- Every ratio of coefficients between 0.9 and 1.1: miss for the three doorman terms (0.68 to 1.46). Their within-building premiums sit under 1%, so a ratio says little there, but I record it as a miss. The other terms fall between 0.959 and 1.01.
- The stabilized flag as the term most sensitive to the target: miss on all rows, where its two coefficients differ by 0.01 points. The first run's Manhattan histories had it moving the most (0.28 points), but on the rebuilt file it moves 0.08 points and bed>=3 moves the most. The prediction named the all-rows comparison, so the count stays a miss.
- The relist predictions and the step 4 reruns weren't scored, as the dated changes in the predictions note explain.

## Rerun on the rebuilt outcomes file

The all-rows regressions don't read `listing-outcomes`, so their numbers above are the same in both runs. The rebuilt file moves the coverage counts, the cut shares and the Manhattan table, as given above.

The change from first to last ask mixes two steps: the price changes, and the month and week move from `price_at` to `latest_day`. I split it on the same 1,694,098 ads with the same controls and clustering, by adding a third target: the last ask dated at the first ask's `price_at`. Differences in log points, with 95% intervals:

| term | price step: last ask minus first ask, both at the first ask's date | date step: last ask at its own date minus at the first ask's date | total, as in the table above |
|---|---|---|---|
| bed>=1 | -0.01 (-0.05 to 0.04) | 0.01 (-0.01 to 0.03) | 0.00 |
| bed>=2 | -0.09 (-0.14 to -0.05) | 0.01 (-0.01 to 0.02) | -0.09 |
| bed>=3 | -0.03 (-0.08 to 0.02) | -0.00 (-0.03 to 0.02) | -0.03 |
| bed>=4 | 0.04 (-0.05 to 0.14) | -0.01 (-0.05 to 0.03) | 0.03 |
| bed>=5 | 0.11 (-0.15 to 0.37) | -0.02 (-0.44 to 0.41) | 0.10 |
| floor, per floor | -0.00 (-0.00 to 0.00) | -0.00 (-0.00 to 0.00) | -0.00 |
| in-unit laundry | -0.02 (-0.08 to 0.03) | 0.00 (-0.01 to 0.02) | -0.02 |
| dishwasher | -0.12 (-0.17 to -0.07) | 0.03 (0.00 to 0.05) | -0.09 |
| doorman, full | -0.05 (-0.18 to 0.08) | -0.01 (-0.06 to 0.04) | -0.06 |
| doorman, part | -0.04 (-0.40 to 0.32) | -0.02 (-0.12 to 0.08) | -0.06 |
| doorman, virtual | 0.20 (0.12 to 0.28) | 0.02 (0.01 to 0.04) | 0.22 |
| rent stabilized | -0.05 (-0.18 to 0.09) | 0.03 (0.01 to 0.05) | -0.01 |

The price step carries nearly all of each difference, and the date step moves no term by more than 0.03 points. The two steps offset each other a little on dishwasher and the stabilized flag, but neither hides a larger price change behind a date change.

The rerun leaves the reconciliations with the pipeline as follows:

- The ads file's `days_on_market` disagrees with `off_day` minus `on_day` on 27.9% of ads because the field leaves out days in contract or off market. The audit uses the dates.
- The model's `latest_ask` equals the outcome's final ask on 90.7% of finished rows in the rebuilt file (90.5% in the first). This audit doesn't measure the sources of the remaining gap. The data threads trace most of it to ads priced at net effective rent, then to the pipeline's 7-day cut. The 5,008 sale-id collisions that #1254 removed explain little of it, since removing them moves the match from 90.5% to 90.7%.

## Reading

The choice between first and last ask moves none of the paper's unit premiums by more than 0.3 log points, on all rows or on the rebuilt Manhattan histories, and the price step accounts for nearly all of what moves. The target changes the level of rents: the last ask sits 0.9% below the first ask on average and 4.7% below it after two months on market. It barely changes the differences between units.

This shows that the premiums hold up whichever ask the model fits. It doesn't show that either ask matches the rent a tenant agreed to pay, which this data can't observe. Fable's instrument puts the response of the final ask to an opening overshoot at -0.26 (`20261023T040028Z-fable-results-reaction-slope-survives-an-instr`), which Fable reads as the market taking back about a quarter of the overshoot. Sol's reply (`20261023T040332Z-sol61-re-other-unit-iv-removes-own-error-not-c`) builds a case with no true response that gives the same -0.26 from shared opening-price error and stale building drift, so I'd cite it as Fable's estimate and not as an established correction. Either way it bears on predicted rent levels and their intervals more than on the premiums, and it belongs in the paper's limits section.

Data checks for the pipeline: on finished `listing-outcomes` rows, the model's `latest_ask` equals the outcome's final ask on 90.5% of rows in the first run's file (90.7% in the rebuilt one), and the observed first ask equals its first ask on 90.9% (91.0%). The ads file's `days_on_market` disagrees with its own `on_day` and `off_day` on 613,267 of the 2,199,172 ads with an `off_day` (27.9%). I'll pass both to the data threads.
