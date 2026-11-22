# Project owner handoff

What the next session needs. Updated at each milestone. Ben's brief of 2026-11-10 00:02Z: the
aim is a superb descriptive model of NYC rents that helps find good deals; one thread owns the
repo, the model and a presentation artifact for 24 hours, with $100 of Modal approved for the
window and no stale jobs to be run. At 12:38Z Ben added up to $40 for the building model's
three full fits, so the ceiling is $140.

## Causal sprint of 2026-11-14, $100 budget

On Nov 14 Ben made this thread the owner of the repo and set a $100 budget for a sprint on
changes to the causal graph. The plan, the rival accounts and the ranked backlog are in
`docs/notes/causal-sprint-2026-11-14.md`. At about 4:00 PM ET he lifted every earlier hold on
research directions and data collection (photo and plan fetches, school zones, other rental
sites, the P1 fit, GPU inference). Their costs count against the $100. He also asked for each
subagent's model and effort to be picked by its task.

## Milestone: 2026-11-21 — Workspace consolidation, research-artifact docs, and strategic reset

- **Live state (unchanged from Nov 21 01:20 ET publish):** Deals reads `range-m3` (`drift-building-bedtext-layout-range`, `base-n9` held scales, 6,502 ads, 1,675 cautioned across 12 codes including `deposit_net` [#1508] and `short_lease` [#1511]; exact CDF quantiles [#1484]; fit-own `prev_ask` [#1499]); backtest `range-j`. Budget: **$80.43 of $100 spent ($19.57 left)**; `range-m4` refresh plan committed in #1527 (`docs/notes/market-refresh-2026-11-23.md`).
- **Nov 21 zero-spend sizing completed (#1512–#1526):** Joint cross-fit on stored `l2bt` / `range-j` predictives quantified the next unified base-refit bundle: Y1 calendar-year noise (+1,174 all years / +329 from 2022, #1520), joint scale/level terms (+1,331 from 2022, #1517), flag-change counts (+230–254, #1519), large 0–1BR >1,000 as-of sqft (+72, #1525), U4 3+BR new-unit scale (0.711 -> 0.810 coverage, #1522), while pruning weak candidates (4+BR, share-0, dishwasher/furnished/full-floor text, ad-source width, renovation step, studio-reading-on-1+BR, matched cross-bed fill).
- **Worktree & branch consolidation (2026-11-21):** Reduced 59 git worktrees -> 8 (main `/home/ben/code/apartments`, 3 systemd service worktrees, active T3 worktree, 3 locked Claude RC worktrees) and 853 local branches -> 4 (`master` + 3 checked-out branches). All 3 dirty worktrees (`wt-ledgernames2`, `asof3-periods`, `stabilized-v2`), 13 unmerged worktree HEADs, 38 untagged branches, and the Sep main checkout (`a3099eb6`) were snapshotted under `archive/*` tags before cleanup. Main checkout `/home/ben/code/apartments` updated onto `master`.
- **Repo as a research artifact:** Added `docs/model/lineage.md` (4-generation evolution tree, score board, production stack matrix), `docs/model/img/drift-plate-diagram.svg` (Bayesian plate diagram), and `frontier/README.md` (195-module architecture map); synced `README.md`, `docs/README.md`, `docs/research-record.md`, and `docs/TODO.md` (including closing `c3` after `cr-j`'s rejection).
- **Ben's strategic directions (2026-11-21, tracked in `docs/TODO.md`):** converge onto a **single unified model** across all site pages; **fold data findings into the model** instead of piling on cautions; **speed up real fits** for faster iteration; run **whole-dataset outlier & data-issue audits** (not just active/1-year backtest rows) modeled on the **Bayesian Workflow** and **Murphy's Model Discovery Agent**; explore **Covid-19 infection/hospitalization data** as an explanatory covariate for the 2020–2022 rent dip; continue strengthening the repo as a faithful research artifact.

### State at about 10 PM ET on Nov 20, after the closing-raise score

- Deals is live from `range-m3` (published Nov 20 at 4:16 PM ET, 6,502 ads, backtest `range-j`;
  results in `docs/notes/market-refresh-2026-11-20.md`).
- Closing-raise cleaning is rejected on `cr-j` (`docs/notes/deals-closingraise-2026-11-20.md`):
  gate passed, but `d_elpd` -59.1 on the unchanged-target ads and z -2.63 on the remaining
  ads. `cr-m3` is not launched. `ops/deals-refresh` keeps a `CLOSING_RAISE` switch and a
  backtest-fit step, both off by default.
- Budget: $80.43 of the $100 spent, $19.57 left.
- Free fixes merged later on Nov 20 and republished from `range-m3` (1,606 cautioned ads,
  `raised` 655, same order): an `uncautioned` table in the backtest validation (#1469), the
  `raised` caution leaving out only the ad itself, so an earlier raised ad of the same unit
  counts (#1470), and 32 replicates per draw for sampled quantiles (#1471).
- Open free work from `docs/notes/deals-closingraise-2026-11-20/plan.md`: the stale parts of
  `docs/model/drift.md`. Dating concessions in `first_net` cannot be built from
  `priceChanges` (`docs/notes/first-net-concessions-2026-11-20.md`).
  From review: quantiles could invert the exact cdf. That is done for Deals (#1484, below).
  A base refit with free scales, roughly $22, needs Ben's decision.
- The R-hat audit of the kept quantities is done (`docs/notes/kept-rhat-audit-2026-11-20.md`,
  no fit): `pred_loc` matches independent draws (no live ad over 1.05, 2 backtest ads, neither
  near the low end), so no 1.01 gate on it. 51 live and 72 backtest buildings did not mix
  (R-hat up to 9.6 and 14.1), mostly single odd ads, none with a live ad. Open from it: a
  post-fit report of predicted ads over 1.05 with a caution (not built), a read of those
  buildings for the ledger, and `keep_every` 5 on a later market fit if Ben wants a steadier
  order (one Monte Carlo error spans about 5 places in the first 100).
- The 96 unmixed building levels were read ad by ad (no fit,
  `docs/notes/building-level-read-2026-11-20.md`): 72 are data errors a ledger row removes
  (commercial 36, placeholder 19, wrong ask 8, two buildings under one id 9), 8 are out of
  scope and 11 are model shape. 68 candidate rows (of 75 read in full; 7 dropped, 4 re-kinded)
  are drafted and not in the ledger. The 29 Deals ads with a level over 0.5 rest on
  well-founded levels; 115 E 62nd (rank 44) and 14 Spencer (rank 285) are weak deals on a thin
  level. Open items are in `docs/TODO.md`.
- The `thin_level` caution is live (#1478, no fit, `docs/notes/thin-level-caution-2026-11-20.md`):
  a building level over 0.3 resting on five or fewer training ads. Held-out history: such ads
  are below the 5% point 14.4% and 14.1% of the time in the two halves of the buildings, against
  5.9%. The site was deployed at `c551883a` and Deals republished from the same run
  (`...6cd1f12b-range-m3`, backtest `...d9028c57-range-j`) on Nov 20 at 6:02 PM ET: 16 ads
  marked, order and `below_share` unchanged, uncautioned 4,896 to 4,884. The files it replaced
  are in `/data1/apartments/tmp/deals-backup/20261120-1641`. Deploy the site before a publish
  whenever a caution is added, or the page shows the raw code.
- After a fit, `python -m rentfrontier.drift_kept_report RUN` lists scored ads and buildings
  whose kept quantities did not mix, and large levels on few ads (#1480). `docs/model/drift.md`
  and the README describe the served model as of Nov 20 (#1481).
- Thin-building shrinkage was sized on held-out history (no fit,
  `docs/notes/thin-building-shrinkage-2026-11-20.md`): levels on 1 to 5 training ads should be
  7% to 10% smaller, only where the level is beyond 0.1 (1,399 held-out ads, 0.74%). The note
  holds a prediction for `--level-dof 8` at held scales ($2.04 backtest, then $2.11 market).
  Recommendation: do not fit now, since the backtest's 100 such ads cannot show the gain and
  `thin_level` covers the false deals.
- Gemini roles: Carbon for modeling and research questions only; Neon for code and review.
- Exact Deals quantiles are live (`docs/notes/exact-quantiles-2026-11-20.md`, no fit). #1483
  (merged) tests the Today table at block edges, with no change in behaviour. #1484 (merged as
  `4e044e73`) makes the Deals bounds exact: they come from inverting the same mixture cdf as
  `below_share` (module `rentfrontier.drift_quantiles`, a safeguarded Newton step with
  bisection). `--sampled` keeps the old path. The Today table stays sampled unless `--exact`
  is given; its cost on Modal is estimated at 20 to 40 minutes and was not run. `score_run`
  stays sampled, so fit scores and validation are unchanged.
- Deals was republished on Nov 20 at 7:50 PM ET from run
  `drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3` with the same backtest.
  The order, `below_share`, cautions and `validation.json` are identical to before. Only the
  bounds, the median and `discount_pct` changed: the bounds moved by a median of 0.05% to
  0.21% and at most 1.46%, and 105 of 6,502 ads change side of a bound. The files it replaced
  are in `/data1/apartments/tmp/deals-backup/20261120-1950`. A publish now takes about 3
  minutes, against 2 before.
- Modal spend is unchanged at $80.43 of $100. Nothing is running or queued.
- Plan-type misses (#1486, merged as `e90e1c52`, no fit,
  `docs/notes/plan-type-misses-2026-11-20.md`): new buildings' units of two or more bedrooms
  share 23% of their backtest gap variance within building and bedroom count (0.0046, se
  0.0013; 431 ads, 221 buildings; 19% and 32% by half; 30% without the five named buildings).
  The unit line adds nothing stable (excess 0.0124 on half A, 0.0006 on half B, 30 pairs), and
  blind ad readings of 302 ads gave no text code that holds on history. The plan image's excess
  is steady but small (0.0022, se 0.0007). So there is no new column, and the building x
  bedroom-count level (LN1, written, unfit) stays a candidate for the next base refit. The 307
  open ads on pages whose previous ad has another bedroom count were answered on history
  instead, in `docs/notes/changed-counts-read-2026-11-20.md` (300 held-out pairs read; the
  wide tails belong to ads whose counts are new to the unit).
- First-ad noise inputs (#1488, merged as `e1491d3d`, no fit, no spend,
  `docs/notes/first-ad-noise-inputs-2026-11-20.md`). The latest split holds no first-ad units,
  so the check ran on the 2025-11-10 Deals backtest (3,168 first-ad ads of 9,346). The label
  standard and the lister's totals do not mark the wide asks. A lister mark (no same-counts
  ad closed in the building in 30 days) gives scale factors of 1.23 and 1.32 against 0.99 and
  0.91 on the two halves. Review showed it mostly stands for thin building history at the same
  bedroom count: the factor is 1.52 and 1.65 with no earlier same-bedroom ad, down to 1.10 and
  1.10 with 20 or more. This is one backtest day with forms seen on both halves, so it is
  suggestive only. Next, in order: fit LN1 (level for building and bedroom count) with a
  market backtest at the next base refit, then test a factor by thin same-bedroom history only
  if it is still needed, and the lister form after that. The $19.57 left has no budget for it.
- Changed counts read (#1490, merged as `1bee0ba6`, no fit, no spend,
  `docs/notes/changed-counts-read-2026-11-20.md`). 300 held-out pairs were read blind to rent
  on Sonnet readers, and no reading (recount, alteration, other apartment, coding error)
  separates the tails. A mark from fields alone, using only earlier ads, does: held-out ads
  whose most recent earlier ad has other counts are 10.5% and 11.6% low and 9.7% and 10.0%
  high by half, with scale factor 1.35 and 1.40 against 0.92 for unchanged counts. Where the
  counts are new to the unit the factor is 1.68 and 1.71. The Deals backtest gives 1.45 (se
  0.09) against 0.94. This is separate from the first-ad finding, and it is a candidate scale
  mark for the next base refit. The next base refit now has four candidates gathered in the
  TODO item on refit terms (LN1, the thin-history factor if needed, the counts-new-to-the-unit
  factor, the level shrinkage `--level-dof 8`), and it needs budget beyond the $19.57 left.
- A Deals caution for counts new to the unit was built and dropped (closed PR #1492, commits
  under the tag `archive/pr-1492`; `docs/notes/changed-counts-read-2026-11-20.md`). On the
  backtest the 47 marked ads with no other caution have factor 1.24 and none below the 5%
  point, against 1.65 on the 114 that `rooms_up` and `beds` already mark, so a caution adds
  nothing and the refit term should start from those marks.
- The Deals page already carries the low-place note by bedroom count (#1457, backtest card; 45% and 39% within 7 days for studios and one-bedrooms against 30% and 29% for mid-range asks, nothing at four or more bedrooms). The TODO item is closed and a test checks the text. Its comparison is first asks below the 5% point against asks between the 25% and 75% points, on 128,554 closed ads from 2022 on.
- Size fills read (no fit, no spend, `docs/notes/size-fills-read-2026-11-20.md`). The run's
  sizes are filled at design time by `sizefill.asof_size`, and on history the fills are sound:
  against sizes the apartment states on later ads, off by more than 30% in 6.3% of
  same-bedroom unit fills and 6.5% of line fills (1.6% and 3.3% against the ad's own stated
  size, a check inflated by reposts copying an earlier number). The sprint's rule to blank
  line fills over 40% of the bedroom median is rejected at every threshold from 20% to 60%
  on both halves, since the fill beats the median a blank gives; on the later check, the
  only evidence on those rows, the margin is 0.31 against 0.42 on half A (thin) and 0.18
  against 0.43 on B. Unit fills from another bedroom count are off in 25.5% (22.2% on the
  own check) and are 13.7% low and 7.8% high held-out, so the supported rule orders the
  layers as same bedroom count, then line, then other bedroom count. It changes 1,830 rows and waits for
  the next base refit (TODO item). 240 ads read by Sonnet readers add little: 4.0% too large
  among the ads the sprint's rule blanks, 1.4% among the rest. Large filled sizes fall low at
  about twice the share of large stated sizes, and predicted rent does not explain it, so a
  slope for filled sizes is a new refit candidate, also in the TODO. Merged as #1495.
- Diagnostics previous ask (#1496, merged as `a443652d`, no fit,
  `docs/notes/diagnostics-prev-ask-2026-11-20.md`). `drift_diagnostics.previous` now takes each
  held-out ad's previous ad from the dataset of the fit that scored it: same model unit, a
  training row, dated strictly earlier. 7,540 of 195,423 rows changed (7,385 had read another
  piece of the apartment, 934 a held-out ad, 162 a same-day ad). Diagnostics were republished
  from the same runs on Nov 20 at about 11:20 PM ET and the site deployed at `a443652d`; the old
  folder is `/data1/apartments/site/diagnostics.old-20261120`. 188 of the 2,942 rings on Deals
  changed. The rings still come from the diagnostics fits, and 2,462 deals have none; a PR
  giving `deals.json` its own previous ad from the Deals run is in progress (TODO item).
- Commercial and placeholder sweep (#1497, merged as `430965ee`, no fit,
  `docs/notes/commercial-sweep-2026-11-20.md`). No mark is precise enough for a rule: 0 or 1 bed
  over 3x the area median is commercial or placeholder in 0.16 and 0.28 of reads by half,
  0.38 and 0.65 with a text word, and the text and short-text marks almost never. 23 candidate
  excludes are drafted, not imported. The low-miss excess in buildings with a ratio row and a
  word is about 2 standard errors (9.3% against 6.7% matched) and is mostly `the-archive`; it
  looks like varied, expensive loft buildings and is no evidence of commercial rows raising
  levels. The cheap option before the next refit is a hand read of the ratio-with-word matches.
- Ratio rows read by hand (#1500, merged as `292f8621`, no fit, same note, section "Hand read
  of the ratio rows (2026-11-21)"). All 934 ratio-mark training rows not read before: 204
  commercial, 27 placeholder, 38 unclear, 665 apartment, with two blind Sonnet reads on every
  code other than apartment (92% agreement). The drafted excludes grow to 254 (226
  `nonresidential`, 28 `bedrooms_unknown`), to import with the next base refit; 31 ids also
  appear in the building-level read's file. A new follow-up: 165 of the apartment rows are
  coded 0 bed and 53 of their reads cite 2 to 5 beds (TODO item, being sized on history).
- Deals previous ask from the Deals fit itself (#1499, merged as `9de1aac5`, no fit).
  `deals.json` now carries `prev_ask` and `prev_day`, taken by `drift_diagnostics.previous` on
  the live run's dataset; older files fall back to the diagnostics. Site deployed at `9de1aac`
  and Deals republished from `range-m3` with backtest `range-j` on Nov 20 at 11:31 PM ET:
  4,380 of 6,502 deals have a previous-ask ring (2,805 before), none lost one, 3 changed
  value, and every other field is identical. Backup in
  `/data1/apartments/tmp/deals-backup/20261120-2329`. From review: `previous` could move to a
  small module both import, replacing the import inside `deals()`. Done in #1502
  (`rentfrontier.drift_previous`, no behaviour change; `drift_diagnostics` re-exports it).
- Diagnostics were republished on Nov 20 at 11:18 PM ET with the #1496 rule (7,258 rows with a
  changed `prev_ask`); the old folder is `/data1/apartments/site/diagnostics.old-20261120`.
- Zero-bed apartments (#1503, merged as `706b658b`, no fit,
  `docs/notes/zero-bed-apartments-2026-11-21.md`). 13,089 training rows coded 0 bed carry a
  text or unit mark for 2 or more beds, but only the 195 with both marks are precise (10 of
  10 blind reads); the unit mark alone is right about 1 in 25 (weighted 0.04). Held-out ads
  with the text mark run +0.048 (SE 0.031, 17 ads) with the ledger-named ads left out, and
  +0.097 (SE 0.038, 21 ads) with them, which the sprint picked partly by their gap. 120 `bedrooms` set rows are drafted (blind read agrees and most
  of the unit's other counted ads agree, per the ad-text rule); import with the next base
  refit. No pipeline rule.
- Any-unit pages (#1504, merged as `9acf3851`, no fit, `docs/notes/any-unit-pages-2026-11-21.md`).
  Neither mark ("any unit in the building" text, or two ads at once on a page with asks over
  10% apart) is precise: 13 of 40 marked pages are several apartments against 0.20 of
  unmarked ones. Held-out marked ads have the same mean gap, 90% coverage 0.84 to 0.85
  against 0.89, and a low share 1.2x to 1.5x. 42 live Deals ads, none in the top 100. Nothing
  changes. The overlap mark reads asks, so it is allowed for a caution and not for a data
  rule; a noise-scale term on it must be built as of each ad's first day from earlier ads.
- Drafted for the next base refit, none in the ledger: 254 commercial and placeholder excludes
  (sweep), 68 building-level rows (31 of them also among the 254), 119 zero-bed bedroom sets.
- Label reuse (#1506, merged as `203109c4`, no fit, `docs/notes/label-reuse-2026-11-21.md`).
  The zero-bed note's "unit" was the page label (its section 6 correction). None of the 410
  ads whose unit's other ads agree shares a fit unit (`split_unit`), and 65 are not in the live dataset, so the 120 sets
  rest on the text and the blind read. The 19 mixed ones were rechecked on Nov 21 (17
  confirmed, 1 dropped, 1 kept), so 119 remain. Before import, check each row's fit unit after
  the split.
- Deals top read (#1507, merged as `1e87824a`, no fit, `docs/notes/deals-top-read-2026-11-21.md`).
  A read of the top Deals ads; among its TODO items: the `deposit_net` caution (done in #1508), a
  short-lease caution ("$17,500 for a 6-month lease"), `beds` wording for "convertible",
  "alcove studio" and "wall not yet installed", screen-only free-months and lease-term fill,
  and history tests of walkups by zone, virtual doormen, owner rentals in condos and co-ops
  and low-floor wording.
- `deposit_net` caution (#1508, merged as `d1f9dc42`, no fit). A flat security deposit at
  least 1.05 times the page price, no coded free months, the deposit not the first ask, and
  deposit × (L−m)/L equal to the page price within max($2, 0.2%) for m of 0.5 to 3 months
  and L of 12 to 24. It reads the deposit with the texts at publish; the backtest has no texts,
  so no backtest ad carries it. Deployed at `d1f9dc4` (site-deploy output) and republished from range-m3 with the
  range-j backtest at 12:59 AM ET on Nov 21 (backup `/data1/apartments/tmp/deals-backup/20261121-0056`):
  75 ads carry it, and the chip renders on the cautioned view (`/deals?all=1`).
- Cautioned toggle tooltip built from `CAUTION_LABELS` (#1509, merged as `71e53d16`), so it
  names every caution. Deployed at `71e53d1`.
- `short_lease` caution (#1511, merged as `3b865368`, no fit,
  `docs/notes/short-lease-2026-11-21.md`). Text naming a lease of 1 to 11 months ("6-month
  lease", "10 mo term"), with guards against "13-month", "1.5 month" and "1 month rental
  fee". Deployed at `3b86536` and republished from range-m3 with the range-j backtest at
  1:18 AM ET on Nov 21 (backup `/data1/apartments/tmp/deals-backup/20261121-0118`): 8 ads.
- Flex and studio wording (no fit, `docs/notes/flex-wording-2026-11-21.md`). No caution.
  A studio reading on an ad coded 1 bedroom or more is still 12.5% and 17.5% low under the
  bedroom-text term. Queued in TODO as a term with reader fixes for the next base refit.
- Four traits from the top read on held-out history (no fit,
  `docs/notes/four-traits-2026-11-21.md`). Walk-ups, the virtual doorman and garden wording
  are closed. Floor 1 runs low on both halves (8.3% and 8.0% low, asks about 1% further below
  the model's price than on higher floors), with or without the snapshot's garden flag.
  This confirms the first-floor level of `docs/notes/duplex-scale-2026-11-18.md`, already on
  the TODO list of terms for the next base refit.
- Width by ad source (no fit, `docs/notes/source-width-2026-11-21.md`): beside the year
  marks the source marks gain +22 (SE 9) on all years and +29 (SE 12) from 2022 on, feed
  scale 0.98 to 1.01. b9's +140 most likely came from feed ads being most of the pre-2020
  ads. The TODO item is closed with no term.
- Unit scales U4 and U1 (no fit, `docs/notes/unit-scale-2026-11-21.md`). The latest split
  holds out no new unit, so U4 was read on the served design's backtest: +21 (SE 10.5), new
  3+ bd coverage 0.711 to 0.810, factors 1.08 to 1.20 and 1.31 to 1.47. On l2bt, re-listed
  3+ bd ads already cover 0.822 and a mark narrows them (+69 from 2022). U1 is modest: +30
  on l2bt from 2022 (slope 0.16 to 0.20), +46 beside U4 on the backtest. Both stay on the
  refit's list with predictions revised down. Reading U4 on l2bt's design needs a backtest of
  that design, which costs money; that is Ben's call.
- Large studios and one-bedrooms (no fit, `docs/notes/large-one-beds-2026-11-21.md`): the
  1,243 ads over 1,000 sq ft from 2022 on l2bt miss low (65% of misses), and a scale and
  shift mark gains +65 (SE 14), scale 1.25, coverage 0.69 to 0.80. Readers name no kind
  that holds a block of the misses; lofts lead at 1.29 times their share inside. Filled
  sizes are 21 of the 30 lowest misses, and both fill layers mix bedroom counts, so a data
  check on the fill is the next item in the TODO.
- Size fills across bedroom counts (no fit, `docs/notes/size-fill-beds-2026-11-21.md`):
  unit fills borrow a size from another bedroom count at 0.189 and line fills at 0.086. On
  l2bt those borrowed fills are not the low misses (coverage 0.833, marks −1.3, SE 3.0), so
  the matched fill stays off the base refit's list. Both size notes read the `unit_features`
  snapshot, while l2bt's design fills sizes with `sizefill.asof_size`; under the model's fill
  20 of 227 large 0-1-bedroom unit fills borrow, so the large-unit mark for the refit should
  be defined on the model's sizes (1,093 of its 1,243 ads agree).
- Large 0-1-bedroom ads on the model's sizes (no fit,
  `docs/notes/large-one-beds-asof-2026-11-21.md`): the mark holds, +71.9 (SE 14.6), scale
  1.27, coverage 0.68 to 0.80 on 1,130 ads. Filled model sizes in the group lean low
  (residual −0.058 and −0.056), and a +9.9 (SE 6.6) split by source supports the
  filled-size slope candidate in the TODO.
- Studio reading on ads coded 1 bedroom or more (no fit,
  `docs/notes/studio-reading-size-2026-11-21.md`): dropped from the refit list. Beside the
  queued terms the mark gains −0.4 (SE 2.9) on 185 ads from 2022 on; the reader fixes
  remain a TODO item.
- Year scale (Y1) on stored predictions (no fit, `docs/notes/year-scale-2026-11-21.md`):
  l2bt's design (best on the latest split; Deals reads the range model) leaves it whole,
  +1,174 (SE 60) on all years with 2020 and 2021 about 25% wider than 2024. From 2022 on it
  gains +329 (SE 32) beside the gap bins and counts, about 1.4 times the counts, with 2026
  at 0.97 of a year-flat scale. It goes to the base refit's list and needs a new module on
  l2bt's design (the merged `drift-building-phase-year` extends L1). L1 and L2 marked done
  in the TODO.
- Renovation step and rewritten descriptions (no fit,
  `docs/notes/renovation-step-2026-11-21.md`): a lasting renovation step adds little (+48, SE
  12). An ad whose text changed in 3 or more of the 31 scan flags since the unit's last ad
  needs a scale of 1.13; the count marks gain +254 (SE 28) beside the base and go to the base
  refit's list, with the renovation switch (+54, SE 12, shift +0.007) beside them. Beside
  bins of days since the unit's last ad the counts keep +230 (SE 26); the bins gain +138 (SE
  22) and are a further candidate.
- Text columns for coded fields left empty (no fit, `docs/notes/text-columns-2026-11-21.md`):
  beside the queued terms the five marks gain +33 (SE 14) together; 72 low-tail ads leave and
  72 join. Three leave the queue; outdoor space with the box unchecked (+16, SE 10) and
  penthouse (+8, SE 5) are optional base-refit terms, by a 1.5 SE cutoff chosen after the run.
- Joint size of the queued base-refit terms (no fit, `docs/notes/joint-terms-2026-11-21.md`):
  +1,331 elpd (SE 70) on held-out ads from 2022 on, stable by half; one in seven low-tail ads
  leaves the tail and about as many join. This is the size to give Ben with the base-refit
  decision (about $22).
- Large-unit wording on held-out history (no fit, `docs/notes/large-unit-text-2026-11-21.md`).
  Full floor and renovation wording show no excess, and duplex wording is in both tails.
  Named finishes mark buildings whose large units the model prices low: at 3+ bedrooms the
  gap runs from −0.011 at building share 0 to +0.006 and +0.010 over 0.5, and it is flat at
  1 to 2 bedrooms. Queued as a base-refit term. The image item now covers only the high
  tail's photos.

### State at 11:15 PM ET on Nov 18, after the `raised` caution

`docs/notes/raise-caution-2026-11-18.md` (no money spent; $23.65 of the $100 left):

- `cautions.raised` marks an ad when another unit of its building has an ad opened in the
  past 365 days standing 15% or more above its first ask. The rule was chosen on half of
  the held-out history's buildings; on the other half 52% of marked low first asks were
  raised against 13%.
- A backtest dataset keeps each open ad's FINAL ask. An ask on the backtest day has to come
  from price paths (`docs/notes/raise-caution-2026-11-18/paths.py`). On the 2025-11-10
  backtest, marked ads below the 5% point on the day were raised 15% or more later 42% of
  the time against 4.9%.
- The caution is live: the table was republished from `range-m2` and the site deployed at
  about 11:30 PM ET on Nov 18 (686 `raised` marks; 1,333 cautioned ads in all).
- The turnover mean term is closed: the held-out history has no gradient
  (`docs/notes/turnover-history-2026-11-18.md`).
- Since then (Nov 19, no money spent): cut-to-low ads behave like opened-low ads (#1456);
  little of the low tail is gathered in buildings, and the Deals backtest card says a low
  place means most for small apartments (#1457, deployed).
- Also Nov 19, on the held-out history (no money spent): days listed of free-month ads do
  not follow price (#1459); coded ad fields show small shifts only (#1460); buildings under
  eight years in the data hold an excess of about 300 low ads, of the 7,200 low ads in the
  history from 2022 on (#1461). No term from any.
  The history scan of the low tail has no open lead; kept for the next base refit are the
  changed-count and many-bath items and the interval for young buildings
  (`docs/notes/history-scan-2026-11-18.md`).
- The held-out low share falls from about 8% in 2022 to 4.4% in 2026, partly because the
  latest split favours low asks among older ads (#1463). Read low-tail checks on 2025 and
  2026 or on a backtest day. On 2025 and 2026 alone, changed counts (scale) and three or
  more baths (mean) still hold; the two-bath gap is gone among ads with matching counts.
- Next: the market refresh due around Nov 20 (`ops/deals-refresh`; plan and predictions in
  `docs/notes/market-refresh-2026-11-20.md`, fit name `range-m3`), and the next trait from
  the held-out history's low misses.

### State at 10:45 PM ET on Nov 18, after the turnover check on the Deals backtest

`docs/notes/turnover-low-asks-2026-11-18.md` (no money spent):

- The Deals backtest has S13's turnover gradient. The top quartile holds 173 of the 359
  first asks below the 5% point. Of the 213 in that quartile and the unknown-units band,
  53% were raised later, by a median 19%
  (2246 Fulton Street: fifteen ads opened near $2,500, later $3,150).
- Coded free months and ad text do not mark them. A building flag does: two or more of
  the past year's ads raised 15% or more above their first ask (428 backtest ads, 86
  buildings; 22.2% of first asks below the 5% point against 3.0%).
- The flag holds on the whole ads table with no model: 13.7% of 98,702 flagged ads ended
  15% or more above their first ask against 0.84% of the rest, in every year from 2015.
- The window (Ben asked why not the whole history): a longer lookback marks more ads and
  each mark says less. Two to four / five or more earlier raised ads: one year 9.3% /
  19.3% raised, whole record 3.4% / 5.7%. Newest raised ad in the last 90 days: 21.7%;
  over two years old: 0.7%, the base rate. On the 189,607 held-out ads of the latest
  split the one-year flag goes from 3.2% to 17.0% of first asks 15% or more under the
  prediction; the whole-record flag from 3.6% to 4.2%.
- Next: add the flag as a caution in `cautions.py` and `drift_deals._cautions`, computed
  from the ads table, with tests. Choose its count and window (candidates: a raised ad in
  the last 90 days; two in a year) on half of the buildings and check on the other half.
  No fit is needed.
- The rest of the gradient (6.5% low in the top quartile without flagged buildings, +5.5%
  in buildings with no other ad) is a candidate mean term for a later fit.

### State at 10:30 PM ET on Nov 18, after the changed-count follow-up

The follow-up section of `docs/notes/history-scan-2026-11-18.md` (no money spent):

- On the history the changed-count misfit is in ads whose counts differ from the unit's
  last training ad. The Deals model's previous-ad marks already carry the level for those
  ads (on the backtest no previous-ad mark is two standard errors from the unmarked
  ads). What stays is spread: sdz
  1.14 on the 864 marked backtest ads, 1.49 with three baths.
- A noise factor for those ads needs a fit with free scales, since `drift.py` refuses
  noise phases with `--scales-fixed`. It stays with the next refit of the base model.
- Outcomes give no ground for a `rooms_down` caution (15 low asks with fewer rooms, none
  cut, median 14 days) and agree with `rooms_up` (6 of 19 later cut against 12.9%).
- Backtest ads of units with no training ad are asked 2.4% above the median. That is the
  known new-unit gap (U4, U3 and the turnover column in `docs/TODO.md`).

### State at 10:15 PM ET on Nov 18, after the history scan

Ben's direction at about 9:45 PM ET: test model misses on the historical held-out ads, and
use live-table counts only to say how the page changes. The scan of the latest split's
held-out ads is in `docs/notes/history-scan-2026-11-18.md` (no money spent).

- From 2022 on the excess low tail is in ads whose bedroom or bath counts differ from the
  unit's training ads and in apartments with three or more baths. First floor and four or
  more bedrooms are asked about 1.4% below prediction. Ad text explains 0.63% of the error
  variance on the unread half of buildings.
- The Deals model's backtest shows the same for scale: changed-count ads sd z 1.16, three
  baths 1.32.
- No class moves enough of the Deals list for a fit of its own. The terms and sizes for
  the next base refit are one item in `docs/TODO.md`.
- A first ask below the 5% point closes sooner in every class except four or more bedrooms
  and ads with coded free months. A Deals page note on that is an open site item.
- The Deals model has no latest-split fit. One would give the 190,000-ad evidence for the
  served model; Ben declined that spend on Nov 18, so it stays a recommendation.
- Scratch frames for further cuts: `/data1/apartments/tmp/history-scan`
  (`baths-l2bt.parquet` joins each held-out ad's scores with its counts and the unit's
  training counts; `X.npz` and `terms.parquet` are the text matrix).

### State at 9:15 PM ET on Nov 18, Deals refreshed

Deals reads the market of 2026-11-18 from `range-m2`
(`drift-building-bedtext-layout-range-b0-market-9f7ed6ec-range-m2`, gate passed, $2.05),
with `range-j` as its backtest: 6,565 ads, 1,086 cautioned. Results and scored predictions
are in `docs/notes/market-refresh-2026-11-18.md`. Sprint money: $76.35 spent, $23.65 left.

- The datasets are `b0-c1761f182246962c-alldata-dense-nyc` and its `-market` and
  `-market-bedtext` copies under `/data1/apartments/frontier/datasets`, with the registry
  `registry/20261119-9f7ed6e-extend` and the texts in
  `/data1/apartments/tmp/refresh-20261118/texts-m2.parquet`. The Nov 9 Deals files are in
  `/data1/apartments/tmp/po-deals-live-before-refresh`.
- A refresh must run `b0nyc` with `--registry` set to the NJ registry of the same pipeline
  build (#1443). With the default snapshot of Oct 19, 12 new NJ rows stayed in and the first
  launch stopped at its design step.
- Nine days closed 34.7% of the Nov 9 table and 61 of its first 100 uncautioned ads. A
  refresh every few days keeps the first page current. Each one costs about $2 and
  about 100 OxyLabs requests.
- The backlog caution for a text count differing from the record is closed: with the model
  reading the text's count, none of the 169 marked uncautioned ads of the Nov 9 table was
  in its first 100.
- The expert read of the new table is done (`docs/notes/first-page-read-2026-11-18.md`): the
  first 100 uncautioned ads carry apartment traits at the mid-table rate (39% against 36%),
  so no new term. They differ in price cuts (22 against 1) and in source: 3 of 100 from a
  landlord's feed against 12 of 25 controls. Open from it, both in `docs/TODO.md`: a gross-up
  of net asks in the dataset (the `net_ask` caution of
  `docs/notes/net-ask-caution-2026-11-18.md` covers Deals meanwhile: published at 9:25 PM ET on Nov 18, 11 live ads
  marked, 5,471 uncautioned, order unchanged) and a
  width by source (about +140 elpd, give or take 50, on held-out feed ads by a free check,
  $4 to fit, not launched). Stale owner ads need no caution: none in the live table.
- Two follow-ups to that read found no missing term: the doubtful bedroom counts are in the
  text (4 of 11 already flex-marked; a first-line rule adds 6 live ads) and the ads with
  another earlier layout already carry a range mark.
- `ops/deals-refresh` runs a refresh's dataset chain, market fit and publish (usage in its
  header). Checked on the Nov 18 build: the datasets step skipped every existing output and
  the publish step wrote files identical to the live ones.

### State at 6:45 PM ET on Nov 18, market refresh under way

With no free check left on the low outliers, the next backlog item is a new market
snapshot for Deals (`docs/notes/market-refresh-2026-11-18.md`, with the steps, the fit
command and the predictions). The top-up scrape started at 6:37 PM ET as the user unit
`topup-20261118`. After it: the pipeline build, the dataset chain, a held-scales market fit
`range-m2` (about $2), then texts and publish with `range-j` as the backtest. Ben decided
to skip the latest-split fit of the Deals model, so the page stays without its held-out
sentence.

### State at 6:30 PM ET on Nov 18, after the duplex checks

The duplex follow-up below ended with no fit and no caution
(`docs/notes/duplex-scale-2026-11-18.md`). The factor calibrates to 1.1 (+92 elpd, about 60 net of the control), too
small to change the Deals list. Open leads from it: a floor-1 level beside the floor curve,
with its own level for duplexes, for the next base refit; a `duplex` caution if another
backtest repeats the low raise rate of marked ads in the lowest tenth. Sprint money left:
$25.80.

The image read's lead on plans labelling fewer bedrooms than the record is closed without
more reads. In the reads already stored, the trait is on 2 of 34 plans in the market pool
and 2 of 26 in the backtest pool (the lowest 2% of the Deals runs), against 11 of 104
among the `b9` controls and 25 of 249 among its low ads. The 13.4% against 2.5% among
in-sample units rested on 1 control plan in 40. The low-outlier work Ben asked for on
Nov 18 has no open free check left. The leads kept are the floor-1 level and the `duplex`
caution above.

### State on Nov 18 after the image read

The image read of the low outliers is done and written up in
`docs/notes/deals-photos-2026-11-18.md`. Scratch (images, reads, draw) is in
`/data1/apartments/tmp/deals-photos-2026-11-18`. It cost no Modal or OxyLabs money.

- Haiku read the photos and plans of 2,144 low ads and 713 controls. Traits passing the
  bar: a plan on 2 or more levels, stairs in the photos, ground or basement. The first two
  are mostly duplexes, and the text mark `duplex` (`rentfrontier.b0duplex`) is on both
  tails of the base model's held-out ads.
- Next: a noise factor on duplex-marked rows for the Deals model
  (`drift-building-bedtext-layout-range`), as a new module after the design D1
  (`docs/notes/duplex-factor-2026-11-13.md`). Held-scales fits sample no scales, so start
  with a free half-and-half calibration of the factor on the `b9` held-out ads, then a
  predictions note before any fit.
- Smaller leads: ground or basement units without a duplex sign (6.2% against 4.1%), and
  plans labelling fewer bedrooms than the record among in-sample low units (13.4% against
  2.5%, on 40 control plans).

### State at 1:00 PM ET on Nov 18

Ben asked for a few hours on ads asking far below the prediction. The note is
`docs/notes/low-outliers-2026-11-18.md`.

- Deals carries a new caution, `rooms_up` (#1434): the ad codes more bedrooms or baths than
  the apartment's previous ad. Published from `heldbed-m` and deployed. The files from
  before are in `/data1/apartments/tmp/po-deals-live-before-roomsup`.
- `layout-j` (`drift-building-bedtext-layout`, four marks against the previous ad, $1.95)
  passes the gate and misses the decision rule: +22.8 elpd (SE 13.8), with -13.7 on 691
  later ads of apartments whose count changed earlier.
- `range-j` (`drift-building-bedtext-layout-range`, four more marks against the lowest and
  highest earlier counts of the apartment, $2.04) passes the gate and the decision rule:
  +48.3 elpd (SE 18.9) against `heldbed-j`, +3.8 (SE 5.8) on the 7,791 unmarked ads.
- `range-m`, its market twin ($2.00), passes the gate. Deals reads it since 11:54 AM ET
  with `range-j` as the backtest, and keeps `rooms_up`. The table before the publish is in
  `/data1/apartments/tmp/po-deals-live-before-range`.
- `rooms_up` keeps both halves. A broker read of 125 ads from the new table
  (`docs/notes/rooms-up-read-2026-11-18.md`) found 1 sound deal among 55 hidden ads, and
  18 of 30 beds-up ads carry a bedroom the text does not support. Fewer-rooms ads read as
  sound as often as plain ads (5 of 30 against 3 of 25) and take no caution. Asks at
  11/12 and like fractions of the first ask are too few and too mixed for a caution.
- The Deals page has no latest-split run of this model, so its held-out sentence stays
  absent. Ben decided on Nov 18 to skip that fit.
- Wording and gained-or-lost field checks explain little and are recorded as dropped.

The sprint has spent $74.20 of $100.

### State at 11:55 PM ET on Nov 17

Ben asked for the full fit of the flagged base model to borrow the base model's scales.
`--scales-fixed NAME` (`rentfrontier.drift_scales`, #1430) has the sweep hold the tight
scales at a stored pool's means. A check on the k50 subsample and three Modal fits are in
`docs/notes/scales-fixed-2026-11-17.md`.

- `heldbase-j` (plain base model, backtest, scales `base-j9`) reproduces the pool j9:
  final-ask elpd 9,972.7 against 9,978.6, the same coverage, 97.9% of the lowest tenth
  shared.
- `heldbed-j` (flagged model, backtest) leads `heldbase-j` by 21.0 elpd (SE 8.1) and takes
  10 of the 23 flagged ads out of the lowest tenth of first-ask places.
- `heldbed-m` (flagged model, market of 2026-11-09, scales `base-n9`) passes the gate in
  one container. Deals was published from it at 11:50 PM ET with `heldbed-j` as its
  backtest. The command is in the note. The files from n9 are kept in
  `/data1/apartments/tmp/po-deals-live-n9-backup`.

Each fit cost about $2 and ran 0.32 to 0.35 s a sweep. The sprint has spent $68.21 of
$100. Nothing is running or queued.

For the next variant of the base model: build its dataset copies, run a held fit on the
backtest and compare it with `heldbase-j`, and run a held market fit only if Deals is to
read it. A model whose scales would differ from the base model's (a new variance term, a
changed noise model) needs an ordinary pool first. The flagged model has no fit on the
latest split, so the Deals page omits its sentence on held-out ads.

### State at 9:30 PM ET on Nov 17

Ben asked for the bedroom-text flag on the base model. `drift-building-bedtext`
(`rentfrontier.drift_building_bedtext`) ran as a short backtest fit beside a short fit of the
base model (`docs/notes/bedtext-base-2026-11-17.md`). The flag moved 9 of the 23 flagged ads
out of the lowest tenth of first-ask places and led by 13 elpd on final asks (SE 9.6, within noise). The
note's rule for proposing full pools is met. Full market and backtest pools would cost about
$25, and no such fit is to be launched until Ben approves it. If he does: build the market
dataset copy with `rentfrontier.b0bedtext` from
`b0-ddd2fe8f5da041b8-alldata-dense-nyc-market`, write predictions, then three containers a
pool with j9's settings (`2 500 9000 40`, seeds 1 to 3, `--level-dof 4`). The sprint has
spent $62.24 of $100.

### State at 12:45 AM ET on Nov 17

Ben approved three fits on Nov 16, and all ran as short fits (one container, `2 500 320 1`,
seed 1) compared with L2's short fit `drift-building-phase-unitkn-level-b0-latest-75fe7f29-l2short`.

- **Short fits work for comparisons** (`docs/notes/short-chains-2026-11-16.md`, #1426).
  L2's short fit scored 89 elpd below its pool for $1.37, and the bedtext short fit 76
  below its pool. Two short fits reproduced the pools' bedtext lead (236.8 against 223.6).
  A short fit misses the scalar gate, so a model adopted on short-fit scores needs a pool
  before Deals reads it.
- **Lease phases: recommend keeping them** (`docs/notes/no-phase-2026-11-16.md`). On the
  full data L2 leads the phase-free model by 1,240.5 held-out elpd (SE 53.4). Among
  held-out ads, none a first ad, 14% of L2's lowest hundredth by cdf leaves. The choice
  is Ben's.
- **bedunit dropped** (`docs/notes/bed-unit-2026-11-16.md`). The variant trails the bedtext
  model by 122.1 (SE 34.9). The bedtext model stays the best on the latest split and is
  not on Deals: it has no market or backtest fit. Those can run as short fits once Ben
  agrees, with the gate covered by the latest-split pool only if he accepts that.
- Launch `ops/modal-fit` runs one at a time and wait for each log's line starting "synced":
  three launches in the same second collided on the shared code checkout and two failed
  at no cost.
- Next: a Deals caution for flagged candidates, a column for text stating more bedrooms
  than coded, the same reading for baths, and the 102 elpd the bedtext model loses on
  unflagged ads in flagged units.
- Sprint spend: $59.76 of $100.

### State at 10:00 PM ET on Nov 16

- **Bedroom text flag: a win** (`docs/notes/bed-text-2026-11-16.md`). The pool
  `drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt` passes the gate
  (R-hat 1.0054, ESS 948) and leads L2 by 223.6 held-out elpd (SE 38.2), +277.9 on the
  5,022 flagged ads. The unit-mean column carries the effect (-0.059; ad column -0.005).
  It is the best model on the latest split and is not on Deals: no market or backtest fit.
  Next: a Deals caution for flagged candidates, a column for text stating more bedrooms
  than coded (608 held-out ads, mean z +0.46), the same reading for baths.
- **Cheaper estimation** (`docs/notes/short-chains-2026-11-16.md`, #1422). Held-out scores
  follow the count of kept draws, and on k50 a row's `pred_loc` has lag-1 autocorrelation
  0.18. 320 consecutive kept sweeps lose 0.0015 elpd an ad. Open with Ben: short
  single-container fits (500 warmup, 320 sweeps, `--keep-every 1`, about $1.25) for market
  and backtest fits of a model whose latest-split pool passed the gate, and a full-data
  test of that at about $1.25. Pools can keep more draws with a smaller `--keep-every`.
- **Lease phases**: unchanged, the full-data pool of `drift-building-unitkn` waits on Ben.
- Sprint spend: $54.22 of $100.

### State at 9:00 PM ET on Nov 16

Ben asked for three threads on Nov 16: cheaper estimation, dropping the lease phases, and
data issues in the tails of the error.

- **Bedroom text flag, pool running** (`docs/notes/bed-text-2026-11-16.md`, #1420). The
  columns of `rentfrontier.b0bedtext` code the bedroom count an ad's text states. On L2's
  held-out ads, 5,019 are flex or state fewer bedrooms than coded, with mean z -0.375 and
  2.53% below the 1st percentile. `drift-building-phase-unitkn-level-bedtext` adds a flag
  for them to L2. Its latest-split pool `l2bt-a`, `l2bt-b`, `l2bt-c` launched at 8:50 PM ET
  at commit c1ffaefd on the dataset copy `...closingraise-bedtext`, about $11. When it
  finishes: check the gate on the pool, score with `drift_score` against
  `drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn`, score the note's
  predictions, add a research-record row. Launch with this worktree's `ops/modal-fit`
  while serve/master's checkout predates #1420, since its `cap.py` lacks the model.
  After that: a Deals caution for flagged candidates, and the same reading for bath counts.
- **Lease phases** (`docs/notes/no-phase-2026-11-16.md`, #1419). On the k50 subsample L2
  leads the phase-free `drift-building-unitkn` by 43.9 elpd (SE 9.1) and the two share 94%
  of the lowest tenth by cdf. The full-data pool, about $11, waits on Ben's word.
- **Cheaper estimation**: not started. Plan: an opt-in sampler flag holding the scales at
  plug-in values for market and backtest fits, a note with predictions, then a free
  comparison on a subsample on thelio's GPU.
- `ops/modal-fit --help` starts a unit that prints the help of `fit.py` into a log. It
  costs nothing, and the help is easier to read with `ops/modal/fit.py --help`.
- Sprint spend: $43.22 before this pool.

### State at 10:15 AM ET on Nov 16

- **Spend:** $43.22 of $100, unchanged. The checks below ran on thelio's GPU.
- **Sampler check on the first-ad noise** (`docs/notes/phase-collapsed-2026-11-16.md`, #1418).
  `drift.make_sampler` has an opt-in `phase_collapsed`: the noise step draws each free phase
  factor after sigma with lam integrated out. On k100 at seeds 1 and 2 against L2:
  - the five later phases' factors gain about 45% in bulk ESS;
  - the first ads' noise gains about a tenth, inside the seed-to-seed gap;
  - `unit_sd` came out lower at both seeds (204 and 289 against 323 and 337), unexplained;
  - posterior means agree and sampling time is the same.
- **No market refit with the option.** The first ads' noise is slow against the unit level
  through lam, kap and u. The next sampler check is a move of the first ads' noise against
  `unit_sd` with lam and kap redrawn inside it, on k100 at both seeds
  (`rehearse.sh` takes `REHEARSAL_SEED`; baselines `unitkn-level` and `unitkn-level-s2`
  under `/data1/apartments/tmp/rehearsals-2026-11-14`).
- The slice steps reach 12 widths to each side. On a 340-row test design that narrowed the
  noise step's chain by a tenth. Full datasets' log scales spread by about 0.01, inside the
  reach.
- #1417 merged: multi-unit and free-rent wording on the Deals list.

The 1:00 AM list below still holds from item 2 on.

### State at 1:00 AM ET on Nov 16

- **Spend:** $43.22 of $100. The six L2 containers for Deals cost $21.34
  (`docs/notes/l2-market-2026-11-15.md`, #1413, #1414).
- **Deals and Price now stay on n9 and j9.** The L2 market pool missed the gate on
  `phase_scale[1]` (split R-hat 1.0108). The backtest pool passed. In the pooled draws, the
  noise scales `sigma` and the phase factors correlate at -0.70 to -0.80 and slow the start of a
  chain. On the backtest's final asks, L2 ties j9 (elpd 9,980.7 against 9,978.6), so its
  6,442 lead over b9 on the latest split does not carry over to Deals. L2 would put fewer ads in the
  bottom tenth (465 against 601), with fewer of them raised later (19% against 37%).
- **No L2 refit** unless Ben asks for one. Refit only with a change that gains on the backtest. The
  sampler already moves sigma and the phase factors together along curvature directions, so
  the slow quantity is the first-ad noise. A guess to test is that the units' Student-t
  mixing scales, which the scale step holds fixed, slow it
  (`docs/notes/l2-market-2026-11-15.md`).
- **A price report for 131 E 23rd St 5C** went to Ben as a private page, with a breakdown of
  each model part against the average ad. Scripts: `parts.py`, `ref.py`, `groups.py` and
  `page.py` in the session's scratchpad `5c/`, which does not persist.

Next, in order:

1. Check on a subset fit whether the first-ad noise mixes faster when the scale step also
   moves the units' Student-t mixing scales, at no Modal cost.
2. The data fixes from the expert read, then the unread-half check if it is still open.
3. Fit A of item 8a, after its note.
4. A false-deals count in scoring, the line contrast check, and pricing the StreetEasy
   top-up.

### State at 6:30 PM ET on Nov 15

- **Spend:** still $21.88 of $100. The GPU stays idle on purpose: Ben asked for Modal spend
  only on terms that would change which ads show as deals.
- **Income-program ads are out of scope** (Ben, Nov 15). Drop the income regime account (E),
  keep income-flagged ads off Deals, and leave the rows and the flag in training.
- **Unit-record term on L2** (#1405, `docs/notes/l2-unit-record-2026-11-15.md`) missed the
  gate on its 1-in-10 rehearsal: 13 of 274 quantities, lowest ESS 80 on `drift_sd`. No Modal
  fit. The note lists two variants worth a rehearsal, both about the OU drift.
- **Expert reads** are part of the aim (#1406, `CLAUDE.md`, `docs/expert-reads.md`). The
  first read of L2's misses (#1409, `docs/notes/expert-read-l2-2026-11-15.md`) used half of
  the held-out buildings (seed 20261115) and keeps the other half unread. Leading candidates:
  duplex or garden units, rooms beyond the coded bedrooms and bath-per-bedroom among the
  ask-far-above ads, regulated asks among the ask-far-below ads. None survives correction for
  68 tests. A subagent is coding candidates 1 to 3 and 7 rent-blind and running the free
  check on the unread half, on branch `claude/expert-read-l2-check`, work in
  `/data1/apartments/tmp/expert-reads-2026-11-15/unread-check/`. Readers also flagged 86 ads
  with serious data errors (`serious_errors.jsonl` there), mostly bedroom counts, for the
  data thread.
- **Latent price per unit** is item 8a of the sprint note (#1407, #1408), with staged fits.
  Step 1, the free data check, is done: 99.8% of training ads have an ending with an off
  date (49.7% RENTED), every ad has a first ask in `ads.first_ask`, and 29.9% have a cut in
  `ads.kept_changes` (`/data1/apartments/tmp/spell-check-2026-11-15/`). The recorded
  `rented_price` (22,182 usable ads, 2014 to 2019) equals the last ask in 92% of them, so it
  cannot check the last ask as a measure of the latent price
  (`/data1/apartments/tmp/rented-gap-2026-11-15/`). Fit A has to estimate that offset.
- **Literature items L1 to L12** are in the sprint note. L1 (days on the market at an
  unchanged ask, as of the ask's date) and L2 (kriging held-out residuals) rate high value at
  low cost.

Next, in order:

1. Act on the unread-half check. If a candidate beats its shuffled null and moves enough ads
   on Deals, it gets a note with predictions and a single-term fit.
2. `drift_today` has to accept a Student-t unit level before L2 can publish.
3. Fit A of item 8a, after its note.
4. A false-deals count in scoring, the line contrast check, and pricing the StreetEasy
   top-up.

### State at 11:45 AM ET on Nov 15

- **Spend:** $21.88 of $100 (L1TKN $10.82, L2 $11.06). The sheet is
  `/data1/apartments/tmp/sprint-20261114/spend.md`.
- **L2 on unitkn is the sprint's base.** Pool
  `drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn` passes the gate (R-hat 1.0050,
  ESS 1,141) and gains 520 elpd over L1TKN on the held-out ads (clustered SE 30), 240 (SE 28)
  after a constant shift of each pool. A unit back within 2 months asks 1.09% less than a
  first ad. Results are in `docs/notes/l2-unitkn-level-2026-11-14.md`. It serves nothing yet.
  Its explainer for Ben is at https://claude.ai/artifact/JMqdHeyuCR3wMeM4QKeHrD.
- **L1TKN** (`drift-building-phase-unitkn-b0-latest-79dd65f8-l1tkn`) was fit 1: +4,106 over
  L1, a tail fix (`docs/notes/l1-row-dof-fixed-2026-11-13.md`). Its explainer is at
  https://claude.ai/artifact/ErU8W6zwB48ReubDKxbA8p.
- **Segment paths are off the fit list as written** (#1402,
  `docs/notes/unitkn-segment-k10-2026-11-14.md`). On 1 building in 10 the Manhattan 3br+
  amplitude had R-hat 1.95 and ESS 1, both 3br+ paths split their chains between
  lengthscales near 0.5 and 2.2 years, and 279 of 431 quarter coefficients missed. Two
  variants could still pass: fixed 3br+ lengthscales (or no 3br+ path), or all eight
  lengthscales held at their 1-in-10 means. Either needs a 1-in-10 rehearsal first.
- **Gap screen** (#1403, `docs/notes/l2-gap-screen-2026-11-14.md`). Cross-fitted shifts on
  L2's held-out ads, gain over a plain constant (360 ± 32):
  - the unit's training record, +691 ± 50, and the record by year, +903 ± 59;
  - year +118, the previous ad's ending +64, the count of training ads +41;
  - cells built from the ad's own cuts, days on the market or ending read its later rents,
    so they serve as diagnostics only.

  The slope of the gap on the unit's record is -0.066 overall: -0.037 within 2 months of the
  unit's previous ad, about -0.05 to -0.10 from 10 months on, and near zero before 2021.
- **Scoring a pool:** `drift_score` takes about an hour on one core.
  `/data1/apartments/tmp/sprint-20261114/pscore.py RUN 6` gives the same output in 5 minutes,
  and `pshift.py` beside it does the constant-shift count. Both need
  `PYTHONPATH=/data1/apartments/serve/master/frontier/src`.
- **`drift_today` refuses a Student-t unit level,** so neither L1TKN nor L2 on unitkn can
  publish Price now or Deals. The code change belongs before step 6 of the plan's fit table.

Next, in order:

1. Fit 3 is a unit-record term on L2: a static factor on the unit's deviation from its
   building, and a decay of that deviation with the months since the unit's earlier ads. Its
   note with predictions comes first, then a 1-in-10 GPU rehearsal, then a Modal fit, estimated near $12 from L2's container costs.
   The screen gives no account of the near-zero slopes before 2021.
2. The other free checks: the regime check on income-program rows, the line contrast, and a
   school-zone screen.
3. Near the end, a StreetEasy top-up for ads opened after 2026-11-09 as a fresh test set,
   after pricing its OxyLabs cost. The rows file's latest `price_at` is 2026-10-19, which is
   unexplained against the 2026-11-09 snapshot.

## Causal sprint, from 2026-11-13 10:51 ET

At 10:51 ET Ben asked for a sprint on changes to the model's causal graph, like L1's lease
phase, and on data issues read as signs of a cause the model lacks, like the duplexes. He also
asked for the research backlog reviewed and ranked, and for a proposal of fits with their cost.
Data work and other free work go ahead without approval. No Modal budget is approved for the
sprint yet, so I have launched, queued and scheduled nothing on Modal.

### State at 11:15 AM ET on Nov 14

The GPU rehearsals the coordinator asked for are done, and they spent nothing on Modal. Each
fit ran on thelio's GPU on the same 741 buildings (about 1 in 92), with its own settings and
2,400 draws a chain. The results go in each fit's note as an exploration run, apart from the
predictions:

| fit | max R-hat | min ESS | new parameters |
|---|---|---|---|
| L2 | 1.0895 | 12 | phase coefficients pass |
| segment walks, fixed | 1.2464 | 3 | chains agree; every lengthscale misses, worst `outer:studio` |
| D1 | 1.0749 | 19 | `k` passes |
| LN1 | 1.5115 | 4 | `line_sd` misses on ESS (277); `unit_sd` misses |
| I1 | 1.0972 | 11 | `k` passes |

- The zone spreads (`bld_sd`) miss in every run. With so few buildings their posterior is
  wide against `drift.SPREAD_WIDTH` (0.05), and with the window at 0.5 L2 passes on both.
- The segment walks' first rehearsal split the outer 1-bedroom path's chains at 2024q1, since
  the units' levels shrink toward their buildings' and the path took the segment's lasting
  gap. `drift_building_phase_segment` now gives each outer bedroom group past studios a level
  column of its own. Predictions 2 and 5 in its note no longer describe the fixed model, and
  I left them as written. If the lengthscales still miss on the full data, the next thing to
  try is a non-centered draw of each segment's amplitude and lengthscale.
- LN1's `unit_sd` still misses on a 1 in 50 subsample (R-hat 1.36, ESS 10). It trades against
  `drift_sd` and `drift_tau` along a ridge, so its Modal fit could miss the gate. A fix would
  change how the scale step in `drift.py` picks its directions, and `drift.py` is protected.
- D1's unit scales miss when a chain sits in the long-tau region at warmup sweep 333. Check
  for that in the warmup log of its Modal fit.

### State at 7:30 AM ET on Nov 14

Still no Modal budget, and nothing from this sprint is on Modal. Merged since the 4:20 AM state,
none of them a fit:

| PR | what |
|---|---|
| #1388 | `outdoor_sqft`, the stated private outdoor area from ad text, in a copy of L1's dataset, with a screen against L1 |
| #1389 | a read and screen of nonresidential ads among the rental rows; no rule |
| #1390 | S7's within-building duplex contrast redone with S14's (n-1)/n correction, and an audit of the sprint's other screens |
| #1391 | the dataset manifests from `ops/pipeline/observations.py` and `rentfrontier.b0data` now record the build's `label_rule` |

What I found:

- **Outdoor size** (`docs/notes/outdoor-size-2026-11-14.md`). Precision 1.00 (0.83 to 1.00)
  on 40 reads. Marked held-out ads miss L1's median by +0.0196 ± 0.0032, and the miss grows
  with the area. `drift-building-phase-outdoorsize` has its predictions written but isn't
  fit; on its own it would most likely tie L1. A noise factor on rows with an area comes
  after I1's fit.
- **Nonresidential** (`docs/notes/nonresidential-2026-11-14.md`). The draft rule's precision
  came to 0.47 (0.26 to 0.69), short of its bar, so I wrote no rule. L1's held-out candidates
  miss its median by the same mean as all held-out ads, which keeps this last among S16's
  follow-ups. A post hoc candidate (a commercial unit label with a strong text or another ad
  of the unit, 56 rows) waits for a pre-registered read.
- **S7 corrected** (`docs/notes/duplex-within-building-2026-11-14.md`). The duplex excess
  within building comes to +0.0039 ± 0.0002, and the share within building to 0.78 (0.74 to
  0.83), up from S7's 0.38. Most of the duplex scatter belongs to the units, which suits D1's
  factor on duplex rows. No fit recommendation changes.

At 6:38 AM ET the coordinator relayed a brief: rehearse each written fit on thelio's GPU, one
at a time through `ops/job gpu`, on a building subsample that fits the 8 GB card, in the
order L2, segment walks, D1 with penthouses, LN1, then I1. Each rehearsal checks only the
sampler (R-hat, ESS, the new parameters' traces, LN1's `unit_sd`, anything stuck at a
boundary), goes into its fit's note as an exploration run apart from the predictions, and
scores no held-out ads. A sampler problem gets fixed in the module before a budget arrives.
A worker started L2's rehearsal at 7:10 AM ET; the scripts go under
`docs/notes/rehearsals-2026-11-14/`.

Next free items, in rank:

1. The stabilized misspellings ("stablized" and kin) and the income band patterns the
   text-flag reads left. Both scan every description, so they wait for an idle GPU.

### State at 4:20 AM ET on Nov 14

Still no Modal budget, so none of this sprint's fits has run, been queued or been scheduled
on Modal. Merged since the state below, and none of them was a fit:

| PR | what |
|---|---|
| #1383 | this note's 3:00 AM state |
| #1384 | S17, a read of 30 studio-coded rows on 5+ rooms against each unit's history and other ads |
| #1385 | the whole sprint in `docs/research-record.md`, each item with its result or status, and a summary row with the option B order and costs |
| #1386 | `studio-history-h1`, S17's H1 as an optional recode of bedrooms, off by default (`rentfrontier.b0studiohistory`) |

What I found:

- **S17** (`docs/notes/studio-rooms-2026-11-14.md`). Weighted to the pool, about a third of
  the studio-coded rows on 5 or more rooms are bedrooms, a sixth are studios, a twelfth are
  commercial spaces, and the text and history leave the rest unresolved. The coordinator
  barred floor plan fetches, in a relay at 2:55 AM ET, so I counted those rows as unresolved.
  H1, a unit ad coded 1 or more bedrooms within 730 days, marks 243 rows. I chose it after
  scoring 9 rules on S16's ads, so its contrast of 0.14 ± 0.07 is post hoc.
- **H1 as a recode** (`docs/notes/studio-history-rule-2026-11-14.md`). In a relay at 3:30 AM
  ET the coordinator asked for a recode in place of the exclusion S17 proposed, since an
  exclusion would take 24 held-out ads out of a comparison with L1, and 243 rows are too few
  for a fit of their own. The rule takes the bedroom count of the nearest 1+ bedroom ad on
  the unit's page within 730 days, from coded fields only; held-out ads read earlier ads only,
  and a chosen count at or above the row's rooms leaves it a studio. On L1's dataset it
  recodes 227 rows, 11 of them held out. Some pages hold more than one apartment, so a few
  recodes borrow another apartment's count. The rule goes with the next data-version change
  that gets a fit anyway.

In progress: `outdoor_sqft`, the stated private outdoor area read from each listing's latest
description, as a column in a copy of L1's dataset, with a precision read by Sonnet readers
and a screen against L1's held-out ads, its predictions committed first. S16 found the
pattern on the same ads, so the screen is not a clean test.

Next free items, in rank:

1. A screen of nonresidential ads (S16's fifth follow-up; S17 found commercial spaces among
   the studio-coded rows).
2. S7's within-building duplex contrast and its (n-1)/n bias.
3. `observations.py` copying `label_rule` through, and the stabilized misspellings and income
   band patterns the text-flag reads left.

### State at 3:00 AM ET on Nov 14

Still no Modal budget, so nothing has run, been queued or been scheduled on Modal. Merged
since the state below, all written and none fit:

| PR | what |
|---|---|
| #1373 | building turnover and as-of residential units as columns in a copy of L1's dataset |
| #1374 | P1, L1 reading MapPLUTO as of each row's month (`drift-building-phase-plutoasof`); the coordinator asked that it not be queued |
| #1375 | S14, penthouses, garden apartments and townhouse floors against L1's spread |
| #1376 | D1 marks text penthouses along with duplexes, with its predictions revised before launch |
| #1377 | `unit-labels-v18`: history joins kept to labels that agree up to spelling |
| #1378 | `income_restricted_v2` and `shared_space_v2` rewritten from read ads, in the `-textflags` copy |
| #1379 | free months read from ad text, in the `-freetext` copy |
| #1380 | S15 and S15b: the new income flag against L1, a negation guard and the AMI tier |
| #1381 | I1, a noise factor on income-restricted rows (`drift-building-phase-income`) |
| #1382 | S16, blind spots in L1's misses read blind by Sonnet readers |

What I found:

- **S15 and S15b** (`docs/notes/income-flag-2026-11-14.md`). Swapping in the new income flag
  for L1's old one gains nothing (-64.1 ± 60.7), and almost all of the loss is at 505 W 37th
  St, whose ads say the restriction is optional. L1's 80% intervals cover 0.56 of the flag's
  held-out ads. A level by AMI tier gains +5.3 ± 6.8, and a wider noise scale on marked rows
  gains +62.4 ± 16.6. I found the spread after S15 missed, on the same ads, so that gain
  overstates a fit's.
- **I1** (`docs/notes/income-noise-2026-11-14.md`) fits that spread as D1 fits duplexes. The
  coordinator added it to the proposal as the spare, in a relay to this thread at 2:05 AM ET
  on Nov 14: it runs only if the spare's money is unspent after fits 1 to 5, at about $11 for
  three chains (PR #1381's body gives the same terms).
- **S16** (`docs/notes/blind-spots-2026-11-14.md`) found three causes over-represented in
  L1's worst misses against random controls: data errors (23% of overpriced misses against
  4%), income programs (6% of underpriced against none) and private outdoor space (7%
  against 3%, about 1.5 SE). Outside the draw, studios coded on units of 5 or more rooms ask
  +0.085 ± 0.027 on 70 held-out ads. That split is post hoc, with no precision read: I chose
  it after the reads, and 1 of the 8 reads at 5 rooms found a one-bedroom. Stated outdoor
  areas of 300 sq ft or more ask +0.021 ± 0.005 at 0.87 precision. None of the causes is new
  to the project.

Next free item: S17, a read of 30 studio-coded rows on 5+ rooms against each unit's history
and other ads, with Sonnet readers. The coordinator barred floor plan fetches for it, so rows
the text and history can't settle stay unresolved.

### State at 10:00 PM ET on Nov 13

Merged in the sprint, all written and none fit:

| PR | what |
|---|---|
| #1354 | ten causal screens of L1's held-out ads, with three fit candidates |
| #1355 | L2, a level for each lease phase (`drift-building-phase-level`) |
| #1356 | segment paths, a path for each bedroom group in each zone |
| #1357 | L1TK, L1T's kap drawn collapsed (expected to miss the gate on unit_sd) |
| #1358 | the duplex column in a copy of L1's dataset |
| #1359 | the host drops its extra copies of the design, so the segment fit runs in the normal container |
| #1360, #1362 | D1, a noise factor for duplex rows, revised before launch to the noise of marked rows only |
| #1361 | L1TKN, L1TK with the rows' nu held at 2 |
| #1363 | S12, the causes behind L1's negative amenity terms |
| #1364 | `drift_today` accepts L2, the segment paths and D1 |
| #1365 | LN1, a level for each line of a building (`drift-building-phase-line`) |
| #1366 | this handoff section |
| #1367 | the previous ad's ending as the column `prev_ending` in a copy of L1's dataset |
| #1368 | `drift_today` accepts LN1 |
| #1369 | `coop` and `condo` columns from each row's own PLUTO release |
| #1370 | unit codes carried from a unit's earlier ads |
| #1371 | S13, building turnover against j9's misses on new units |

When Ben approves option B in the thread, I run the fits one at a time, three H100 containers
each on the latest split against L1, in this order:

1. L2, about $11.50.
2. The segment paths, $11 to $12.50.
3. D1, about $11.50.
4. LN1, $11.50 to $12.
5. The winner's market and backtest fits and the Deals publish, about $23.

Option B with a spare comes to about $81. Each note holds its launch commands and its
predictions, committed before launch.

Open asks to Ben, each put once in the thread:

- A Modal budget for option B. Until he gives one, nothing runs on Modal.
- His own words allowing the S12 photo pilot to fetch listing photos through OxyLabs. Until
  then it stays stopped, and the memory note `oxylabs-standing-spend` stays as it is.

S12 found no fit candidate (the S12 bullet below has the details). The photo pilot was meant
to test finish quality as the cause behind roof rights, hardwood and live-in super.

Free work, each through its own reviewed PR, in the coordinator's order:

1. Done in #1368: `drift_today` takes LN1 fits, with a line block in its covariance, so LN1
   can feed Deals if it wins. Its worker memory is unmeasured until the first LN1 Price now
   run, which should record it.
2. Done in #1367: how a unit's previous ad ended, read from the raw status history as in
   screen S3, is the column `prev_ending` in a copy of L1's dataset
   (`docs/notes/ending-column-2026-11-13.md`).
3. Done in #1369 to #1371: data changes for new units, which the backtest j9
   (`docs/model/drift.md`) scores. No fit reads any of them.
   - #1369: `coop` and `condo` columns from each row's own PLUTO release, in a copy of L1's
     dataset (`docs/notes/coop-column-2026-11-13.md`). L1's held-out co-op ads sit at
     -0.74 ± 0.14% from its median, against -0.43 ± 0.02% for the rest. L1 shows no co-op
     excess, since its unit levels come from each unit's own ads, so a co-op term bears on
     the new-unit j line more than on L1. The note also found that every PLUTO feature of the
     drift line, the condo flag among them, reads the 26v2 release for every row, so an ad
     priced in 2015 reads its building as of 2026. No drift module reads the point-in-time
     PLUTO base.
   - #1370: unit codes carried from a unit's earlier ads, in a copy of L1's dataset
     (`docs/notes/amenity-carry-2026-11-13.md`). The carried code equals L1's `umean:` above
     zero on every row, so L1 and j9 already read it. The only new form is an omission flag,
     which a fit should build inside the kitchen-sink design.
   - #1371: S13, a screen of building turnover (`docs/notes/turnover-screen-2026-11-13.md`).
     On j9's new units the lowest turnover quartile asks +2.25 ± 0.29% over j9 and the
     highest -0.72 ± 0.28%, while L1's held-out ads show no gradient (+0.02 ± 0.04). Its
     verdict is a turnover column, with no fit until L1's line has a market-split backtest.

### Earlier in the sprint

- **Screens.** In `docs/notes/causal-screens-2026-11-13.md` (#1354) I ran ten screens of
  L1's held-out ads and found three fit candidates: a level for each lease phase, paths for
  bedroom groups and zones, and a noise factor for duplexes.
- **Proposal.** https://claude.ai/artifact/B9E2j5YXVE6P6gApecazLv, put to Ben as option B
  at 12:34 ET. Fits 1 to 4 each run three H100 containers on the latest split against L1:
  1. L2, a level for each lease phase: +150 to +350 elpd, gate 75%, about $11.50.
  2. Segment paths: +250 to +600, gate 50%, $11 to $12.50. Before the memory PR the host
     needed the large container, at $15 to $16.50.
  3. A duplex noise factor of 1.25 to 1.45: +150 to +300, 80% coverage of duplex ads from
     0.72 to 0.77 or more, gate 70%, about $11.50.
  4. A level for each line, from a new collapsed module: +150 to +600, gate 45%, about
     $11.50.
  5. The winner's market and backtest fits and the Deals publish, about $23.

  Option B covers fits 1 to 5 and a spare, about $81. A fit that adds sweep time gets a
  timing check before launch. Fits 2 to 4 would go on L1T if a Student-t unit level passed
  its gate first. L1T missed it, and L1TK (#1357, written, not fit) is expected to miss on
  unit_sd, so for now they go on L1.
- **Written and ready.** L2, `drift-building-phase-level` (#1355,
  `docs/notes/l2-phase-level-2026-11-13.md`), and the segment paths,
  `drift-building-phase-segment` (#1356, `docs/notes/segment-paths-2026-11-13.md`). Each note
  holds its launch commands and predictions. The segment paths step by quarter, since weekly
  steps would need 85 GB for the design.
- **Host memory.** `b0.main_run` now deletes the design of all rows before the sampler
  starts, and `drift.make_sampler` gathers each block's design straight from the training
  rows, with every pinned draw unchanged. The segment fit's host peak falls from about 44 GB
  to about 21 GB and L1's from about 16 GB to about 9 GB, so the segment fit runs in the
  normal 40 GiB container (`docs/notes/segment-paths-2026-11-13.md`, Cost).
- **Duplex column.** `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex` in
  `/data1/apartments/frontier/datasets/` holds L1's dataset with S7's pattern as the column
  `duplex` (`docs/notes/duplex-column-2026-11-13.md`). The duplex fit's module is
  `drift-building-phase-duplex`, D1 (`docs/notes/duplex-factor-2026-11-13.md`), with its
  launch commands and predictions. Its factor k widens the noise of marked rows only, so no
  row's location in a draw moves with its own mark; I revised it to that before any launch
  (#1362). After S14 (`docs/notes/unusual-units-2026-11-13.md`) I folded the ads whose text
  calls the unit a penthouse into its mark (#1376): `rentfrontier.b0penthouse` writes the
  column `penthouse` into `...-closingraise-duplex-penthouse`, the copy D1 now reads, and I
  revised its predictions before any launch. It is written, not fit. `drift_today` supports
  it (#1364).
- **S12, the negative amenity terms.** In `docs/notes/amenity-signs-2026-11-13.md` I looked
  for the causes behind L1's wrong signs, with no fit. In the ad regressions hardwood's own
  term comes from re-listing drift, about 0.75% less per later ad of a unit, though I haven't
  run that inside L1. City views and balcony are negative only between buildings and
  listers. Patio, roof rights, hardwood between
  units and live-in super have no named cause. No fit candidate came out.
- **S12's photo pilot.** I committed its method and predictions (fb308c5f) and started the
  fetch of 483 photos at 6:10 PM ET on Nov 13. I stopped it at 6:14 PM, about 200 photos in,
  after the auto-mode classifier refused two related actions as instruction poisoning. The
  memory note `oxylabs-standing-spend` says photo fetches need Ben's own message, and I asked
  him for it in the thread. `p_fetch.py` skips the keys already in `fetch.jsonl`, so a rerun
  resumes. The data sits in `/data1/apartments/tmp/sprint-20261113/photos/`. `PHOTO_RATER.md`
  and `p_score.py` are committed with the line model's PR. To finish it, move the `rate/`
  folders into a directory holding nothing else, run a Sonnet rater for each of the 7 batches
  and score with `p_score.py`.
- **LN1, the line model.** `drift-building-phase-line` (`drift_line.py`,
  `drift_building_phase_line.py`) gives each unit's lasting level a line level (building,
  bedrooms, full baths) and integrates the lines out in the building's collapsed step. It is
  written, not fit, with its note and predictions in `docs/notes/line-level-model-2026-11-13.md`.
  On the 1-in-90 sample line_sd comes to about 0.13 and unit_sd to about 0.015, against L1's
  0.06. Three containers would cost about $11.50 to $12.00. `drift_today` prices its
  apartments with their line levels (#1368).
- **Another thread's jobs.** The l1t and l1tk work on thelio belongs to another thread. I
  leave it alone.

## Research sprint, 2026-11-12 12:48Z to 20:48Z

Ben started an 8-hour sprint at 12:48Z with $20 of Modal. I spent $18.82 of it: c3's three
containers and a failed start ($11.11), then L1's two ($7.71). The ledger is
`/data1/apartments/tmp/sprint-20261112/spend.md`. No sprint fit is running.

- **c3 won.** b9's design on `b0closingraise` gained 641.5 elpd over b9 (SE 100.7) on the
  183,272 held-out ads the two datasets share (#1331, `docs/notes/closing-asks-2026-11-11.md`).
- **L1 won over c3.** `drift-building-phase` (#1330, 9a7830fb) scales each row's noise by
  its lease phase, the months since the unit's previous ad. The pool
  `drift-building-phase-b0-latest-9a7830fb-l1` passes the gate and beats c3's first four
  chains by 554.6 elpd (SE 63.2), and all six by 515.5 (SE 62.1). Results and the scored
  predictions are in `docs/notes/lease-phase-noise-2026-11-12.md` (#1334), the explainer at
  https://claude.ai/artifact/KUjb66H78JKQkJunjW9Dng. Neither c3 nor L1 is on the site yet.
  The site needs L1's market and backtest fits first.
- **L1's market and backtest queue, waiting for a sprint budget.** Ben ended the daily Modal
  budget on 2026-11-12 at 12:27 ET and now approves a budget for each sprint, so nothing
  launches until he approves the next one. At 12:35 ET I stopped the transient timer
  `queue-l1-market.timer`, which was set to fire at 15:50 ET. Stopping it removed it, and no
  other user timer or unit launches Modal fits. `cap.py`'s rate and ceiling are $0 from
  12:27 ET (`docs/model/modal.md`). The script
  `/data1/apartments/tmp/sprint-20261112/queue-l1-market.sh` stays on disk. It launches six
  containers, l1na, l1ja, l1nb, l1jb, l1nc, l1jc (seeds 31, 41, 32, 42, 33, 43), on the
  closingraise market and as-of 2025-11-10 datasets (#1332), at about $23 in all. Under a
  sprint budget it needs `--outside-budget` added to its arguments. Its `cap.py
  --check-launch` loop passes the same arguments, so with the flag that check exits 0 at
  once. After the fits, pool
  them as `drift-building-phase-b0-market-9a7830fb-l1n` (l1na, l1nb, l1nc) and `...-l1j`
  (the three j's), check the gate, run the backtest, and publish Deals from the market
  pool.
- **Sampler version of the queue's fits.** #1337 rewrote the slice step in `drift.py` as a `lax.scan`,
  and its draws are bit-identical to the old step's on CPU only. The queue passes commit
  9a7830fb to `ops/modal-fit`, and the container copies that commit's checkout
  (`ops/modal/app.py`), so the market and backtest fits run the sampler L1's latest-split
  fit ran. I also ran the GPU check below, so fits from either side of #1337 can be
  compared.
- **Free checks**, each in a note:
  - Deals ads on pricier lines (#1335, `docs/notes/deals-pricier-lines-2026-11-12.md`).
    The 17,594 held-out ads whose median sits 0.15 or more above the building's other
    same-count asks land 0.024 under L1's median, and its 80% intervals cover 0.703 of
    them, against 0.812 for the rest. Neither L1 nor U2 is expected to move them. The note
    proposes a level for each line (building, bedrooms, full baths).
  - First ads and quick returns (#1336, `docs/notes/first-ads-and-quick-returns-2026-11-12.md`).
    L1's large "none" factor (1.64) comes from the tails: units with a single ad have 0.82%
    of rows beyond 6 robust scales, later ads 0.31%. Ads 0 to 2 months after the previous
    one undercover because cuts and raises over 10% cover 0.38 and 0.37, while same-ask
    reposts cover 0.91.
  - Noise by calendar year (#1337, `docs/notes/year-noise-2026-11-12.md`). L1 loses 226.7
    elpd (SE 30.3) to c3ab on 2020 to 2022 asks and covers 0.736 of them at 80%.
  - A level for each line (#1342, `docs/notes/line-level-screen-2026-11-12.md`). I moved
    each held-out ad by the shrunk mean of other units' held-out residuals in its group
    and rescored L1's predictive. Counting only earlier ads, the line gains +750 elpd
    (SE 83) and building and bedrooms +706 (SE 49). The Deals ads on pricier lines gain
    elpd too, but their median shortfall only moves from -0.0246 to -0.0235. I did not
    write the term: the note sets out a nested, collapsed line level for a new module,
    with predictions.
- **F1 withdrawn.** `drift-building-phase-first` (#1341) split L1's "none" phase by
  whether the unit is listed again later, which reads the future. Ben withdrew it at
  16:24 ET before any fit, and #1344 removed the module
  (`docs/notes/first-ad-split-2026-11-12.md`). I checked L1, Y1 and U2 for the same
  flaw. L1's phase counts months back to the unit's previous ad, Y1's factor reads the
  row's own year, and U2 changes only the prior on unit levels, so none of them reads a
  row's later ads.
- **U2 launch error.** I launched U2's three containers at 17:04 ET without
  `--split latest`, so they fit the rows split and can't be compared with c3. I stopped
  u2b and u2c at 17:56 ET. The round cost $11.10 (u2a $3.61, u2b $3.76, u2c $3.73) on
  top of the sprint's $18.82. On u2a's draws the unit level's degrees of freedom come to
  about 2.2, and `unit_dof` and `nu` mix slowly enough (ESS 65 and 46 on 2 chains) that a
  6-chain pool would likely miss the gate (`docs/notes/unit-t-level-2026-11-12.md`).
  `ops/modal-fit --baseline RUN` now refuses a launch on a split other than RUN's, and the
  launch script passes it. A relaunch, about $11, waits for Ben.
- **Models merged and not yet fit.** Y1 (`drift-building-phase-year`, #1337, L1's noise
  times a factor for each calendar year, against L1, two containers, about $8.4). Its
  predictions are in its note.
- **Tests on master 99bf5f92.** The folder-at-a-time run was killed at its memory cap, so
  I ran pytest once per file instead (`/data1/apartments/tmp/sprint-20261112/suite/`,
  `runfiles.sh` and `runroot.sh`, summaries in `files.summary` and `rfiles.summary`).
  The root tests ran all 205 files and passed 3,099, with four files holding no tests. The three Modal files need the
  `modal` package, which `bridge-root` lacks, so I ran them in `nj-root`, where their 5 tests pass. The frontier
  tests passed 964 in the 98 files left after the killed run, which had
  passed 329 in the 55 files before it. No test failed. `test_building_zones_floor.py`
  passed 14 tests and then hit the 30-minute limit for one file, so its remaining tests
  went unrun.

### Follow-ups the review of #1337 left

1. Done at 12:20 ET. I ran the phased test design (2 chains, 60 warmup, 8 draws, seed 3)
   on thelio's GPU at 9a7830fb and at f9277d32, using the `sim-recovery` venv, the one
   with a CUDA jaxlib. On the GPU the draws are not bit-identical: 26 of the 40 traced
   and kept arrays differ, by at most 9e-8 of an array's largest value. Two runs at the
   same commit gave different hashes too (b2aa3ea8 and then 7da3aee7 at 9a7830fb,
   16b3833c and then b6aa8a8b at f9277d32), so the GPU itself rounds differently from run
   to run, and the scan adds nothing larger. The script and arrays are in
   `/data1/apartments/tmp/sprint-20261112/gpucheck/`.
2. Done in #1339: sha256 pins for the draws of `drift-building-phase` and
   `drift-building-unitt`.
3. Y1's cap margin. `cap.py` estimates 3,560 s a container against the 3,600 s cap. The
   sampler stops on its 2,520 s budget rather than a draw count, so Y1's wall should
   match L1's: L1 had the same estimate and settled at 3,165 s and 3,191 s. That leaves
   about 400 s for staging and download. Before Y1 launches, either keep the design and
   record that margin in its note, or cut the sampling budget by 300 s and lower its
   draw estimate to match.

### After L1's market and backtest fits, in order

This replaces the list under the outlier sprint below. Every fit here waits for a budget Ben approves for a sprint, and it launches with `--outside-budget`.

1. **Y1** (about $8.4). It is the only queued change built on L1, so a win serves
   directly once its own market fits run. The 2020 to 2022 shortfall it targets is the
   largest loss L1 has by year. It launches after follow-ups 1 and 3.
2. **U2** (about $11), against c3 as its note sets it, launched with `--split latest
   --baseline drift-building-b0-latest-ae875fc6-c3`. A win shows that the heavy unit
   tail helps, but serving it needs a fit of the tail on L1's line, so it comes second.
   I read the 300 units furthest from their building
   (`docs/notes/unit-level-reads-2026-11-12.md`): 74% are real apartments with real
   premiums, about 6% carry a backed data error, and b9 prices the ones above their
   building too low on their held-out ads (43% above its 80% interval). The note
   recommends writing L1 with a Student-t unit level whose degrees of freedom are fixed
   at 3, without waiting for the data fixes, and writes its predictions. That model,
   `drift-building-phase-unitt` (L1T, #1349), ran on 2026-11-13 in 3 containers for
   $10.94 and missed the gate on R-hat (nu 1.025, unit_sd 1.019). As a free check it beats
   L1 by +4,095 elpd (SE 172) on the shared held-out ads
   (`docs/notes/l1-unit-t-fixed-2026-11-12.md`). It is not served, and gets no new seed. The
   next step was a model change that lets nu and unit_sd move with the kap.
   `drift-building-phase-unitk` (L1TK, `docs/notes/l1-unit-kap-collapsed-2026-11-13.md`)
   draws the kap with u and the levels integrated out. On a CPU check it frees nu (its
   autocorrelation time falls 3.5 times) but barely moves unit_sd, so the pool would likely
   still miss the gate on unit_sd (expected R-hat 1.017). It is not launched.
   `drift-building-phase-unitkn` (L1TKN, `docs/notes/l1-row-dof-fixed-2026-11-13.md`)
   holds the rows' nu at 2 as well, a second change against L1 that L1T's posterior
   (nu 1.99) makes negligible. On the same check unit_sd's autocorrelation time falls
   from 44 to 12.5, and the pool's expected highest R-hat is 1.008, so it likely passes
   (75%). It waits for Ben's approval to launch, at about $11 for 3 containers. The fit adding duplex and outdoor size
   (`docs/notes/unit-flags-scope-2026-11-12.md`) comes after it. Of its 18 backed corrections, 4 went into the ledger (plus a fifth ad of one unit), 2 were already there, 10 are flex bedroom counts left out under the 2026-10-17 retract, and 2 failed a closer check (`pipeline/ledger/2026-11-12-unit-level-reads.ndjson`).
3. **The income flag** (`docs/notes/income-flag-2026-11-11.md`), on c3's dataset. It gains
   997 rows and loses 110, so I expect a small gain. Serving it also needs a fit on L1's line.
4. **Candidates from the free checks.** Each needs its predictions written first:
   - a noise mix for quick returns, separating near repeats from repricings
   - a noise factor for units with no earlier ad, built from what is known when the ad
     opens (`docs/TODO.md`)
   - a level for each line. The screen in #1342 supports it on all ads but not as a fix
     for the Deals ads on pricier lines, and the model needs a new module first

## Outlier sprint, final state at 2026-11-12 13:00Z

Ben asked at 2026-11-11 18:55Z for 24 hours of chasing the ads the model prices worst; the
sprint ends about 2026-11-12 18:55Z. The findings are in
[the sprint note](../notes/outlier-sprint-2026-11-11.md) and
[the closing note](../notes/closing-asks-2026-11-11.md). Scratch work is in
`/data1/apartments/tmp/outlier-sprint/`, with the second session's work under `s2/` (a
folder for each line of work, each with a `results.md`).

- **No Modal fits until the sprint ends** (Ben, 2026-11-11 22:07Z). The unit `outlier-c2` is
  stopped and stays stopped, and no Modal unit or timer is pending. Every fit idea of the
  sprint is in `docs/TODO.md` with its predictions.
- **Merged:** the ledger corrections (#1307), `b0closing` (#1308), `b0income` (#1309), the
  closing-ask results (#1310), the sprint note (#1311), the walk's slow hyperparameters
  (#1313), the causes of the off-day price changes (#1314), the pass 2 ledger (#1315),
  the narrowed closing dataset `b0closingraise` (#1317), the second-look ledger (#1318),
  `b0chains` (#1319, with the carried split in #1320), the sprint docs (#1322, #1324), the
  ledger for ads coded 0 across all listers (#1325) and rule B2 with the record fixes of
  the random read (#1326).
- **Closing asks.** A second look at the records' event times kept the rewrite for the
  59,026 rows whose ask is a raise typed as the ad closed, and dropped it for cuts and
  earlier raises. c3 (b9's design on `b0closingraise`, three containers of 2 chains) takes
  c2's place; its 7 predictions are in the closing note. To score it against b9 on the
  unchanged held-out ads, pool with `rentfrontier.drift_pool`, score with
  `rentfrontier.drift_score`, and compare with the scratch script
  `/data1/apartments/tmp/outlier-sprint/compare_c1.py RUN_A RUN_B`.
- **c1's gate miss** reads as a tail event of 4 chains on a ridge the walk's scales cross slowly
  (chance 2.1% to 2.8% against 0.55% to 0.74% for 6 chains). Gate fits run 6 chains. The
  reparameterization proposed earlier is withdrawn.
- **Reads.** Pass 2's 600 ads are in `p2/reads/b_*.jsonl` with the proposals in
  `p2/actions.parquet`. The text flags of every row are in `qual/flags.parquet` (1,893,800
  rows, 31 flags), and their residuals are in the sprint note. The commercial and room
  screen (`nonres/matches2.parquet`) led to no pipeline rule: its matches sit near zero gap.
- **Ledger rule learned in the sprint.** An apartment changes over the years (a renovation,
  a flex wall, two units combined), so another ad of the unit backs a correction only when
  it is close in time or the ad shows the same configuration. Two merged bedroom sets
  failed that test and are retracted. The table of every sprint set against the distance
  to its backing ad is `s2/F3/timegaps.parquet`.
- **The Rheingold (10 Monteith St)** has brokers posting ads for any unit of the building
  under arbitrary unit pages: 431 of its 592 pages with two or more kept ads hold two or
  more bedroom counts. A page of this building does not identify an apartment.
- **Reposts under a new label.** A lister reposts an apartment under a changed label the
  day its ad comes down. Ben's standard (2026-11-11): photos, text and timing only
  nominate a link, since a landlord reuses them for other apartments of a line. A join
  needs a label to fail as a real unit, absent from the lot's city records and off the
  building's grid of floors and lines. `s2/G/code/std.py` applies it: 19,787 joins of
  64,953 nominated links, 16,381 between two passing labels, 28,785 undecided (records
  too thin in 55% of the buildings). Verdicts are in `s2/R/v4/links_standard.parquet`,
  the collapsed dataset in `s2/C/ds-std` (18,208 rows dropped). An earlier count of
  70,300 chains is withdrawn. Ben has two looser variants in front of him (adequacy at
  50%, the grid deciding alone on thin-record lots) and has not chosen either, so the
  75% standard stands.
- **Units with no ad in training** (about a third of open ads, counting buildings new to
  training). In the backtest j9 the 80% range covers 0.767 of the final asks of new units
  in known buildings and 0.678 in new buildings, against 0.805 for units with history.
  Relabeled reposts and placeholder pages account for little of it. The shortfall is in
  apartments of 2 or more bedrooms (0.733, 0.693, 0.663 by count), and the new large
  units of a building miss together (pair covariance 0.0082, half their variance).
  Candidates U4 and U3 in `docs/TODO.md`. Scripts and saved output are in `s2/N/` and
  `s2/N/out/`.
- **The level of the held-out gap.** The served median is 0.47% above the held-out asks,
  and in 2022 and 2023 most of that comes with the latest split holding out each unit's
  last ad, an ask low against the unit's history. A base of about -0.4% in the other
  years is unexplained. Closing asks in training
  give about 0.1 point. On the single backtest day j9 the open ads with unit history
  have +0.3% (n9, on asks still open, has +0.8%), so the offset of the split is not
  measured on the Deals page's ads. A level change gaining elpd on the latest split needs a
  backtest before it reads as a better median.
- **Concessions.** Wording with no recorded free months is on 11.9% of rows through 2019
  and 12.3% of 2020's, and on about 1% since. In 2020 those ads are covered 0.730
  against 0.762 with no concession, so the wording gives at most about 0.01 of the
  year's shortfall, and none of 2021's.
- **Ads coded 0 bedrooms across all listers.** About two thirds of the blank ads coded 0
  are real studios, so the blank-form exclusion stays with the listers whose form sends the
  default (Real Street, M1 Ventures, Stuyvesant Heights Realty). The ledger file
  `2026-11-12-outlier-sprint-zero-coded-feedwide.ndjson` sets 270 ads and excludes 479; the
  scripts and the Sonnet reads are in `/data1/apartments/tmp/outlier-sprint/s2/Z/`
  (`zrules.py`, `zbuild.py`, `sread/`). A unit page's other ads do not back a set for a
  blank ad: the listers posting blank forms score 81% to 90% on their own typed ads.
  Rule B2 excludes 412 more blank ads in buildings with no studio anywhere in their history
  (`2026-11-12-outlier-sprint-zz-blank-rule-b.ndjson`, scripts in `s2/BB/`).
- **Deals.** Of the default top 60, readers judged 36 false, and 27 of those come from the
  model with a correct record: a building level set by pricier lines (15) or a unit whose
  own recent asks match the deal (12). For 9 of those 12 the fit has 1 to 9 training ads of
  the unit and still prices it 14% to 39% above them. I added no caution and
  left the page as published. The reads are in `/data1/apartments/tmp/outlier-sprint/s3/deals/`.
- **Updates to Ben.** He asked for a short update about every 30 minutes and whenever
  something finishes, with the long reports kept for results.

### After the outlier sprint, in order (superseded by the research sprint's list above)

No sprint item is running or queued on Modal or thelio. The fits wait for Ben's lift of the
sprint's hold, each with its predictions in the sprint note or the closing note before it
is launched. Order, by what each is worth for the Deals page:

1. c3, b9's 6-chain design on `b0closingraise` (closing note). It replaces c2.
2. The income flag on c3's winner's dataset (`docs/notes/income-flag-2026-11-11.md`).
3. U4, a unit scale by bedroom count, then U1 (a unit scale growing with size), U3 (a
   building term for large units) and U2, for units with no ad in training.
4. L1 (a noise scale by lease phase), then Y1 (by calendar year), then L2 (a level per
   lease phase on L1's winner).
5. No fit of its own for the sprint's ledger entries or for R, the collapsed repost chains.
   The pipeline's next dataset rebuild for a market snapshot carries both into the next fit.

From the Deals reads: the 9 unit-history deals with training ads follow the pattern of
"Previous asks far over the model" in the sprint note (held-out gaps rising with the unit's
previous-ask deviation, most for units with no coded size), so U4 comes first among the
unit scales. A free check is still open for the 15 deals whose building level follows its
pricier lines: whether the building's same-count ads predict their final asks better than
the median does.

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
