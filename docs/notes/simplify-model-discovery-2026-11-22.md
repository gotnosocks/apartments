# Overnight Sprint Pre-Fit Predictions: Model Discovery Agent & Parameter Pressure-Test (`2026-11-22`)

Committed **before** launching any Modal GPU containers, in strict accordance with `CLAUDE.md`.

## Mission & Budget
- **Goal:** Build on top of `u5-svgpmo` (`1d62c667`, `layrng,size,sv_gp_mo,marks,seg`) to upgrade the **Model Discovery Agent workflow** (`rentfrontier.screen` + `ops/modal-screen` with parsimony/non-inferiority Bayesian routing, `bits/min`, `bits/$`, `ELPD/param`, and Pareto-frontier tracking) and systematically **pressure-test the value-add of every parameter block**, compressing the model to be **smaller, simpler, faster, and cheaper to fit** while preserving held-out ELPD, calibration, and convergence across `latest` and `market`.
- **Authorized Modal Ceiling:** **`$100.00`** across all waves (Wave 1 single-change ablations `~$9–$11`, Wave 2 Pareto combinations & multi-date validation `~$6–$8`, Wave 3 full 6-chain production gate validation of the winning simplified model `~$25–$40`).

## Zero-Spend Structural Audit of `u5-svgpmo` (`695` explicit global params on `latest`)
From stored `clean5-lat` / `vg-lat-5-svgp-mo` posteriors (`$0.00` spend):
1. **`seg:paths` = `371` of `634` `beta` cols (`58.5%`) + `7` GP hypers (`14` scalars)** — and the single worst-mixing block (`R-hat = 1.089, ESS = 12` on `screen-k5`). Exact variance decomposition shows **`97.5%` of total segment-path variance is purely additive (`zone + bed`, 4 paths not 7)** and **`98.3%` is rank-2**.
2. **`floor_gp` = `68` dummy cols (`unit:elev_f2..64`, `unit:walkup_f2..6`) + `2` RBF GPs (`4` scalars)**. A 3-term smooth basis (`lin + quad + log`) fits the 63 elevator floor dummies to **`wR² = 99.63%`** (`rms_err = 0.0043`), and 2 indicators fit walkup floors `2–4` vs `5–6`.
3. **Legacy kitchen-sink blocks (`130` `beta` cols: `43 umean`, `35 ad`, `52 bld`)** were built in October *before* the model had Student-t unit random effects `s_k`, unit OU drift `u(t)`, or building AR(1) paths. `24/35` `ad` cols and `18/52` `bld` cols have `|z| < 2` on `k5`.
4. **Noise scale step (`K_scale = 43`: `3 hyp + 4 sigma + 36 phase_factor`)**:
   - All four bedroom `sigma[0..3]` lie within `±2%` (`0.01425–0.01487`) once `mark:baths_2/3p` are included (`scalar_sigma` removes 3 coupled scale dims).
   - `sv_gp_mo` uses `24` modes; `16` modes capture `96.3%` R², `12` modes capture `90.9%` R².
   - `phase:22-25` has posterior multiplier `0.97–1.01` (`|z| < 1.5`, indistinguishable from `10-13` reference).
   - Cutting `K_scale` from `43 → ~25` cuts `scales_curvature` finite-difference evaluations by **~66%** (`946 → 325`) and `slice_along` by **~42%** every sweep!
5. **Global dense system `G = pb + W1 + 1 + K` (`~1,500`)**: `143/195` spatial wave modes have `|z| < 2` (`spatial_k80` cuts `-115` dims), and `W1 = 673` weekly knots (`biweekly_walk` cuts `-336` dims).

## Wave 1 Pre-Fit Quantitative Predictions (`screen-k5` `latest` & `screen-mkt-k5` `market`)

Anchor (`s0-anchor` on `latest`, `m0-anchor` on `market`): `u5-svgpmo` (`layrng,size,sv_gp_mo,marks,seg` / `layrng,size,sv_gp_mo,marks`). Every Wave 1 arm changes **one** structural block from the anchor (`2 250 400 10`, `A100-40GB`, `seed=1`).

| # | Arm Label | Exact Single Change vs `u5-svgpmo` | ΔExplicit Params (ΔG) | Pre-Fit Projected Full ΔELPD | Pre-Fit Verdict (`tol=50` lat / `15` mkt) |
|---|---|---|---:|---:|---|
| `s0` | `s0-anchor` | Anchor `layrng,size,sv_gp_mo,marks,seg` | `0` (`0`) | `0` (ref) | Reference |
| `s1` | `s1-seg-add` | `seg` → `seg_add` (4 additive quarterly GPs) | `-165` (`-159`) | `-60 to +40` | `SIMPLIFY_KEEP` |
| `s2` | `s2-seg-add-lr16` | `seg` → `seg_add_lr16` (4×16 Matérn eigenmodes, 0 GPs) | `-321` (`-307`) | `-120 to +40` | `SIMPLIFY_KEEP` (faster + cleaner R-hat) |
| `s3` | `s3-seg-add-lr12` | `seg` → `seg_add_lr12` (4×12 Matérn eigenmodes, 0 GPs) | `-337` (`-323`) | `-200 to -20` | `ESCALATE` / `KEEP_COMPLEX` |
| `s4` | `s4-seg-lr16` | `seg` → `seg_lr16` (7×16 Matérn eigenmodes, 0 GPs) | `-273` (`-259`) | `-80 to +60` | `SIMPLIFY_KEEP` |
| `s5` | `s5-floor-poly` | `+floor_poly` (5 smooth cols, 0 floor GPs) | `-67` (`-63`) | `-40 to +20` | `SIMPLIFY_KEEP` |
| `s6` | `s6-no-umean` | `+no_umean` (drop all 43 Mundlak cols) | `-43` (`-43`) | `-400 to -100` | `KEEP_COMPLEX` |
| `s7` | `s7-umean-core` | `+umean_core` (keep top 5 Mundlak cols) | `-38` (`-38`) | `-80 to +20` | `SIMPLIFY_KEEP` |
| `s8` | `s8-ad-core` | `+ad_core` (keep top 6 legacy `ad:*` cols) | `-29` (`-29`) | `-50 to +30` | `SIMPLIFY_KEEP` |
| `s9` | `s9-bld-core` | `+bld_core` (keep top 17 `bld:*` cols) | `-35` (`-35`) | `-40 to +30` | `SIMPLIFY_KEEP` |
| `s10` | `s10-no-bld-ks` | `+no_bld_ks` (drop all 52 `bld:*` cols) | `-52` (`-52`) | `-150 to +10` | `ESCALATE` (quantify bld prior value) |
| `s11` | `s11-scalar-sigma` | `+scalar_sigma` (collapse `sigma[4]` → scalar) | `-3` (`0`, `-3 K_scale`) | `-30 to +20` | `SIMPLIFY_KEEP` |
| `s12` | `s12-sv-mo16` | `sv_gp_mo` → `sv_gp_mo16` (16 modes) | `-8` (`0`, `-8 K_scale`) | `-80 to +20` | `SIMPLIFY_KEEP` / `ESCALATE` |
| `s13` | `s13-sv-mo12` | `sv_gp_mo` → `sv_gp_mo12` (12 modes) | `-12` (`0`, `-12 K_scale`) | `-180 to -30` | `KEEP_COMPLEX` |
| `s14` | `s14-phase-compact` | `+phase_compact,no_season2` | `-7` (`-6`, `-1 K_scale`) | `-30 to +30` | `SIMPLIFY_KEEP` |
| `s15` | `s15-biweekly` | `+biweekly_walk` (`W1: 673 → 337`) | `0` (`-336`) | `-250 to -50` | `KEEP_COMPLEX` / `ESCALATE` |
| `s16` | `s16-spatial-k80` | `+spatial_k80` (`K: 195 → 80`) | `0` (`-115`) | `-40 to +20` | `SIMPLIFY_KEEP` |
| `s17` | `s17-no-bld-ar` | `+no_bld_ar` (drop building quarterly AR(1)) | `-2` (latent AR) | `-4,500 to -2,000` | `KEEP_COMPLEX` (core structural backbone) |
| `s18` | `s18-marks-baths` | `marks` → `mark_baths,mark_thin` | `-3` (`0`, `-3 K_scale`) | `-350 to -150` | `KEEP_COMPLEX` on `latest` (positive on `market`) |
| `s19` | `s19-no-phase-mean` | `+no_phase_mean` (drop 6 `phase:*` mean cols) | `-6` (`-6`) | `-250 to -60` | `KEEP_COMPLEX` |
| `m0` | `m0-anchor` | `screen-mkt-k5` anchor `layrng,size,sv_gp_mo,marks` | `0` | `0` (ref) | Reference |
| `m1` | `m1-floor-poly` | `market` `+floor_poly` | `-67` (`-63`) | `-10 to +10` | `SIMPLIFY_KEEP` |
| `m2` | `m2-ks-core` | `market` `+umean_core,ad_core,bld_core` | `-102` (`-102`) | `-25 to +15` | `SIMPLIFY_KEEP` / `ESCALATE` |
| `m3` | `m3-scalar-sv16` | `market` `sv_gp_mo16,scalar_sigma,phase_compact,no_season2` | `-18` (`-12 K_scale`) | `-15 to +15` | `SIMPLIFY_KEEP` |
| `m4` | `m4-marks-bt` | `market` `marks` → `mark_baths,mark_thin` | `-3` (`-3 K_scale`) | `+15 to +65` | `SIMPLIFY_KEEP` (beats `u5` on `market`!) |
| `m5` | `m5-spatial-biwk` | `market` `+spatial_k80,biweekly_walk` | `0` (`-451 G`) | `-20 to +10` | `SIMPLIFY_KEEP` / `ESCALATE` |
