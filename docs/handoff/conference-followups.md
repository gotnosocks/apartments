# Conference follow-ups thread: handoff

State as of 2026-10-23 13:30Z (09:30 ET). This thread revises the paper and runs the follow-up fits listed in `docs/notes/conference-followups-2026-10-22.md`. Fits run on Modal one at a time, fit-only (`--no-loo --no-heldout`), under the $10/day limiter and the 1-hour cap. Each fit gets a predictions note first, then a results note and an explainer artifact. Nothing here is served, and the site stays as it is.

## Paused (Ben, 2026-10-23 12:07Z)

Ben paused the thread. Fit 4 ran to its end and got its post-fit analysis. Nothing is queued now, and no `wait-next` runs.

- Fit 5 (`building-zones-floor-asof3-periods` at 96a9156e with `--joint-amp`, tag `periods-jointamp-w1000`, worktree `conf-fit5-run`) has not launched. To restart it: `systemd-run --user --unit conf-queue-fit5k /data1/apartments/tmp/conference-followups/queue-fit5k.sh`. The script waits for no active `modal-fit-*` unit and for the limiter. Predictions: `docs/notes/building-zones-floor-asof3-periods-predictions-2026-10-23.md` and `amp-joint-predictions-2026-10-23.md`.
- Fit 4 missed the gate on the coefficients of columns fixed within a unit (floor, bedroom and bath steps). The next model step is a module that integrates the unit effects out of the coefficient draw, as step 1 already does for the building levels; see the results note.

The scripts are in `/data1/apartments/tmp/conference-followups/`. Scoring a unit-effect run needs about 7 GB (`score-unitmean.sh`, run with MemoryMax=8G while no fit runs).

## Done

- asof2 refit on the #1235 build: results in #1241, R-hat range fix in #1245. Explainer: https://claude.ai/artifact/HJogRb1FPT3ozGSTbwouWN (sources in `/data1/apartments/tmp/asof2-explainer`).
- Backlog item for a hash-keyed latest split: #1243.
- Frontier dataset on the #1242 build: `/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc` (1,896,471 rows), made with `/data1/apartments/tmp/conference-followups/mkdata-b3dd.sh` (b0data, v36 set-aside, b0trim, b0nyc).
- asof3 and asof3-cap64 modules with the fit 8 predictions: #1247. The unit-effect model (asof3-unit) with the fit 4 predictions: #1248. Removing rows reshuffles the latest split's held-out draw, so compare runs on different builds only on the held-out ads they share.

- Fit 6 (simulated recovery, realistic truth): results in #1255, `docs/notes/simulated-recovery-asof2-2026-10-23.md`, 3 hits and 1 miss. Explainer: https://claude.ai/artifact/X5DLegFq6343pc6aBSXjkk (sources in `/data1/apartments/tmp/sim-asof2-fit6-explainer`).
- Final and latest ask tuning rules moved to the rebuilt outcomes file as v2: #1258. Only the two nb8-nostuy-v1 C tuning fits used v1.
- Delist audit: #1251, rerun on the rebuilt outcomes file with the price and date steps in #1259, and Fable's past-only IV with the doorman re-score in #1261.
- Park placebo: predictions #1256, results #1260.
- Stabilized split: results note `docs/notes/stabilized-split-2026-10-23.md`.
- Within-unit OLS on Sol's audited endpoints: predictions #1262, results #1263. The fit 4 comparison is still open.
- Fit 8 (elevator curve to 64): results in #1271, 7 hits and 3 misses. Explainer: https://claude.ai/artifact/HPabtovyrTuwpdJ9jCXUhW (sources in `/data1/apartments/tmp/cap64-fit8-explainer`).
- Fit 4 (unit effects and unit means, joint amplitude step): results in `docs/notes/building-zones-floor-asof3-unitmean-2026-10-23.md`, 14 hits and 6 misses, and 5 hits and 2 misses on the amplitude predictions. It misses the gate. `score.py` draws unit effects since #1273.
- Fit 7 (simulated recovery, contextual truth): results in #1266, 6 hits and 1 miss; it missed the gate on `amp[outer]` (R-hat 1.0115).
- `amp[outer]` diagnosis and the opt-in joint amplitude and wave step (`rentfrontier.amp_joint`, `--joint-amp`): #1267, with predictions in `docs/notes/amp-joint-predictions-2026-10-23.md`. The diagnostic scripts are `amp_diag.py` and `amp_toy_iat.py` in `docs/notes/conference-followups-2026-10-22/`.

## Open work, in order

1. Fit 5 once Ben lifts the pause, scored against the amplitude predictions as well as its own. The group's first-ask fit ran at 06:01 ET and is the group's to report.
2. Fit 9 (SBC) only if budget remains.
3. After each fit: results note, explainer artifact, and a board post.
4. Fable asked for a table of `latest_ask` against the outcomes' final ask, split by sign, on finished Manhattan rows. It's a small addition to `delist_audit.py`'s coverage step.

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
