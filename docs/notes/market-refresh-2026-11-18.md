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
     COMMIT range-m2 drift-building-bedtext-layout-range b0 2 200 3600 20 \
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
- Of the 6,774 ads open on Nov 9, 20% to 40% have closed. The backtest's ads closed within
  14 days of their first day at a rate of 20% to 25%, and an open ad on a given day is on
  average older than a new one.
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

To be filled in after the fit.
