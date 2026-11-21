# Diagnostics: the previous ask from the fit's own dataset and unit (2026-11-20, no fit)

The TODO item "Diagnostics: take each held-out ad's previous ask from the same build and the
same model unit as the fit" (PR #1496). `drift_diagnostics.previous` used to give each
held-out ad the row before it in its apartment's history, with the pieces `~1`, `~2` of a
unit read together. That row could be another configuration of the apartment, a held-out ad
of the fit, or an ad of the same day. It now gives the latest training row of the same
building and `unit_id`, dated strictly before the ad, in the dataset of the fit that scored
the ad.

## Data

- Runs: `drift-building-b0-latest-67d14e17-b9` and `drift-building-b0-market-67d14e17-n9`,
  the runs of the published diagnostics.
- Old columns: the published `/data1/apartments/site/diagnostics/ads.parquet` (26,405,129
  bytes, modified 2026-11-10 19:02 ET, sha256 `9c555f68086f13fa…`, 195,423 rows). The next
  publish replaces it, so `save_old.py` saved the columns compared here to
  `diagnostics-prev-ask-2026-11-20/old-prev.parquet` (1.9 MB).
- New table: the same runs rebuilt by `publish` at 76efd792 into
  `/data1/apartments/tmp/diag-prev/new/` (`publish.log`), never written to the site.
- The time adjustment uses the outlier sprint's repeat-ad index by quarter, for Manhattan and
  for the other boroughs (`repeat-index.parquet`).

The scripts and their logs are in `diagnostics-prev-ask-2026-11-20/`.

## Rows that change

7,540 of the 195,423 rows change `prev_ask` or `prev_day` (`compare.log`): 7,096 of the
latest fit's rows and 444 of the market fit's. Under the old rule their previous ad was
another piece of the apartment in 7,385 rows, a held-out ad of the fit in 934 and an ad of
the same day in 162 (`classify.log`; a row can have more than one of these). 407 rows lose
their previous ad and none gain one.

The group whose time-adjusted previous ask sits over 0.3 above the model's median held 2,006
ads. 1,956 of them keep a previous ask, 1,184 keep the same one, and 1,221 stay over 0.3.
The group now holds 1,275 ads (0.65% of all). Each table is compared against its own
median: since #1484 the market rows' quantiles are exact, which moves 6,461 market medians
by up to 1.1%.

`beds_jump` falls from 9,737 ads to 2,382 (1.2%), and `ask_jump` from 930 to 788.

## Deals

The ring on each row of Deals is `prev_ask` from the diagnostics table, joined by listing
id (`deals.log`). Of the 6,502 live deals (run
`drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3`, scoring day 2026-11-20),
2,942 show a ring, and 188 of those rings change under the fix (137 lose the ring). 2,462
deals have no diagnostics row at all, because the diagnostics come from the 2026-11-09 fits
and not from the fit Deals publishes. `docs/TODO.md` has an item for that.
