# Conference follow-ups thread: handoff

State as of 2026-10-23 03:20Z (23:20 ET). This thread revises the paper and runs the follow-up fits listed in `docs/notes/conference-followups-2026-10-22.md`. Fits run on Modal one at a time, fit-only (`--no-loo --no-heldout`), under the $10/day limiter and the 1-hour cap. Each fit gets a predictions note first, then a results note and an explainer artifact. Nothing here is served, and the site stays as it is.

## Running

- `conf-queue-sims` (systemd user unit, script `/data1/apartments/tmp/conference-followups/queue-sims.sh`) launches fit 6 and then fit 7 on model `building-zones-floor-asof2` at 0e260c3a, each once the limiter covers it and no other `modal-fit-*` unit is active. Fit 6 can start near 01:44 ET on 10-23. Leave it running.
  - Fit 6: `--dataset .../sim-asof2-realistic-20261023`, tag `sim-realistic-w1000`.
  - Fit 7: `--dataset .../sim-asof2-mundlak-20261023`, tag `sim-mundlak-w1000`.
  - Predictions: `docs/notes/simulated-recovery-asof2-predictions-2026-10-23.md` (#1244).
  - Scoring: `python -m rentfrontier.simulate score RUN /data1/apartments/tmp/sim-recovery-asof2/<scenario> OUT --root /data1/apartments/tmp/sim-recovery-asof2`.

## Done

- asof2 refit on the #1235 build: results in #1241, R-hat range fix in #1245. Explainer: https://claude.ai/artifact/HJogRb1FPT3ozGSTbwouWN (sources in `/data1/apartments/tmp/asof2-explainer`).
- Backlog item for a hash-keyed latest split: #1243.
- Frontier dataset on the #1242 build: `/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc` (1,896,471 rows), made with `/data1/apartments/tmp/conference-followups/mkdata-b3dd.sh` (b0data, v36 set-aside, b0trim, b0nyc).

## Open work, in order

1. Branch `asof3-modules` (58f41c57, pushed, no PR yet) holds the asof3 and asof3-cap64 modules with registrations and tests. A restart cut the agent off before it ran fmt, lint and tests, so run `ops/fmt`, `ops/lint --changed` and the tests (`frontier/tests/test_building_zones_floor*.py`, JAX_PLATFORMS=cpu, MemoryMax=6G), fix, open a PR and get a default-model review.
2. Fit 8 (cap64) on asof3: add a short predictions note pointing at `docs/notes/building-zones-floor-asof2-cap64-predictions-2026-10-23.md`, compared with asof2 on shared held-out ads (`docs/notes/conference-followups-2026-10-22/compare.py`), and queue it after fit 7 with `--input rows-b3ddebf19af1dc1e.parquet` and the b3ddebf dataset.
3. Fit 4 (random effect per unit): the draft on asof2 is pushed as branch `unit-effect-asof2-draft` (cca0523f). Port it to an asof3-unit module on top of `asof3-modules`, with a predictions note, a PR and a default-model review, then queue the fit.
4. Fit 5 (amenity effects by period: laundry_in_unit, dishwasher, garden and the doorman types, split before 2020-03, 2020-03 to 2021-12, and 2022 on) on asof3: module, predictions, PR, fit.
5. Fit 9 (SBC) only if budget remains.

## CPU hypothesis tests (Ben, 2026-10-23 03:09Z)

Targeted tests may use methods outside the Bayesian framework, held to the same standards: predictions before the run, held-out or placebo comparisons, a results note, and a reviewed PR for code. They run on thelio CPU between fits (MemoryMax=3G scopes) and need no GPU or Modal.

- Washer as renovation: repeat ads of the same unit where `laundry_type` changes, with co-listings under 60 days apart set against relists after a vacancy.
- The stabilized discount split by build year and by 421-a or DHCR status.
- Park-facing placebo views, and front against rear lines.
- An audit of delists and relists.

Methods: unit fixed effects or within-building regressions, SEs clustered two ways (building and week), and permutation nulls. Data: the pipeline rows `rows-b3ddebf19af1dc1e.parquet` carry `unit_id`, `price_at`, `latest_day`, `laundry_type`, `relist_unit` and the ad fields, and the frontier dataset carries `rent_stabilized` and `income_restricted`. No predictions note exists yet for any of these.

Changes to the plan above (coordinator, 03:10Z):
- Argon's laundry direction now owns the washer-as-renovation test, so this thread drops it.
- The delist audit results go on the board with Fable (first-ask markdowns) and Opus (FARE fee) tagged.

## Research group board (`/data1/apartments/research-group/`, handle `conference`)

Members post and read with `bin/board-post conference "Title" [--reply-to ID] < body.md` and `bin/board-read --list` or `--since ID`. The README there gives the format.

Posted:
- `20261023T031132Z-conference-base-model-building-zones-floor-spec-and`, a spec of the base model with the paths to the paper, defense and blog. Its source text is in `/data1/apartments/tmp/conference-followups/board/a.md`.
- `20261023T031132Z-conference-conference-follow-ups-results-so-far-and`, the results from #1232, #1233, #1238 and #1241, with the fit queue (`b.md`).

- `20261023T031332Z-conference-open-objections-to-the-building-zones-fl`, the 26 open objections from the reviewers, the panel and the blog commenters, numbered (`c.md`).
- `20261023T031332Z-conference-re-split-argon-a-repeat-unit-design-for`, a reply to Argon with a repeat-unit design for the washer test and the switch counts by gap (`washer.md`, counts from `/data1/apartments/tmp/conference-followups/tmp/washer-count.py`).

Queue order, as the coordinator relayed it at 03:12Z: fits 6, 7 and 8 keep their places, and group "Fit request" posts with 3 or more supporters go ahead of fits 4 and 5. The coordinator's board post `20261023T031145Z-coordinator-modal-queue-order` describes turn-taking between the two queues instead, so check with the coordinator before a group request and fit 7 or 8 compete for a slot. The group session checks `ops/job status` and the limiter before it launches. Check the board at each wake.
