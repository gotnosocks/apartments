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

---

## Wave 1 Scored Results (`af19ed85`, all 26/26 runs landed, `$15.80` total)

Reference anchor: `u5-svgpmo-lat` (`695` explicit params, full 6-chain production gate **PASSED** in sibling thread at **`243,290.3` ELPD**, `+538.8 ± 48.1` over `u4s-lat`, `R-hat = 1.0087` on `sigma[2]`, `ESS = 1,077`, `$27.68`).

### `screen-k5` (`latest`, 19/19 single-block ablations, `80.7` total IG bits, `$12.00`, `0.28 bits/min`, `6.7 bits/$`)

| Arm | Exact Ablation | ΔParams (ΔG) | Projected ΔELPD ± SE | ELPD / Removed Param | s/sweep | Max R-hat | Verdict | Prediction Hit? |
|---|---|---:|---:|---:|---:|---:|---|---|
| `s11-scalar-sigma` | `sigma[4]` → scalar | `-3` (`-3 K_scale`) | **`+53 ± 40`** | `-17.7` (improves!) | `0.713` (`-6.3%`) | `1.128` | **`SIMPLIFY_KEEP`** | **HIT** (also removes `u5`'s `sigma[2]` R-hat bottleneck!) |
| `s8-ad-core` | `35 → 6` legacy `ad:*` | `-31` (`-31`) | **`-6 ± 44`** | `+0.19` | `0.759` | `1.096` | `ESCALATE` (pure noise) | **HIT** |
| `s15-biweekly` | `W1: 673 → 337` | `0` (`-336`) | **`-23 ± 36`** | `0` | `0.749` | `1.114` | `ESCALATE` (pure noise) | **BETTER than predicted** |
| `s1-seg-add` | `7` → `4` additive seg GPs | `-165` (`-159`) | **`-30 ± 86`** | `+0.18` | `0.732` (`-3.8%`) | **`1.071`** (ESS `3×`) | `ESCALATE` (pure noise) | **HIT** |
| `s5-floor-poly` | `68` floor dummies + `2` GPs → `5` | `-67` (`-63`) | **`-32 ± 42`** | `+0.47` | `0.756` | **`1.051`** | `ESCALATE` (pure noise) | **HIT** |
| `s14-phase-compact` | drop `phase:22-25`, `none`, `sin2/cos2` | `-7` (`-6`) | `-49 ± 33` | `+7.0` | `0.761` | `1.098` | `ESCALATE` | Miss (slightly steeper) |
| `s9-bld-core` | `52 → 17` legacy `bld:*` | `-35` (`-35`) | `-63 ± 42` | `+1.81` | `0.720` (`-5.4%`) | `1.072` | `ESCALATE` | Slight miss |
| `s16-spatial-k80` | `K: 195 → 80` | `0` (`-115`) | `-72 ± 38` | `+0.63/mode` | `0.742` | `1.090` | `ESCALATE` | Slight miss |
| `s10-no-bld-ks` | drop all `52` legacy `bld:*` | `-52` (`-52`) | `-78 ± 59` | `+1.50` | `0.716` (`-5.9%`) | `1.074` | `ESCALATE` | **HIT** |
| `s12-sv-mo16` | `24 → 16` `sv_gp_mo` modes | `-8` (`-8 K_scale`) | `-119 ± 39` | `+14.9` | `0.691` (`-9.2%`) | `1.086` | `KEEP_COMPLEX` | Steeper than predicted |
| `s13-sv-mo12` | `24 → 12` `sv_gp_mo` modes | `-12` (`-12 K_scale`) | `-148 ± 44` | `+12.3` | `0.652` (`-14.3%`) | `1.090` | `KEEP_COMPLEX` | **HIT** |
| `s19-no-phase-mean` | drop `6` `phase:*` mean cols | `-6` (`-6`) | `-485 ± 68` | `+80.8` | `0.771` | `1.097` | `KEEP_COMPLEX` | **HIT** (even stronger) |
| `s2-seg-add-lr16` | fixed-amp `lr16` additive seg | `-321` (`-307`) | `-661 ± 130` | `+2.06` | `0.691` | `1.149` | `KEEP_COMPLEX` | Miss (fixed `amp=0.05` over-shrunk COVID) |
| `s4-seg-lr16` | fixed-amp `lr16` 7-seg | `-273` (`-259`) | `-702 ± 120` | `+2.57` | `0.708` | `1.138` | `KEEP_COMPLEX` | Miss (fixed `amp=0.05` over-shrunk COVID) |
| `s3-seg-add-lr12` | fixed-amp `lr12` additive seg | `-337` (`-323`) | `-778 ± 139` | `+2.31` | `0.696` | `1.177` | `KEEP_COMPLEX` | **HIT** |
| `s18-marks-baths` | drop `changed/floor1/large01br` | `-3` (`-3 K_scale`) | `-817 ± 129` | **`+272.3`** | `0.708` | `1.095` | `KEEP_COMPLEX` | **HIT** (even stronger) |
| `s7-umean-core` | `45 → 5` Mundlak `umean:` cols | `-40` (`-40`) | `-999 ± 170` | `+25.0` | `0.769` | `1.127` | `KEEP_COMPLEX` | Miss (Mundlak cols are huge!) |
| `s6-no-umean` | drop all `45` `umean:` cols | `-45` (`-45`) | `-2,417 ± 265` | `+53.7` | `0.771` | `1.063` | `KEEP_COMPLEX` | **HIT** (even stronger) |
| `s17-no-bld-ar` | drop building quarterly AR(1) | `0` (latent AR) | **`-34,228 ± 1,829`** | `+17,114/hyp` | `0.438` | `1.150` | `KEEP_COMPLEX` | **HIT** |

### `screen-mkt-k5` (`market`, 5/5 ablations, `33.4` total IG bits, `$2.54`, `0.55 bits/min`, `13.1 bits/$`)

| Arm | Exact Ablation | ΔParams | Projected ΔELPD ± SE | 80% Cov Shift | s/sweep | Max R-hat | Verdict | Prediction Hit? |
|---|---|---:|---:|---:|---:|---:|---|---|
| `m4-marks-bt` | `marks` → `mark_baths,mark_thin` | `-3` | **`+50 ± 22`** | `+0.85 pp` | `0.629` | **`1.036`** | **`SIMPLIFY_KEEP`** | **HIT** |
| `m5-spatial-biwk` | `+spatial_k80,biweekly_walk` | `0` (`-451 G`) | **`+8 ± 7`** | — | `0.638` | **`1.038`** | **`SIMPLIFY_KEEP`** | **HIT** |
| `m1-floor-poly` | `+floor_poly` | `-67` | **`+6 ± 7`** | — | `0.654` | `1.058` | **`SIMPLIFY_KEEP`** | **HIT** |
| `m3-scalar-sv16` | `sv_gp_mo16,scalar_sigma,phase_compact,no_season2` | `-18` | `-38 ± 13` | — | `0.521` (`-20%`) | `1.065` | `KEEP_COMPLEX` | Miss (`sv_gp_mo16` cost `-38`) |
| `m2-ks-core` | `+umean_core,ad_core,bld_core` | `-106` | `-48 ± 48` | — | `0.610` | `1.061` | `ESCALATE` | **HIT** (driven by `umean_core`) |

---

## Wave 2 Pre-Fit Quantitative Predictions (Pareto Combinations, Single-Fit `--split unified` Proof, and `bits/min` Optimization)

Committed **before** launching Wave 2 (`13` Modal `A100-40GB` screens, est. `~$5.80`).

### 1. Combined Pareto Frontier Candidates (`latest` & `market` — testing ONE IDENTICAL unified model across both splits)
- **`c1-compact`**: `layrng,size,sv_gp_mo,marks,seg_add,floor_poly,ad_core,scalar_sigma,biweekly_walk` (`429` params, `-266` / `-38%`, `4` GPs vs `9`, `-39% G_dim`)
  - `latest` (`w2-c1-compact`): projected ΔELPD **`-120 to +40`**, `s/sw ≈ 0.65–0.70`, `max_rhat ≤ 1.06`.
  - `market` (`w2-m-c1-compact`): projected ΔELPD **`-20 to +25`** vs `m0-anchor` (proving `seg_add` can stay in the single unified model for `market` too!).
- **`c1s-semi`**: same as `c1-compact` with **`seg_add_semi`** (`4` semi-annual Matérn-3/2 GPs, **`325` params, `-370` / `-53%`!!**)
  - `latest` (`w2-c1s-semi`): projected ΔELPD **`-160 to +20`** vs `s0-anchor` (within `-40` of `c1-compact` while cutting `-104` more params!).
  - `market` (`w2-m-c1s-semi`): projected ΔELPD **`-15 to +25`** vs `m0-anchor`, `max_rhat ≤ 1.05`.
- **`c2-lean`**: `c1s-semi` + `no_bld_ks,spatial_k80,phase_compact,no_season2` (**`266` params, `-429` / `-62%`!!**, `G_dim: -51%`, skips slow `bld:` step!)
  - `latest` (`w2-c2-lean`): projected ΔELPD **`-280 to -80`**, `s/sw ≈ 0.54–0.62` (`1.25–1.40×` speedup!).
  - `market` (`w2-m-c2-lean`): projected ΔELPD **`-30 to +15`** vs `m0-anchor`, `s/sw ≈ 0.48–0.56`.
- **`c3-ultra`**: `c2-lean` with `sv_gp_mo16` (**`258` params, `-63%`**, `K_scale: 43 → 31`)
  - `latest` (`w2-c3-ultra`): projected ΔELPD **`-400 to -180`**, `s/sw ≈ 0.48–0.55` (`1.40–1.55×` speedup!).
- **`c0-noseg`**: `layrng,size,sv_gp_mo,marks,floor_poly,ad_core,scalar_sigma,biweekly_walk` (0 GPs, **`209` params, `-70%`**!)
  - `latest` (`w2-c0-noseg`): quantifies exact total ELPD value of `seg_add` on `latest` — predicted **`-1,800 to -900`** vs `s0-anchor`.
  - `market` (`w2-m-c0-noseg`): predicted **`-10 to +20`** vs `m0-anchor` (direct paired test of whether `seg_add_semi` helps or is neutral on `market`).

### 2. Single-Fit Consolidation Proof (`--split unified` vs `--split market` on `screen-mkt-k5`)
- **`w2-m-unified-proof`**: `c1s-semi` fitted on **`--split unified`** (holding out all `open` ads + 5% non-active `latest` closed ads) vs `w2-m-c1s-semi` on `--split market`:
  - **Pre-fit prediction on shared `open` active ads:** **`ΔELPD = -8 to +8` (`|z| < 1.0`)**, 80% coverage shift **`within ±0.3 pp`**, proving ONE SINGLE FIT serves `/deals`, `/price-now`, `/estimates`, AND `/diagnostics` with zero active-market degradation — cutting live production fit count immediately by **`2×`**!

### 3. Model Discovery Agent `bits/min` & `bits/$` Frontier Optimization
- **`w2-fast-k5-short`** (`screen-k5`, `2 150 200 5`, `c2-lean`): predicted wall **`~6 min` (`$0.25`)**, **`≥ 0.55 bits/min` (`~2×` faster discovery rate!)** and **`≥ 13 bits/$`**, matching `w2-c2-lean` full-schedule ΔELPD within `±60`.
- **`w2-k10-anchor`** & **`w2-k10-c2-lean`** (`screen-k10`, `2 200 300 10`): predicted wall **`~5–6 min` (`$0.23`)**, **`≥ 0.65 bits/min`**, **`≥ 15 bits/$`** — mapping the exact `(subsample × schedule × model complexity)` discovery rate Pareto frontier!
