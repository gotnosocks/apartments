# New buildings per row, with clustered SEs (2026-10-13)

This is action 1 of the 2026-10-13 next actions. It extends the new-building score
(`docs/model/newbuilding-2026-10-13.md`) and needs no refit: every number comes from fits whose
draws are already on thelio. All of it cost $0.

## What I changed

- `python -m rentfrontier.newbuilding` now writes `rows.parquet` beside `result.json`. For each
  training row and rung it holds the audit id, building, lot (BBL), walk knot, listing year,
  building-rows bin, PLUTO class, residential units and their tercile, whether the size is stated,
  the log ask `y`, the predictive median, the fitted building part, the PIT and the log predictive
  density. `y`, the median and the building part are on the model's log scale, so median minus `y`
  is the log miss. The lpd is the log of the draw mean of the Student-t densities.
- `result.json` adds every row group split by listing year (2010-13, 2014-16, 2017-19, 2020-21,
  2022-23, 2024-26), and `building_weighted`: the miss, the coverage and the summed lpd with each
  building counted once, each with a standard error from 1,000 bootstrap resamples of tax lots.
- `--walk-origin first` starts a new building's walk at its own first knot. `--drop-group G` leaves
  feature group G's term out of the mean. Both are diagnostics, and their output directories carry
  a tag (`-walkfirst`, `-drop<G>`) and a `diagnostic` block, so they stay off the board.
- `python -m rentfrontier.clusterse` reports SEs clustered by building and by tax lot beside the
  iid SE: for paired PSIS-LOO (`loo`), for paired new-building lpd from two `rows.parquet` files
  (`rows`), for coverage strata (`strata`), and for the label term's variance (`labels`). New
  PSIS-LOO records carry `elpd_loo_se_building` and `elpd_loo_se_lot` (the lot SE is null on a
  remote fit with no lot registry). All of this is report-only: the board's tie tolerance still
  uses the iid SE.

Outputs:

- C's per-row file, which action 2 reads:
  `/data1/apartments/frontier/newbuilding/m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-nb8-nostuy-v1-rows-5c1e5c7e-a100-4500k9cb1-nb8-ul15r1s4q12ad3-45006f5/rows.parquet`
- the other rescores, beside it with the same `-45006f5` suffix;
- the clustered-SE records, in `/data1/apartments/frontier/clusterse/`.

## Predictions, written before running

| Quantity | Predicted (interval) | Result | Hit or miss |
|---|---|---|---|
| C reproduces miss and 80/95 coverage | 11.9%, 90.7/98.1 within 0.05 pp / 0.3 | 11.89% (was 11.90%), 90.69/98.16 (was 90.70/98.13) | hit |
| 80% coverage gap, 2024-26 minus 2014-16 rows, within row bins | +4 to +5 pp (0 to +10) | +5.2 pp | inside the interval, just over the central range |
| Overall 80% coverage with the first-knot walk origin | 86-88.5 (82-90.5) | 88.9 | inside the interval, just over the central range |
| Clustered/iid SE ratio, building-level pairs | 1.4-1.5 (1.05-3.0) | 1.43-1.60 by building, 1.44-1.70 by lot, leaving out areatime (1.83 and 4.02) | inside the interval; the central range catches only lines |
| C-era serving verdicts changed by clustered SEs | 0 (0-1, only bigbed can flip) | 1, and it is lines, not bigbed | miss |
| Paired building-weighted new-building lpd, lines minus C | +3 to +8 nats, lot SE 6-7 (3-13), a tie | +83.9 nats, lot SE 14.4 | miss |
| New-building miss over the area with labels removed | 13.0-13.4% | 13.75% | miss |
| Descriptive share and new-unit coverage | 26.1%, 67/89 unchanged | unchanged | hit (no refit recomputes them) |

Miss criteria set in advance:

- A lot-clustered SE for lines vs C over 15 nats would have counted as a miss. It came out at
  14.4, so that criterion holds.
- The walk origin was to be cleared if the year gap were under 2 pp and the first-knot shift under
  2 pp. The shift is 1.8 pp (90.7 to 88.9), but the year gap is 5.2 pp, and it stays at 5.6 pp
  with the first-knot origin. The walk origin is not cleared, and it does not explain the year
  gap either.

## Coverage by listing year (C, new building)

80% coverage by row bin and listing year:

| Building rows | 2010-13 | 2014-16 | 2017-19 | 2020-21 | 2022-23 | 2024-26 |
|---|---:|---:|---:|---:|---:|---:|
| 1-5 | 67.9 | 77.4 | 78.0 | 73.4 | 79.7 | 82.6 |
| 6-20 | 79.8 | 81.9 | 87.4 | 85.0 | 86.0 | 89.9 |
| 21-100 | 85.5 | 90.5 | 92.4 | 90.5 | 93.0 | 93.4 |
| 101+ | 90.8 | 87.6 | 91.0 | 90.3 | 93.0 | 94.6 |

The 2024-26 minus 2014-16 gaps are +5.2, +8.0, +2.8 and +7.0 pp by bin. I weighted each bin by
the smaller of its two row counts, which gives +5.2 pp. Coverage rises with the year in every bin,
so the intervals are too wide for recent listings and closer to nominal for old ones. Rows from
2010-13 in buildings with 1-5 rows are the worst covered, at 67.9%.

By residential-units tercile and PLUTO class the pattern repeats. One group stands apart: big
buildings (101+ rows) whose lot has no residential units on record (class family "other", unitsres
unknown) cover only 25.6-75.1% at 80%. That group is 1,088 rows, and its buildings are probably
matched to the wrong lot, which makes it a lead for the Data thread. Full tables:
`python -m rentfrontier.clusterse strata <dir>`.

## The first-knot walk origin

| Building rows | C: miss, 80, 95 | First-knot origin: miss, 80, 95 |
|---|---|---|
| all | 11.89%, 90.7, 98.2 | 11.89%, 88.9, 97.5 |
| 1-5 | 17.47%, 77.6, 92.4 | 17.40%, 72.5, 89.3 |
| 6-20 | 14.37%, 85.9, 96.5 | 14.36%, 83.0, 95.3 |
| 21-100 | 11.51%, 91.9, 98.6 | 11.51%, 90.0, 97.9 |
| 101+ | 11.68%, 91.1, 98.4 | 11.67%, 89.8, 98.0 |

Starting the walk at the building's own first knot narrows every bin by about 1-5 points at 80%.
That brings the bigger buildings nearer nominal and pushes the 1-5 bin further under it. The
year gap stays at +5.6 pp. The panel origin therefore explains about 1.8 points of the overall
over-coverage and none of the year gap.

## Clustered SEs on C-era pairs (PSIS-LOO)

Each pair is C minus the other fit, on 193,376 shared rows in 5,369 buildings on 5,016 lots. The
combined Monte Carlo error is about 15.2 in every pair. The verdict is at 2 combined SEs, as the
board computes it.

| Other fit | C minus other | SE iid | SE building | SE lot | Verdict iid | Verdict building / lot |
|---|---:|---:|---:|---:|---|---|
| lines | -53.0 | 15.4 | 22.0 | 22.1 | other wins | tie |
| elevfill | -36.0 | 13.9 | 21.3 | 21.3 | tie | tie |
| bigbed | -46.8 | 18.1 | 28.8 | 30.7 | tie | tie |
| areatime | -405.5 | 36.4 | 66.6 | 146.3 | other wins | other wins |
| nofloorslope | +318.8 | 42.9 | 66.0 | 68.3 | C wins | C wins |

- Clustering by building multiplies the SE by 1.43-1.83, and clustering by lot by 1.44-1.70,
  except in areatime. Areatime's lot SE is 4.0 times the iid SE, because its area-by-time terms
  move whole lots together.
- One verdict changes. Under the iid SE, lines beats C on PSIS-LOO (53.0 against a tolerance of
  43.2). Under either clustered SE it is a tie (tolerance 53.5). Bigbed was a tie under the iid SE
  by 0.5 nats, and it stays a tie.

## Lines vs C on new buildings

On new-building lpd, building-weighted (each building's mean, summed over 5,415 buildings), lines
minus C is +83.9 nats. Its SEs are 11.8 iid, 14.1 by building and 14.4 by lot, so lines wins by
5.8 lot SEs. The row-summed difference is +2,375 nats with a lot SE of 826.

The gain is spread over the row bins (+26.9, +27.9, +24.2 and +4.9 nats from 1-5 up to 101+) and
over the listing years. Lines' building-weighted miss is also lower (14.09% ± 0.17 against C's
14.29% ± 0.18), while its row-level miss is 0.1 pp higher (11.99% against 11.89%). Per building
the gain averages 0.016 nats, which is small, but the sum over 5,415 buildings is large. My
prediction got the scale wrong.

## Building-weighted scores

With each building counted once and lot-bootstrap SEs:

| Fit | Rung | Miss | 80% | 95% | lpd sum (nats) |
|---|---|---:|---:|---:|---:|
| C | new building | 14.29% ± 0.18 | 84.7 ± 0.4 | 95.5 ± 0.2 | -226 ± 55 |
| C | new unit (in-sample) | 3.04% ± 0.03 | 90.9 ± 0.2 | 97.5 ± 0.1 | 6,345 ± 68 |
| lines | new building | 14.09% ± 0.17 | 84.8 ± 0.4 | 95.6 ± 0.2 | -142 ± 55 |
| areatime | new building | 14.20% ± 0.19 | 84.8 ± 0.4 | 95.4 ± 0.2 | -202 ± 55 |
| nofloorslope | new building | 14.27% ± 0.18 | 84.6 ± 0.4 | 95.6 ± 0.2 | -227 ± 56 |

Paired with C on the same rows, building-weighted new-building lpd moves by +83.9 nats for lines
(lot SE 14.4), +24.1 for areatime (lot SE 9.0) and -0.8 for nofloorslope (lot SE 9.3). Weighted by
row, areatime scores 11.9% and 90.6/98.1, and nofloorslope 12.0% and 90.5/98.1, both within 0.1 of
C. Areatime's lead over C on PSIS-LOO (405 nats) shrinks to 24 nats on new buildings, because its
area-by-time terms carry over to a new building only through its area and listing time.

Weighted by building, C's new-building intervals sit close to nominal (84.7/95.5), while
weighted by row they look over-wide (90.7/98.1). Rows concentrate in big buildings, which C
predicts better than small ones, so the row-weighted figure leans on them.

## The neighbourhood labels (C)

The label coefficients against Chelsea (posterior median, 90% interval) are West Village +10.2%
(8.3 to 12.0), Greenwich Village +8.3% (6.4 to 10.2), Flatiron +8.0% (5.3 to 10.7), NoMad -5.2%
(-7.9 to -2.5), Gramercy Park -8.3% (-10.1 to -6.7) and East Village -12.4% (-13.5 to -11.2). The
-13.2% quoted for East Village earlier is the change in the log coefficient, read as a percentage;
as a ratio of asks it is -12.4%.

Per draw, the label term's variance over C's training rows is 0.0080 (90% interval 0.0070 to
0.0091), an SD of 0.089 log points (0.084 to 0.095). That is 3.9% (3.4 to 4.4%) of the log ask's
variance over the same rows.

Leaving the label term out of the new-building mean, with nothing refit, moves the miss over all
rows from 11.89% to 13.75%, and the 80/95 coverage from 90.7/98.2 to 88.5/97.7. By area (median
miss, then the median signed error, prediction over ask):

| Area | Rows | Miss with labels | Signed | Miss without | Signed |
|---|---:|---:|---:|---:|---:|
| Chelsea | 47,306 | 11.8% | -2.2% | 11.8% | -2.2% |
| East Village | 59,741 | 10.2% | -0.4% | 15.7% | +13.7% |
| Flatiron | 10,890 | 11.3% | -1.0% | 13.1% | -8.3% |
| Gramercy Park | 16,497 | 12.7% | -3.7% | 12.9% | +5.0% |
| Greenwich Village | 16,662 | 16.8% | +7.0% | 14.9% | -1.2% |
| NoMad | 8,212 | 14.7% | -10.8% | 13.2% | -5.9% |
| Stuyvesant Town/PCV | 3,254 | 7.9% | +4.1% | 7.9% | +4.1% |
| West Village | 30,814 | 13.2% | -0.2% | 14.5% | -9.4% |

These figures are an upper bound on what the labels carry, since a refit without labels would let
other terms take some of their work. Two areas already miss in the same direction with their labels
on: C prices new buildings in Greenwich Village 7.0% above the ask and in NoMad 10.8% below it.
Dropping the label shrinks both of those errors.
