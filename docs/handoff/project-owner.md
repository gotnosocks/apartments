# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run.

## State at 2026-11-10 05:20Z

- **Branch and PR.** `claude/project-thread-09vaqy`, PR #1281, head `1552f44` plus notes. The
  PR holds the model, the Deals page and the docs, because this thread may push one branch
  only.
- **Data.** A one-off scrape on 2026-11-10 brought the listings to 2026-11-09 (pipeline build
  `ddd2fe8f5da041b8`). On thelio: `frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market`
  (6,774 ads on the market) and `...-asof-20251110` (the backtest, 9,346 on the market that
  day). The latest split is on `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`.
- **Model code.** `rentfrontier.drift` (unit level plus drift), `drift_building` (plus a
  quarterly AR(1) path per building, integrated out of the scale draws) and `drift_local`
  (plus a path per neighbourhood, not refit after round two: it added 952 elpd). Scoring is
  `drift_score`; the deals table, its backtest check and the site's files are `drift_deals`.
- **Fits.** No fit has passed the gate yet. Held-out elpd on the 189,647 ads: kitchen sink
  156,105, `drift` 195,315, `drift-building` 233,273 (monthly, round two) and 230,683
  (quarterly, pilot). Rounds one to four each missed the gate on a scale drawn given a
  latent that pinned it. Round five (`1552f44`) draws every unit and noise scale with the
  unit levels, building levels and building paths integrated out; its pilots `p5d` and
  `p5b` were launched at 05:08Z. `docs/notes/drift-2026-11-10.md` has every round's
  predictions and results.
- **Limits on a fit.** `ops/modal/cap.py` refuses a launch estimated over an hour, and the
  container is killed at 75 minutes. The design build takes about 10 minutes and the compile
  4 to 5, so sampling has about 45.
- **Review.** The model reviewer approved through `1552f44`. The Deals page and docs were
  approved at `c290f9d`; the explainer's `pagedata.py` and the rewrite of
  `docs/model/drift.md` since then still need a docs pass.
- **Site.** `src/apartments/site/deals.py`, `templates/deals.html`, route `/deals`. It reads
  `<site root>/deals/{deals,meta,validation}.json`, which `drift_deals publish` writes.
  Nothing is published yet, because no fit has passed the gate.
- **Presentation.** `docs/notes/drift-2026-11-10/artifact/`: `pagedata.py` turns the output
  of `artifact-data/extract.py` into the page's data, and `build.py` writes the page. Tested
  end to end on a round-two extract (`artifact-data/smoke-round2.json`, to delete before
  merge).
- **Modal spend.** $22.97 settled, about $27 with the two pilots, of $100.

## Next, in order

1. From the pilots' sweep times, size the full round five fits to end inside the hour and
   launch `drift` and `drift-building` on the latest split, the market dataset and the
   backtest dataset. Score round five's predictions in the note.
2. Pick the winner (highest held-out elpd among the fits that pass the gate), write the
   results into the note, `docs/model/drift.md` and `README.md` (each has a
   `RESULTS-PLACEHOLDER` line), and add the 2026-11-10 section to `docs/research-record.md`.
3. `drift_deals publish` from the winner's market run, with its backtest and held-out runs.
4. Build the explainer, publish it as an Artifact, and commit the built page as
   `docs/model/drift-explainer.html`.
5. Merge PR #1281 after the reviewers approve (squash, tag `archive/pr-1281`), deploy the
   site with `ops/site-deploy.sh`, and check `/deals`.
6. Final summary to Ben: links, Modal spend, what remains. The window ends 2026-11-11 00:02Z.

## Things a newcomer would trip on

- The feature snapshots are module constants with hard-coded paths. A dataset's
  `inputs.json` redirects them (`market.apply_inputs`), and `drift.design` applies it.
- The full design needs about 15 GB of memory, so it is built on Modal, not on thelio.
- All project timers on thelio are disabled since late October. Nothing is queued.
- `config/main-analysis.json` still selects the all-scraped fit of 2026-10-17, which failed
  the gate. The site's per-listing estimates come from it until the Deals page lands.
