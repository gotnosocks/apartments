# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run.

## State at 2026-11-10 01:50Z

- **Branch and PR.** `claude/project-thread-09vaqy`, PR #1281. Head `dabc6a3`.
- **Data.** A one-off scrape on 2026-11-10 brought the listings to 2026-11-09 (pipeline build
  `ddd2fe8f5da041b8`). `ops/market-dataset ddd2fe8f5da041b8` built, on thelio,
  `frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market` (1,900,276 ads, 6,774 on
  the market) and `...-asof-20251110` (the backtest: 1,763,952 ads, 9,346 on the market that
  day), each with an `inputs.json` that points the feature snapshots at the new build.
- **Model code.** `rentfrontier.drift` (unit level plus drift), `drift_building` (plus a
  monthly process per building) and `drift_local` (plus a quarterly one per neighbourhood).
  Scoring is `drift_score`, the deals table and its backtest check are `drift_deals`.
- **Fits so far.** One pilot of `drift` on Modal ($0.94): outputs correct. Its log showed
  17 s a sweep, which a profile on thelio does not reproduce (the sweep is dominated by the
  same dense products as the kitchen sink's). The pilot's rate is being re-read from its log.
- **Review.** The first review of PR #1281 asked for changes; `dabc6a3` answers findings 1 to
  5, 7, 9, 11 and 12. Open: 6 (make `market.apply_inputs` refuse non-path constants), 8
  (`drift.run` should say when a split leaves it nothing to predict), 10 (is the ads table's
  `first_ask` net of free months, like `latest_ask`?).
- **Modal spend.** $0.94 of $100.

## Next, in order

1. Full fits on the latest split of the old dataset (`b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`,
   the one fits 4 and 8 and the kitchen sink used): `drift`, `drift-building`, `drift-local`.
   Predictions are in `docs/notes/drift-2026-11-10.md`.
2. Score each with `drift_score`, compare on the same 189,647 held-out ads, write the results
   into that note and into `docs/model/drift.md`.
3. Fit the winner on the backtest and market datasets (`--split market`), run
   `drift_deals validate` on the backtest and `drift_deals deals` on the market fit.
4. Serve: a Deals page on the site that reads the deals table, through a reviewed PR.
5. Docs: fill the results into `README.md` and `docs/model/drift.md`, add the 2026-11-10
   section to `docs/research-record.md`, update `CLAUDE.md` for the new aim.
6. The presentation artifact on how the model works, and the final summary to Ben.

## Things a newcomer would trip on

- The feature snapshots are module constants with hard-coded paths. A dataset's
  `inputs.json` redirects them (`market.apply_inputs`), and `drift.design` applies it.
- The full design needs about 15 GB of memory, so it is built on Modal, not on thelio.
- All project timers on thelio are disabled since late October. Nothing is queued.
- `config/main-analysis.json` still selects the all-scraped fit of 2026-10-17, which failed
  the gate. The site's per-listing estimates come from it until the Deals page lands.
