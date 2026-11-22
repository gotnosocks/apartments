# Fast Screening & Single-Change Ablations on Modal `screen-k5` (2026-11-22)

**Goal:** Use our newly calibrated Modal Cloud GPU Fast Screening Harness (`A100-40GB`, `screen-k5`, `2 250 400 10`, ~6.5–10 min, ~$0.27–$0.45/screen) to:
1. **Cleanly ablate every individual component bundled inside `unified`** (`+2,844 ± 316` over `l2bt` on `screen-k5`, `+2,762.9` full-data) one change at a time — directly addressing PR #1530's no-bundling feedback.
2. **Screen 6 queued `docs/TODO.md` #3 modeling ideas** one change at a time over `l2bt`:
   - Explanatory NYC DOHMH Covid-19 macro covariates (borough-relative hospitalizations/cases + Covid × property-type mean interactions, AND 2-level Covid volatility regime)
   - 2020–2022 concession-building history & unrecorded-concession gap
   - DHCR rent-stabilized building counts (strictly as-of prior year) + stabilized path decoupling (2020–2021 dip, 2022+ boom)
   - Income-restricted noise scale mark (`I1`)
   - Per-bedroom new-unit uncertainty (`U4` proxy for 2BR and 3+BR first ads)
3. **Diagnose the `market` (`asof-20251110`) 80% coverage regression** (`-2.5 pp` full / `-1.90 pp` on `screen-mkt-k5`) by screening `l2bt`, `l2bt + Y1`, and `l2bt + 6 marks` separately on `screen-mkt-k5`.

**Budget & Time Box:** 1-hour sprint (`11:27–12:27 ET`), hard Modal ceiling **`$20.00`** (strictly tracked in `/data1/apartments/modal/ledger.jsonl` after `2026-11-22T11:27:00-05:00`).

---

## 1. Pre-Fit Predictions (Committed Before Launching Any Modal Container)

All predictions below are recorded **before** launching Wave 1 on Modal and will be scored honestly once Wave 1 & Wave 2 settle.

### Part A — Single-Term Additive Ablation of `unified` over `l2bt` (`screen-k5`, `37,199` held-out ads)
- **A1 (`y1` — calendar-year noise scale):** Biggest single piece of `unified`: **`GO`**, projected full ΔELPD **`+1,000` to `+1,600`** (`z >= +6`), explaining ~40–50% of `unified`'s `+2,844` gain.
- **A2 (`marks` — 6 exogenous noise-scale marks):** Second biggest piece: **`GO`**, projected full ΔELPD **`+800` to `+1,400`** (`z >= +5`), driven mainly by `mark:changed_counts`, `mark:baths_2/3p`, and `mark:thin_first_ad`.
- **A3 (`layrng` — 8 bed/bath change & range mean columns):** Modest-to-medium positive: projected **`+100` to `+400`** (`ESCALATE` or `GO`).
- **A4 (`size` — filled-size slope + `large_01br`):** Small positive: projected **`+50` to `+250`** (`ESCALATE` or weak `GO`).
- **A5 (`bedunit` — unit-ever bedtext memory) & `sbf` (`same_bed_first`):** Tiny/near-zero on `latest` (`-50` to `+150`, `ESCALATE` or `KILL` — `same_bed_first` only changes ~1,830 rows out of 1.9M!).

### Part B — Queued `docs/TODO.md` #3 Candidates over `l2bt` (`screen-k5`)
- **B1 (`covid_mean` — borough-relative Covid hosp/cases + Covid × Manhattan/2+BR/doorman/outdoor):** **`GO`**, projected **`+300` to `+900`** full ΔELPD — because the 2020–2021 Manhattan/doorman plunge vs outer-borough/2+BR/outdoor flight-to-space is huge and cannot be captured by `l2bt`'s single citywide weekly walk `L(w)`!
- **B2 (`covid_vol` — 2-level Covid hospitalization volatility regime):** **`GO`**, projected **`+250` to `+650`** full ΔELPD — capturing a meaningful share (30–50%) of `Y1`'s 12-parameter year noise gain with only **2 explanatory degrees of freedom**!
- **B3 (`stab_dhcr` — DHCR rent-stabilized counts + 2020–21 / 2022+ regime decoupling):** Positive **`GO` or `ESCALATE`**, projected **`+100` to `+450`** full ΔELPD (stabilized rents stay flat while market rents fell in 2020–21 and surged in 2022+).
- **B4 (`concess_gap` — 2020–2022 concession-building history & missing-concession gap):** Small-to-medium positive **`+50` to `+300`** (`ESCALATE` or `GO`).
- **B5 (`income_scale` — `income_restricted` noise scale mark):** Small positive **`+40` to `+200`** (`ESCALATE` or `GO`, limited by the small share of flagged rows in `l2bt`'s base column).
- **B6 (`u4_bed` — per-bedroom 2BR / 3+BR new-unit noise scale marks):** Small positive **`+30` to `+200`** on `latest` (bigger value on `market` where ~34% of ads are first ads).

### Part C — `market` (`asof-20251110`, `screen-mkt-k5`) Coverage-Regression Diagnosis
- **C1 (Which piece caused the `-1.90 pp` / `-2.5 pp` 80% coverage regression on `market`?):** **`y1` (`yr:2025` / calendar-year noise shrinkage on recent ads) OR `marks` (`thin_first_ad` / `baths`)** will clearly separate in `mkt-l2bt` vs `mkt-y1` vs `mkt-marks`: we predict **`y1`** is the primary culprit tightening 2025 predictive intervals below nominal 80% (pulling 80% coverage down by `>= 1.0 pp` relative to `mkt-l2bt`), whereas `marks` improves `market` ΔELPD with less or zero coverage erosion.

---

## 2. Wave 1 Results

*(To be populated once Wave 1 settles.)*

## 3. Wave 2 Follow-Up & Pruned Winner Combination

*(To be populated once Wave 2 settles.)*

## 4. Honest Pre-Fit Prediction Scorecard & Itemized Modal Spend

*(To be populated before PR hand-off.)*
