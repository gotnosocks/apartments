# Data improvements — handoff

Updated 2026-10-07 23:45 ET. Thread owner: the Data improvements project thread (bridge session on thelio).

## 2026-10-07 23:45 ET

- **Five neighbourhoods are on master (#460, 5789d79):** Chelsea, the West Village,
  Greenwich Village, Flatiron and Gramercy Park.
  - `rentfrontier.areas` splits the FGP crawl into Flatiron and Gramercy Park, each building
    taking the area named in its StreetEasy page title. Snapshot:
    `external/areas/20261008-6027acc` (480 Gramercy Park and 327 Flatiron buildings; one Park
    Slope building left out).
  - `cohort areas` relabels each row's `neighbourhood` to its building's area. No rows or rules
    change.
  - `DATASET_NB5` = `datasets/chelsea-wv-gv-flatiron-gramercy-analysis-20261008-0a23057`.
    Rows: Chelsea 52,614, WV 34,205, GV 18,425, GP 18,333, Flatiron 12,182.
  - `nb5-coded-v2` = nb3-coded-v2 plus Flatiron and Gramercy Park indicators (`hoods_v1`); it
    is in NB4_SETS.
  - Map check: two contiguous areas. One Union Square South keeps StreetEasy's Flatiron label.
- **Every queued test now runs on five neighbourhoods.** The nb4-* ids are gone from the
  branches. Modeling queues each as its own full fit on DATASET_NB5, after the nb5-coded-v2 base
  fit (launched 23:20) and its bedtime6 test.

  | PR | Test | Head | Unit |
  |---|---|---|---|
  | #435 | nb5-stab-v1 | 0233ec5 | frontier-modalq-nb5tests; suite passed |
  | #439 | nb5-plutoasof-v1 (`hoods_v1` over nb3-plutoasof-v1) | 8af14dc | frontier-modalq-nb5tests |
  | #420 | unit-labels-v12 | 881b345 | frontier-modalq-nb5rules |
  | #425 | unit-splits-v5 | d478a5b | frontier-modalq-nb5rules |
  | #437 | nb5-permit-v1, DOB `external/dob/20261008-4e1948c` (50,420 jobs) | e935808 | frontier-modalq-nb5permit |

- **The DOB fetch now retries 5xx errors and uses smaller queries** (25 BINs per request, pages
  of 10,000), on the #437 branch.
- **Run test suites with `JAX_PLATFORMS=cpu XLA_PYTHON_CLIENT_PREALLOCATE=false`.** A suite
  held 6 GB of the GPU and made Modeling's m0-base baseline fail with a GPU OOM.
- **PR bodies:** read them with `gh pr view` from inside a worktree. Run outside one, it prints
  nothing, and a PATCH built from that wipes the body. #437's body was restored from its
  userContentEdits history.

## 2026-10-07 22:20 ET

- **Flatiron + Gramercy Park data is on master:**
  - #447 adds unit-labels-v11 (FGP aliases and history pairs). This is now the current rule.
  - #451 adds the nb4 snapshots: `NB4_*_FILE` in features.py, `_NB4_DESCRIPTIONS`, and
    `descriptions.FGP_SOURCE`. Storefronts are now fetched one reporting year at a time. The
    pre-squash commit e78c6fd is kept in archive/pr-451.
  - #452 adds `DATASET_NB4`: 135,759 rows, 30,515 of them FGP; 135,477 pass the master rules.
  - In listing extras, 165 nb3 listings now take FGP's later capture. That touches 39 CWG rows.
- **Modeling's part:** Modeling builds nb4-coded-v2 in its own PR and queues one full fit of the
  served design on DATASET_NB4. DATASET, `ops/modal/fit.py` and `config/main-analysis.json` stay
  on CWG until an nb4 fit is served.
- **The queued tests are rebased onto v11** so their fits stay servable.

  | PR | Test | Head |
  |---|---|---|
  | #420 | now unit-labels-v12: v11 plus merging spelled-out labels | dc65ba3 |
  | #425 | unit-splits-v5 | 65260da |
  | #435 | stab | 5bd6e4b |
  | #437 | permit | a941744 |
  | #439 | plutoasof | bbc0805 |

  The queue is frontier-modalq-data11. The first fit starts about 06:30 ET and the rest follow
  about every 2.4 h. Merge #420 only if its fit passes. Bump no other rule version mid-queue
  without telling Modeling first.
- **Possible follow-up:** RULE_SOURCES for v11/v12 records only the alias file, not
  history-20261007.jsonl. Ask Modeling before changing it.

## 2026-10-07 21:45 ET

- **Policy (Ben, 22:27Z, relayed):** every test is its own Modal full fit through Modeling's
  queue and is served if it passes the gate. There are no thelio exploration pairs and no
  bundling. The Modal balance is capped at one day's accrual (#433). Merge a feature PR only once
  its fit passes the gate.
- **Open-data survey (#434, merged):** it is at the top of `docs/model/research-backlog.md`.
  Survey scripts and data are in `/data1/apartments/tmp/suspect/opendata/`. HPD owners and agents
  are not proposed.
- **Three features are queued with Modeling as their own Modal full fits:**

  | PR | Feature | Head | Snapshot | Rows affected | Fit |
  |---|---|---|---|---|---|
  | #435 | nb3-stab-v1 | 2c38a45 | rentstab/20261008-6b42fe8 | share > 0 on 73% | frontier-modalq-stab, about 08:30 ET 10-08; suite passed |
  | #437 | nb3-permit-v1 | 9fdd817 | dob/20261008-ab3d278 | 1,390 rows, 928 units | frontier-modalq-permit, about 10:55 ET |
  | #439 | nb3-plutoasof-v1 | 77c738e | plutohistory/20261008-931c6e8 | 23,352 rows | asked to queue after permit |

  - **nb3-stab-v1:** rent-stabilized share as of the tax bill of the year before the listing.
  - **nb3-permit-v1:** a DOB A1/A2 permit naming the apartment, issued in the 3 years before the
    listing month.
  - **nb3-plutoasof-v1:** nb3-coded-v2 with MapPLUTO from the release of the year before the
    listing. Today's year built is kept.
  - Each fit pairs against the 4500-draw serving refit, which passed the gate at 20:56 ET and
    which autoselect switches to.
  - After each fit lands: record it in `docs/model/feature-tests.json` `hand_tests`. If it passes,
    merge the PR (frozen heads; merge master in first), and tell Modeling and the coordinator.
- **Still queued with Modeling:** unit-labels v10 (#420, 2da098d) and v5 (#425, 98a146d).

## 2026-10-07 15:40 ET

- **quarantine-v6 and unit-reviews-v1 (#419, merged 9b6c16d) are current.** At 110 W 26th St,
  R and B are the same rear unit (Ben, 17:59Z: the R and B listings "both refer to the unit at the
  back of the building"): `config/reviews/unit-joins-20261007.jsonl` joins 4R/4B and 5R/5B. The
  five bare floor-number ads there are quarantined (`quarantine_unit_unknown`). `apply_rules` now
  refuses unit-reviews before unit-labels. Modeling re-pointed the v4 serving refit
  (frontier-modalq-sp4) to 9b6c16d. The cheap 2015 5F ad (https://streeteasy.com/rental/1566842)
  is a genuine renovation and relist (Ben, 18:44Z), so it stays in the unit.
- **unit-labels-v10 (#420, draft, head 2da098d) won its exploration pair:** +49.2 ± 21.9
  (2.2 SE; Chelsea +19.3, WV +22.8, GV the rest) against fa61d6c's coded-v2 arm on v9 + v4. Each fit's LOO
  MCSE is about 10. It joins spelled-out labels to short ones ("5 FL" = "5", "Penthouse" = "PH",
  126 groups, 262 rows, no bedroom guard: v4 splits bedroom changes). Modeling queued its Modal
  full fit after the v4 serving refit. Merge #420 only after that pair; merging makes v10 current.
- **Renovation split (coordinator relay 18:45Z): sized, not run as a split.** Sizing is in
  `/data1/apartments/tmp/suspect/renov/size.py`: 179 splits at a market-adjusted jump of at least 30%,
  93 with a broker change, 51 at 50% or more, about 80% precision. A price-gated split reads the row's
  own rent, so I proposed the leak-free feature instead: **nb3-renov-v1 (#422, draft)** flags
  4,008 rows whose ad says newly or gut renovated when the unit's previous ad did not. Its arm
  is unit frontier-renov-explore (`/data1/apartments/tmp/suspect/renovfit/`, rules q-v5, ul9, splits-v4,
  label ul9s4), paired with fa61d6c's arm through `pair_subsets.py` (see `prevjump/pair3.sh`).
- **Skipped or backlog:** loft flag skipped (Ben, 17:46Z); HowLoud sound scores to the backlog.

## 2026-10-07 14:10 ET

- **unit-splits-v4 (#414, merged 5f0a7f0) is current.** It is v3, but a one-bedroom change does not
  split when the earlier ad gave no square footage and the new one does. Why: v3 failed coded-v2's
  group R-hat gate at building 120 = 110 W 26th St, a loft building (split R-hat on level, bedroom
  slope and size slope 1.08, against 1.00 under v1). Five cheap footage-less "1-bed" ads
  ($2.4–2.6k, 2015–2021; probably room shares, no ad text) split its 1,400–1,650 sq ft units.
  v4 moves 619 rows of 314 units in 184 buildings back relative to v3. The attribution of
  v3-vs-v1's +953 put only +5.3 on those boundaries. Scripts: `/data1/apartments/tmp/suspect/rhat/`.
  Modeling queued frontier-modalq-sp4 (coded-v2, loc-v1, bedtime6 at 5f0a7f0, label
  a100-3600k9cb1-gv1006-ul9s4) to land about 00:30 ET 10-08. Autoselect switches if the gate passes.
  Modeling then sends the v4-vs-v1 pair and loc-v1's clean pair. Record both in the ledger.
- **nb3-loc-v1 ledger note (#415):** +9.2 ± 15.3, provisional until the clean pair on v4.
- **Lofts (Ben, 17:34Z: "a different category for these loft-style apartments?").** Sizing:
  MapPLUTO has no L class among our buildings. D5 (converted) covers 21 buildings and 2,111 rows.
  In 310 buildings at least half of all ads (any date) say "loft". In those buildings a 1-bed has a median of
  1,015 sq ft against 700 elsewhere, and units change bedroom count 25% of the time against 12.5%.
  Room shares: no rule. A spot-check of "roommate" text hits found whole apartments; most cheap
  footage-less ads were real studios. Scripts: `/data1/apartments/tmp/suspect/loft/`.
- **nb3-loft-v1 (#416, merged fa61d6c):** coded-v2 plus a causal loft flag (D5, or at least half
  of at least 3 strictly-earlier ads say loft), loft × (bedrooms − 1) and loft × size deviation.
  It flags 7,890 rows in 304 buildings (the causal rule is stricter than the sizing): D5 only 1,634, text only 5,779, both 477. Modeling's exploration pair is
  unit frontier-loft-explore (label x-2060-100w600d-gv1006-ul9s4, v9 + v4), due about 15:15 ET.
  If it gains, Modeling runs a Modal full fit. Record the pair in the ledger.

## 2026-10-07 11:00 ET

- **unit-splits-v3 (#408, merged 8f40c96) is current.** It splits a unit's history at any change of
  bedroom count (threshold 1, from #400's v2). When a count returns, those listings rejoin that
  earlier piece. Coded-v2 pairs on v9: v3 vs v1 +953.0 ± 98.0 (Chelsea +381.8, WV +339.0, GV the rest); v2 vs
  v1 +780.3 ± 101.5; v3 vs v2 +172.7 ± 42.6. #400 closed as superseded. I asked Modeling and the
  coordinator for the coded-v2 serving full fit on 8f40c96 in place of the v1-rules fit.
  Pair scripts: `/data1/apartments/tmp/suspect/prevjump/pair3.sh`.
- **text-v1 (Ben, 2026-10-07):** fair WV+GV score +43.7 ± 23.5 (1.9 SE); not restored. It is back
  in `docs/model/research-backlog.md` as text-v2 (#406). Ledger rows: `hand_tests` in
  `docs/model/feature-tests.json` (#404).
- **Yearnoise lead:** the gain is market scatter (residual SD about 9% from Sep 2020 to Feb 2021),
  not a data problem; no rule. Modeling takes a pandemic term per segment.
- Possible follow-ups: #408 reviewer nits (merge the duplicate isnan checks, test a multi-row ad
  with rejoin); ledger hand_tests rows for unit-splits v2/v3.

## 2026-10-07 09:00 ET

- **Prevprice jump audit** (asked by Modeling). The served fit's high-k rows with a big rent jump
  from the unit's previous listing are not from bad label joins: the share of jumps over 40% is
  8.2% for raw StreetEasy ids and 6.5–9.7% for the v5/v8/v9 joins. They come from bedroom counts
  that change inside one unit id. Change of 2 or more: 583 pairs, 63% big jumps, 5.8% high-k.
  No change: 6.8% and 0.6%. Scripts: `/data1/apartments/tmp/suspect/prevjump/`.
- **unit-splits-v1 (#397, merged 39c3c8a):** a unit's history splits where an ad's bedroom count
  differs by 2 or more from the previous ad with a count; 1,058 rows of 463 units. `apply_rules`
  refuses unit-splits unless it comes last. Exploration pairs (rows split, 69cb5c6, v8, splits
  vs base): coded-v2 +475.4 ± 56.4, prevprice-v2 +488.2 ± 57.6. In both, the moved rows gain
  about +210 and the rest comes from rows left in the original unit.
- **#394 (v9) merged** as 9c96f74. Modeling cancelled the v8 latest arm and will run one Modal
  trio on 39c3c8a from midnight ET 10-08: prevprice-v2 rows (the one to serve) and prevprice-v2
  and coded-v2 latest.
- A threshold of 1 for the split is untested: 3,871 pairs, 20.7% big jumps, 1,374 of them
  involving a studio. Alcove and flex coding make that noisier.

## 2026-10-07 04:40 ET

- **unit-labels-v9 (#394, draft, reviewer approved):** v8 plus number-word-and-letter labels
  ("fourb"/4B, "five-a"/5A) joined to their twins when bedrooms agree; 46 unit ids, 297 rows.
  Exploration pair vs v8 (coded-v2, rows, b50430b): +29.9 ± 20.0 overall, +22.5 ± 8.2 on the 261
  relabelled rows. **Merge only after Modeling decides v8** (its last v8 latest arm launches on
  Modal at midnight ET 10-08; latestselect refuses arms off the current rules). Modeling then
  queues the v9 Modal fits at the merged master commit.
- What's left of label splits after v9 is too mixed for one rule; 55 rows carry listing-id-like
  labels ("01226"), one-row units.

## 2026-10-07 01:00 ET

- unit-labels-v8 (#336) merged as 4d6e6f7 (paired full fit +279.6 ± 33.5 vs current rules, gate passed).
  Drafts #326 (v6) and #335 (v7) closed as superseded. Modeling queues the v8 full fits on Modal;
  autoselect decides serving. Served model before v8: nb3-prevprice-v2 (#392).

## 2026-10-07 00:00 ET
- **Retests on GV data** (yearnoise design, paired against nb3-coded-v2, 94,453 rows; none fully converged,
  R-hat 1.07–1.10): text-v1 +106.4 ± 32.8 (later: fails 2 SE on the fair WV+GV score, not served;
  back on the backlog as text-v2, Ben 14:21Z/14:30Z); null: noise +3.3 ± 14.3, water +0.7 ± 14.6, flagfix +0.1 ± 23.7,
  walkup −6.2 ± 14.0, attrs −7.5 ± 28.9. loc-v1 OOMs at the 7G GPU-job cap on thelio; it ran on a
  Modal A100 on 10-07 (+9.2 ± 15.3, provisional; ledger #415) and Modeling has it queued again after bedtime6. Results in `/data1/apartments/tmp/bridge/retest-pair-*.txt`. Don't relaunch
  scripts in that folder; it is Modeling's queue.
- **Exposure outlook (#382):** `exposure-manual.csv` has an `outlook` column ("wall"); 82-86
  Washington Pl 2B is the only row. Website shows no pill for single hand labels (Ben).
- **Facing-a-wall feature: dropped** (Ben, 2026-10-07 "don't build a facing-a-wall feature").
  The WIP stays on the local branch `data/wall-v1`, unpushed.
- **1 University Place J line:** Ben kept #2J coded 1BR (convertible unit; PR #386 closed). The
  other J units have one-bedroom plans (Ben). /best notes "can be set up as a 2-bed" (#387).

## State
- **Greenwich Village fold-in: done on the data side.** #292 (cohort, listing extras, alias table
  `config/unit-aliases/wv-gv-20261005.jsonl`, rule `unit-labels-v5`, feature sets
  `nb3-coded-v1` / `nb3-prevprice-v1` / `nb3-lineface-v1` on the three-neighbourhood snapshots
  dated 20261005) and #297 (three-name neighbourhood labels in term text, listing summaries and
  the rent map's area caveat). Snapshot names carry the pre-rebase commits 2d5b3b6 / 77068ea.
- **Modeling owns the GV fits** (units `frontier-gvfit`, `frontier-gvfrontier`,
  `frontier-gvrefit-early`; logs in `/data1/apartments/tmp/bridge/`). Plan for the night of Oct 5:
  GV explorations (lineface pair ~20:00 ET), served design + nb3-coded-v1 refit ~21:30 ET at
  3600 draws (4500 would overrun 2 h on 21% more rows), then nb3-coded-v1 vs nb3-prevprice-v1 on
  the latest split ~23:30–05:30, then a prevprice rows serving fit in the morning if it wins by
  more than 2 SE. Modeling reports the paired numbers to this thread.
- **Prevprice (pre-GV):** passed the leak-free latest-split gate (+75.5 ± 15.7 PSIS-LOO, ~4.8 SE)
  but its rows serving fit overran the 2 h cap (16:02 Oct 5); not served, not retried on the old
  data. Prevprice is slower per draw, so the GV serving fit is borderline on time.
- **LPC as-of (#307, merged):** `nb3-coded-v2` / `nb3-prevprice-v2` date the landmark and
  historic-district flags by the LPC's designation dates (`external lpc`, snapshot
  `/data1/apartments/external/lpc/20261005-8946d6f/`). This fixes 94 + 37 rows flagged for
  designations made after the listing, and puts 420 condo-lot rows in a district MapPLUTO leaves
  blank. Ben approved moving tonight's GV refit and the latest-split pair to v2 (unit
  `frontier-gvrefit-v2`, from ~21:00 ET).
- **Footprints as of the listing year: measured, NOT shipped.** Neighbours built after a listing
  change 708 rows' building sides, but only ~50 rows' facing features (side street versus rear).
  Dating them cost 154 s per feature build against 10 s. The patch (`nb3-coded-v3`,
  `building_sides_as_of`) is kept at `/data1/apartments/tmp/suspect/lpc/sides-as-of.patch` in
  case it is wanted later.

- **#167 revert (Ben, 2026-10-05 "Revert them"): PR #314 `fields-review-v3`**, approved and
  tagged, NOT merged. It is a no-op rule that takes `fields-review-v1` out of `current_rules()`.
  None of the 16 apartments has another listing to back its correction. Held until Modeling's
  `frontier-gvlatest48` prevprice pair lands (~12:15 ET) and latestselect has run; Modeling
  messages then. Merge with `gh pr merge 314 --squash --match-head-commit 8d81e7e`. Full fits
  after that use v3.
- **Exposure evidence table sent to Website** (`/data1/apartments/exposure/labels-evidence-20261006.parquet`
  and .csv; builder `/data1/apartments/tmp/suspect/exposure-evidence/evidence.py`). Logged in
  their backlog item 11 (#315); website features are on hold (Ben, 2026-10-05).
- **Prevprice on GV (v2 sets, latest split):** +92.5 ± 16.7 (5.5 SE), but both arms failed the ESS
  gate (380 and 334 < 400). They are being rerun at 4800 draws as `frontier-gvlatest48`.
- **Present-day MapPLUTO unit counts: measured, NOT worth a feature set.** Dated by the DOB housing
  database (`/data1/apartments/external/housingdb/20261002-f155dcc/`), 3,153 rows (3.0%) were
  listed before a unit-changing job on their lot completed, but only ~1% see a material change in
  units. The biggest apparent changes are new buildings whose final CO came years after leasing
  under a TCO, so a naive as-of count adds noise. Only one lot is plainly wrong: London Terrace's
  1007217501 records 2 units (4 building pages, 167 rows; its area per unit is already unknown).
  Buildings where we see far more units than MapPLUTO records (130) are unit-id fragmentation,
  not bad lots: 248 10th Ave has 9 units and 40 ids (`3`, `three`, `3a`, `a3`, `2b`, `2-b`).
  Notes and scripts: `/data1/apartments/tmp/suspect/pluto-asof/` (FINDINGS.md).

- **Wish features (coordinator relay, 2026-10-06 15:03Z):** Ben wants no separate preference
  model. Garden view, floor-through and quiet street become interpretable rent-model terms that
  Modeling recombines into pros and cons. Each has a per-apartment table in `/data1/apartments/wishes/`.
  - #328 `nb3-garden-v1` (merged): rear windows' openness from footprint rays. Fit `frontier-gvgarden`.
  - #329 `nb3-through-v1` (merged): one or two apartments per floor, plus the ad text. Fit `frontier-gvthrough`.
  - #330 `nb3-quiet-v1` (merged): busy road, narrow roadway, mid-block, plus the ad text. Modeling
    chains its fit after gvthrough (`frontier-gvquiet`).
  Each fit pairs the set with nb3-coded-v2 on PSIS-LOO; Modeling reports the paired numbers.
  Results (relayed to Ben): garden +11.8 ± 14.2, through +5.4 ± 15.7, quiet +8.1 ± 14.2, all
  noise. Coefficients: one apartment per floor +18.9% [+15.9, +22.0], two per floor +8.3%, ad
  says floor-through +0.9%; garden and quiet terms about zero. Suggested /best shows the
  floor-through premiums only.
- **Location features (coordinator relay, 2026-10-06 16:46Z, from Ben's /best feedback):** four
  wish sets on nb3-coded-v2, from free open data, all merged. Modeling runs them in `frontier-gvwish`
  (from ~14:15 ET, results ~16:30 ET) as reference + loud, transit, nearby, retail.
  - #344 `nb3-loud-v1`: which building sides front a busy road (`loud.py`).
  - #345 `nb3-transit-v1`: weekday-morning subway minutes to midtown from the MTA GTFS (`transit.py`,
    `external gtfs`, snapshot `20261006-6158e22`), as of the 7 extension (Sept 2015).
  - #346 `nb3-nearby-v1`: log metres to dog run, hospital, EMS, drop-in center, NYCHA, MSG
    (`nearby.py`, `external places`, snapshot `20261006-7c4c408`, NYC open data + OSM dog parks),
    as of `OPENED` dates. DHS shelters have no addresses, so they are left out.
  - #347 `nb3-retail-v1`: storefronts and food places within 150 m (`retail.py`, `external storefronts`,
    snapshot `20261006-5fd0c26`, 2019-2020 filings; vacancy left out as future information).
  Snapshot-writing commits are kept by `archive/snapshot-*` tags. Outside a build, set
  `features._LOTS` from `features.lot_files(set)`, or half the rows read the old registry.
- **Commute table (Ben, 2026-10-06; #353):** `rentfrontier.commute` writes
  `/data1/apartments/wishes/commute-<date>.parquet` and `.csv` (building, destination, address,
  minutes, transfers, walk_to_station_min, station), weekday 08:00-09:00 subway to the places in
  `config/commute-destinations.json` (default: office, 65 E 55th St). Ranking only, never a
  feature set (Ben is wary of over-tuning to him). Website reads the newest CSV at runtime for
  /best pills (#355); tell Website before renaming columns or moving the file.
- **Line and access wishes (Ben, 2026-10-06 18:34Z: "to price"):** #357 `nb3-lines-v1`
  (`lines.py`: a "<group> within 8 min" term for each line group that at least 1% of buildings
  have within an 8-minute walk; the 7, J/Z and G are too far away to price; PATH is not in the
  MTA feed) and #358 `nb3-access-v1` (`access.py`: log of the jobs within 30 min by walking and
  subway, from LODES8 WAC (`external lodes`, snapshot `20261006-e587e60`), lagged two years,
  stations as of the listing month). Travel times are our own Dijkstra on the GTFS with grid
  walks, not r5py or OSM. Modeling runs both in gvwish2 (results ~17:30-17:55 ET); Ben wants
  to know which lines come out positive. The amenity half of access (groceries, parks and gyms
  within 15 min) is a later PR.
- **Photo pilot (done 2026-10-06; Ben OK'd the fetch at 18:35Z):** 202 apartments, 680 images
  in `/data1/apartments/photo-pilot/` (answers/, key.json, QUESTIONS.md), 10 Sonnet readers,
  ~1.3M tokens (under $4). Windows street/rear: 65 unknown, and 68% agreement with our exposure
  labels where answered, so no full run. Floor plans: readers transcribe bedroom dimensions
  well (85/86 match the clearance rule), but 77/86 bedrooms fit a king. Any full run needs a new
  costed OK from Ben.
- **Bed size (Ben's mattress idea; #359):** `bedsize.py` reads the largest bed each listing's
  own ad states (king/queen/full; ~21% of rows), and `nb3-bedsize-v1` adds three 0/1 terms.
  The per-apartment table `/data1/apartments/wishes/bed-size-<date>.*` goes to Website for
  /best. I asked Modeling for an exploration fit.
- **Parks (amenity access, parks half; #364):** `parks.py` and `external parks` (NYC Parks
  properties enfh-gkve, snapshot `20261006-d208294`). `nb3-parks-v1` adds "log walk min to a park"
  (1+ acre, acquired before the listing month) and "High Line within 5 min". `parks.SECTIONS`
  dates the High Line (2009 / 2011 / Spur 2019; no Rail Yards in the source) and Bella Abzug Park
  (two south blocks, 2015-08-31); `places()` refuses large undated or post-2000 parks without
  sections. Hudson River Park (state) is missing. Groceries and gyms: no dated source (NYS food
  licences undated, storefront categories too coarse). Exploration fit requested from Modeling.
- **Wish-set verdicts (all exploration fits vs nb3-coded-v2; ledger docs/model/feature-tests.md):**
  only lines-v1 is worth carrying (+21.6 ± 17.2; N/Q/R/W +9.4%, L +2.6%, 2/3 +1.8%; 1, A/C/E,
  4/5/6 negative, all geography proxies). Null: loud −10.1, transit −7.4, nearby −1.3, retail
  +6.2, access −12.7, bedsize −25.2, parks −6.0 (High Line within 5 min +3.0%). Modeling refits
  lines and retail on the served design (gvnext). Location nulls get a retest after the
  Flatiron + Gramercy fold-in. Full fits now go to Modal (Ben 23:00Z, via Modeling); thelio's
  GPU is for exploration fits. DOT traffic counts: too sparse (89 one-year segments), dropped.
- **Performance review items:** rebuild memory measured (#351, 44 KB per row, no change);
  granular export row groups 8,192 (#352).
- **#326 `unit-labels-v6`** (draft) waits for a batch full fit.

## Next
- Act on the stab, permit and plutoasof fits as they land (see 21:45 above), and on v10 and v5.
- Permit follow-ups: read every label in a list ("APTS 2A & 3A" reads 2A only), and drop
  generic hits such as "HVAC UNITS" (harmless now).
- More open data: unused MapPLUTO fields and dated DOB certificates of occupancy (new-building
  unit counts).
- Flatiron + Gramercy: the data is done (see 22:20). Location retests go in as full fits.
- Backlog: bldgclass for condo conversions, Jane St registry fix, 13 excluded new-building
  rows, gross rent, relist gap.

## Rules that bind this thread
- Rule-based changes, one PR per change, no future information; descriptions never override coded
  fields; no new LLM calls, image downloads or scraping beyond what Ben approved.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
- Tests through `ops/job light` with `TMPDIR=/data1/apartments/tmp/suspect/tmpdir`; venv
  `/data1/apartments/venvs/data-line`, ruff via `uvx ruff`.
