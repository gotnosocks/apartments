# The next market snapshot for Deals (planned for 2026-11-20)

The Deals page lists the ads open on 2026-11-18 from `range-m2`. Nine days closed 61 of the
first 100 uncautioned ads of the table before it
(`docs/notes/market-refresh-2026-11-18.md`), so the list is refreshed every few days. This
note is the plan and the predictions for the next refresh, written on Nov 19 before the
scrape. The model (`drift-building-bedtext-layout-range`), the held scales (`base-n9`), the
sampler settings, the backtest (`range-j`) and the cautions stay as they are. The data is
the single change.

## Steps

All from `/data1/apartments/serve/master` at `origin/master`, with `ops/deals-refresh`
(usage in its header):

1. `ops/streeteasy-collect topup` at 64 requests a minute, then
   `systemctl --user start apartments-pipeline-build.service`. Call the new rows hash `H`.
2. `ops/deals-refresh datasets H`. It runs `b0nyc` against the NJ registry of the same
   build (#1443).
3. `ops/deals-refresh fit range-m3 H`, one Modal fit outside the daily budget, with no
   scoring. Expected cost about $2, charged to the sprint's $100 ($76.35 spent before it).
4. `ops/deals-refresh publish RUN` to the staging folder, a comparison with the live files,
   then the same to `/data1/apartments/site/deals` after a copy of the live files goes to
   `/data1/apartments/tmp/po-deals-live-before-refresh-1120`.

## Predictions, written before the scrape, the build and the fit

`D` is the number of days from Nov 18 to the new snapshot (2 if the scrape runs on Nov 20).

- The scrape and build finish without a failed region, and the latest `first_day` is the
  scrape's day (UTC days can make it the next one).
- The market dataset holds 6,100 to 6,900 open ads (6,565 on Nov 18).
- Of the 6,565 ads open on Nov 18, 3% to 6% a day have closed: 6% to 12% at `D` = 2. The
  last interval closed 34.7% in nine days, 3.9% a day, and the first days after a snapshot
  take the ads nearest their close.
- Of the first 100 uncautioned ads of the live table (cautions as published on Nov 18 at
  11:30 PM ET, with `raised`), 10 to 25 have closed at `D` = 2. Nine days closed 61 of the
  first 100 last time.
- The fit passes the gate in one container: worst R-hat at most 1.01, least bulk ESS above
  400 (`range-m2` had 1.0061 and 757). A sweep takes 0.32 to 0.37 s and the fit costs $1.90
  to $2.20.
- For the ads open in both snapshots with an unchanged ask, the Spearman correlation of
  the two places is at least 0.99 (0.9904 over nine days last time), and at least 93 of
  each 100 ads of the old lowest tenth stay in the new lowest tenth (93.6 last time).
- The cautioned share is 18% to 23% (1,333 of 6,565, 20.3%, in the live table), with
  `raised` on 550 to 800 ads (686 in the live table).
- Among ads new since Nov 18, the share below the 5% point is 4% to 8%. New ads stand at
  their first ask, and 4.6% of the backtest's ads at their first ask were below the 5%
  point on the day.

If the fit misses the gate, Deals keeps the Nov 18 table, and the new rows are read before
anything else.

## Results

To be written after the fit.
