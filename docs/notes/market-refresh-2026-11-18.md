# A new market snapshot for Deals (2026-11-18)

The Deals page lists the ads open on 2026-11-09. This note refreshes the list with a new
scrape and a market fit of the same model, `drift-building-bedtext-layout-range`, with the
same held scales (`base-n9`) and sampler settings as `range-m`. The model, its backtest
(`range-j`) and the cautions stay as they are, so the data is the single change.

## Steps

1. I started `ops/streeteasy-collect topup` at 6:37 PM ET on Nov 18 from
   `/data1/apartments/serve/master` at `b3b522df`, with the rate at 64 a minute. It reads
   the ACTIVE ads of the five regions and runs the export. On Nov 9 the same command took
   14 minutes.
2. A pipeline build (`apartments-pipeline-build.service`) writes a new rows file, ads file
   and records file. Call its hash `H`.
3. Datasets, each from the last:
   - `rentfrontier.b0data` writes `b0-H-alldata` from the pipeline state;
   - `rentfrontier.b0trim` writes `b0-H-alldata-dense`;
   - `rentfrontier.b0nyc` writes `b0-H-alldata-dense-nyc`;
   - `ops/market-dataset H codes amenities units attrs age market verify` writes the
     snapshots and `b0-H-alldata-dense-nyc-market`. I leave out its backtest step, since
     `range-j` on the build of Nov 9 remains the backtest;
   - `rentfrontier.b0bedtext` writes `b0-H-alldata-dense-nyc-market-bedtext`, the dataset
     the layout-range model reads.
4. A Modal fit, after this note is on master:

   ```sh
   ops/modal-fit --outside-budget --gpu H100 --dataset "$M-bedtext" --input "$IN" --split market \
     --baseline drift-building-b0-market-67d14e17-n9 COMMIT range-m2 drift-building-bedtext-layout-range b0 2 200 3600 20 \
     --seed 1 --level-dof 4 --scales-fixed base-n9 --no-loo --no-heldout
   ```

5. `drift_deals texts`, then `drift_deals publish` with `range-j` as the backtest, after a
   copy of the live files goes to `/data1/apartments/tmp/po-deals-live-before-refresh`.

The scales in `base-n9` are the pooled means of the base model's market fit on the build of
Nov 9. Nine more days of ads add well under 1% to the 1.9 million rows, so I hold the same
scales and expect no visible effect from doing so.

## Predictions, written before the build and the fit

- The scrape and build finish without a failed region, and the new latest `first_day` is
  2026-11-18 (UTC days can make it Nov 19).
- The market dataset holds 6,200 to 7,400 open ads (6,774 on Nov 9). Late November is a
  slow month, so I expect a count a little under the last one.
- Of the 6,774 ads open on Nov 9, 10% to 30% have closed. About 13% of the backtest's ads
  closed within 14 days of their first day (20% to 25% in the lowest three tenths of
  places, 6% in the highest), and an open ad on a given day is on average older than a new
  one.
- Of the first 100 uncautioned ads of the Nov 9 table, 25 to 50 have closed, a higher
  share than among all ads, as the backtest's lowest tenth closed sooner (median 26 days
  against 32 to 42 in the next tenths).
- The fit passes the gate in one container: worst R-hat at most 1.01, least bulk ESS
  above 400 (`range-m` had 1.0057 and 789). A sweep takes 0.32 to 0.37 s and the fit costs
  $1.90 to $2.20.
- For the ads open in both snapshots with an unchanged ask, the place in the predictive
  distribution moves little: Spearman correlation of the two places at least 0.98, and at
  least 85 of each 100 ads of the old lowest tenth stay in the new lowest tenth.
- The cautioned share of the table stays between 15% and 20% (1,183 of 6,774 on Nov 9,
  17.5%).

If the fit misses the gate, Deals keeps the Nov 9 table, and I look at the new rows before
anything else.

## Results

Deals has read `range-m2` since 9:00 PM ET on Nov 18: 6,565 ads open on 2026-11-18, with
`range-j` as the backtest. The live files of the Nov 9 table are kept in
`/data1/apartments/tmp/po-deals-live-before-refresh`. `score.py` in
`docs/notes/market-refresh-2026-11-18/` prints the counts below from the two tables and
the new ads file.

**A failed first launch.** The first launch of `range-m2` stopped 44 seconds in, at the
design step, for $0.10: 12 open ads in 11 Hoboken and Jersey City buildings had no
registry point. `b0nyc` set NJ rows aside by the NJ registry of Oct 19, and those buildings
were first scraped after it. The `verify` step builds the design on 10% of buildings and
none of the 11 was in the draw. I moved the NYC, market and bedtext datasets to
`/data1/apartments/tmp/refresh-20261118/superseded`, rebuilt the NYC dataset against the
NJ registry the pipeline build wrote (`registry-nj/20261119-9f7ed6e`, which holds every
building of the Oct 19 snapshot and 12 more), and rebuilt the other two from it. The 12
rows went out, which left 6,565 open ads. #1443 gives `b0nyc` a
`--registry` option and has `verify` place every building.

**Predictions scored.**

| Prediction | Result | Verdict |
| --- | --- | --- |
| Scrape and build without a failed region, latest `first_day` 2026-11-18 | no failed region; the build finished at 7:23 PM ET after 20 minutes; latest first day 2026-11-18 | held |
| 6,200 to 7,400 open ads | 6,565 (5,977 ACTIVE, 588 TEMPORARILY_OFF_MARKET) | held |
| 10% to 30% of the 6,774 Nov 9 ads closed | 2,350, 34.7% (939 RENTED, 594 NO_LONGER_AVAILABLE, 466 DELISTED, 348 IN_CONTRACT, 3 in review) | missed, above |
| 25 to 50 of the first 100 uncautioned Nov 9 ads closed | 61 | missed, above |
| Gate passes in one container; sweep 0.32 to 0.37 s; $1.90 to $2.20 | worst R-hat 1.0061 (`beta[unit:log_size_rel]`), least bulk ESS 757 (`beta[bed=0:full>=2]`); 0.354 s a sweep; $2.05, plus $0.10 for the failed launch | held |
| Same-ask ads in both tables: Spearman of places at least 0.98 | 0.9904 on 3,293 ads | held |
| At least 85 of each 100 of the old lowest tenth stay in the new lowest tenth | 93.6 of 100 (308 of 329) | held |
| Cautioned share 15% to 20% | 1,086 of 6,565, 16.5% | held |

**The closings.** I set the range for closings from the backtest's 14-day rate for new ads
and then argued an open ad is older than a new one, which should have pushed the range up
and did not push it far enough. Over nine days 34.7% of the table closed. The ads the
model placed lowest closed faster: 46.2% of the lowest tenth of uncautioned ads (258 of
559), and 61 of the first 100. A list nine days old had lost most of its first page, so
the refresh interval matters more for the ads a renter reads first than the overall rate
suggests.

**Asks that moved.** Of the 4,391 ads in both tables, 1,098 have another ask: lower on
932 and higher on 166, with a median change of 3.0%.

**Cautions in the new table.** `off_market` 588, `beds` 292, `rooms_up` 285, `income` 63,
`takeover` 15, `owners_only` 1, `not_home` 1.
