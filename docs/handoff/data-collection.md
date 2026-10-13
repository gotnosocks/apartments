# Data collection — handoff

Updated 2026-10-13 11:40 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
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
  for ads that open on their own page. Next: Ben decides on 1 or 2 live check requests (does
  `/building/330-1-avenue-new_york/05e` list ad 3822968?) and on any resume.
- **Unit pages could be skipped (Oxylabs check, `unitcheck/` in that probe dir).** On 30 Manhattan
  pilot buildings the probe-style guess from the API's `displayUnit` gives the crawl's unit for
  5,844/5,857 post-cutoff ads (12 of 13 misses are zero-padded spellings). The API lists 1,066
  more post-cutoff ads no unit page vouched for: 900 sit on a unit page the crawl never fetched
  (API slug `05e`, crawl guessed `/5e` → 404), so the label guess misses real unit records; 166
  have a unit page that vouched for nothing. Ben kept unit pages as the association source
  (StreetEasy's own data, dedup on unit URLs), so no API vouching rule; the unit-path probe
  above (#708) is what he chose.
- **Brooklyn crawl STOPPED on Oxylabs 429s (likely credits), waiting on Ben.** Ran Oct 12 23:01 ET at 64/min: Downtown Brooklyn + Fort Greene +
  Boerum Hill as one scrape (neighborhood `downtown-brooklyn-fort-greene-boerum-hill`, #695–#697).
  Service `apartments-brooklyn-pass-20261013`, controls `data/probes/brooklyn-pass-20261013/`
  (runner `run-64pm-16w.py`, fallback `run-32pm-8w.py` on 429s), archive
  `/data1/apartments/archive/crawls/brooklyn-dtbk-fg-bh-20261013`. No monitor timer. Ben, typed
  Oct 13: "go at 64/min if possible until the credits run out"; 03:04Z: "If oxylabs starts
  refusing just stop and wait for me to resolve by adding credits on oxylabs." On a credit or
  account refusal: leave it stopped, tell Ben, resume only on his word. Estimate 75–200k requests
  ($85–225), 20–50 h. When it finishes: snapshot (compacted), dataset, tell Modeling and Data
  improvements (first Brooklyn rows; Manhattan-only features need checking).
  Stopped Oct 13 03:24 ET: every request since 03:01 ET returned HTTP 429 (447 in a row) after
  7 h with no 429s at the same rate, so most likely credits ran out. Ben told 03:24 ET. At the stop:
  12,322 pages done (12,049 OK, 273 404), 71,510 pending (detail pages), about $14–15 spent.
  On Ben's word that credits are added: `systemctl --user reset-failed` the unit and relaunch the
  same runner (it resumes), or a GraphQL-flag runtime if Ben chooses it (see above). 429s again: `run-32pm-8w.py`; still at 32/min: stop and ask Ben.
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
- **No daily refresh** of current listings exists; every capture so far was on demand. Proposed
  to Ben Oct 10 (about 2–3k requests a day, roughly $2–4); awaiting his typed answer.

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
- Ben, Oct 8 00:49 UTC: the Oxylabs budget is limited. Before proposing any new paid collection,
  estimate its value to the model (coverage gaps, unit-history depth) against its cost.

## Rules that bind this thread
- Oxylabs requests and new timers need Ben's words typed in this thread (the classifier blocks
  relayed approvals).
- Never raise rate/concurrency beyond Ben's setting (FGP's last setting: 32/min, Oct 7; the Oct 8 crawls: 32/min combined, then 64/min from Oct 9); never loosen eligibility; crawl code
  only through a new frozen runtime directory.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
