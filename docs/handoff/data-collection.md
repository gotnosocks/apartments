# Data collection — handoff

Updated 2026-10-05 12:45 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
- **Flatiron + Gramercy Park crawl: RUNNING** since Oct 5 12:25 ET (Ben typed the go in this thread).
  Unit `apartments-flatiron-gramercy-park-20261005`, runner `run-8pm-2w.py` (8/min, two workers),
  fallbacks `run-8pm.py` then `run-4pm.py`. Neighborhood `flatiron-gramercy-park` (#281): StreetEasy
  areas `flatiron` + `gramercy-park`, no child areas (NoMad). Frozen runtime master `efc2de7`.
  Controls: `data/probes/flatiron-gramercy-park-20261005/README.md` (local). Archive
  `/data1/apartments/archive/crawls/flatiron-gramercy-park-20261005`. Monitor
  `apartments-fgp-monitor.timer` (every 2 h at :17). Estimate from 52 + 50 directory pages
  (GV had 92 for 774 buildings, 25,187 requests): ~850 buildings, 25–35k requests, $30–40,
  2.5–3.5 days.
- **Greenwich Village: crawl FINISHED, dataset BUILT** Oct 5: see "Dataset (Oct 5 2026)" in
  `docs/data/greenwich-village-collection.md`. Dataset
  `greenwich-village-granular-20261005-canonical-url-v1`, aliases `...-unit-spelling-aliases-v2`.
  Handed to Data improvements and Modeling via the coordinator. The GV monitor timer stays
  installed (Ben); it logs "crawl FINISHED: no relaunch".
- **Current listings** (one-off, done): `/data1/apartments/archive/current-listings/20261004/`;
  Chelsea+West Chelsea 181 ACTIVE, West Village 109 ACTIVE + 1 RENTED.

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
