# Data improvements — handoff

Updated 2026-10-07 11:00 ET. Thread owner: the Data improvements project thread (bridge session on thelio).

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
  R-hat 1.07–1.10): text-v1 +106.4 ± 32.8 (Modeling: full fit on Modal, plus a latest-split check
  `frontier-latesttext`); null: noise +3.3 ± 14.3, water +0.7 ± 14.6, flagfix +0.1 ± 23.7,
  walkup −6.2 ± 14.0, attrs −7.5 ± 28.9. loc-v1 OOMs at the 7G GPU-job cap on thelio; Modeling
  runs it on Modal. Results in `/data1/apartments/tmp/bridge/retest-pair-*.txt`. Don't relaunch
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
- Relay Modeling's gvnext refit (lines, retail on the served design), the prevprice selection
  (~01:30-02:00 ET) and the v8 pair; row-rule merges wait for the prevprice selection.
- PATH stations from their own GTFS snapshot, only if lines-v1 holds up in the refit. Hudson
  River Park has no dated outline in state open data (only plantings and facility points).
- Location follow-ups (retest after the Flatiron + Gramercy fold-in): loud's line orientation
  ignores Village named streets; a no-footprint flag; more dog-run opening dates and closures
  (St Vincent's) in `nearby.OPENED`; drop the private OSM "The Fi Office" dog run.
- Relay to Ben: the lineface paired score and the prevprice outcome when Modeling sends them.
- After the GV switch, Modeling updates the "map grows less than the median ask" note figures.
- #222 `unit-labels-v4` waits for a batch full fit; the next unit-labels version should add the
  Morton Square + 100 Morton join.
- Pair Modeling's 39c3c8a trio when it lands (10-08 overnight). A unit-splits threshold-1 or
  studio-aware variant is the next candidate, after the trio.
- Run full-data scripts only while the GPU is free: GPU fits lean on swap (memory note, 2026-10-06).
- Backlog: bldgclass for condo conversions, Jane St registry fix, 13 excluded new-building rows, confirm
  q-v3/q-v4 on held-out rows, gross rent, relist gap.

## Rules that bind this thread
- Rule-based changes, one PR per change, no future information; descriptions never override coded
  fields; no new LLM calls, image downloads or scraping beyond what Ben approved.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
- Tests through `ops/job light` with `TMPDIR=/data1/apartments/tmp/suspect/tmpdir`; venv
  `/data1/apartments/venvs/data-line`, ruff via `uvx ruff`.
