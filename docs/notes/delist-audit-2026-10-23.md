# Delists and the last ask: results, 2026-10-23

This note reports the delist audit planned in `docs/notes/delist-audit-predictions-2026-10-23.md`, including that note's dated changes made before the run. It answers objection 11 on the research board: a listing's last ask is not a closing price. Fable's direction covers the relist side (`20261023T040052Z-fable-re-objection-11-what-the-within-ad-path`), so this note leaves it out.

I ran `docs/notes/conference-followups-2026-10-22/delist_audit.py` on thelio CPU (199 s, 2.9 GB peak). Its outputs are in `/data1/apartments/tmp/conference-followups/delist/`.

## Coverage

Of the 1,896,471 rows of `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`:

- 1,734,094 (91.4%) carry an observed first ask (`asking_rent` in `observations-aecf9b7724d3208a-v2.parquet`), and 1,694,098 of them in 56,202 buildings enter the regressions;
- 228,146 have a finished ask history in `listing-outcomes`, from the Manhattan crawls;
- 1,888,330 have days on market, taken as `off_day` minus `on_day` from `ads-3775f6d9b3e028ca.parquet`. The file's own `days_on_market` disagrees with those dates on 29% of ads, so I used the dates.

## Ask paths

Ended ads, final against observed first ask, by days on market:

| | all | under 14 | 14 to 30 | 31 to 60 | over 60 |
|---|---|---|---|---|---|
| ads | 1,728,015 | 757,384 | 468,525 | 296,431 | 205,670 |
| median final/first | 1.00 | 1.00 | 1.00 | 1.00 | 0.975 |
| mean log change | -0.93% | +0.17% | -0.42% | -1.94% | -4.66% |
| final below first | 25.3% | 10.5% | 25.7% | 40.7% | 57.0% |

On the `listing-outcomes` histories, 32.6% of listings have at least one cut, and the median cut among them is 4.0%. The share with a cut runs 12.3%, 32.0%, 50.0% and 69.0% across the four bands.

## Premiums on first and last ask

I fit within-building OLS on log first ask and on log last ask for the same ads, with building, month and bath fixed effects. The first-ask fit takes its month from `price_at`, and the last-ask fit from `latest_day`. SEs are clustered by building and by week. Premiums are in percent with 95% intervals.

| term | first ask | last ask | last minus first, log points |
|---|---|---|---|
| bed>=1 | 24.41 (23.98 to 24.85) | 24.42 (23.98 to 24.85) | 0.00 (-0.09 to 0.09) |
| bed>=2 | 21.02 (20.68 to 21.37) | 20.92 (20.57 to 21.26) | -0.09 (-0.20 to 0.03) |
| bed>=3 | 18.57 (18.13 to 19.01) | 18.53 (18.09 to 18.97) | -0.03 (-0.22 to 0.16) |
| bed>=4 | 12.90 (12.29 to 13.53) | 12.94 (12.33 to 13.55) | 0.03 (-0.13 to 0.19) |
| bed>=5 | 10.17 (8.90 to 11.45) | 10.27 (9.03 to 11.53) | 0.10 (-0.17 to 0.36) |
| floor, per floor | 0.27 (0.25 to 0.30) | 0.27 (0.24 to 0.30) | 0.00 (-0.01 to 0.00) |
| in-unit laundry | 6.65 (6.30 to 7.01) | 6.63 (6.28 to 6.99) | -0.02 (-0.15 to 0.11) |
| dishwasher | 2.31 (2.14 to 2.47) | 2.21 (2.04 to 2.38) | -0.09 (-0.17 to -0.02) |
| doorman, full | -0.27 (-0.72 to 0.18) | -0.33 (-0.81 to 0.15) | -0.06 (-0.23 to 0.11) |
| doorman, part | 0.20 (-0.62 to 1.03) | 0.14 (-0.69 to 0.97) | -0.06 (-0.41 to 0.28) |
| doorman, virtual | 0.48 (0.28 to 0.69) | 0.71 (0.50 to 0.91) | 0.22 (0.11 to 0.34) |
| rent stabilized | -3.22 (-3.71 to -2.73) | -3.24 (-3.76 to -2.71) | -0.01 (-0.18 to 0.15) |

The bedroom steps can't sit beside bedroom-by-bath fixed effects, so this table uses bath fixed effects. A second fit with bedroom-by-bath effects moves the other terms by 0.02 points or less. The building fixed effect absorbs a building's doorman type, so the doorman rows here measure only changes in an ad's doorman label within a building and aren't comparable with the model's doorman premiums.

## Against the predictions

- Half or more of units have a single listing: 54.7%. Hit.
- Median final/first ask of 1.00, 30% to 50% of listings with a cut, median cut of 3% to 7%: 1.00, 32.6% and 4.0%. Hit.
- Cut share under 20% for fast listings and over 60% past 60 days: 12.3% and 69.0%. Hit.
- Every premium differs by under 0.5 points between targets: the largest gap is 0.23 points, on virtual doorman. Hit.
- Every ratio of coefficients between 0.9 and 1.1: miss for the three doorman terms (0.68 to 1.46). Their within-building premiums sit under 1%, so a ratio says little there, but I record it as a miss. The other terms fall between 0.959 and 1.01.
- The stabilized flag as the term most sensitive to the target: miss. Its two coefficients differ by 0.01 points.
- The relist predictions and the step 4 reruns weren't scored, as the dated changes in the predictions note explain.

## Reading

The choice between first and last ask moves none of the paper's unit premiums by as much as a quarter point. The target changes the level of rents: the last ask sits 0.9% below the first ask on average and 4.7% below it after two months on market. It barely changes the differences between units. A last ask still overstates the clearing rent when an ad opened too high, since Fable's instrument finds the market takes back only about a quarter of an opening overshoot (`20261023T040028Z-fable-results-reaction-slope-survives-an-instr`). That bears on predicted rent levels and their intervals more than on the premiums. It belongs in the paper's limits section.

Data checks for the pipeline: on finished `listing-outcomes` rows, the model's `latest_ask` equals the outcome's final ask on 90.5% of rows, and the observed first ask equals its first ask on 90.9%. The ads file's `days_on_market` disagrees with its own `on_day` and `off_day` on 29% of ads. I'll pass both to the data threads.
