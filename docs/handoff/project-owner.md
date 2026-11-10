# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run.

## State at 2026-11-10 11:09Z

- **Served model.** `drift`. Its three full fits passed the gate (f6 on the latest split,
  m6 on the market dataset, k6 on the backtest; run names `drift-b0-latest-fabd6f9d-f6`,
  `drift-b0-market-fabd6f9d-m6`, `drift-b0-market-fabd6f9d-k6`). Held-out elpd 195,320,
  median abs error 0.0506, coverage 0.513 / 0.799 / 0.896 / 0.949.
- **Deals.** `/data1/apartments/site/deals` was republished at 10:35Z from m6 with k6, f6
  and the ad texts (`--texts /data1/apartments/tmp/overhaul/texts-m6.parquet`), from
  master `9266983`, and the site deployed from the same commit. `/deals` shows 5,981 of
  6,774 ads by default, 793 left out for a caution, and the corrected backtest (28 to 61
  days on market, 18% to 60% cut, lowest tenth to highest). A reader classed 35 of the
  first 40 ads shown as ordinary apartments (10 of 22 before the cautions).
- **PRs.** #1281 (the model, the Deals page, the docs) merged as `252a82a`, head `f1380fc`.
  #1282 (cautions, the backtest on one basis) merged as `9266983`, head `93bbfca`. The tags
  `archive/pr-1281` and `archive/pr-1282` are not pushed: this thread can push only its
  own branch. Work after #1282 is on the same branch, `claude/project-thread-09vaqy`,
  with master merged in (a force push to restart it was refused), and goes in a third PR.
- **In the third PR, not yet merged or published.** The beds caution reads a split unit's
  pieces together (it missed 655 Hart St 2F, rank 2 of the list); after the merge,
  republish with the same command as above and deploy. Round seven's results and the
  cause of the building model's miss in the docs. `Settings.level_dof`.
- **`drift-building`.** Better by 35,541 elpd (230,861 in b7; median abs error 0.0407) and
  not served: every pooled fit misses the gate. Round seven (2 chains a container, chains
  of 2,920 to 3,440 draws) cured round six's misses on drift_tau and the sigmas and left
  one, bld_sd[outer]: R-hat 1.0130 in b7 (latest split), 1.0202 in n7 (market), 1.0447 in
  j6 (backtest, round six). The cause is found: about ten buildings of placeholder
  listings coded as studios at 3-bedroom rents sit 5 to 6 spreads out, cross one way
  over thousands of sweeps, and move the zone's spread by leverage under the normal prior
  on levels (the note, "Leverage"). Pooled runs on thelio:
  `drift-building-b0-latest-7023bba1-b6` and `-b7`, `drift-building-b0-market-7023bba1-n6`,
  `-n7` and `-j6`. Scripts for every check: `/data1/apartments/tmp/overhaul/artifact-data/`
  (`qoffset.py`, `holds.py`, `crossings.py`, `conflicts.py`, `leverage.py`, `jobe/`).
- **Round eight.** One container, `b8c`: `drift-building --level-dof 4` (a Student-t prior
  on building levels) on the latest split with `b7c`'s settings and seed. Predictions are
  in the note. If it is not launched or not scored when you read this, check the note's
  last section before doing anything.
- **Data.** A one-off scrape on 2026-11-10 brought the listings to 2026-11-09 (pipeline build
  `ddd2fe8f5da041b8`). On thelio: `frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market`
  (6,774 ads on the market) and `...-asof-20251110` (the backtest, 9,346 on the market that
  day; its name has no `-market-`). The latest split is on
  `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`.
- **Model code.** `rentfrontier.drift`, `drift_building`, `drift_local` (not refit after
  round two), `drift_score`, `drift_deals` (publish refuses a market fit that missed the
  gate), `drift_pool`.
- **Limits on a fit.** A drift fit stops its sweeps at 2,520 s and saves what it has; the
  container is killed at 75 minutes. Outside the sweeps a fit takes 13 to 15 minutes. H100
  sweeps of 4 chains: `drift` 0.55 to 0.59 s, `drift-building` 1.14 to 1.28 s; of 2
  chains, `drift-building` 0.61 to 0.75 s. R-hat is set by a chain's length, so run the
  building model as containers of 2 chains and pool them with `drift_pool`. Do not
  launch a long drift fit on the exploration tier: its cap of 1,800 s is below the budget.
- **What was ruled out** (so nobody tries it again). For the slow unit scales: stuck
  slices, directions of the wrong length, a trade-off with the building spreads, drawing
  lam with u integrated out, letting lam ride on its filtered distribution. For the
  offsets in bld_sd[outer]: any traced quantity moving with it, lone rows trading level
  against outlier weight (a toy mixes in 3.5 sweeps), and conflicting ads within a unit
  (6,857 pairs in the outer boroughs, carrying 3% of it).
- **Review.** Everything in PRs #1281 and #1282 was reviewed before its merge. Work after them needs a
  fresh review: a model reviewer for model, selection, data or ops code, a Sonnet reviewer
  for docs and site pages.
- **Presentation.** `docs/notes/drift-2026-11-10/artifact/`: `pagedata.py` turns
  `artifact-data/extract-full.json` (written by `artifact-data/extract.py` on thelio) into
  the page's data and `build.py` writes the page.
- **Modal spend.** $90.79 settled after round seven ($92.44 with two upper bounds, one a
  preempted run's minutes and one a stopped launch). Round eight's container is about
  $3.85. Nothing else is to be launched inside the $100.

## Next, in order

1. Round eight: launch `b8c` after the code review, score its six predictions in the note,
   and say in `README.md`, `docs/model/drift.md` and the record what it showed.
2. The third PR: review (a model reviewer for the code, a Sonnet reviewer for the docs),
   squash-merge, then republish the Deals folder and deploy, and check that 655 Hart St
   2F carries the beds caution.
3. Final summary to Ben: links, Modal spend, what remains. The window ends 2026-11-11 00:02Z.
4. After the window, with a new budget: the three full fits of `drift-building` under
   whichever fix round eight supports, then publish from it. The data rule for
   studio-coded ads that are not studios is in `docs/TODO.md`.

## Things a newcomer would trip on

- The feature snapshots are module constants with hard-coded paths. A dataset's
  `inputs.json` redirects them (`market.apply_inputs`), and `drift.design` applies it.
- The full design needs about 15 GB of memory, so it is built on Modal, not on thelio.
- All project timers on thelio are disabled since late October. Nothing is queued.
- `config/main-analysis.json` still selects the all-scraped fit of 2026-10-17, which failed
  the gate. The site's per-listing estimate pages still come from it; the Deals page does not.
