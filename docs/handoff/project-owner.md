# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run.

## State at 2026-11-10 08:05Z

- **Branch and PR.** `claude/project-thread-09vaqy`, PR #1281. The PR holds the model, the
  Deals page and the docs, because this thread may push one branch only.
- **Data.** A one-off scrape on 2026-11-10 brought the listings to 2026-11-09 (pipeline build
  `ddd2fe8f5da041b8`). On thelio: `frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market`
  (6,774 ads on the market) and `...-asof-20251110` (the backtest, 9,346 on the market that
  day; its name has no `-market-`). The latest split is on
  `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`.
- **Model code.** `rentfrontier.drift` (unit level plus drift), `drift_building` (plus a
  quarterly AR(1) path per building, integrated out of the scale draws) and `drift_local`
  (plus a path per neighbourhood, not refit after round two: it added 952 elpd). Scoring is
  `drift_score`; the deals table, its backtest check and the site's files are `drift_deals`
  (publish refuses a market fit that missed the gate); `drift_pool` makes one run from a
  fit launched as several containers.
- **Sampler.** Round six fixed the two things that kept every earlier round from the gate:
  the scale step's slice directions now come from the curvature of its own density, and the
  `bld:` coefficients are drawn once more with the building paths integrated out. In the
  pilots the unit scales take 8 to 11 sweeps a draw and the `bld:` coefficients 1.4 to 3.7.
- **Fits in flight.** `drift` in full from `fabd6f9` on an H100 (4 chains, 500 warmup, up
  to 6,000 draws, launched about 07:50Z): `drift-b0-latest-fabd6f9d-f6`,
  `drift-b0-market-fabd6f9d-m6`, `drift-b0-market-fabd6f9d-k6` (the backtest). The full
  `drift-building` fits are eight containers (labels `b6a` to `b6c` on the latest split,
  `n6a` to `n6c` on the market dataset, `j6a` and `j6b` on the backtest), to be pooled
  with `drift_pool`. Their predictions are in `docs/notes/drift-2026-11-10.md`.
- **Scores so far** (held-out elpd on the 189,647 ads, none from a fit that passed the
  gate): kitchen sink 156,105, `drift` 195,315, `drift-building` 233,273 (monthly, round
  two) and 230,683 (quarterly, pilot).
- **Limits on a fit.** A drift fit stops its sweeps at 2,520 s and saves what it has
  (`Settings.budget_seconds`); the container is killed at 75 minutes. Outside the sweeps a
  fit takes 13 to 15 minutes. On an H100 a `drift` sweep is 0.54 s once the warmup has
  settled (0.8 s on an A100); a `drift-building` sweep is 1.75 s on an A100. Do not launch
  a long drift fit on the exploration tier: its cap of 1,800 s is below the budget.
- **What was ruled out for the slow unit scales** (so nobody tries it again): stuck slices
  (none), directions of the wrong length (3 to 4 posterior sd), a trade-off with the
  building spreads (they explain under 2% of the unit scales' variance), drawing lam with u
  integrated out, and letting lam ride on its filtered distribution (both tried on a toy).
- **Review.** The model reviewer approved through `35ba4a4`. The Deals page and docs were
  approved at `c290f9d`; the explainer's `pagedata.py` and the docs since then still need a
  docs pass.
- **Site.** `src/apartments/site/deals.py`, `templates/deals.html`, route `/deals`. It reads
  `<site root>/deals/{deals,meta,validation}.json`, which `drift_deals publish` writes.
  Nothing is published yet, because no fit has passed the gate.
- **Presentation.** `docs/notes/drift-2026-11-10/artifact/`: `pagedata.py` turns the output
  of `artifact-data/extract.py` into the page's data, and `build.py` writes the page. Tested
  end to end on a round-two extract (`artifact-data/smoke-round2.json`, to delete before
  merge).
- **Modal spend.** $29.20 through round six's pilots, $12.57 estimated for the three
  `drift` fits and $33.52 for the eight building containers: about $75 of $100.

## Next, in order

1. When the `drift` fits land: score their predictions in the note and run `drift_score`
   on the latest-split run.
2. When the building containers land: `python -m rentfrontier.drift_pool` for each of the
   three fits, then `drift_score` on the pooled latest-split run, and score the
   predictions.
3. Pick the winner (highest held-out elpd among the fits that pass the gate), write the
   results into the note, `docs/model/drift.md` and `README.md` (each has a
   `RESULTS-PLACEHOLDER` line), and fill the `FULL-FIT-ROWS` line of
   `docs/research-record.md`.
4. `drift_deals publish` from the winner's market run, with its backtest and held-out runs.
5. Build the explainer, publish it as an Artifact, and commit the built page as
   `docs/model/drift-explainer.html`.
6. Merge PR #1281 after the reviewers approve (squash, tag `archive/pr-1281`), deploy the
   site with `ops/site-deploy.sh`, and check `/deals`.
7. Final summary to Ben: links, Modal spend, what remains. The window ends 2026-11-11 00:02Z.

## Things a newcomer would trip on

- The feature snapshots are module constants with hard-coded paths. A dataset's
  `inputs.json` redirects them (`market.apply_inputs`), and `drift.design` applies it.
- The full design needs about 15 GB of memory, so it is built on Modal, not on thelio.
- All project timers on thelio are disabled since late October. Nothing is queued.
- `config/main-analysis.json` still selects the all-scraped fit of 2026-10-17, which failed
  the gate. The site's per-listing estimates come from it until the Deals page lands.
