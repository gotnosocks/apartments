# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

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
