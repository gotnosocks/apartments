# Data improvements — handoff

Updated 2026-10-06 12:00 ET. Thread owner: the Data improvements project thread (bridge session on thelio).

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
- **#326 `unit-labels-v6`** (draft) waits for a batch full fit.

## Next
- Relay to Ben: the lineface paired score and the prevprice outcome when Modeling sends them.
- After the GV switch, Modeling updates the "map grows less than the median ask" note figures.
- #222 `unit-labels-v4` waits for a batch full fit; the next unit-labels version should add the
  Morton Square + 100 Morton join.
- Next data item: unit-id splits (fragmented labels in small buildings; see the MapPLUTO note).
  Run full-data scripts only while the GPU is free: GPU fits lean on swap (memory note, 2026-10-06).
- Backlog: bldgclass for condo conversions, Jane St registry fix, 13 excluded new-building rows, confirm
  q-v3/q-v4 on held-out rows, gross rent, relist gap.

## Rules that bind this thread
- Rule-based changes, one PR per change, no future information; descriptions never override coded
  fields; no new LLM calls, image downloads or scraping beyond what Ben approved.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
- Tests through `ops/job light` with `TMPDIR=/data1/apartments/tmp/suspect/tmpdir`; venv
  `/data1/apartments/venvs/data-line`, ruff via `uvx ruff`.
