# Predictions: new-building score checks (2026-10-13)

These predictions were written before the fits, for the coordinator's three steps that Ben approved
at 02:47Z on 2026-10-13. Neither fit is scored by PSIS-LOO, because each is a tuning fit
(`tune-` rule), so they are recorded here rather than in `config/predictions.jsonl`.

## 1. Grouped-building holdout refit of C

The fit is C (`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` /
`nb8-nostuy-v1`, row split, served data rules) plus `tune-holdout-lots-v1`. That rule drops every
row of 542 buildings on 508 tax lots, which is 10% of lots (seed 20261013, `config/holdout/lots-v1.tsv`).
`python -m rentfrontier.newbuilding --holdout <run>` scores those buildings' rows that C trains on.
The step 1 score on the same rows is `python -m rentfrontier.newbuilding --only
config/holdout/lots-v1.tsv <C>`.

- **Rule (Ben):** if the two agree within about 0.3 pp of median miss and 0.02 of coverage, step 1
  becomes the board's number; otherwise the refit is.
- **Prediction (coordinator, Ben's go):** step 1 is slightly optimistic, by under 0.5 pp of median
  miss.

## 2. Final-ask fit of C

The fit is C plus `tune-finalask-v1`. Each row is priced at its listing's last ask (#554). The
rule leaves out:

- listings still live at the last capture (0.4% of rows);
- listings no crawl captured (37%);
- final asks more than twice or under half the first ask (0.5%; sale prices and typos).

That leaves 134,297 rows, of which 13,262 are held out and shared with C.
`python -m rentfrontier.finalask <run> <C>` scores both fits on those rows against the final ask.

**Prediction (Modeling):**

- The final-ask fit's median miss against the final ask is 0.2 to 0.6 pp below C's on those rows.
- Their 80% and 95% coverage are within 0.02 of each other.
- The intercept moves down about 1% (asks get cut more often than raised: 17% vs 6% of rows).
- Feature coefficients move less than their posterior SD, except that the size and unknown-size
  terms may move more.
- The descriptive share is within 1 pp of C's.

## 3. predsize

The fit is C on `nb8-nostuy-predsize-v1`. On the 135,097 rows without a stated size, the bedroom-median default (0) becomes
Data improvements' rent-blind predicted log size relative to the bedroom median: case b, building-grouped out-of-fold LightGBM with the row's own unit left out,
`/data1/apartments/external/size-predicted/20261013-5701f4b4/`. Those fills have mean −0.14 and SD 0.21.
`sqft_unknown` and its slope stay. The prediction (coordinator note, 02:59Z; also in `config/predictions.jsonl`):

- PSIS-LOO near a tie, since sizeunkslope already absorbs the average gap.
- A lower new-building miss on unknown-size rows.
- A lower descriptive share, counting slopes.

It is judged on all three.
