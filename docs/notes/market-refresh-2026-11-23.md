# The next market snapshot for Deals (planned for 2026-11-23)

The Deals page lists the ads open on 2026-11-20 from `range-m3`
(`docs/notes/market-refresh-2026-11-20.md`). Two days closed 17 of the first 100
uncautioned ads of the table before it, so the list is refreshed every few days. This note
is the plan and the predictions for the next refresh, written on Nov 21 before the scrape.
The model (`drift-building-bedtext-layout-range`), the held scales (`base-n9`), the sampler
settings, the backtest (`range-j`) and the cautions as merged by then stay as they are. The
data is the single change. The fit's name is `range-m4`.

## Steps

All from `/data1/apartments/serve/master` at `origin/master`, with `ops/deals-refresh`
(usage in its header):

1. `ops/streeteasy-collect topup` at 64 requests a minute, then
   `systemctl --user start apartments-pipeline-build.service`. Call the new rows hash `H`.
   Reread the scrape log for failed regions before step 2.
2. `ops/deals-refresh datasets H`. It runs `b0nyc` against the NJ registry of the same
   build (#1443).
3. `ops/deals-refresh fit range-m4 H`, one Modal fit outside the daily budget, with no
   scoring. Expected cost about $2, charged to the sprint's $100 ($80.43 spent before it).
4. `ops/deals-refresh publish RUN` to the staging folder, a comparison with the live files,
   then the same to `/data1/apartments/site/deals` after a copy of the live files goes to
   `/data1/apartments/tmp/po-deals-live-before-refresh-1123`.

## Predictions, written before the scrape, the build and the fit

`D` is the number of days from Nov 20 to the new snapshot (3 if the scrape runs on Nov 23).
Nov 21 and 22 are a weekend.

- The scrape and build finish without a failed region in the scrape log, and the latest
  `first_day` is the scrape's day (UTC days can make it the next one).
- The market dataset holds 6,100 to 6,900 open ads (6,502 on Nov 20).
- Of the 6,502 ads open on Nov 20, 9% to 16% have closed at `D` = 3. The last interval
  closed 10.2% in two days, 5.1% a day, and a weekend is slower for leases and new ads.
- Of the first 100 uncautioned ads of the live table (as published on Nov 21 at 1:20 AM
  ET), 15 to 32 have closed at `D` = 3 (17 in two days last time).
- The fit passes the gate in one container: worst R-hat at most 1.01, least bulk ESS above
  400 (`range-m3` had 1.0059 and 605). A sweep takes 0.32 to 0.37 s and the fit costs $1.90
  to $2.20.
- For the ads open in both snapshots with an unchanged ask, the Spearman correlation of
  the two places is at least 0.99 (0.997 over two days last time), and at least 93 of each
  100 ads of the old lowest tenth stay in the new lowest tenth (97.2 last time).
- The cautioned share is 23% to 28% (1,675 of 6,502, 25.8%, in the live table), with
  `raised` on 550 to 800 ads (655 in the live table).
- Among ads first listed after Nov 20 (all of them, whatever their ask since), the share
  below the 5% point is 3% to 8% (4.9% of 507 new ads last time).

If the fit misses the gate, Deals keeps the Nov 20 table, and the new rows are read before
anything else.
