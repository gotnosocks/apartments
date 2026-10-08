# Data collection — handoff

Updated 2026-10-07 21:15 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
- **Flatiron + Gramercy Park crawl: FINISHED** Oct 7 21:01 ET (spider `finish_reason: finished`).
  39,191 requests (~$45), no 429s or account errors, 372 coverage-gap 404s; 1,067 building, 450
  directory and 68k listing frontier entries. It ended with 8,659 pending that the run does not
  dispatch (GV also ended with 5,668). The last runner was `run-32pm-8w.py` (32/min, Ben, Oct 7), at
  about 31/min to the end. The monitor `apartments-fgp-monitor.timer` logs "crawl FINISHED: no
  relaunch". Neighborhood `flatiron-gramercy-park` (#281): StreetEasy `flatiron` + `gramercy-park`,
  without NoMad. Archive `/data1/apartments/archive/crawls/flatiron-gramercy-park-20261005` (48 GB DB).
  Controls are in `data/probes/flatiron-gramercy-park-20261005/README.md` (local).
- **FGP dataset: BUILDING** since Oct 7 21:08 ET as unit `apartments-fgp-build-20261007`. It is the
  GV `build.sh` template on master code (`/data1/apartments/tmp/fgp-build-20261007`, log
  `build.log`). Outputs: snapshot `/data1/apartments/archive/snapshots/flatiron-gramercy-park-20261005-final`,
  dataset `flatiron-gramercy-park-granular-20261007-canonical-url-v1`, aliases
  `...-unit-spelling-aliases-v2`, audit `audit.json`. Hand off to Data improvements and Modeling
  when it is done.
- **Greenwich Village: crawl FINISHED, dataset BUILT** Oct 5: see "Dataset (Oct 5 2026)" in
  `docs/data/greenwich-village-collection.md`. Dataset
  `greenwich-village-granular-20261005-canonical-url-v1`, aliases `...-unit-spelling-aliases-v2`.
  Handed to Data improvements and Modeling via the coordinator. The GV monitor timer stays
  installed (Ben); it logs "crawl FINISHED: no relaunch".
- **Current listings** under `/data1/apartments/archive/current-listings/`: `20261004/`
  (Chelsea+West Chelsea 181 ACTIVE, West Village 109 ACTIVE + 1 RENTED) and
  `20261006-greenwich-village/` (Ben, Oct 6: 51 ACTIVE of 55 in-scope ads, 4
  canonical_unit_mismatch; GV without NoHo; 63 requests). The GV route and per-run seed subsets
  came in #375; the capture paused FGP while it was running (pause-and-swap, combined rate 8/min) and resumed it.
  Controls: `data/probes/current-listings-gv-20261006/` (local; `swap.sh` is the template for
  later refreshes). Rows: `details/snapshot/candidates.jsonl`, `listing_status == "ACTIVE"`.

## Next
- Finish the FGP build, document it like GV's "Dataset (Oct 5 2026)", and hand it off.
- Ben, Oct 8 00:49 UTC: the Oxylabs budget is limited. Before proposing any new paid collection,
  estimate its value to the model (coverage gaps, unit-history depth) against its cost.

## Rules that bind this thread
- Oxylabs requests and new timers need Ben's words typed in this thread (the classifier blocks
  relayed approvals).
- Never raise rate/concurrency beyond Ben's setting (FGP's last setting: 32/min, Oct 7; it applies to any relaunch); never loosen eligibility; crawl code
  only through a new frozen runtime directory.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
