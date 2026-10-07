# Data collection — handoff

Updated 2026-10-07 12:45 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
- **Flatiron + Gramercy Park crawl: RUNNING** since Oct 5 12:25 ET (Ben typed the go in this thread).
  Unit `apartments-flatiron-gramercy-park-20261005`, runner `run-32pm-8w.py` (32/min, eight
  workers) since Oct 7 11:53 ET (Ben, typed: 16/min first, then 32/min, 429s back to 8/min);
  `run-16pm-4w.py` ran 30 clean minutes first. On 429s the monitor steps down `run-32pm-8w.py` or
  `run-16pm-4w.py` → `run-8pm-2w.py` → `run-8pm.py` → `run-4pm.py` → STOPPED. Neighborhood
  `flatiron-gramercy-park` (#281): StreetEasy areas `flatiron` + `gramercy-park`, no child areas
  (NoMad). Frozen runtime master `efc2de7`. Controls: `data/probes/flatiron-gramercy-park-20261005/README.md`
  (local). Archive `/data1/apartments/archive/crawls/flatiron-gramercy-park-20261005`. Monitor
  `apartments-fgp-monitor.timer` (every 2 h at :17). No spend cap (Ben, Oct 6: "the Oxylabs budget
  will stop it"); Oxylabs documents no separate out-of-credit code, so budget exhaustion likely
  shows as 429 and ends in STOPPED via the step-down. Oct 7 12:43 ET: 23.8k requests (~$27), 188 of
  ~770 buildings, 31 of ~102 directory pages; median finished building 23 unit pages. Estimate:
  ~57k requests (~$65), finishing about Oct 8 06:00 ET (01:00–14:00). Report at $50 and at the end.
  Oxylabs plan limit is 50 jobs/s; the Oct 1 GV 429s came at 4/min (quota, not rate).
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
