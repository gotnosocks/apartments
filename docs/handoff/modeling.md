# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## Update (2026-10-15 02:30 UTC): Midtown West C queued, serving hold lifted

- Modeling runs as a single session in its own thread since 01:45Z.
- Ben lifted the 2026-10-13 hold on autoselect, serving and publishing at 02:12Z and 02:26Z. The
  served model is the current best under the selection rules. The hold notes in older sections
  below no longer apply.
- The served C is `5c1e5c7e` on quarantine-v12 (`main-analysis.json`, the Oct 10 build). Older
  sections call it the split C `f469edaa` on quarantine-v13, which is wrong.
- `tmp/bridge/modalq-nb9.queue` holds the NB9 C (`nb9-nostuy-v1`, label `...q23ad6la4ep1`) on
  master 8b3ce683's rules (bedrooms-ad-v6, quarantine-v23). The runner `modalq-nb9-2204` launches
  it once the Modal balance covers $2.03. If it passes the gate and wins, serve and publish it,
  then tell Website so it can merge #776 and rebuild.
- If it fails, the fallback is the local subset test of a per-building bedroom slope
  (`tmp/bridge/slopecheck.sh`), at no Modal cost.

## Update (2026-10-14 21:45 UTC): every-building gate, quarantine-v17, wing C held

- Ben chose the strict gate at 21:10Z. #788 checks split R-hat (at most 1.01) and bulk ESS (over
  400) on every building effect, where the old check took 32 random buildings. It adds about 8 s
  to a C fit (0.08 s per chain in the scan, 7 s of statistics after it), 195 MB of GPU memory and
  43 KB of output (`rhat/building`, `ess/building`). Recorded results of older fits keep their old
  pass, so the served C (split C `f469edaa`, on quarantine-v13) stays served until a replacement
  passes. The served C has 6 buildings over 1.01 on its kept draws (worst 1.013), so it would most
  likely fail the new gate.
- Short full-data C fits are OOM-killed on thelio at about 6.9 GB inside the GPU job slice, on
  old and new code alike. Time full-data changes on Modal or with a scan benchmark.
- 110 W 26th: the five low asks are smaller one-bedrooms in the same building, not East Village
  ads. Ben moved their release and unit split to the thread "110 W 26th St data check" (branch
  `data/110w26-release-split`). Modeling doesn't write that PR.
- #789 merged quarantine-v17, the Brooklyn filter only (326 held rows, a standing screen for new
  datasets). A new fit on quarantine-v16 can't be served now.
- The v16 wing C line in `modalq-c.queue` is commented out as obsolete. Fit the wing C on master's
  rules once the coordinator names the version (v17 alone, or v17 plus the 110 W 26th split).
  Serve nothing until Ben says so. The NB9 C and the fixed-rho arwalk wait on a passing wing C.
  Data improvements keeps #778 and #782 held.

## Update (2026-10-14 20:50 UTC): no seed retries, wing C fails the gate

- The wing-rule C (`...-nb8-nostuy-wings-v1-rows-676a0348-...-wings1`, #779) fits in 1,648 s and
  fails the gate on one traced building effect: R-hat 1.015, ESS 183. That effect is 110 West
  26th Street (building index 222), which isn't a West Coast building. The building effect trades
  off against its walk.
- I queued a rerun on seed 20261015. Ben asked for it to stop at 20:45Z, so I stopped it and settled
  it at $0.58. We never
  retry a failed fit on a new seed. A convergence failure is investigated in this order: data,
  then model structure, then sampler settings. Per the coordinator's brief, I report the data
  findings before any refit (`docs/model/modal.md`, "When a fit fails the gate"). Ben's data-first rule from 09:04Z applies
  to the first step.
- Next: investigate 110 W 26th's rows and report before a refit. The fixed-rho arwalk and the NB9
  C (nb9-nostuy-v1 with elevator-from-ad-v1 and pets-from-ad-v1, #778 and #782) wait for a wing C
  to pass. Data improvements is holding both PRs until then.

## Update (2026-10-14 17:30 UTC): summary on thelio, lines retest

- At 15:26Z Ben moved the summary and calibration out of the Modal container (#761, #763). After a
  full-tier row-split fit downloads, `ops/modal/fit.py` starts `ops/modal/summarize` in its own
  `modal-summary-*` unit, logging to `/data1/apartments/modal/logs/`. The script runs the summary
  under `ops/job gpu -m 5G` (it refuses gate failures), then calibration as a light job. The lines
  fit ran both on thelio without help. If calibration reports "no complete bundle", run it by hand
  on the newest `summaries/<run>-<7 chars>/` directory.
- The split C's bundle (`...-025f0ca`) and its calibration are built.
- Lines on the split C's rules (`...-lines-v1-rows-11c81a08-...`, #762 prediction, #765 results)
  passes the gate. Paired PSIS-LOO is +22.5 with iid SE 9.3 and lot SE 10.3, a tie, so it is
  unserved. The building-weighted new-building lpd is +63.2 with lot SE 13.9. I told Ben, and I
  recommended keeping C.
- Waiting on Ben: lines (serve it for its new-building gain or not), the fixed-rho arwalk (AR(1)
  card), and the split as a non-tune rule. Nothing is on the Modal queue.

## Update (2026-10-14 13:20 UTC): latest-ask refit and the west-coast split

- I refit C on latest-ask-v2 + quarantine-v13 (`...-rows-bcaac064-...q13ad3la2`). It failed the
  gate on group R-hat 1.283, all in the-west-coast (one lot with two structures, BBL 1006430001).
- Data improvements built `tune-westcoast-split-v1` (#745). It moves the floor-and-letter labels to
  97-horatio-street-new_york. C on it (`...-rows-f469edaa-...q13ad3la2-tune-westcoast-split-v1`,
  $2.63) passes the gate with a max group R-hat of 1.026. My #747 predictions:
  - gate, held-out and new-building: hit
  - paired PSIS-LOO: miss (+72 ± 19 against the refit, where I predicted a tie)
- v1 sends the two label schemes to the wrong BINs: floor-and-letter labels run to floor 10, which
  fits the 122.6 ft BIN 1012154, not 97 Horatio (BIN 1012155). `tune-westcoast-split-v2` (#767)
  swaps them. The grouping and the gate pass stay as they were, so there is no refit on its own
  account. The next split C fit, and the arwalk if Ben approves it, run on v2.
- Both fits are scored against latest asks on 21,511 held-out rows (`rentfrontier.finalask`). The
  split C misses by 3.73% with 79.4/94.9 coverage, and the served C by 4.02% with 76.8/93.6.
- Waiting on Ben:
  - Should the split become a non-tune rule, with a C refit on it as the servable latest-ask base?
  - The fixed-rho arwalk fit (#748, #749). Ben answers on the card in the AR(1) thread, and the
    coordinator relays it. If he says yes, I run it once, on `tune-westcoast-split-v2`.
  - The summary-step fix, in the worktree `/data1/apartments/tmp/wt-sum`. Gate-passing runs
    time out after 20 minutes in the summary step, which made the split fit cost $2.63.
- Per the coordinator's brief, each fit is capped at about 1 hour or $2. `modalq-c.sh` skips a
  line when `cap.py --check-launch` exits 2. Lines and areatime are held. Neither fits the cap at
  C's settings.

## Update (2026-10-14 09:40 UTC): data first, then refit

- Ben's rule (09:04Z): when a fit shows a problem, look for and fix a data issue first, and patch
  the model only after that.
- Ben stopped the AR(1) retry at 08:58Z. At 09:01Z he asked for the $1,000 row at 15 E 17th St #4
  (the likely cause of the unit R-hat failure) to be fixed first, then a refit.
- The trace is in `/data1/apartments/tmp/arwalk/prov/findings.md`, sent to the coordinator for Data
  improvements. It found three rent-blind mechanisms: same-day price corrections, a current price
  missing from the event history, and same-day delists. Data improvements writes the rule.
- When the rule merges, refit C and arwalk under it (launch2.sh holds C's settings; launch3.sh,
  the longer chain, is not approved) once the coordinator or Ben clears Modal launches.
- The hold on autoselect, serving and publishing from 03:16Z on 2026-10-13 still stands.

## Update (2026-10-14 03:45 UTC): AR(1) sampler fix merged, retry held

PR #726 (faab7d5) replaces the collapsed solo updates on sd and rho with updates along the
principal axes of their warmup covariance, under `walk_ar` only. All 11 arwalk tests pass,
including the slow CPU recovery test. Ben's hold on autoselect, serving and publishing still
stands.

- On simulated panels the ESS of sd rose 2.2 and 3.7 times at the same cost per sweep. Adding log
  building_scale as a third axis gave no further gain. The comparison script and logs are in
  `/data1/apartments/tmp/arwalk/axes/`.
- At C's settings the retry predicts ESS on sd near 85 to 145, below the gate's 400. The
  predictions note records that before the retry.
- Ben is choosing between the retry at C's settings (about $2) and a longer chain. For the longer
  chain I proposed 24,000 draws keeping every 48th, which predicts ESS 460 to 770, takes about 2.4 h
  of container time and has a limiter estimate of $7.30. No Modal fit launches until his answer
  arrives through the coordinator.
- The launcher is `/data1/apartments/tmp/arwalk/launch2.sh`. It runs C's settings, so the
  longer chain needs its draws and keep changed first. Record the chosen setting in
  `docs/model/predictions-arwalk-2026-10-14.md` before launch.
- The first fit's group R-hat failure on unit effects (1.065) is not addressed by #726.

## Update (2026-10-14 02:00 UTC): AR(1) fit result

The arwalk fit (commit 24a7e9b, $2.00) ran once on Modal. The write-up is
`docs/model/arwalk-2026-10-14.md`. Ben's hold on autoselect, serving and publishing still stands.

- It fails the gate: R-hat 1.041 on rho, ESS 39 on sd. The chains agree within 0.002 but mix
  slowly, because rho and sd move together (posterior correlation +0.93).
- rho 0.890 (0.884-0.898), sd 0.077, building_scale 0.157. All three revised parameter
  predictions missed.
- PSIS-LOO vs C +395 (lot SE 55), building-weighted new-building lpd +70 (lot SE 11), year gap
  +1.5 pp (C +5.2), descriptive share level.
- Next: a joint (sd, rho) proposal in the collapsed step (PR plus CPU recovery), then one retry at
  C's settings. The retry needs Ben's go, because his approval covered one fit.

## Update (2026-10-14 00:30 UTC): AR(1) building deviation fit

Ben approved one Modal fit at 23:51Z: C with its walk replaced by a level plus a stationary AR(1)
deviation. The coordinator's brief came at 23:52Z, with a follow-up at 23:57Z. Ben's 03:16Z hold on
autoselect, serving and publishing still stands, so I run none of them for this fit.

- Model: `m7-…-sizeunkslope-arwalk` (`walk_ar=True`, rho ~ Beta(20, 1.2)) on `nb8-nostuy-v1`, with
  C's rows, rules and settings. Branch `model/arwalk`. Tests are in `frontier/tests/test_arwalk.py`.
- Long-lag check on C (`/data1/apartments/tmp/arwalk/lagsum.txt`): lag-1 correlation 0.83, lag 20
  0.64, lags 25-30 about 0.52, with no plateau. An AR fit gives rho 0.986.
- CPU recovery (`/data1/apartments/tmp/arwalk/recover.log`): all three cases recover rho, sd and
  building_scale inside their 80% intervals. Posterior corr(building_scale, sd) is -0.88 to -0.90.
- Predictions: `docs/model/predictions-arwalk-2026-10-14.md` and `config/predictions.jsonl`. The
  briefed block and a revised block (rho 0.985, sd 0.15, building_scale 0.08) both get scored.
- Next: merge the PR, launch the fit from `/data1/apartments/tmp/arwalk/launch.sh`, then score it
  (gate, paired PSIS-LOO with clustered SEs, `newbuilding`, descriptive share, parameter
  intervals) and write the result doc.

## Update (2026-10-13 22:20 UTC): new buildings per row, clustered SEs

Action 1 of the 2026-10-13 next actions ran on thelio at no Modal cost. The write-up with
predictions and results is `docs/model/newbuilding-clustered-2026-10-13.md`.

- `newbuilding` writes `rows.parquet` per run and building-weighted scores with lot-bootstrap SEs.
  It also has two diagnostics, `--walk-origin first` and `--drop-group G`, which stay off the board.
- `rentfrontier.clusterse` reports building- and lot-clustered SEs. New `loo` records carry
  `elpd_loo_se_building` and `elpd_loo_se_lot`. Since 2026-10-14 the board's paired SE, and so the
  tie tolerance, is the larger of the iid SE and the lot-clustered SE (`leaderboard.paired_se`).
- Under clustered SEs, lines vs C on PSIS-LOO becomes a tie (it was a lines win under iid). On
  new-building lpd, building-weighted, lines leads C by +83.9 nats (lot SE 14.4).
- New-building 80% coverage rises by about 5 pp from 2014-16 to 2024-26 rows within row bins. The
  walk origin does not explain that rise.

## Update (2026-10-13 03:15 UTC)

Ben's "go" (02:47Z) approved three steps from the coordinator. They run in this order, ahead of the
building sets in the modalq-c queue.

1. **New-building score.**
   - Code: `rentfrontier.newbuilding`, on branch model/newbuilding-score (PR pending).
   - Both rungs are scored from kept draws on thelio.
   - Building slopes now count as descriptive.
   - Back-fill on C, areatime (and its rerun), lines and nofloorslope.
2. **Held-out-lots refit.** Fit C with `tune-holdout-lots-v1` (`config/holdout/lots-v1.tsv`: 542
   buildings on 508 lots), then score with `newbuilding --holdout`. Compare against `newbuilding
   --only config/holdout/lots-v1.tsv <C>`. A tune- rule never gets served.
   `ops/modal/fit.py` keeps `--tier full` with a tune- rule.
3. **Final-ask fit.** Fit C with `tune-finalask-v1`, then compare with `rentfrontier.finalask
   <run> <C>`.

Predictions are in `docs/model/predictions-newbuilding-2026-10-13.md`.

Queued after those: predsize (coordinator note, 02:59Z; Ben may drop it). I've asked Data for a
per-row predicted-size parquet.

The queue runner needs a way to add a rule. Either restart modalq-c2 with a per-line rule prefix,
or pass rules on the queue line.

## Update (2026-10-10 21:10 UTC)

- **The Fable framework applies to every fit report** (Ben 20:03Z, via the coordinator). Each report
  gives paired PSIS-LOO vs the served fit at about 2 SE, and explained share vs the permutation null.
  A family beats chance only when explained > max(0, null_95); excess is explained − null_mean, so it
  is not a test. It also gives the latest-split result for rent terms, new-unit coverage vs 0.79/0.95,
  the descriptive share, and the prediction written before the fit with hit or miss, all as medians and
  intervals. Predictions live in `config/predictions.jsonl` (#675); write a one-line prediction there
  and send it to the coordinator before each queue launch.
- **Modal post-fit steps** (#678, #681): after a fit and its PSIS-LOO, the container runs variance,
  summary (full tier), calibration (after the summary) and explained (`--explain SET`). Each step is
  capped, and none can fail the fit. The records land on thelio through `.incoming` staging. Thelio
  keeps the research-data build, autoselect and the site build. Open question: run the post-fit steps
  on a CPU container instead of the idle A100 (about $0.10–0.15 a fit). Decide from lognoise's
  `runs/<name>/modal/modal.json` post timings.
- **Budget:** #680 estimates a served full fit at $1.80 (old rows stay at $0.88, so the history isn't
  repriced). Ben 20:39Z: keep the accruing $10/day balance. Today's real spend was $11.48 by 20:30Z.
- **Board:** entries carry `explained` (#678) and `new_unit_coverage` (#682). Coverage comes from the
  newest calibrated latest-split refit with the same model, feature set and rules. data.json carries
  `predictions` (#675). The installed path unit watches explained/ and calibration/.
- **Queue** (`modalq-c.queue`, unit modalq-c2; it checks out origin/master before each launch):
  lognoise (about 23:51Z), then C `--split latest` (for C's new-unit coverage), areatime,
  nofloorslope, bigbed, amenlevel latest, amenlevel, petsfill, lister, then Data's
  retail/noise/trees/crime/hpd. For Data's sets, send ΔELPD ± SE vs nb8-nostuy-v1 and coefficient
  medians with 90% intervals.

## Update (2026-10-10 19:00 UTC)

- **NB8 live 18:27:55Z (#655)** on the no-size-slope fit. The site build peaked at about 5.0 GB, so it was
  published at MemoryMax=5G; this PR raises ops/autoselect-publish.sh's cap to 6G.
- **This PR serves option C** (`…-sizeunkslope-nb8-nostuy-v1-rows-5c1e5c7e-…`, summary `-fe76a90`) by
  autoselect: PSIS-LOO +2,305.5 ± 105.9 and held-out +167.2 ± 25.3 against the no-size-slope fit. Ben
  17:59Z "Swap after checks". Checks: group R-hat max 1.022 (unit); split R-hat for the building
  effect is 1.0013 at 423 E 12th, 0.9989 at The West Coast and 0.9995 at The Everett Building. 78 of
  214,887 rows move more than 40%; all are single-listing units, 55% of them toward the ask.
- **Queue results on the no-size-slope base:** lines +2.0 ± 1.7 held-out and PSIS-LOO +21.7, but it
  fails the gate (group R-hat 1.079). elevfill +0.4 ± 2.3 and PSIS-LOO +8.3, passes. Both tie. Later
  items run on C.

## Update (2026-10-10 18:10 UTC)

- **Served (this PR, Ben 16:56Z): the eight-neighbourhood no-size-slope fit**,
  `m7-…-yearnoise-nosizeslope-nb8-nostuy-v1-rows-71f317f3-a100-4500k9cb1-nb8-ul15r1s4q12ad3`, summary
  `-fe76a90`. Gate R-hat 1.0072, ESS 595. PSIS-LOO 222,318.6 ± 483.9, +51,134.7 vs the new board
  baseline `m0-base-base-v1-rows-fe76a905-x-2060-300w1500d-nb-nb8` (fit on thelio with CHAIN_BATCH=1:
  two vmapped chains ran out of the 2060's 8 GB in collect). `data.DATASET` and the Modal default
  move to NB8; the NB5 baseline and dataset become `dashboard.PRIOR_*`.
- **Autoselect's own pick is option C** (`…-sizeunkslope-…-rows-5c1e5c7e-…`): PSIS-LOO +2,306 over
  the served fit, held-out +166.2 ± 25.3 paired. Ben has the swap question; its summary
  (`summary-nb8c` unit) and the R-hat checks at 423 E 12th, West Coast and Everett come first.
- **Queue:** lines running on Modal on the no-size-slope base, elevfill queued behind it
  (`bridge/modalq-nb8-lines-elevfill.sh`); later items go on C.

## Update (2026-10-10 12:30 UTC)

- **Runs still paused.** Launch nothing on Modal or the GPU until Ben lifts the pause.
- **Base order** (Ben 2026-10-08 20:58Z, "Wait for all"): one plutoasof-v3 base fit on all eight
  neighbourhoods first, then each feature test rebased on it. The nb6/nb7 feature-set fits do not go first.
- **Merged on master:** quarantine-v12 (#622), unit-labels-v15 (#624, East Village aliases) and NB8
  (#625, cb38e88). That makes DATASET_NB8 215,156 rows with East Village, plus nb8-nostuy-v1 and the
  lister, sizefill and nta sets on it. The served fit stays eligible: same_rows holds on v12 and v15.
- **nta set:** nb8-nostuy-nta-v1 uses nta_v2, which folds the East Village and Greenwich Village NTAs
  into the reference so the NTA levels and neighbourhood indicators are not collinear (rank test in
  test_nb8). nb7-nostuy-nta-v1 has a West Village + Greenwich Village ridge, so read any nb7 nta fit with that in mind.
- **Riverparks** is not in NB8 yet. Pier 42 has no opening date, so Data will date it, and East River
  Park's closure, in its own PR.
- **Ready to run:** /data1/apartments/tmp/bridge/modalq-nb8.sh (the base, current rules, not launched).
  It supersedes modalq-pluto3.sh. After it, each nb8 set gets its own Modal full fit.
- **Registered predictions** (pre-check, no fit, review/r12/c33.py):
  - East Village border: not checkable before the NB8 registry, because East Village buildings had no coordinates.
  - NoMad label: no drift (−0.20 ± 0.09 pp/yr). The level is inconclusive without a surface
    (+3.3 pp against the Flatiron NTA, −5.2 pp against buildings within 400 m).
  - The registered tests run on the NB8 base fit.

## Update (2026-10-09 12:10 UTC)

- **Runs still paused** (Ben, 2026-10-08 16:07Z); no fits queued.
- **NoMad (Data):**
  - `unit-labels-v14` (#611) is a rule change that appends NoMad unit spellings. nb6 rows are
    unchanged. Data reported (by message to Modeling, 2026-10-09, before the merge) that
    `autoselect.eligible()` is the same set on v13 and v14: the served fit, with `same_rows`
    True.
  - #615 adds `data.DATASET_NB7` (the six neighbourhoods plus NoMad, 148,673 rows) and the
    `nb7-nostuy-v1` sets on rule base nb5-plutoasof-v3.
  - It repoints NTA_FILE, BLOCKLOTS_SNAPSHOT and LISTER_FILE to supersets. That changes the
    source hashes of the nb6 nta, lister, explain, stabopen-v2, owner and open-v2 sets, so queue
    any nb6 fit from current master.

## Update (2026-10-09 03:30 UTC)

- **Data's sets for resume, no rule changes, all on base nb6-nostuy-v1:**
  - `nb6-nostuy-lister-v1`: lister type plus the building's as-of agent share (#600, merged);
  - `nb6-nostuy-sizefill-v1`: as-of size fill (#602, merged);
  - `nb6-nostuy-nta-v1`: 2020 NTAs (#603, merged);
  - `nb6-nostuy-riverparks-v1`: Hudson River Park and its piers, dated (#604, merged).

  Each is its own Modal full fit against nb6-nostuy-v1.
- **As-of note (Data):** `unit_size=True` (unitfloor-v2, the whole nb6-nostuy-v1 lineage) fills
  sqft with the unit's median over all its listings, later ones included. That covers about 41%
  of rows, against about 36% as-of. sizefill-v1 is the as-of fix.

## Update (2026-10-09 03:00 UTC)

- **Runs are still paused. The free-check round rests** until the East Village and NoMad scrapes
  land or Ben weighs in. The last checks (`c32.py`):
  - large buildings' walks rose about 8 pp against small ones in 2021, then converged;
  - the per-building bedroom slope's variance is 0.4–0.6× as large where size is known.
- **Candidates for resume (post hoc, unfitted):**
  - #590 lognoise (`first_listing`), plus lister type as a factor;
  - drop the per-building floor slope;
  - a 3+ bedroom × elevator/condo curve;
  - a bedroom-slope scale that depends on the size-known share.

## Update (2026-10-09 02:30 UTC)

- **Runs are still paused.** The per-building parameter checks are recorded (`c31.py`). The noise
  multiplier is 1.02 on repeat rows and 1.19 on singles. The floor slope's per-building
  deviation is a drop candidate (post hoc). Walks are not linear in large buildings. A 3+ bedroom ×
  elevator/condo curve is a candidate term.

## Update (2026-10-09 02:00 UTC)

- **Runs are still paused.** Lister type, building history and skew are recorded (`c30.py`). The
  once-listed excess is heavy tails on both sides, and it stays at 1.27–1.46× within lister type.
  Lister type (brokerage, management, other) is a candidate noise factor beside #590's
  `first_listing`.

## Update (2026-10-09 01:30 UTC)

- **Runs are still paused.** The once-listed gap is not an artefact of the unit level: with
  leave-one-row-out it is 1.36–1.50×. The unit prior is not too narrow for returning units (`c28.py`, `c29.py`). So the ν_unit = 4 fit is not written. #590's `first_listing` noise
  factor is the lever on resume.

## Update (2026-10-09 01:00 UTC)

- **Runs are still paused.** The new-unit coverage checks are recorded in the backlog (#591 and
  this PR; scripts `review/r12/c26.py`, `c27.py`). Once-listed units, 47% of units (`c26b.out`), are typically about
  1.35× wider in every stratum checked; it is not labels, building stock or seller.
- **Merged:** log-linear noise code (#590, config `…-bedtime-lognoise`), keyed on as-of first
  listing. No fit yet; on resume, judge it on new-unit coverage too, and watch the multiplier
  acceptance rate.

## Update (2026-10-09 00:30 UTC)

- **Runs are still paused.** Label vs NTA, noise cells and line coverage are recorded in
  `docs/model/research-backlog.md` (`review/r12/c24.py`, `c25.py`).
- **Label vs NTA:** the NTA wins only for the 98 GV-labelled buildings in the WV NTA. The Midtown
  South sets price with their label or below both, so NTA hoods are not queued as the served
  geography. The WV line is closed; its served form would be a per-NTA 2022 step.
- **Log-linear noise:** code-only PR from branch `model/lognoise` (config `…-bedtime-lognoise`), with
  no fit. Held-out single-listing rows cover 0.62 at 80%, so judge it on new-unit coverage too.

## Update (2026-10-08 23:45 UTC)

- **Runs are still paused.** The coordinator's follow-up checks are recorded in
  `docs/model/research-backlog.md`: #582 (A–E), #584 (what moved WV), #585 (label vs geography)
  and the NTA re-base, market beta, shared shape and attention checks (this PR). Scripts are
  `review/r12/c19.py` to `c23.py`.
- **Finding:** the WV rise is a place-specific step around 2022 (checks 2 and 3), and its step and
  drift follow the geocode rather than the label (#585). If `area_time` gets a fit, define it on 2020 NTA areas, as a per-area walk or a 2022 step,
  not as a beta on the market curve.
- **On resume:** Data's candidates nb6-nostuy-explain-v1 and nb6-nostuy-stabopen-v2 go against
  nb6-nostuy-v1. `modalq-resume.sh` must be rewritten to the 22:10Z order before it is launched.

## Update (2026-10-08 23:00 UTC)

- **Runs are still paused.** All 12 review checks (sections 9 and 10) and the coordinator's
  follow-ups are recorded in `docs/model/research-backlog.md` (#570, #573) and reported to Ben.
  Scripts are in `/data1/apartments/tmp/bridge/review/r12/`.
- **The resume order changes.** The line term (ranked item 5) goes ahead of the noise fit. The
  noise fit is bedroom group × single-listing × small building (≤ 5 rows), 16 scales in place of
  `yearnoise`. Neither is in `modalq-resume.sh` yet.
- **In progress:** a Gibbs line block. `gibbs.py` refuses `line_effects` today. Branch
  `model/gibbs-lines`. It needs default-model review and a CPU test, with no fit.
- **Open with Ben:** NB5-first or NB6-first on resume. The default is NB5 first.

## Update (2026-10-08 18:30 UTC)

- **Runs are paused by Ben (16:07Z)** while scrapes collect more data. Launch nothing until he resumes.
- **On resume,** launch `/data1/apartments/tmp/bridge/modalq-resume.sh` as a systemd unit. It runs the
  pluto3 base, the nb5p3 tests, locnolabel (#535), then unical and trees. Before launching, add Data's
  claimed-area sets at #543's merge commit and the quarantine-v11 swap (#542 head); both are in the
  script's comments.
- **Queue additions since the pause:** claimed area (#543, 840cf57), crime (#548, 053277a),
  concession by era (#551, 9631c96) and HPD condition (#552, 140a44b). All are additive on
  plutoasof-v3 and already in `modalq-resume.sh`. #542 (quarantine-v11) still waits for its fit.
- **Served summary:** bundle `-37f33c1` of the same fit, with new-unit levels clipped (#540, #544).
  Published and deployed at 13:50 ET.
- **Free checks** have Ben's standing approval (17:52Z). The noise check is recorded under ranked
  item 1 in `docs/model/research-backlog.md` (#545). Heteroscedastic noise is the first model-term
  test on resume.

## State (2026-10-08 16:15 UTC)

- **PAUSED (Ben 2026-10-08 16:07Z): "Let's pause model runs. I want to collect more data (in progress
  scrapes) before doing more iterations."** No fit queue units run; launch nothing until Ben resumes.
- **Served (autoselect, this PR): the current-rules refit** of the five-neighbourhood design.
  m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise + nb5-coded-v2, run
  `…-nb5-coded-v2-rows-fedd83d-a100-4500k9cb1-nb5-ul11r1s4q10ad3`, summary d3e8c34, 1,120 s on Modal
  A100, R-hat 1.0054, ESS 820, group R-hat 1.024, PSIS-LOO 139,842.7 ± 386.4; against the previous
  selection on shared rows +84.6 ± 32.7 (held-out +6.6 ± 9.4). Variance: features 73.0%, building 8.9%,
  market and time 7.3%.
- **Current rules:** baths-ad-v3, bedrooms-ad-v3, fields-review-v3, quarantine-v10, unit-labels-v11,
  unit-reviews-v1, unit-splits-v4. A merged rule version makes the served fit unservable: Data tells
  Modeling before merging one.
- **Next base (Ben 2026-10-08 14:07Z): "Serve plutoasof-v3 on passing the gate, as the new base."**
  nb5-plutoasof-v3 (#523, b8b7e44): point-in-time PLUTO, 44 releases, published + 7 days. Its queue
  script is /data1/apartments/tmp/bridge/modalq-pluto3.sh (stopped by the pause, never launched). Serve
  it on passing the gate whatever its ELPD; later tests build on it (NB4_SETS → nb5-plutoasof-v3).
- **Same rows, same rules (Ben 2026-10-08 02:51Z, #458):** autoselect treats a fit whose rule set
  differs from master's as on the current rules when its rows hash (`rows_sha256`) matches.
- **Modal rule (Ben 2026-10-07 22:27Z, #432):** every data-rule, feature or model-term test is its own
  Modal full fit, 2 × (300 + 4500), no exploration, no thelio pairs, no bundling; autoselect serves the
  best passing fit on master's rules (a rule or feature fit only after its PR merges). Budget (#433):
  $8.80 a day accrual, capped at $8.80; one full fit about every 2.4 h.
- **prevprice removed (Ben, 2026-10-07 14:17Z):** `autoselect.BLOCKED` refuses feature sets containing
  `prevprice`.
- **After the pause:** modalq-pluto3.sh first; then the feature tests rebased on v3 (Data adds nb5p3-*
  copies of lines, loc, walkup, noise, parks, water, permit-v1/v2), the rule swaps unit-labels-v12 (e8b247e)
  and unit-splits-v5 (9a10335) on v3, the university calendar nb5-unical-v1 (Ben approved 15:40Z; Data
  building on v3), and last the 21 single-feature fits (filler only, docs/TODO.md). The old queues
  (nb5tests … singles) were stopped on Ben's word, 14:30Z; modalq-current.sh is superseded.
- **Variance:** run `rentfrontier.variance` on every served fit (Website's /research/story reads it);
  regenerate docs/model/cleaning.json with every switch PR.
- **Not on thelio:** serving fits (Ben 2026-10-07 14:29Z); the thelio GPU idles under the all-Modal rule,
  apart from board baselines for a new dataset.

## Next

1. Wait for Ben to resume model runs (new scrapes first); then the queue above.
2. As each queued fit lands: autoselect dry run, pair, report to Ben and Data; switch if it wins.
3. Cut Modal's fixed ~800 s a fit (upload, image, PSIS-LOO), recommended to Ben.
4. A mean-side pandemic term (2020–21 deviation by price tier or bedroom group); pooled per-year noise
   scales as a smaller fix. Areatime as a full fit. Each needs a queue slot under the Modal rule.
5. Backlog: autoselect `why_not` should check the dataset before `scored`; elegance.needed_pairs and
   the site's hardware view still assume TARGET_HARDWARE only (#391 review notes).

## Modal fits (2026-10-06)

Frontier fits can run on Modal with `ops/modal-fit` (docs/model/modal.md), within a dollar budget accruing 10 full fits a day, $8.80, capped at that balance (Ben 2026-10-07 21:59Z and 22:23Z; ledger
/data1/apartments/modal/ledger.jsonl). The served design on an A100-40GB: fit 822 to 919 s, PSIS-LOO
139 s, identical results to thelio, about $0.80 a full fit. The Modal Volume is deleted after 24 h
unused by apartments-modal-cleanup.timer.

## Update (2026-10-13 03:50 UTC): Ben's three tasks only

Ben (03:16Z, 03:20Z): run or enqueue nothing but his three tasks. The modalq-c runner is stopped, the queue
is empty, and the held fits are listed in docs/research-plan.md ("Held fits", #698). petsfill was cancelled
(about $0.94, settled in the ledger), and summ-1013 (the lines/lognoise summaries) was stopped. Autoselect
and publishing are on hold.

- Task 1: unit `nb-backfill` (`tmp/bridge/nb-backfill.sh`) scores C (full and `--only` the held-out lots),
  areatime, lines and nofloorslope from master #700. Results go to `/data1/apartments/frontier/newbuilding/`.
- Tasks 2 and 3: unit `ben3` (`tmp/bridge/ben3.sh`) launches `modal-one.sh` for C with tune-holdout-lots-v1
  and then tune-finalask-v1, one at a time, when cap.py allows.
- Then: `python -m rentfrontier.newbuilding --holdout <refit>` and `python -m rentfrontier.finalask <final> <C>`.

## Update (2026-10-13 10:40 UTC): Ben's three tasks done

All three tasks are done and written up in `docs/model/newbuilding-2026-10-13.md`.

- Step 2 agrees with step 1 on the held-out lots (12.20% vs 12.09%), so step 1's new-building score
  is the board number.
- The final-ask fit misses the final ask by 0.32 pp less than C does (3.71% vs 4.02%). The
  coefficient and descriptive-share moves were much larger than predicted, probably because the
  rule changes which rows are in the fit.
- A fit of C on the same rows at their first ask would separate the two causes. It has not been
  run or queued.
- `finalask.compare` had an unpacking bug, fixed in #703.

Still in force: run or enqueue nothing beyond Ben's three tasks (03:16Z). The modalq-c runner is
stopped and the held fits are in docs/research-plan.md. `ben3` has exited.

## Update (2026-10-13 16:10 UTC): latest-ask fit and the Modal new-building score

Ben asked (13:51Z) for a fit at each listing's latest ask, and for the new-building score on Modal
if it ran much faster there.

- #706 added `tune-latestask-v1`, and the fit has run. Against the latest ask it misses 0.28 pp
  less than C (3.73% vs 4.01%), and its descriptive share is 25.9%. The results and prediction
  outcomes are in `docs/model/newbuilding-2026-10-13.md`.
- #712 runs `rentfrontier.newbuilding` in parallel over row chunks. Every Modal fit now gets the score in a 32-core
  CPU container after it finishes, and the container's cost goes into the fit's. For a run already
  on thelio, use `ops/modal/newbuilding.py RUN` with the Modal venv. A run costs about $0.13 and
  takes 3 to 4 minutes, against about 19 on thelio.
- Bridge scripts: `/data1/apartments/tmp/bridge/nb-modal.sh RUN` waits for the balance and runs
  the score; `latestask-score.sh` ran the comparison.

Still in force: run or enqueue nothing beyond Ben's tasks (03:16Z). The held fits stay in
docs/research-plan.md.

