# Unified Base-Refit Drift Model (`drift-building-phase-unitkn-unified` & `unified-seg`): Pre-Fit Predictions (2026-11-21)

Written BEFORE launching any Modal GPU fit.

## Motivation & Zero-Spend Sizing Summary
Joint cross-fitted sizing (`p2_joint_sizing.py` & `p2_panel_c.py` in `/data1/apartments/tmp/whole-dataset-audit-2026-11-21/`) evaluated our Phase 1 whole-dataset audit candidates on top of the queued base-refit bundle (`j1`'s 8 kept terms + `Y1` calendar-year noise + `j5` gap bins & flag-change counts) across three panels:

1. **`l2bt` all years (`189,647` held-out ads, `df=5`):**
   - `BASE (j1 + Y1 + j5)`: `+3,573.5` (SE `108.6`, A `+1,630.4`, B `+1,943.1`).
   - Added over `BASE`, leave-one-block-out:
     - `layout-range` (8 directional bed/bath change & range columns): **`+1,175.1` (SE `64.1`, z=`+18.3`)** (`+782` shift-only, `+418` scale-only).
     - `large_01br` + `size_imp_log_size_rel`: **`+212.1` (SE `26.9`, z=`+7.9`)** (`+127` shift, `+87` scale).
     - `bed_grp x era`: **`+212.4` (SE `29.2`, z=`+7.3`)**; `outer_boro x era`: **`+146.5` (SE `21.8`, z=`+6.7`)**.
     - Rejected (failed gate on `l2bt`): `rent_stabilized` (`+6.0`, SE `9.1`), `concession` (`+0.8` LOO, SE `11.7`).
2. **`l2bt` `2022+` (`129,861` held-out ads, `df=7`):**
   - `BASE (j1 + Y1 + j5)`: `+2,503.9` (SE `92.8`, A `+1,154.1`, B `+1,349.8`).
   - Leave-one-block-out: `layout-range` **`+621.0` (z=`+12.8`)**, `large_01br + size_imp_slope` **`+175.5` (z=`+7.1`)**, `bed_grp x era` **`+122.2` (z=`+5.3`)**, `outer_boro x era` **`+47.1` (z=`+3.7`)**.
3. **`range-j` Deals backtest (`9,346` open ads as of `2025-11-10`, `df=7`):**
   - `no_unit_history + thin_bld_bed` (`<5` prior same-bed training ads): **`+75.4` (SE `19.3`, z=`+3.9`, A `+34.6`, B `+40.8`)**, lifting `no_hist & thin_bed<5` 80% coverage from `68.1% -> 80.2%` and cutting `>95%` tail from `16.6% -> 6.2%`.
   - `j1` bath/floor/tier scale subset: **`+73.9` (SE `15.8`, z=`+4.7`)**.
   - Rejected on `range-j`: `concession` (`+2.1` LOO), `rent_stabilized` (`-0.2` LOO).

## Models Implemented
1. **`drift-building-phase-unitkn-unified`**:
   - Base: `drift-building-phase-unitkn-level` (`nu_u=3` collapsed Student-t unit levels, fixed row `nu=2`, collapsed building AR(1) paths + Student-t building levels `dof=4`, lease-phase level columns).
   - Mean upgrades: `same_bed_first=True` in `sizefill.asof_size`, `bedunit` (`ad:bed_text_smaller` + `uever`), `layout-range` (8 columns), `ad:size_imp_log_size_rel`, `ad:large_01br`.
   - Additive log-scale factors (`Design.phase_map`, compact observed cells): 6 lease phases + up to 12 calendar years (`Y1`, ref `2024`, dropping empty years automatically) + 6 strictly exogenous marks (`changed_counts`, `baths_2`, `baths_3p`, `floor_1`, `large_01br`, `thin_first_ad`).
2. **`drift-building-phase-unitkn-unified-seg`**:
   - Same as `unified`, plus quarterly Gaussian-process market-segment paths (`drift_building_phase_segment`, 8 `(zone, bed)` segments).

## Pre-Fit Predictions (Recorded Before Launch)

### On `latest` split vs `l2bt` (`189,647` all years; `129,861` `2022+`)
1. **`unified` held-out Δelpd vs `l2bt`:**
   - All years: **+1,500 to +3,200 elpd**, positive on BOTH halves A and B (note: real Bayesian refit will absorb some cross-fitted gain into building/unit scales, so ~50–80% of the +4,500 post-hoc sum is expected).
   - `2022+`: **+900 to +2,100 elpd**, positive on BOTH halves A and B.
2. **`unified-seg` held-out Δelpd vs `unified`:**
   - All years: **+200 to +550 elpd** (from 2020–21 and 2022–26 segment divergence).
   - `2022+`: **+80 to +220 elpd**.
3. **80% interval coverage by calendar year (`unified`):**
   - Moves 2020–2021 coverage from `0.730–0.738` to **`0.785–0.815`**; 2022 from `0.760` to **`0.790–0.815`**; 2024–2026 within **`0.790–0.815`**.
4. **Key fitted parameters (`unified`):**
   - `mark:changed_counts` scale: **`1.15 to 1.30`**; `mark:baths_2`: **`1.10 to 1.25`**; `mark:baths_3p`: **`1.30 to 1.65`**; `mark:large_01br`: **`1.15 to 1.35`**; `mark:thin_first_ad`: **`1.15 to 1.45`**.
   - `yr:2020` and `yr:2021` scales: **`1.18 to 1.32`** relative to 2024; `yr:2026`: **`0.93 to 0.99`**.
   - `ad:size_imp_log_size_rel` beta: **`-0.015 to -0.045`** (shrinking filled-size slope toward 0.8× stated slope).
   - `ad:beds_up_prev` / `ad:baths_up_prev`: negative (**`-0.015 to -0.045`**); `ad:beds_down_prev` / `ad:baths_down_prev`: positive (**`+0.015 to +0.050`**).
5. **Convergence & sweep speed:**
   - H100 sweep time for `unified`: **`0.85 to 1.35 s/sweep`** (2 chains), allowing `2,000–2,900` sweeps per 42-min container (`~1.0–1.5x` `l2bt`'s `0.76 s/sweep`).
   - 3 containers × 2 chains (6 chains pooled): passes strict convergence gate (**max split R-hat ≤ 1.01, min bulk ESS > 400** across all scalars, betas, and buildings).

### On `market` Deals backtest (`asof-20251110`, `9,346` open ads) vs `range-j`
6. **`unified` held-out Δelpd vs `range-j`:**
   - **+180 to +450 elpd** on `9,346` open ads (positive on BOTH halves A and B), combining `unitkn` Student-t unit levels + `bedunit` + `Y1` + `j1` bath/floor/large-01br scales + `thin_first_ad` scale.
7. **First-ad (`no_unit_history`, `n=3,168`) and thin-building (`no_hist & thin_bed<5`, `n=727`) calibration:**
   - `no_unit_history` 80% coverage improves from `75.8%` to **`78.5%–81.5%`**.
   - `no_hist & thin_bed<5` 80% coverage improves from `68.1%` to **`76.0%–82.0%`**, and `>95%` tail drops from `16.6%` to **`<9.0%`**.
8. **Deals low tail (`cdf < 0.05`):**
   - Stays well-calibrated (**`4.5% to 5.6%`** overall and on both `no_unit_history` and `has_unit_history`).

## Experimental Plan & Budget Cap
- Authorized Modal budget: **$100.00** (zero OxyLabs spend).
- Stage 1 (Cheap 2-chain H100 screening pilots, ~$6–$10 total):
  - Pilot A: `unified` on `market` (`asof-20251110`, 2 chains, ~25 min, ~$2.50) vs `range-j`.
  - Pilot B: `unified` on `latest` (2 chains, ~30–40 min, ~$3.00) vs `l2bt`.
  - Pilot C: `unified-seg` on `latest` (2 chains, ~35–45 min, ~$3.50) vs Pilot B.
- Stage 2 (Full 6-chain = 3×2-container pooled gate fits on the winning spec(s), ~$25–$40 total):
  - Gate Fit 1: 3 containers (`seed=1,2,3`) on `latest` vs `l2bt` (~$12–$15).
  - Gate Fit 2: 3 containers (`seed=1,2,3`) on `market` (`asof-20251110`) vs `range-j` (~$10–$14).
  - Optional Gate Fit 3 (if `unified-seg` beats `unified` cleanly and mixes well, or to test a further refinement discovered from Pilots A–C): ~$12–$15.
- All runs launched via `ops/modal-fit --outside-budget --gpu H100` from committed clean git SHAs; exact settled costs summed from `/data1/apartments/modal/ledger.jsonl` and strictly capped below $100.
