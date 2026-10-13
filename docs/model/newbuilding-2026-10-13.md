# New-building score (2026-10-13)

This is Ben's step 1 of 2026-10-13. It is computed by `python -m rentfrontier.newbuilding` (#700) on
the fits' kept draws, with results in `/data1/apartments/frontier/newbuilding/<run>-0f93b1e/`. Each
training row is scored in two ways:

- **New building:** the building's terms (level, walk, bedroom premium, feature slopes, trend) are
  drawn from their population distributions. This tells what the model would quote for a building it
  has never seen.
- **New unit, in-sample:** only the unit's terms are drawn; the building keeps the terms the fit
  learned, including from the row's own asks. That makes this rung **in-sample** for the building,
  and it reads better than out-of-sample. The honest new-unit figure is the row split's held-out
  rows from units the fit never saw (`summary.new_unit_coverage`, #688). For the served C that is
  **67% / 89%** coverage over 964 rows.

The miss is the median absolute % miss of the predictive median. Coverage is the share of asks
inside the central 80% and 95% predictive intervals.

## C (`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` / `nb8-nostuy-v1`, rows)

| Rows | n | New building: miss | 80% | 95% | New unit (in-sample): miss | 80% | 95% |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 193,376 | 11.9% | 90.7 | 98.1 | 3.7% | 86.1 | 96.9 |
| size stated | 70,977 | 11.8% | 90.6 | 97.9 | 3.6% | 88.1 | 97.7 |
| size unknown | 122,399 | 12.0% | 90.7 | 98.3 | 3.7% | 84.9 | 96.4 |
| building rows 1–5 | 4,128 | 17.3% | 77.8 | 92.3 | 2.5% | 95.0 | 98.2 |
| building rows 6–20 | 17,451 | 14.3% | 85.9 | 96.5 | 3.3% | 90.4 | 96.9 |
| building rows 21–100 | 85,450 | 11.5% | 91.9 | 98.5 | 3.5% | 87.3 | 96.9 |
| building rows 101+ | 86,347 | 11.7% | 91.1 | 98.3 | 4.0% | 83.6 | 96.7 |
| held-out lots' buildings | 20,023 | 12.1% | 91.4 | 98.2 | 3.7% | 86.2 | 96.8 |

Out-of-sample new unit (row split's held-out rows from unseen units, #688): 67% / 89% over 964 rows.

The new-building coverage of 91/98 looks over-wide. One possible reason is that the score draws the
building level and its walk independently, while their posterior trades one against the other. This
is an inference, not yet tested or fixed. Buildings with 1–5 training rows are the exception: their
intervals are too narrow (78/92).

## Other fits (all rows)

| Fit | New building: miss | 80% | 95% | New unit (in-sample): miss | 80% | 95% |
|---|---:|---:|---:|---:|---:|---:|
| C + areatime (`e76570bb`) | 11.9% | 90.6 | 98.1 | 3.7% | 86.1 | 96.9 |
| C on `nb8-nostuy-lines-v1` (`306d7299`) | 12.0% | 90.8 | 98.2 | 3.7% | 86.1 | 96.9 |
| C − floorslope (`306d7299`) | 12.0% | 90.5 | 98.1 | 3.7% | 85.9 | 96.9 |

All four fits' draws are on thelio.

## Descriptive share of C

`python -m rentfrontier.variance` (#700), with building slopes counted as descriptive:

- market and time 8.0%;
- features 67.2%;
- building 10.2%;
- building over time 5.6%;
- **building slopes 4.1%**;
- unit 2.8%;
- residual 2.2%.

The **descriptive share is 26.1%** (90% interval 25.4–26.8%).

## Held-out-lots refit (Ben's step 2)

C was refit with `tune-holdout-lots-v1`, which leaves out every row of 542 buildings on 508 tax lots.
The fit passed the gate (max R-hat 1.006, min ESS 647; 1,533 s fit; $1.61). `python -m
rentfrontier.newbuilding --holdout` scores the left-out buildings' 20,023 rows as new buildings. The
step 1 score on the same rows (`--only config/holdout/lots-v1.tsv`) is the last row of the C table
above.

| Score on the held-out lots' 20,023 rows | Miss | 80% | 95% |
|---|---:|---:|---:|
| Refit, buildings never seen | 12.20% | 91.2 | 98.1 |
| Step 1, building terms drawn from C | 12.09% | 91.4 | 98.2 |

They agree within Ben's bound (0.3 pp of miss, 0.02 of coverage), so **step 1's new-building
score is the board number**. The prediction was that step 1 would be optimistic by under 0.5 pp. It
was optimistic by 0.11 pp: a hit.

## Final-ask fit (Ben's step 3)

C was refit with `tune-finalask-v1`: each row is priced at its listing's last ask. The rule leaves
out listings still live at the last capture (live listings are excluded throughout), listings no
crawl captured, and final asks over twice or under half the first. The fit passed the gate (max R-hat 1.008, min ESS 619;
1,446 s fit; $2.00, of which about $0.80 was the post-fit summary that timed out after 20 minutes).
It trains on 121,035 rows; C trains on 193,376.

`python -m rentfrontier.finalask` scores both fits on the 13,262 held-out rows they share, each
with the unit's terms drawn from the population.

| Fit, against | Miss | 80% | 95% |
|---|---:|---:|---:|
| Final-ask fit, final ask | 3.71% | 79.5 | 95.0 |
| C, final ask | 4.02% | 76.9 | 93.9 |
| C, first ask (its own target) | 3.73% | 79.1 | 94.9 |

The size-stated and size-unknown rows split the same way. Size stated: 3.85% vs 4.20%, and 78.6
vs 75.5. Size unknown: 3.61% vs 3.87%, and 80.3 vs 78.0.

**Reading.** On final asks, C misses by about 0.3 pp more than the final-ask fit (0.32 pp
unrounded), and its intervals cover 2.6 points too few at 80%. The final-ask fit predicts the final
ask about as well as C predicts the first ask. These figures are absolute misses, so they say
nothing about the sign of C's error on final asks.

**Coefficients and descriptive share.** These moved far more than predicted:

- Of 115 feature coefficients, 58 moved by more than one of C's posterior SDs, and 34 by more than
  two. The largest moves:
  - `text:concession`, from −1.0% to −3.9%;
  - East Village, from −13.2% to −0.4%;
  - bathrooms 2, 3 and 4+, up 3.4, 7.9 and 8.7 points;
  - building era 1990–2009, from +8.4% to +16.4%;
  - `numfloors_unknown`, from −0.4% to −3.8%.
- The size slope moved by +1.8 SD and `sqft_unknown` by −1.0 SD.
- The intercept fell from −0.424 to −0.489, about 6.5%. It trades against the building and
  neighbourhood terms, so it does not by itself measure the average price cut.
- The descriptive share fell from 26.1% (90% interval 25.4–26.8%) to 21.6% (20.7–22.5%). The building
  share is 9.2% (C: 10.2%), building over time 4.9% (5.6%), building slopes 3.7% (4.1%), and features
  70.4% (67.2%).

Most of the coefficient and share movement probably comes from the rows rather than the price. The
final-ask fit trains on 37% fewer rows than C, mostly rows whose listing no crawl captured, so the
two fits describe different listings. One example is East Village, whose capture rate differs from the other areas. A fit of
C on the same 121,035 rows at their first ask would separate the two causes. It has not been run.

## Latest-ask fit

Ben asked for a fit priced at each listing's latest available ask. I refit C with
`tune-latestask-v1` (#706). Each row takes the last ask any crawl recorded for its listing, from
the outcomes file I rebuilt on 2026-10-13 from all seven crawls (`listing-outcomes/20261013-57c2a78`).
A listing with a single ask keeps it. Two kinds of row get special handling:

- A listing still live at its last capture (1,076 rows) takes its current ask.
- A row whose listing no crawl captured (0.1%), or whose latest ask is under half or over twice the
  row's ask (587 rows), keeps the row's own ask.

No rows are dropped, so the fit trains on C's 193,376 rows. Of all 214,887 rows, 79,719 change
price, 8,350 of them held out. Asks went down on 27% of rows and up on 10%. The fit passed the gate:
max R-hat 1.005, min ESS 663, a 2,307 s fit, $2.05.

`python -m rentfrontier.finalask` scores both fits on all 21,511 held-out rows against the latest ask:

| Fit, against | Miss | 80% | 95% |
|---|---:|---:|---:|
| Latest-ask fit, latest ask | 3.73% | 79.3 | 94.9 |
| C, latest ask | 4.01% | 76.8 | 93.5 |
| C, its own ask | 3.74% | 79.3 | 94.7 |

Against the latest ask, C misses 0.28 pp more than the latest-ask fit and covers 2.5 points too few
at 80%. On median miss and coverage, the latest-ask fit does about as well on the latest ask as C does on its own ask.

**Coefficients.** I compared posterior means, in units of C's posterior SD. Of 223 parameters, 82
moved by more than 1 SD and 42 by more than 2.

- `text:concession` moved the most, from −1.0% to −3.6% (28 SD). The final-ask fit moved it to −3.9%.
  Listings with a concession get cut more often after they first list.
- Four noise scales (`sigma` 27, 10, 61 and 44) grew by 20 to 30%.
- `text:no_fee` went from +0.5% to +0.2% and `outdoor:roof_deck` from +1.8% to +1.2%. The
  month-of-year season terms flattened by 0.4 to 0.6 pp.
- The intercept fell 0.4%.
- East Village is outside the 30 largest moves. Its −13% swing in the final-ask fit came from the
  old outcomes file, which predates the East Village crawl.

**Descriptive share.** 25.9% (90% interval 25.2–26.6%), against C's 26.1%.

When I changed the price and kept the rows, the concession term, a few noise scales and the season
moved, and the descriptive share stayed within 0.2 pp. The large moves in the final-ask fit
appear to come mostly from its smaller set of rows, though no fit isolates that.

## New-building score of the ask fits

I ran these on Modal with `ops/modal/newbuilding.py` (#712): a 32-core container, one worker per
core. The latest-ask fit's score took 157 s and cost $0.13; on thelio a single process takes about
1,120 s on the same number of rows.

| Rows | Latest ask: n | New building: miss | 80% | 95% | New unit (in-sample): miss | 80% | 95% |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 193,376 | 12.0% | 90.4 | 98.0 | 3.7% | 86.2 | 97.0 |
| size stated | 70,981 | 11.7% | 90.5 | 97.9 | 3.6% | 88.2 | 97.8 |
| size unknown | 122,395 | 12.1% | 90.3 | 98.1 | 3.8% | 85.0 | 96.5 |
| building rows 1–5 | 4,128 | 16.8% | 78.5 | 92.5 | 2.5% | 95.2 | 98.3 |
| building rows 6–20 | 17,451 | 14.1% | 86.0 | 96.5 | 3.2% | 91.0 | 97.1 |
| building rows 21–100 | 85,450 | 11.7% | 91.4 | 98.3 | 3.6% | 87.4 | 96.9 |
| building rows 101+ | 86,347 | 11.7% | 90.8 | 98.3 | 4.0% | 83.6 | 96.9 |

The final-ask fit, on its 121,035 rows, scores 12.5% miss and 90.6 / 98.4 for a new building, and
3.9% and 86.2 / 97.0 for a new unit. It took 119 s and cost $0.14.

The latest-ask fit and C give nearly the same new-building score: 12.0% against 11.9% miss. Each
is scored on its own prices, so the numbers compare the fits' quotes for unseen buildings rather
than a shared target.

## Prediction outcomes

| Prediction | Outcome |
|---|---|
| Step 1 optimistic by under 0.5 pp (step 2) | Hit: 0.11 pp |
| Final-ask miss 0.2–0.6 pp below C's | Hit: 0.32 pp |
| 80% and 95% coverage within 0.02 | Partly: 95% within 0.011; 80% differs by 0.026 |
| Intercept down about 1% | Miss: down about 6.5%, though not cleanly identified |
| Coefficients move less than their SD, except size | Miss: 58 of 115 moved more than 1 SD |
| Descriptive share within 1 pp | Miss: 4.5 pp lower |
| Latest-ask miss 0.1–0.4 pp below C's | Hit: 0.28 pp |
| Latest-ask 80% and 95% coverage within 0.02 | Partly: 95% within 0.014; 80% differs by 0.025 |
| Latest-ask intercept down about 1% | Miss: down 0.4% |
| Concession moves down; most others under 1 SD; East Village steady | Hit on concession and East Village; 82 of 223 moved more than 1 SD |
| Latest-ask descriptive share within 1 pp | Hit: 25.9% vs 26.1% |
