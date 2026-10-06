# Data collection — handoff

Updated 2026-10-06 20:05 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
- **Flatiron + Gramercy Park crawl: RUNNING** since Oct 5 12:25 ET (Ben typed the go in this thread).
  Unit `apartments-flatiron-gramercy-park-20261005`, runner `run-8pm-2w.py` (8/min, two workers),
  fallbacks `run-8pm.py` then `run-4pm.py`. Neighborhood `flatiron-gramercy-park` (#281): StreetEasy
  areas `flatiron` + `gramercy-park`, no child areas (NoMad). Frozen runtime master `efc2de7`.
  Controls: `data/probes/flatiron-gramercy-park-20261005/README.md` (local). Archive
  `/data1/apartments/archive/crawls/flatiron-gramercy-park-20261005`. Monitor
  `apartments-fgp-monitor.timer` (every 2 h at :17). Oct 6 20:00 ET: 14.9k requests (~$17),
  74 buildings finished. FGP buildings are much bigger than GV's (unit URLs per building median 47
  vs 5, mean 92 vs 14.5; ~190 requests per finished building), so the estimate was raised from
  $30–40 to 60k–160k requests, $70–180 (central ~$100), 5–14 more days; sent to Ben, who may set
  a dollar cap (stop the crawl there). Next spend report at $50.
- **Greenwich Village: crawl FINISHED, dataset BUILT** Oct 5: see "Dataset (Oct 5 2026)" in
  `docs/data/greenwich-village-collection.md`. Dataset
  `greenwich-village-granular-20261005-canonical-url-v1`, aliases `...-unit-spelling-aliases-v2`.
  Handed to Data improvements and Modeling via the coordinator. The GV monitor timer stays
  installed (Ben); it logs "crawl FINISHED: no relaunch".
- **Current listings** under `/data1/apartments/archive/current-listings/`: `20261004/`
  (Chelsea+West Chelsea 181 ACTIVE, West Village 109 ACTIVE + 1 RENTED) and
  `20261006-greenwich-village/` (Ben, Oct 6: 51 ACTIVE of 55 in-scope ads, 4
  canonical_unit_mismatch; GV without NoHo; 63 requests). The GV route and per-run seed subsets
  came in #375; the capture paused FGP (pause-and-swap, combined rate 8/min) and resumed it.
  Controls: `data/probes/current-listings-gv-20261006/` (local; `swap.sh` is the template for
  later refreshes). Rows: `details/snapshot/candidates.jsonl`, `listing_status == "ACTIVE"`.

## Next
- Watch the FGP crawl (429s, account errors, stalls); refine the estimate once the building list
  fills in. When it finishes: ask Ben once, then build the same way as GV (build script
  `/data1/apartments/tmp/gv-build-20261005/build.sh` is the template).

## Rules that bind this thread
- Oxylabs requests and new timers need Ben's words typed in this thread (the classifier blocks
  relayed approvals).
- Never raise rate/concurrency beyond Ben's setting (8/min); never loosen eligibility; crawl code
  only through a new frozen runtime directory.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
