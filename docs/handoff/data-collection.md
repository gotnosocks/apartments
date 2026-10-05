# Data collection — handoff

Updated 2026-10-05 10:00 ET. Thread owner: the Data collection project thread (bridge session on thelio).

## State
- **Greenwich Village crawl: FINISHED** Oct 4 23:54 ET (`finish_reason: finished`). 25,187 observations,
  774 in-scope buildings, 8,635 units with canonical rental membership. The 5,668 frontier rows still
  "pending" are out of scope (citywide/other-area links) and never claimed. Do not relaunch.
  Controls and history: `data/probes/greenwich-village-20261001/README.md` (local, gitignored).
  Archive: `/data1/apartments/archive/crawls/greenwich-village-20261001`. Findings:
  `docs/data/greenwich-village-collection.md`.
- Safety timer `apartments-gv-monitor.timer` (monitor.py, :47 every 2 h) still runs and logs
  "crawl FINISHED: no relaunch"; it honours a `PAUSED` file. Ben may want it disabled.
- **Current listings** (one-off, Ben "Capture once", no weekly refresh): captured Oct 5 01:47–02:30 UTC,
  344 requests. Chelsea+West Chelsea 181 ACTIVE, West Village 109 ACTIVE + 1 RENTED, 8 identity
  mismatches. Output `/data1/apartments/archive/current-listings/20261004/details/snapshot/candidates.jsonl`
  (seed per ad in `review/detail-review-queue.jsonl`). Site/data side turns them into
  `current_capture_gross_ask` rows (as `models/fit_robust_analysis.current_rows` did for Chelsea);
  handed to the coordinator for the Website thread. Kit: `data/probes/current-listings-20261004/`.

## Waiting on Ben
- "build GV"? Ben said (Oct 4) to build the GV dataset once, after the crawl, and to ask first. Asked
  Oct 5 ~13:55 UTC. Plan: snapshot under the crawler lock, transform to a new dataset ID, collection
  audit (`--data` dir must hold `archive.sqlite3` and `bodies/`), unit spelling-alias table with the
  #213 v2 rule (history-confirmed groups only; ~166 of 190 spelling-excluded ads recovered). All via
  `ops/job light`, no requests.

## Rules that bind this thread
- Oxylabs requests need Ben's explicit word in the thread (the classifier blocks relayed approvals).
- Never raise rate/concurrency beyond Ben's setting (8/min); never loosen eligibility; deploy crawl
  code only through a new frozen runtime directory.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
