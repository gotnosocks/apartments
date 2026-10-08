# Data collection — handoff

Updated 2026-10-08 01:20 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
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

## Next
- **Storage review** (Ben, Oct 8): see `docs/data/archive-storage.md`. `streeteasy_archive.compact`
  (#471) copies a database without the duplicate provider HTML, saving 44%; the GV trial gave
  30.1 → 16.8 GB with an identical audit. Two proposals await Ben's typed go:
  1. "Delete the Chelsea and West Village crawl databases; keep the snapshots." Both
     (`crawls/chelsea-resume`, `crawls/west-village-low-rate-20260919`) cmp-match their snapshots
     apart from 4 header bytes (~199 GiB). Then repoint the disabled `apartments-archive.service`
     (:8765) at the Chelsea snapshot.
  2. "Compact the snapshots." Do one at a time (~125 GiB in total), check audit equality before
     each swap, regenerate `.sha256`, and never prune `bodies/`.
- Ben, Oct 8 00:49 UTC: the Oxylabs budget is limited. Before proposing any new paid collection,
  estimate its value to the model (coverage gaps, unit-history depth) against its cost.

## Rules that bind this thread
- Oxylabs requests and new timers need Ben's words typed in this thread (the classifier blocks
  relayed approvals).
- Never raise rate/concurrency beyond Ben's setting (FGP's last setting: 32/min, Oct 7; it applies to any relaunch); never loosen eligibility; crawl code
  only through a new frozen runtime directory.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
