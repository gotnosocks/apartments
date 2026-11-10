# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run.

## State at 2026-11-10 02:20Z

- **Branch and PR.** `claude/project-thread-09vaqy`, PR #1281. Head `1becc8c`. The PR now
  holds the model, the Deals page and the docs, because this thread may push one branch only.
- **Data.** A one-off scrape on 2026-11-10 brought the listings to 2026-11-09 (pipeline build
  `ddd2fe8f5da041b8`). `ops/market-dataset ddd2fe8f5da041b8` built, on thelio,
  `frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market` (1,900,276 ads, 6,774 on
  the market) and `...-asof-20251110` (the backtest: 1,763,952 ads, 9,346 on the market that
  day), each with an `inputs.json` that points the feature snapshots at the new build.
- **Model code.** `rentfrontier.drift` (unit level plus drift), `drift_building` (plus a
  monthly process per building) and `drift_local` (plus a quarterly one per neighbourhood).
  Scoring is `drift_score`; the deals table, its backtest check and the site's files are
  `drift_deals` (`deals`, `validate`, `publish`).
- **Fits.** A 16-draw pilot of `drift` scored elpd 193,385 on the latest split (fit 4:
  177,137). Round one (F2, B1, L1, F4, F5 from `00aa62e`, launched 01:55Z) is running. The
  second review found that the capped stepping out of `b0.slice_vec` narrows scale draws, and
  that rows with no neighbourhood read the wrong path; `ad2f827` fixes both. Round two (the
  same five plus `drift-local` on the market and backtest datasets, from `1becc8c`) is the
  record; round one stays as the check on how much the fix matters. Predictions for both
  rounds are in `docs/notes/drift-2026-11-10.md`.
- **Review.** Two passes on the model code, findings fixed through `ad2f827`. A third pass on
  the fixes and a separate review of the Deals page and docs are running.
- **Site.** `src/apartments/site/deals.py`, `templates/deals.html`, route `/deals`. It reads
  `<site root>/deals/{deals,meta,validation}.json`, which `drift_deals publish` writes.
- **Presentation.** Source in `docs/notes/drift-2026-11-10/artifact/` (`page.html`,
  `build.py`). It needs one data file; the thelio worker's `extract.py` (Task X) produces the
  raw numbers from the scored runs.
- **Modal spend.** $0.94 settled, about $26 committed with both rounds, of $100.

## Next, in order

1. When the fits land: score the note's predictions, pick the winner (highest held-out elpd
   among the fits that pass the gate), write the results into the note, `docs/model/drift.md`
   and `README.md` (each has a `RESULTS-PLACEHOLDER` line), and add the 2026-11-10 section to
   `docs/research-record.md`.
2. `drift_deals publish` from the winner's market run, with its backtest and held-out runs.
3. Build the explainer from the Task X numbers, publish it as an Artifact, and commit the
   built page as `docs/model/drift-explainer.html`.
4. Merge PR #1281 after the reviewers approve (squash, tag `archive/pr-1281`), deploy the
   site with `ops/site-deploy.sh`, and check `/deals`.
5. Final summary to Ben: links, Modal spend, what remains.

## Things a newcomer would trip on

- The feature snapshots are module constants with hard-coded paths. A dataset's
  `inputs.json` redirects them (`market.apply_inputs`), and `drift.design` applies it.
- The full design needs about 15 GB of memory, so it is built on Modal, not on thelio.
- All project timers on thelio are disabled since late October. Nothing is queued.
- `config/main-analysis.json` still selects the all-scraped fit of 2026-10-17, which failed
  the gate. The site's per-listing estimates come from it until the Deals page lands.
