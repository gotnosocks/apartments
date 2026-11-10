# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run.

## State at 2026-11-10 09:32Z

- **Served model.** `drift`. Its three full fits passed the gate (f6 on the latest split,
  m6 on the market dataset, k6 on the backtest; run names `drift-b0-latest-fabd6f9d-f6`,
  `drift-b0-market-fabd6f9d-m6`, `drift-b0-market-fabd6f9d-k6`). Held-out elpd 195,320,
  median abs error 0.0506, coverage 0.513 / 0.799 / 0.896 / 0.949.
- **Deals.** `/data1/apartments/site/deals` was published at 09:04Z from m6 with k6 and f6
  (6,774 ads). The site code that reads it is in PR #1281 and goes live with its merge and
  `ops/site-deploy.sh`.
- **Branch and PR.** `claude/project-thread-09vaqy`, PR #1281. The PR holds the model, the
  Deals page and the docs, because this thread may push one branch only.
- **`drift-building`.** Better by 35,565 elpd (230,885; median abs error 0.0406) and not
  served. Round six ran each fit as containers of 4 chains pooled by `drift_pool`: b6
  (latest, 12 chains) misses on drift_tau at R-hat 1.0106, n6 (market) on bld_sd[outer] at
  1.0135, and the backtest part j6a has frozen chain-to-chain offsets in bld_sd[outer]
  (R-hat 1.07). Pooled runs on thelio: `drift-building-b0-latest-7023bba1-b6`,
  `drift-building-b0-market-7023bba1-n6`. The lesson: R-hat is set by a chain's length, and
  an hour of 4 chains gives 1,600 draws where about 4,000 are needed.
- **Round seven, in flight.** The same code with 2 chains a container, three containers a
  fit: `b7a` to `b7c` on the latest split, `n7a` to `n7c` on the market dataset. `b7a` was
  launched at 09:29Z; the other five follow only if it sweeps in 0.75 s or less.
  Predictions are in the note. If the pooled market fit n7 passes, the Deals folder can be
  republished from it (its backtest j6 missed the gate and `meta.json` will say so).
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
  sweeps of 4 chains: `drift` 0.55 to 0.59 s, `drift-building` 1.14 to 1.28 s. Do not
  launch a long drift fit on the exploration tier: its cap of 1,800 s is below the budget.
- **What was ruled out** (so nobody tries it again). For the slow unit scales: stuck
  slices, directions of the wrong length, a trade-off with the building spreads, drawing
  lam with u integrated out, letting lam ride on its filtered distribution. For the frozen
  offsets in bld_sd[outer]: any traced quantity moving with it, and lone rows trading
  level against outlier weight (a toy mixes in 3.5 sweeps).
- **Review.** The model reviewer approved the fit code through `5c13cab`. The Deals page
  and docs were approved at `c290f9d`; everything in docs and the explainer since then
  needs the docs pass before merge.
- **Presentation.** `docs/notes/drift-2026-11-10/artifact/`: `pagedata.py` turns
  `artifact-data/extract-full.json` (written by `artifact-data/extract.py` on thelio) into
  the page's data and `build.py` writes the page.
- **Modal spend.** $70.94 through round six with j6b at its estimate; round seven is about
  $25 more if all six run.

## Next, in order

1. Build the explainer from `extract-full.json`, publish it as an Artifact, and commit the
   built page as `docs/model/drift-explainer.html`.
2. Docs review, then merge PR #1281 (squash, tag `archive/pr-1281`), deploy the site with
   `ops/site-deploy.sh`, and check `/deals`.
3. Round seven: score the predictions when the fits land, and replace the "was running
   when this was written" sentences in `README.md`, `docs/model/drift.md` and the round
   seven row of `docs/research-record.md` with the result. If n7 and b7 pass, republish and
   rebuild the explainer.
4. Final summary to Ben: links, Modal spend, what remains. The window ends 2026-11-11 00:02Z.

## Things a newcomer would trip on

- The feature snapshots are module constants with hard-coded paths. A dataset's
  `inputs.json` redirects them (`market.apply_inputs`), and `drift.design` applies it.
- The full design needs about 15 GB of memory, so it is built on Modal, not on thelio.
- All project timers on thelio are disabled since late October. Nothing is queued.
- `config/main-analysis.json` still selects the all-scraped fit of 2026-10-17, which failed
  the gate. The site's per-listing estimates come from it until the Deals page lands.
