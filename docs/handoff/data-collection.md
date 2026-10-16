# Data collection — handoff

Updated 2026-10-16 10:10 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
- **Area collection through the GraphQL API (Oct 15).** Ben, Oct 14 22:23 ET, asked for a
  cheaper scraper to collect Manhattan below 59th St and Brooklyn north and west of Prospect
  Park, and to top up the dataset on a schedule. At 22:57 ET he agreed that units' histories may
  come from the API in place of unit pages, and at 00:37 ET he approved the backfill with north
  Brooklyn, Crown Heights and Manhattan up to 110th St (not a re-read of crawled areas). Changes to
  `streeteasy_archive.graphql_search` and `ops/streeteasy-collect` go through the "faster,
  cheaper" thread; see `docs/data/graphql-collection.md`. Offline on NoMad it needed 86 requests against the page
  crawl's 13,504 and found 22% more memberships, with every shared ad on the same unit. Every
  region writes into the shared archive, `crawls/api`, and each run records its region. Collections take `crawls/oxylabs.lock`; a page crawl started beside
  them should run under `flock` on the same file so the combined rate stays within 64/min.
  `apartments-streeteasy-topup.timer` (Fridays 05:30 ET) reads current ads of every region
  into `current-listings/api-REGION`. Ben asked in the thread on Oct 15 (09:42 ET) for a weekly
  top-up in place of a daily one, and the timer went in that day. Its first run, Fri Oct 16
  from 05:30 to 05:49 ET, found 7,011 ACTIVE ads in 120 requests ($0.14) as runs 6 to 10. The
  site counts an ad as on the market for 9 days after its last capture
  (`CURRENT_DAYS` in `src/apartments/site/captures.py`, widened from 7 by the Website thread
  in #836), so an ad stays on the site through the next Friday's run even when a backfill
  holding `oxylabs.lock` at 05:30 delays the top-up by up to 18 hours.
  The backfill reopens a finished run with `--reopen`. A band of one price splits by bedrooms
  (#849, 8 meaning 8 or more), then by area (#834), then by map box starting from the four boxes
  around New York (#843, #853), until each part holds 1,000 ads or fewer and gets read from one
  end (#850). #852 retries Oxylabs answers with no status or content. The last reopen ran from
  13:51 to 14:34 ET on Oct 15 in 1,081 requests ($1.23) and left every region's IDs at or above
  its count, with no pending, truncated or unanswered band. The four runs total 10,265 requests
  ($11.69); `docs/data/graphql-collection.md` has the tables. The dataset
  `datasets/api-granular-20261015-canonical-url-v1` (1.71 million ads on 767,445 units), its
  aliases `...-unit-spelling-aliases-v2` and the snapshot `snapshots/api-20261015` (taken 12:47
  ET, after the box reopen and before the bedroom and split reopens) came from
  `/data1/apartments/tmp/api-build-20261015/build.sh`. After each Friday top-up, check
  `crawls/streeteasy-collect.log` for each region's exit and the export's, check that each
  region's `current-listings/api-REGION` link moved, tell the coordinator so the Website thread
  rebuilds the site data, and message the pipeline thread's session with the new runs.
  `apartments-streeteasy-backup.timer` (09:00 ET) copies `crawls/api` to
  `/data2/apartments-backup/streeteasy-api` (Ben asked for a scheduled backup, Oct 15 03:57 ET).
- **Re-read of the page-crawl areas (run 5, Oct 15).** Ben approved it at 15:50 ET. Run 5
  (`backfill manhattan-page-crawl-areas`, no unit histories) ran from 15:52 to 17:48 ET in 2,054
  requests ($2.34). Its searches found 522,774 ad IDs, equal to the count, with no pending,
  truncated or unanswered band. It read 424,776 ads and wrote 160,579 units and 8,003 buildings.
  The IDs it left unread fall below the listing-ID cutoff or were already final in the archive.
  The dataset and snapshot above predate it. On Oct 16 I found 2,261 ads at or above the cutoff
  in its units' histories with no archive entry, so the region now reads unit histories like
  the others (#908). Run 11, a top-up of the region from 09:46 to 09:50 ET (25 requests, $0.03),
  read them. 2,222 of the 2,266 ads it read for the first time are DRAFT and 1 is RENTED, so the
  dataset gains almost no listings.
- **Raw Parquet export (#863, #864).** `streeteasy_archive.graphql_export` writes every reply of
  each run to `crawls/api/export/{ads,buildings,requests,calls}/run-NNNN/` and lists the files
  in `manifest.ndjson`. `ops/streeteasy-collect` runs it at the end of each invocation and logs
  "export exit N". Runs 1 to 10 are exported and match the archive (checked by hand). A call
  row's `attempt` holds its POST count, so `sum(attempt)` gives a run's requests. The "API
  data pipeline rebuild" thread reads the export; message its session after each new run.
- **GraphQL past-rentals reads (no-JS), Oct 13.** Ben 09:42 ET: switch the Brooklyn crawl to
  StreetEasy's GraphQL `rentalsHistoryByBuildingId` (api-v6, plain Oxylabs GET with
  `apollo-require-preflight`, 24 buildings/request, browser as fallback). Built as #705
  (`streeteasy_archive/graphql_inventory.py`, crawl flag `--graphql-inventory`). Ben 09:53 ET:
  "DO NOT RESUME THE SCRAPE YET ... only test the no-JS change" ($10 added for testing). Tested
  with 8 requests (`data/probes/graphql-inventory-test-20261013/`): 96/96 Brooklyn histories
  contain every browser-list ad (1,007; API has 2,041 = all ads per unit, the browser list
  shows only the latest per unit); end to end on a scratch archive 30/30 recorded, no fallbacks.
  It replaces only the rendered list step; unit and ad pages are plain requests and still
  fetched. **Resume needs Ben's word** and a new frozen runtime from master with the flag.
- **Unit paths from the API (#708, merged Oct 13).** Ben 11:10 ET agreed to visit the
  `/building/<building>/<unit>` path StreetEasy gives as each ad's `urlPath` instead of guessing
  the unit route from the label. Flag `--graphql-unit-paths` (with `--graphql-inventory`). Ads
  whose `urlPath` is `/rental/ID` keep the label guess. Membership still comes only from the
  unit page's history; the rule and dedup are unchanged. Offline on the 30 pilot responses:
  2,743 API unit paths replace 3,128 label guesses (2,251 of which were right), plus 743 guesses
  for ads that open on their own page.
- **One spelling per unit (#710, merged Oct 13).** Ben asked for `/04c` at 240 1st Ave (1
  Oxylabs request, 9 of the $10 test budget used): it lists the same 7 ads as the captured `/4c`,
  so StreetEasy keeps two records for one unit and fetching both would exclude those ads as
  conflicting. With `--graphql-unit-paths` the crawl now compares spellings as letter and digit
  runs without leading zeros. A label guess yields to an API path, an API path yields to a
  captured, in-flight, deferred or linked spelling, and a pending guess is superseded (the
  probe keeps the newer source ad for the cutoff). Pilot: guesses 743 -> 508; 112 API paths
  give way to spellings already captured. Known nit: an older probe reason already in
  `scope_urls` wins over a newer one (INSERT OR IGNORE). Next: Ben decides on any resume; the
  Brooklyn scrape stays stopped until he says so.
- **Unit pages could be skipped (Oxylabs check, `unitcheck/` in that probe dir).** On 30 Manhattan
  pilot buildings the probe-style guess from the API's `displayUnit` gives the crawl's unit for
  5,844/5,857 post-cutoff ads (12 of 13 misses are zero-padded spellings). The API lists 1,066
  more post-cutoff ads no unit page vouched for: 900 sit on a unit page the crawl never fetched
  (API slug `05e`, crawl guessed `/5e` → 404), so the label guess misses real unit records; 166
  have a unit page that vouched for nothing. Ben kept unit pages as the association source
  (StreetEasy's own data, dedup on unit URLs), so no API vouching rule; the unit-path probe
  above (#708) is what he chose.
- **Brooklyn archive deleted Oct 13 (Ben 12:23 ET), restart from scratch.** The Oct 12 run
  (Downtown Brooklyn + Fort Greene + Boerum Hill, `brooklyn-dtbk-fg-bh-20261013`, 9.7 GB,
  stopped on Oxylabs 429s) is gone, with its failed transient service. Ben asked whether
  dropping it and restarting was simpler: a restart in place needed a way to close the old
  queue (#715, closed unmerged), and the old modal histories had no unit paths. An offline dry
  run of that restart queued 76,249 pages and skipped 9,212 recent captures, which a fresh run
  fetches again. Ben had the database of the small `downtown-brooklyn-20261013` (131 pages)
  deleted on Oct 14 at 15:00Z and the rest of its folder at 15:20Z. Ben moved the next crawl to Midtown West (below) at 12:25 ET.
- **Midtown West: crawl FINISHED** Oct 14 11:09Z (109,765 requests, about $125, no 429s or
  account errors), **dataset BUILT** 12:20Z: see `docs/data/midtown-west-collection.md`. The
  service `apartments-midtown-west-20261013` has exited, and no crawl is running. The snapshot
  matched the crawl database on every row and on the audit. Compaction stripped nothing, since
  the crawl already stored compact captures. Ben had the crawl database (74 GB), which
  duplicated the snapshot, deleted on Oct 14 at 15:00Z; `bodies/` stays. Paths went to Modeling and Data improvements on
  Oct 14. Data improvements decides how Midtown West joins the analysis dataset.
  - For the next crawl: with 32 workers the crawler fetched 105 to 117 pages a minute, limited
    by the parse work on its main thread and by a pacer that let each slot's lateness carry into
    the next, so 128/min nominal gave about 113/min. Two merged fixes address this and take
    effect on the next frozen runtime:
    - #753 (`known_links.py`) skips scope enrolment for links already enrolled as they would be
      written. On 30 ad pages of a copy of the Midtown West database it skipped all 40,973 links,
      and parse time per ad page went from 0.21 s to about 0.15 s.
    - #754 (`pacer.py`) keeps submissions on a fixed grid of slots with at least 0.85 intervals
      between them, so the rate stays at or below the setting, and lateness under 15% of an
      interval no longer lowers it.
    - #756 (`parse_once.py`) reuses the first `parse_listing` result for the second
      `annotate` call on the same page. On 60 ad pages the two calls went from 0.036 s to
      0.018 s per page with identical policy data.
    - On 30 ad pages run through the spider's parse, the fixes together took main-thread
      time from 0.21 s to 0.12 s per ad page (Oct 14). The profiling scripts are in
      `/data1/apartments/tmp/mwprof2-scripts`; they expect a copy of a crawl database, and
      the 36 GB copy they ran on is deleted.
  - A restart replays every page fetched since the previous start before it sends new
    requests, at about 11 pages a second.
- **Brooklyn scout** Oct 13 (22 requests): `data/probes/brooklyn-scout-20261013/README.md` has
  live rentals and directory pages for Greenpoint, Williamsburg, East Williamsburg, Bushwick, Park
  Slope, Prospect Heights, Boerum Hill, Fort Greene, Clinton Hill, Downtown Brooklyn. Suggested
  next: Greenpoint, Williamsburg, Clinton Hill; Park Slope and Bushwick last (cost per rental).
- **Stuyvesant Town/PCV: crawl FINISHED** Oct 8 15:21 ET (6,139 requests, ~$7, no 429s),
  **dataset BUILT** 15:41 ET: see `docs/data/stuyvesant-town-pcv-collection.md`. Snapshot written
  compacted (5.9 → 3.3 GB, rows and audit verified). `apartments-stuytown-monitor.timer` disabled.
  Handed to Data improvements and Modeling via the coordinator.
- **NoMad: crawl FINISHED** Oct 9 08:39 ET (13,504 requests, ~$15), **dataset BUILT** 08:59 ET:
  see `docs/data/nomad-collection.md`. Snapshot written compacted (20.4 → 11.5 GB, rows and audit
  verified). `apartments-nomad-monitor.timer` disabled. Handed to Data improvements and Modeling
  via the coordinator.
- **East Village: crawl FINISHED** Oct 10 05:55 ET (82,979 requests, ~$95, no 429s after Oct 8),
  **dataset BUILT** 07:02 ET: see `docs/data/east-village-collection.md`. Building-first from
  16:10 ET Oct 9 (#620, now the default claim order for backfill/update/resume) and 64/min from
  18:57 ET Oct 9 (Ben, typed 22:56 UTC: "Double the rate to 64/min"). Snapshot written compacted
  (99.7 → 55.7 GB, rows and audit verified). `apartments-ev-monitor.timer` and
  `apartments-rate-balance.timer` disabled; no crawl is running. Handed to Data improvements and
  Modeling via the coordinator.
- **EV, NoMad and Stuy Town crawl databases deleted** Oct 10 16:00 ET (Ben, typed: "delete
  them."): `/data1` went from 230 to 347 GB free. Kept: the three `snapshots/*-final`, each
  crawl's `bodies/`, and all datasets.
- **NoMad, East Village crawl setup**: launched Oct 8 02:23 ET (Ben, typed
  06:19 UTC). One StreetEasy area each (`nomad`, `east-village`, `stuyvesant-town`; #482), FGP
  policy, launched at `run-8pm-2w.py` each (24/min combined), fallback 8pm → 4pm → STOP; monitors
  `apartments-{nomad,ev,stuytown}-monitor.timer`. **Combined 32/min** (Ben, typed Oct 8 15:53
  UTC: "manipulate the scrape rates as each one finishes so that the overall rate stays at
  32/min"): `data/probes/rate-balance-20261008/rebalance.py` (local; `apartments-rate-balance.timer`,
  every 15 min) gives each live crawl 8/min and the rest to the first live one of EV, Stuy Town,
  NoMad (runners `run-16pm-4w`, `run-24pm-6w`, `run-32pm-8w`; a 429 step-down from them goes to
  `run-8pm-2w`). EV on 16/min from 11:55 ET, 24/min from 15:35 ET (Stuy Town finished); paused 18:40–20:00 ET. It holds while any crawl has a recent 429, a PAUSED
  file or a monitor step-down. Disable the timer once all three finish. Controls: `data/probes/<name>-20261008/README.md`
  (local); archives `/data1/apartments/archive/crawls/<name>-20261008`. Estimates from FGP's ratio:
  NoMad ~8k requests (~$9), EV ~70k (~$80), Stuy Town 15–30k (unit pages dominate). When each
  finishes: snapshot, compact the snapshot (`streeteasy_archive.compact`), build the dataset,
  audit and alias table as for FGP, and hand off via the coordinator.
- **Flatiron + Gramercy Park crawl: FINISHED** Oct 7 21:01 ET (spider `finish_reason: finished`).
  39,191 requests (~$45), no 429s or account errors, 372 coverage-gap 404s; 1,067 building, 450
  directory and 68k listing frontier entries. It ended with 8,659 pending that the run does not
  dispatch (GV also ended with 5,668). The last runner was `run-32pm-8w.py` (32/min, Ben, Oct 7), at
  about 31/min to the end. Neighborhood `flatiron-gramercy-park` (#281): StreetEasy `flatiron` +
  `gramercy-park`, without NoMad. Crawl bodies in `/data1/apartments/archive/crawls/flatiron-gramercy-park-20261005/bodies`.
  Controls are in `data/probes/flatiron-gramercy-park-20261005/README.md` (local).
- **FGP dataset: BUILT** Oct 7 21:30 ET: see "Dataset (Oct 7 2026)" in
  `docs/data/flatiron-gramercy-park-collection.md`. Dataset
  `flatiron-gramercy-park-granular-20261007-canonical-url-v1`, aliases `...-unit-spelling-aliases-v2`.
  Reported to Ben and the coordinator for Data improvements and Modeling.
- **Crawl databases deleted** Oct 8 00:40 ET (Ben, typed: "Delete the FGP and GV crawl databases;
  keep the snapshots."). Each snapshot matched its crawl DB apart from 4 header bytes. Kept: both
  `snapshots/*-final`, both crawls' `bodies/`, and all datasets. `/data1` went from 37 to 109 GB free.
  `apartments-gv-monitor.timer` and `apartments-fgp-monitor.timer` are disabled; their unit files
  stay. A re-crawl starts from a writable copy of the snapshot. Active-listing top-ups
  (`data/probes/current-listings-gv-20261006`) never read crawl databases.
- **Greenwich Village: crawl FINISHED, dataset BUILT** Oct 5: see "Dataset (Oct 5 2026)" in
  `docs/data/greenwich-village-collection.md`. Dataset
  `greenwich-village-granular-20261005-canonical-url-v1`, aliases `...-unit-spelling-aliases-v2`.
  Handed to Data improvements and Modeling via the coordinator. Its crawl database is deleted
  (see above).
- **Current listings** under `/data1/apartments/archive/current-listings/`: `20261004/`
  (Chelsea+West Chelsea 181 ACTIVE, West Village 109 ACTIVE + 1 RENTED) and
  `20261006-greenwich-village/` (Ben, Oct 6: 51 ACTIVE of 55 in-scope ads, 4
  canonical_unit_mismatch; GV without NoHo; 63 requests). The GV route and per-run seed subsets
  came in #375; the capture paused FGP while it was running (pause-and-swap, combined rate 8/min) and resumed it.
  Controls: `data/probes/current-listings-gv-20261006/` (local; `swap.sh` is the template for
  later refreshes). Rows: `details/snapshot/candidates.jsonl`, `listing_status == "ACTIVE"`.
- **Current listings, Oct 10** (Ben, typed 19:09 UTC: "go ahead with scraping the new
  neighborhoods for active listings"): `20261010-{flatiron,gramercy-park,nomad,east-village,stuyvesant-town}/`,
  15:16–15:32 ET at 30/min, 366 requests (~$0.40): 38, 46, 56, 141 and 25 ACTIVE; 9
  `canonical_unit_mismatch` failures. Needed #662 (`rental-search-v4`: the five routes and
  StreetEasy's new `listingData` search template, live since about Oct 8). Controls:
  `data/probes/current-listings-new-areas-20261010/` (local; `run-capture.py`, `run-all.sh`).
  The Website thread reads them; its reader measures the 7-day window from today (#665) and lets
  a newer capture replace a unit's dataset row (#667).
- **History crawl → current listings** (#664, Ben 19:11 UTC): `apartments.crawl_current_listings`
  turns a finished crawl's newest-ACTIVE ads into `candidates.jsonl` with no requests, dated by
  page capture time. Not published: the Oct 10 capture is newer for those areas.
- **Weekly refresh**: `apartments-streeteasy-topup.timer` (see the GraphQL entry above) replaces
  the on-demand captures for every area in its regions.

## Next
- **Storage review** (Ben, Oct 8): see `docs/data/archive-storage.md`. `streeteasy_archive.compact`
  (#471) copies a database without the duplicate provider HTML, saving 44%; the GV trial gave
  30.1 → 16.8 GB with an identical audit. Proposals:
  1. DONE Oct 8 01:50 ET (Ben, typed): deleted the `archive.sqlite3` files (with `-wal` and
     `-shm`) in `crawls/chelsea-resume` and `crawls/west-village-low-rate-20260919`. Each had
     matched its snapshot apart from 4 header bytes. `/data1` went from 108 to 308 GB free. Logs
     and bodies stay. The disabled `apartments-archive.service` now serves
     `archive/browse/chelsea-backfill-20260912` (symlinks to the snapshot and `archive/bodies`).
  2. DONE Oct 8 04:16 ET (Ben, typed: "Compact the snapshots."): all six snapshots compacted
     and swapped in, 304.7 → 170.9 GB (see `docs/data/archive-storage.md`). Never prune `bodies/`.
     The `bytes` in `snapshots/chelsea-20260908/complete.json` is the pre-compaction size.
  3. DONE Oct 10 (#671, Ben: "Stop at 671"): the crawler writes the provider envelope without
     its HTML copy, so new crawl databases are compact and need no compaction step. Compressing
     `extracted` or dropping `scripts` is declined.
- Ben, Oct 15 12:14 ET, gave this thread standing permission to spend Oxylabs credits. His Oct 8
  note that the budget is limited no longer applies, though a new paid collection still needs an
  estimate of its value to the model against its cost.

## Rules that bind this thread
- New timers need Ben's words typed in this thread, since the classifier blocks relayed
  approvals. Oxylabs requests go ahead under his Oct 15 12:14 ET permission; when the classifier
  blocks one, cite that message.
- Never raise rate/concurrency beyond Ben's setting (FGP's last setting: 32/min, Oct 7; the Oct 8 crawls: 32/min combined, then 64/min from Oct 9); never loosen eligibility; crawl code
  only through a new frozen runtime directory.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
