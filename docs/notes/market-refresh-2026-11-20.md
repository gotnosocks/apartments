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
  first 100 last time, on a list without the `raised` marks, so the two lists differ a
  little.
- The fit passes the gate in one container: worst R-hat at most 1.01, least bulk ESS above
  400 (`range-m2` had 1.0061 and 757). A sweep takes 0.32 to 0.37 s and the fit costs $1.90
  to $2.20.
- For the ads open in both snapshots with an unchanged ask, the Spearman correlation of
  the two places is at least 0.99 (0.9904 over nine days last time), and at least 93 of
  each 100 ads of the old lowest tenth stay in the new lowest tenth (93.6 last time).
- The cautioned share is 18% to 23% (1,333 of 6,565, 20.3%, in the live table), with
  `raised` on 550 to 800 ads (686 in the live table).
- Among ads first listed after Nov 18 (all of them, whatever their ask since), the share
  below the 5% point is 4% to 8%. New ads stand at
  their first ask, and 4.6% of the backtest's ads at their first ask were below the 5%
  point on the day.

If the fit misses the gate, Deals keeps the Nov 18 table, and the new rows are read before
anything else.

## Results

Deals has read `range-m3` since about 4:16 PM ET on Nov 20: 6,502 open ads, with `range-j`
as the backtest. The run is `drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3`
on pipeline build rows `4f487ef77bb6ca61`. It launched at 3:24 PM ET, settled at 3:54 PM ET
and cost $2.11. The backtest is `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j`.
The live files of the Nov 18 table are kept in
`/data1/apartments/tmp/po-deals-live-before-refresh-1120`. The sprint has spent $78.46 of
$100.

**Predictions scored.**

| Prediction | Range | Result | Verdict |
| --- | --- | --- | --- |
| Scrape and build without a failed region; latest `first_day` is the scrape's day | as written | scrape done 2:47 PM, build `4f487ef77bb6ca61` done 2:57 PM; latest `first_day` 2026-11-20, the scrape's day; the scrape log was not reread for failed regions | first day inside, regions not checked |
| Open ads in the market dataset | 6,100 to 6,900 | 6,502 (5,917 ACTIVE, 585 TEMPORARILY_OFF_MARKET) | inside |
| Share of the 6,565 Nov 18 ads closed at `D` = 2 | 6% to 12% | 670, 10.2% | inside |
| Of the first 100 uncautioned Nov 18 ads, closed at `D` = 2 | 10 to 25 | 17 | inside |
| Gate: worst R-hat | at most 1.01 | 1.0059 (`beta[bed=0:full>=2]`) | inside |
| Gate: least bulk ESS | above 400 | 605 (`beta[bed=0:full>=2]`) | inside |
| Seconds a sweep | 0.32 to 0.37 | 0.352 | inside |
| Cost of the fit | $1.90 to $2.20 | $2.11 | inside |
| Spearman of places, same-ask ads open in both tables | at least 0.99 | 0.997 on 5,402 ads | inside |
| Old lowest tenth still in the new lowest tenth | at least 93 of 100 | 97.2 of 100 | inside |
| Cautioned share | 18% to 23% | 1,604 of 6,502, 24.7% | outside, above |
| Ads with `raised` | 550 to 800 | 653 | inside |
| Ads first listed after Nov 18 below the model's 5% point | 4% to 8% | 4.9% of 507 | inside |

**The cautioned share.** I drew the 18% to 23% range from the handoff's figure of 1,333
cautioned ads. That figure was stale: the live table of Nov 18 already had 1,640 of 6,565
(25.0%) cautioned, so the range sat below the starting point and could not have held. The
share itself barely moved, to 24.7%. `raised` fell from 686 to 653 and `off_market` from 588
to 585. The other codes are `beds` 286, `rooms_up` 286, `income` 58, `takeover` 15,
`net_ask` 6, `not_home` 1 and `owners_only` 1.

**The table two days on.** By training ads, 4,380 of the open ads have their unit in the
training data, 2,028 have only their building and 94 have neither. Of the 6,565 ads of the
Nov 18 table 670 are no longer open, and 17 of its first 100 uncautioned ads are gone, a
rate near a sixth where nine days had taken 61. The ranking is steady: the 5,402 ads open
in both tables with an unchanged ask keep a Spearman of 0.997 between their places, and
97.2% of the old lowest tenth stay in the lowest tenth. In the new first 100 uncautioned
ads, 80 were in the Nov 18 first 100 and 11 are ads new since Nov 18.

**New ads.** Of the 507 ads first listed after Nov 18, 4.9% are below the model's 5% point
at their ask now, near the 4.6% of the backtest's ads at their first ask and above the
3.7% for all ads in the new table (4.0% in the Nov 18 table). With 507 ads the 4.9% has a
standard error near one point, so it does not differ from the overall rate.
