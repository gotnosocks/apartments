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

## Results

Deals has read `range-m4` since 3:56 PM ET on Nov 23: 6,200 open ads, with `range-j`
as the backtest. The run is `drift-building-bedtext-layout-range-b0-market-1f0c240c-range-m4`
on pipeline build rows `b157a29e19aa837a`. It launched at 2:27 PM ET, settled at 2:59 PM ET
and cost $2.28. The live files of the Nov 20 table are kept in
`/data1/apartments/tmp/po-deals-live-before-refresh-1123`. By the handoff's count the sprint
has spent $82.71 of $100. The Modal ledger counts more (below).

**Predictions scored.**

| Prediction | Range | Result | Verdict |
| --- | --- | --- | --- |
| Scrape and build without a failed region; latest `first_day` is the scrape's day | as written | both topups ran all 6 regions with exit 0 and no errors; a second topup and build were needed (below); latest `first_day` 2026-11-23 | inside |
| Open ads in the market dataset | 6,100 to 6,900 | 6,200 (5,666 ACTIVE, 534 TEMPORARILY_OFF_MARKET) | inside |
| Share of the 6,502 Nov 20 ads closed at `D` = 3 | 9% to 16% | 661, 10.2% | inside |
| Of the first 100 uncautioned Nov 20 ads, closed at `D` = 3 | 15 to 32 | 19 | inside |
| Gate: worst R-hat | at most 1.01 | 1.0062 (`beta[bed=4:full>=3]`) | inside |
| Gate: least bulk ESS | above 400 | 829 (`beta[ad:months_free]`) | inside |
| Seconds a sweep | 0.32 to 0.37 | 0.360 | inside |
| Cost of the fit | $1.90 to $2.20 | $2.28 | outside, above |
| Spearman of places, same-ask ads open in both tables | at least 0.99 | 0.9965 on 5,432 ads | inside |
| Old lowest tenth still in the new lowest tenth | at least 93 of 100 | 97.1 of 100 | inside |
| Cautioned share | 23% to 28% | 1,577 of 6,200, 25.4% | inside |
| Ads with `raised` | 550 to 800 | 618 | inside |
| Ads first listed after Nov 20 below the model's 5% point | 3% to 8% | 6.2% of 226 | inside |

**The cost.** The fit ran 32 minutes from launch to settle, against 30 for `range-m3`, and
cost $0.17 more than `range-m3`'s $2.11, $0.08 over the range. Slower sweeps (0.360 s
against 0.352 s over 3,800) explain about 30 s of it. The rest came outside sampling.

**Two tooling faults, both worked around by hand.**

- *A Monday morning scrape fails `b0trim`.* The first topup ran at 9:42 AM ET and build
  `1577b0105d865a9d` held 85 rows with `latest_day` Nov 23. `b0trim.dense_start` bins weeks
  from Monday 2000-01-03 and needs at least 100 rows in every week through the last, so the
  week that began that morning failed it ("the last week holds fewer than 100 rows"). A
  second topup ran from 12:45 to 12:57 PM ET, and build `b157a29e19aa837a` followed at
  1:02 PM ET. The first build's `b0-1577b0105d865a9d-alldata` dataset is left over, unused.
- *The registry glob misses a second snapshot from the same day.* The failed first attempt
  had already written `external/registry/20261123-1f0c240-extend`, so the second
  `registry-extend` wrote `20261123-1f0c240-extend-180210` (1 building added,
  `413-east-53-street-new_york`). The `*-extend` glob in `ops/market-dataset` and
  `ops/deals-refresh` matches only the first, so the verify step stopped on "buildings with
  no registry point 1". `registry-extend` also exited 134 ("terminate called without an
  active exception") after its NJ step, having written its file. I removed the units, attrs,
  age and market outputs of the new build and reran them and `datasets`, then `publish`,
  with `REGISTRY` set to the `-180210` snapshot.

**The table three days on.** By training ads, 4,169 of the open ads have their unit in the
training data, 1,944 have only their building and 87 have neither. Of the 6,502 ads of the
Nov 20 table 661 are no longer open, and 19 of its first 100 uncautioned ads are gone, close
to the 17 of the two days before. The ranking holds: the 5,432 ads open in both tables with
an unchanged ask keep a Spearman of 0.9965 between their places, and 97.1% of the old lowest
tenth stay in the lowest tenth. In the new first 100 uncautioned ads, 75 were in the Nov 20
first 100 and 10 are ads new since Nov 20. The cautioned share barely moved, from 25.8% to
25.4%: `raised` 618 (655), `off_market` 534 (585), `rooms_up` 275, `beds` 268,
`deposit_net` 66, `income` 55, `thin_level` 15, `takeover` 13, `short_lease` 8, `net_ask` 3,
`not_home` 1 and `owners_only` 1.

**New ads.** Of the 226 ads first listed after Nov 20, 6.2% are below the model's 5% point
at their ask now, against 3.4% for all ads in the new table (3.65% in the Nov 20 table).
With 226 ads the 6.2% has a standard error near 1.6 points, so the gap is under two
standard errors. A weekend gave fewer new ads than the 507 of the two days before.

**Spend.** The handoff counts $80.43 before this fit. The Modal ledger
(`/data1/apartments/modal/ledger.jsonl`) holds $386.57 of settled fits from Nov 14 on,
$279.65 of it in 207 fits on Nov 22 and $26.49 in 7 on Nov 23, most from other sessions.
The two counts need reconciling before the next paid fit.
