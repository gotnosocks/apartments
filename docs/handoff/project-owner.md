# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run.

## State at 2026-11-10 10:26Z

- **Served model.** `drift`. Its three full fits passed the gate (f6 on the latest split,
  m6 on the market dataset, k6 on the backtest; run names `drift-b0-latest-fabd6f9d-f6`,
  `drift-b0-market-fabd6f9d-m6`, `drift-b0-market-fabd6f9d-k6`). Held-out elpd 195,320,
  median abs error 0.0506, coverage 0.513 / 0.799 / 0.896 / 0.949.
- **Deals.** `/data1/apartments/site/deals` was published at 09:04Z from m6 with k6 and f6
  (6,774 ads). The site was deployed from master `252a82a` at 09:42Z and `/deals` shows
  the table, the model line and the backtest.
- **Follow-up PR #1282** (open, code and docs reviewed): cautions on the deals table and
  the page, and the backtest corrected to one basis. After its merge, on thelio:
  `drift_deals publish drift-b0-market-fabd6f9d-m6 --out /data1/apartments/site/deals
  --registry REGISTRY --backtest drift-b0-market-fabd6f9d-k6 --heldout
  drift-b0-latest-fabd6f9d-f6 --texts /data1/apartments/tmp/overhaul/texts-m6.parquet`
  (the texts table was written by `drift_deals texts` at `98ec2b6`), then
  `ops/site-deploy.sh`, then rebuild and republish the explainer from the new
  `extract-full.json`. Until then the live page and the explainer show the uncorrected
  backtest.
- **The backtest was wrong for ads with free months** and is corrected in #1282: asks
  are net of free months, price histories are gross, and `validate` compared the two. The
  corrected table: lowest tenth to highest, 28 to 61 days on market and 18% to 60% cut
  (first published as 27 to 62 days and 18% to 79%). Ben was told at 10:07Z.
- **Cautions.** 793 of the 6,774 market ads carry one (`rentfrontier.cautions`); the page
  leaves them out unless asked. The model's own text flags are wrong often and are a TODO.
- **Branch and PR.** PR #1281 (the model, the Deals page and the docs) was squash-merged
  as `252a82a`. Its head was `f1380fc`; the tag `archive/pr-1281` is not pushed, because
  this thread can push only its own branch (Ben has been told). Follow-up work is on the
  same branch, `claude/project-thread-09vaqy`, with master merged in (a force push to
  restart it was refused), and goes in a new PR.
- **`drift-building`.** Better by 35,565 elpd (230,885; median abs error 0.0406) and not
  served. Round six ran each fit as containers of 4 chains pooled by `drift_pool`: b6
  (latest, 12 chains) misses on drift_tau at R-hat 1.0106, n6 (market) on bld_sd[outer] at
  1.0135, and the backtest j6 (8 chains of 1,550) on bld_sd[outer] at 1.0447 with ESS 68:
  two chains sit near 0.0923 and six near 0.0927 to 0.0928 for the whole run. About five
  buildings in 68,000 hold one of two levels for a whole chain and carry about a quarter
  of the offset. The rest is a shift shared thinly across the outer buildings' levels,
  frozen within a chain, source unknown (the note, "The direct check"). Pooled runs
  on thelio: `drift-building-b0-latest-7023bba1-b6`, `drift-building-b0-market-7023bba1-n6`,
  `drift-building-b0-market-7023bba1-j6`. The lesson: R-hat is set by a chain's length, and
  an hour of 4 chains gives 1,600 draws where about 4,000 are needed.
- **Round seven, in flight.** The same code with 2 chains a container, three containers a
  fit: `b7a` to `b7c` on the latest split, `n7a` to `n7c` on the market dataset. `b7a` was
  launched at 09:29Z and swept in 0.62 s, so the other five were launched at 09:41Z and are
  due by about 10:40Z. `b7a` landed: 3,440 draws a chain, its own gate passes (R-hat
  1.0081, ESS 446), $3.70. Predictions are in the note. If the pooled market fit n7 passes, the Deals folder can be
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
- **Review.** Everything in PR #1281 was reviewed before its merge. Work after it needs a
  fresh review: a model reviewer for model, selection, data or ops code, a Sonnet reviewer
  for docs and site pages.
- **Presentation.** `docs/notes/drift-2026-11-10/artifact/`: `pagedata.py` turns
  `artifact-data/extract-full.json` (written by `artifact-data/extract.py` on thelio) into
  the page's data and `build.py` writes the page.
- **Modal spend.** $72.41 settled with `b7a`. The five containers still running are
  estimated at $4.19 each, which would bring the total to about $95 of the $100.

## Next, in order

1. Done: the explainer is published (https://claude.ai/artifact/CidAo43kMNH2Kw7GHwTHf7,
   built page `docs/model/drift-explainer.html`), PR #1281 is merged and the site deployed.
2. Merge #1282, republish and deploy as written under "Follow-up PR #1282" above, and
   check `/deals` (the left-out count, a caution line under "include them", the corrected
   backtest table).
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
  the gate. The site's per-listing estimate pages still come from it; the Deals page does not.
