# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run. At 12:38Z Ben added up to $40 for the building model's
three full fits, so the ceiling is $140.

## Outlier sprint, state at 2026-11-11 22:40Z

Ben asked at 2026-11-11 18:55Z for 24 hours of chasing the ads the model prices worst; the
sprint ends about 2026-11-12 18:55Z. The findings are in
[the sprint note](../notes/outlier-sprint-2026-11-11.md), and scratch work is in
`/data1/apartments/tmp/outlier-sprint/`.

- **Merged:** the ledger corrections (#1307), `b0income` (#1309), the closing-ask results
  (#1310) and the sprint note (#1311).
- **No Modal fits until the sprint ends** (Ben, 2026-11-11 22:07Z). He stopped c2 before
  its first container. The unit `outlier-c2` is stopped, and no Modal unit or timer is
  pending. c2, the income fit and a reparameterization of the walk's hyperparameters are in
  `docs/TODO.md` with their predictions. To run c2 later, restart `c2/run.sh` as a user unit.
  It skips a part whose `result.json` exists. After `c2c` finishes, from
  `/data1/apartments/serve/master/frontier` with `PYTHONPATH=src` and the bridge-frontier
  venv:

  ```sh
  python -m rentfrontier.drift_pool drift-building-b0-latest-5f766394-c2 \
      drift-building-b0-latest-5f766394-c2a drift-building-b0-latest-5f766394-c2b \
      drift-building-b0-latest-5f766394-c2c
  python -m rentfrontier.drift_score drift-building-b0-latest-5f766394-c2
  python /data1/apartments/tmp/outlier-sprint/compare_c1.py \
      drift-building-b0-latest-67d14e17-b9 drift-building-b0-latest-5f766394-c2
  ```

  `compare_c1.py` is a scratch script in `/data1/apartments/tmp/outlier-sprint/`. It
  compares two runs' `pred_scores.npz` on the held-out ads whose target is unchanged.
- **Leads not started:** a Student-t unit level, wider noise for large units, splitting unit
  records shared by two apartments, a text rule for commercial spaces and rooms.

## Manhattan doorman fit, 2026-11-11 06:50Z

Ben approved a Manhattan copy of the doorman columns (`drift-building-doorman`, #1304) and
set a $10 Modal limit for the night. Two containers ran as `...-cb94a194-d1a` and `d1b`
($7.75) and pool as `drift-building-doorman-b0-latest-cb94a194-d1`. It passes the gate but
scores -4.8 (SE 5.9) against b9's first four chains (`...-67d14e17-b9ab`), so the served
model stays `drift-building`. Manhattan's full-doorman premium is +4.1%, the outer boroughs'
+0.4%. The building levels kept the premium because the doorman column changes within a
building as its ads come in. Results are in `docs/notes/drift-building-doorman-2026-11-11.md`
(#1305), the explainer at https://claude.ai/artifact/Fd9aaEHP45MYJL9VGvB1rw. The next
candidate is a doorman value fixed for each building from its training ads.

When comparing held-out elpd, pool the same number of chains: elpd falls with fewer draws.

## App sprint, state at 2026-11-11 03:40Z

The site was rebuilt around Deals, the Workbench and Tags in PRs #1297 to #1302, all merged
and deployed from master `feac6837`. The plan and the `diagnostics/` folder are described in
[the sprint note](../notes/app-sprint-2026-11-10.md).

- **Pages.** `/` and `/deals` (market ads by cautious saving), `/listings/<id>`, `/estimates`
  and `/listings` (held-out ads), `/workbench` (overview, signals, triage, buildings, a
  building's history), `/tags`, `/about`, `/new-jersey`. The pages of the October 19 fit are
  deleted along with their modules and tests.
- **Data the pages read.** `/data1/apartments/site/{deals,estimates,diagnostics}` as published
  on 2026-11-10 from the round-nine fits, and `/data1/apartments/site/tags/` for the ledger,
  which the site creates on the first tag. A new fit needs `drift_deals publish`,
  `drift_estimates publish` and `drift_diagnostics publish` (see `docs/model/diagnostics.md`),
  then `ops/site-deploy.sh`.
- **Playtest.** Three personas read the site after #1301; their reports are in
  `/data1/apartments/tmp/sprint/playtest/{renter,phone,modeler}/report.md`, and #1302 carries
  the fixes. No persona has read the site since #1302.
- **Open items.**
    1. Deals ranks by the gap to the model, and 4,246 of 6,774 market ads ask at least 90% of
       the median of their building's other asks of the same size. The `peers` caution hides
       only the 216 of them asking below the model's 80% range. A ranking built on the
       building's own asks as well as the model is the next product question.
    2. On new units the 80% range covers 72.9% (building basis) and 66.9% (area basis) of
       held-out asks. This is a modeling finding from the Workbench overview.
    3. The centered signal score uses the bin's own standard error, though the reference mean
       includes the bin. Peers of an ad include ads dated after it, up to the scoring day.
    4. About 85 market ads have a `prev_day` in `ads.parquet` that disagrees with
       `history.parquet`. The Workbench coverage counts include rows with a NULL interval.
    5. The tags ledger has a single-process append test only. Spelling in the Workbench
       templates and `observed.html` is still "Neighbourhood".
- **Builders.** Gemini Argon and Carbon ran through `pi` with OpenRouter; the account ran out
  of credits at 02:03Z on 2026-11-11 and needs a top-up from Ben before more delegation.
- **Preview.** The user unit `sprint-preview3` serves the thread's checkout on port 8613 with
  a sandboxed site root, `/data1/apartments/tmp/sprint/siteroot`.

## State at 2026-11-10 15:02Z

- **Housekeeping since.** A 24-hour tidy-up followed from 15:22Z ([housekeeping.md](housekeeping.md)).
  It pushed every missing `archive/pr-N` tag (#1281 to #1289), deleted 46 old branches after
  tagging them `archive/branch/*`, and moved September and October runs and pipeline lanes to
  `/data2/apartments-offload/`, leaving symlinks at the old paths.

- **Served model.** `drift-building` with `--level-dof 4` (a Student-t prior on building
  levels), since 14:19Z. Its three full fits (round nine) pass the gate, each a pool of
  three containers of two chains: `drift-building-b0-latest-67d14e17-b9`,
  `drift-building-b0-market-67d14e17-n9`, `drift-building-b0-market-67d14e17-j9`.
  Held-out elpd 230,989, median abs error 0.0406, coverage 0.525 / 0.807 / 0.901 / 0.952.
  The fits were launched with the flag; since #1287 4 is `drift-building`'s default
  (`drift_building.LEVEL_DOF`), and `--level-dof 0` is the normal prior that missed the
  gate. No fit has run from the code with the new default: the first one should show
  `level_dof` 4.0 in its run record's sampler settings. `drift` (f6, m6, k6; elpd 195,320, error 0.0506) was served from
  09:42Z until then and passes its gate too.
- **Deals.** `/data1/apartments/site/deals` was published at 14:19Z from n9 with j9 as
  its backtest, b9 as its held-out fit and the ad texts
  (`--texts /data1/apartments/tmp/overhaul/texts-m6.parquet`), and again at 14:45Z from
  master `45968c30` with the `takeover` caution; the site is deployed from that commit.
  `/deals` shows 5,792 of 6,774 ads by default, 982 left out for a caution (646 off
  market, 328 beds, 55 income, 14 takeover, 2 not_home, 1 owners_only), and the backtest
  (26 to 71 days on market, 18% to 61% cut, lowest tenth to highest). Scores and order
  are those of 14:19Z (`deals_sha256` `e18cedca...`). The folder as `drift` had it is kept at
  `/data1/apartments/tmp/overhaul/fixcheck/deals-drift-m6/`. A reader classed 36 of the
  first 40 ads of the 14:19Z list as ordinary apartments, 2 low for a plain reason (a
  lease takeover, cautioned since; a text that names a fourth bedroom) and 2 it could
  not tell (35 of 40 on the morning's `drift` list).
- **PRs.** #1281 (the model, the Deals page, the docs) merged as `252a82a`, head `f1380fc`.
  #1282 (cautions, the backtest on one basis) merged as `9266983`, head `93bbfca`. The tags
  `archive/pr-1281` and `archive/pr-1282` are not pushed: this thread can push only its
  own branch. #1283 (round seven and eight, the cause of the building model's miss,
  `Settings.level_dof`, the beds caution that reads a split unit's pieces together)
  merged as `67d14e17`, head `51c00d5`; its tag `archive/pr-1283` is not pushed either.
  #1284 (round nine's record, the docs and the explainer around the served model)
  merged as `8d2fd1a6`, head `54113bd`; no tag either. #1285 (the `takeover` caution) merged as
  `45968c30`, head `2eafe54`; no tag. #1286 carried the handoff and the explainer's
  refreshed numbers. #1287 makes the t prior the building model's default and is the
  last PR of the day. All work is on the one branch,
  `claude/project-thread-09vaqy`, with master merged in after each PR (a force push to
  restart it was refused).
- **Round nine, done.** Ben approved up to $40 more on Modal at 12:38Z (ceiling $140).
  Nine containers of `drift-building --level-dof 4` ran from master `67d14e17` and cost
  $33.02. All six predictions hit. Three containers stopped at Modal's image build on
  the first launch (nine launched in one second onto a new commit's code folder) and
  were relaunched unchanged: launch the first container of a new commit alone.
- **`drift-building` under the normal prior.** Better than `drift` by 35,541 elpd
  (230,861 in b7; median abs error 0.0407) and never served: every pooled fit missed
  the gate. Round seven (2 chains a container, chains
  of 2,920 to 3,440 draws) cured round six's misses on drift_tau and the sigmas and left
  one, bld_sd[outer]: R-hat 1.0130 in b7 (latest split), 1.0202 in n7 (market), 1.0447 in
  j6 (backtest, round six). The best-supported cause: about ten buildings, most of them with
  placeholder listings coded as studios at 3-bedroom rents, sit 5 to 6 spreads out, cross one way
  over thousands of sweeps, and move the zone's spread by leverage under the normal prior
  on levels (the note, "Leverage"). Pooled runs on thelio:
  `drift-building-b0-latest-7023bba1-b6` and `-b7`, `drift-building-b0-market-7023bba1-n6`,
  `-n7` and `-j6`. Scripts for every check: `/data1/apartments/tmp/overhaul/artifact-data/`
  (`qoffset.py`, `holds.py`, `crossings.py`, `conflicts.py`, `leverage.py`, `jobe/`).
- **Round eight, done.** One container, `b8c` (`drift-building-b0-latest-7aab6e47-b8c`):
  `drift-building --level-dof 4`, a Student-t prior on building levels, on the latest
  split with `b7c`'s settings and seed. Its own gate passes (worst R-hat 1.0090), the
  leverage is gone (R squared 0.02 against 0.84), elpd 230,794 against `b7c`'s 230,668.
  The launch command is in the note's "Round eight". Ben approved the $40 for the three full fits at
  12:38Z; round nine is above.
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
- **Review.** Every PR of the day was reviewed by a separate reviewer before its merge,
  and each PR's description says what the review found: #1281 and #1282; #1283 (a model
  reviewer for `level_dof` and the beds caution, a Sonnet reviewer for the docs); #1284
  (docs, a Sonnet reviewer); #1285 (the `takeover` pattern, a default-model reviewer in
  three passes, approved at `8a690cb`); #1286 (docs, a Sonnet reviewer); #1287 (the
  default, a default-model reviewer). New work needs
  the same: a model reviewer for model, selection, data or ops code, a Sonnet reviewer
  for docs and site pages.
- **Presentation.** `docs/notes/drift-2026-11-10/artifact/`: `pagedata.py` turns
  `artifact-data/extract-full.json` (written by `artifact-data/extract.py` on thelio) into
  the page's data and `build.py` writes the page. Build it with `--level-dof 4` so the page
  states the building levels' standard deviation, not the t's scale. Published at
  https://claude.ai/artifact/CidAo43kMNH2Kw7GHwTHf7, last at 14:52Z from the extract of
  commit `4f76d784`, with the live page's 982 cautioned ads.
- **Modal spend.** $127.44 settled ($129.09 with two upper bounds, one a preempted run's
  minutes and one a stopped launch) against a ceiling of $140: the first $100 and the
  $40 Ben added for round nine. Nothing else is planned.

## Next, in order

1. Final summary to Ben: links, Modal spend, what remains. The window ends 2026-11-11 00:02Z.
2. Nothing is running or queued. The items are in `docs/TODO.md` under "From the Deals
   list of 2026-11-10"; the order here is mine, by what I judge each is worth for finding
   deals: a new market snapshot and refit (the list is the market of 2026-11-09, and the
   three fits cost about $33 at round nine's size); the data rule for studio-coded ads
   that are not studios; a caution that tells an apartment's own bedroom count in the
   text from the building's mix.
3. To republish after any change to the cautions, from `/data1/apartments/serve/master`
   at the merged commit, in the environment of the earlier publishes (the thelio
   worker ran it from `/data1/apartments/tmp/overhaul/artifact-data` as
   `pscore.py publish`, which is `drift_deals publish` with the scoring on two workers):

   ```sh
   python -m rentfrontier.drift_deals publish drift-building-b0-market-67d14e17-n9 \
     --out /data1/apartments/site/deals \
     --registry /data1/apartments/external/registry/20261110-f1fc080-extend/registry.parquet \
     --backtest drift-building-b0-market-67d14e17-j9 \
     --heldout drift-building-b0-latest-67d14e17-b9 \
     --texts /data1/apartments/tmp/overhaul/texts-m6.parquet
   ```

   then `ops/site-deploy.sh`. Publish to a staging `--out` first and compare: scores and
   order must not move (`deals.json` with the cautions column left out). The readers'
   files of the caution readings are under `artifact-data/joba/`, `jobb/` and `jobc/`
   on thelio.

## Things a newcomer would trip on

- The feature snapshots are module constants with hard-coded paths. A dataset's
  `inputs.json` redirects them (`market.apply_inputs`), and `drift.design` applies it.
- The full design needs about 15 GB of memory, so it is built on Modal, not on thelio.
- All project timers on thelio are disabled since late October. Nothing is queued.
- Most September and October run directories under `frontier/runs/`, and every
  `tmp/pipeline/lanes/` lane, are symlinks into `/data2/apartments-offload/`. `/data2` is at
  84%, so put new bulk output on `/data1`.
- `config/main-analysis.json` still selects the all-scraped fit of 2026-10-17, which failed
  the gate. The site's per-listing estimate pages still come from it; the Deals page does not.
